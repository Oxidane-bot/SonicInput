"""事务管理模块 - 处理模型变更和配置变更的原子性操作

此模块提供了一个事务管理类，确保模型加载和配置保存操作的原子性。
如果任何步骤失败，会自动回滚到之前的状态。

主要功能:
- 事务式模型加载
- 事务式配置保存
- 自动状态备份和回滚
- 完整的错误处理和日志记录

典型使用场景:
    transaction = ApplyTransaction(model_service, settings_service, event_service)
    try:
        transaction.begin()
        transaction.apply_model_change("paraformer")
        transaction.apply_config_changes({"transcription.provider": "local"})
        transaction.commit()
    except TransactionError as e:
        logger.error(f"事务失败: {e}")
"""

import copy
from typing import Any, Dict, Optional

from ..core.interfaces import IEventService
from ..core.services.ui_services import (
    UIModelService,
    UISettingsService,
)
from ..utils.logger import app_logger

LAUNCH_AT_LOGIN_KEY = "ui.launch_at_login"


class TransactionError(Exception):
    """事务操作异常类

    当事务操作失败时抛出此异常。异常消息会包含详细的错误信息。

    Attributes:
        message: 错误描述信息
        original_exception: 原始异常对象（如果有）
    """

    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        """初始化事务异常

        Args:
            message: 错误描述信息
            original_exception: 导致此异常的原始异常对象
        """
        super().__init__(message)
        self.original_exception = original_exception


class ApplyTransaction:
    """事务管理类 - 确保模型变更和配置变更的原子性

    此类实现了一个简单的事务机制，用于管理模型加载和配置保存操作。
    它确保这些操作要么全部成功，要么全部失败并回滚到初始状态。

    事务流程:
        1. begin() - 开始事务，备份当前状态
        2. apply_model_change() - 应用模型变更（可选）
        3. apply_config_changes() - 应用配置变更（可选）
        4. commit() - 提交事务，清理备份
        5. rollback() - 回滚事务，恢复备份状态（仅在失败时）

    Attributes:
        _model_service: 模型管理服务接口
        _settings_service: 设置管理服务接口
        _event_service: 事件服务接口
        _in_transaction: 是否处于事务中
        _backup_config: 备份的配置数据
        _backup_model_name: 备份的模型名称
        _changes_applied: 是否已应用变更
    """

    def __init__(
        self,
        model_service: UIModelService,
        settings_service: UISettingsService,
        event_service: IEventService,
        launch_at_login_service=None,
    ):
        """初始化事务管理器

        Args:
            model_service: 模型管理服务实例
            settings_service: 设置管理服务实例
            event_service: 事件服务实例
            launch_at_login_service: 开机自启系统集成服务（可选）
        """
        self._model_service = model_service
        self._settings_service = settings_service
        self._event_service = event_service
        self._launch_at_login_service = launch_at_login_service

        # 事务状态
        self._in_transaction = False
        self._backup_config: Optional[Dict[str, Any]] = None
        self._backup_model_name: Optional[str] = None
        self._backup_launch_at_login_state: Optional[bool] = None
        self._changes_applied = False

    def begin(self) -> None:
        """开始事务 - 备份当前状态

        创建当前配置和模型状态的备份，以便在事务失败时恢复。

        Raises:
            TransactionError: 如果已经在事务中或备份失败
        """
        if self._in_transaction:
            raise TransactionError("事务已经在进行中，不能重复开始")

        try:
            app_logger.debug("开始事务，备份当前状态")
            self._backup_state()
            self._in_transaction = True
            self._changes_applied = False
            app_logger.debug("事务已开始，状态已备份")
        except Exception as e:
            app_logger.error(f"开始事务失败: {e}")
            raise TransactionError("开始事务失败", e)

    def apply_model_change(self, model_name: str) -> None:
        """应用模型变更 - 事务式加载新模型

        在事务上下文中加载指定的模型。如果加载失败，事务会自动回滚。

        Args:
            model_name: 要加载的模型名称

        Raises:
            TransactionError: 如果不在事务中或模型加载失败
        """
        if not self._in_transaction:
            raise TransactionError("必须先调用 begin() 开始事务")

        try:
            app_logger.debug(f"应用模型变更: {model_name}")
            self._load_model_with_transaction(model_name)
            self._changes_applied = True
            app_logger.debug(f"模型变更已应用: {model_name}")
        except Exception as e:
            app_logger.error(f"应用模型变更失败: {e}")
            self.rollback()
            raise TransactionError(f"应用模型变更失败: {model_name}", e)

    def apply_config_changes(self, changes: Dict[str, Any]) -> None:
        """应用配置变更 - 事务式保存配置

        在事务上下文中应用配置变更。使用扁平化的键值对格式。
        例如: {"transcription.provider": "local", "ai.enabled": True}

        Args:
            changes: 要应用的配置变更，使用点分隔的键名

        Raises:
            TransactionError: 如果不在事务中或配置保存失败
        """
        if not self._in_transaction:
            raise TransactionError("必须先调用 begin() 开始事务")

        try:
            app_logger.debug(f"应用配置变更: {len(changes)} 项")
            self._save_config_with_transaction(changes)
            self._changes_applied = True
            app_logger.debug("配置变更已应用")
        except Exception as e:
            app_logger.error(f"应用配置变更失败: {e}")
            self.rollback()
            raise TransactionError("应用配置变更失败", e)

    def apply_launch_at_login_change(self, changes: Dict[str, Any]) -> None:
        """应用开机自启系统集成变更。"""
        if not self._in_transaction:
            raise TransactionError("必须先调用 begin() 开始事务")

        if LAUNCH_AT_LOGIN_KEY not in changes:
            return

        service = self._resolve_launch_at_login_service()
        if service is None:
            return

        try:
            target_enabled = bool(changes.get(LAUNCH_AT_LOGIN_KEY, False))
            service.sync(target_enabled)
            self._changes_applied = True
            app_logger.log_audio_event(
                "Launch-at-login synced in transaction",
                {"enabled": target_enabled},
            )
        except Exception as e:
            app_logger.error(f"同步开机自启失败: {e}")
            self.rollback()
            raise TransactionError("同步开机自启失败", e)

    def commit(self) -> None:
        """提交事务 - 确认所有变更并清理备份

        提交事务后，备份数据会被清理，变更会永久生效。

        Raises:
            TransactionError: 如果不在事务中
        """
        if not self._in_transaction:
            raise TransactionError("没有活动的事务可以提交")

        try:
            app_logger.debug("提交事务")
            self._cleanup_transaction()
            app_logger.info("事务已成功提交")
        except Exception as e:
            app_logger.error(f"提交事务失败: {e}")
            raise TransactionError("提交事务失败", e)

    def rollback(self) -> None:
        """回滚事务 - 恢复到事务开始前的状态

        回滚会恢复配置和模型到事务开始前的状态。
        此方法在任何步骤失败时自动调用。
        """
        if not self._in_transaction:
            app_logger.warning("没有活动的事务可以回滚")
            return

        try:
            app_logger.warning("回滚事务，恢复到之前的状态")

            # 恢复配置
            if self._backup_config is not None:
                app_logger.debug("恢复配置到备份状态")
                # 使用扁平化格式逐项恢复配置
                flat_config = self._flatten_config(self._backup_config)
                for key, value in flat_config.items():
                    try:
                        self._settings_service.set_setting(key, value)
                    except Exception as e:
                        app_logger.error(f"恢复配置项 {key} 失败: {e}")

                # 保存配置到文件
                try:
                    self._settings_service.save_settings()
                except Exception as e:
                    app_logger.error(f"保存恢复的配置失败: {e}")

            # 恢复模型
            if self._backup_model_name is not None:
                app_logger.debug(f"恢复模型到备份状态: {self._backup_model_name}")
                try:
                    self._model_service.load_model(self._backup_model_name)
                except Exception as e:
                    app_logger.error(f"恢复模型失败: {e}")

            # 恢复开机自启系统状态
            if self._backup_launch_at_login_state is not None:
                launch_service = self._resolve_launch_at_login_service()
                if launch_service is not None:
                    try:
                        launch_service.sync(self._backup_launch_at_login_state)
                    except Exception as e:
                        app_logger.error(f"恢复开机自启系统状态失败: {e}")

            app_logger.info("事务已回滚")
        except Exception as e:
            app_logger.error(f"回滚事务时发生错误: {e}")
        finally:
            self._cleanup_transaction()

    def _backup_state(self) -> None:
        """备份当前状态 - 保存配置和模型信息

        创建当前配置的深拷贝和当前模型名称的备份。

        Raises:
            Exception: 如果备份过程中发生错误
        """
        # 备份配置
        try:
            current_config = self._settings_service.get_all_settings()
            self._backup_config = copy.deepcopy(current_config)
            app_logger.debug("配置已备份")
        except Exception as e:
            app_logger.error(f"备份配置失败: {e}")
            raise

        # 备份模型名称
        try:
            model_info = self._model_service.get_model_info()
            self._backup_model_name = model_info.get("model_name")
            app_logger.debug(f"模型已备份: {self._backup_model_name}")
        except Exception as e:
            app_logger.error(f"备份模型名称失败: {e}")
            raise

        # 备份开机自启系统状态（Windows）
        launch_service = self._resolve_launch_at_login_service()
        if launch_service is not None:
            try:
                self._backup_launch_at_login_state = launch_service.is_enabled()
            except Exception as e:
                app_logger.error(f"备份开机自启系统状态失败: {e}")
                self._backup_launch_at_login_state = None

    def _load_model_with_transaction(self, model_name: str) -> None:
        """事务式加载模型

        在事务上下文中加载模型。如果加载失败，会抛出异常触发回滚。

        Args:
            model_name: 要加载的模型名称

        Raises:
            Exception: 如果模型加载失败
        """
        try:
            app_logger.debug(f"事务式加载模型: {model_name}")
            self._model_service.load_model(model_name)
            app_logger.debug(f"模型加载成功: {model_name}")
        except Exception as e:
            app_logger.error(f"模型加载失败: {e}")
            raise

    def _save_config_with_transaction(self, changes: Dict[str, Any]) -> None:
        """事务式保存配置

        在事务上下文中保存配置变更。使用扁平化的键值对格式。

        Args:
            changes: 要保存的配置变更，使用点分隔的键名

        Raises:
            RuntimeError: 如果热重载被阻止（例如录音进行中）
            Exception: 如果配置保存失败
        """
        try:
            app_logger.debug(f"事务式保存配置: {len(changes)} 项")

            # 使用批量设置 API 避免重复热重载
            # 批量更新所有配置项，仅触发一次热重载事件
            config_service = self._settings_service.config_service
            config_service.set_settings_batch(changes, immediate=True)

            app_logger.debug("配置保存成功（批量模式，已触发热重载事件）")
        except RuntimeError as e:
            # 热重载被阻止（录音进行中）- 重新抛出供 UI 处理
            app_logger.warning(f"配置热重载被阻止: {e}")
            raise
        except Exception as e:
            app_logger.error(f"配置保存失败: {e}")
            raise

    def _cleanup_transaction(self) -> None:
        """清理事务状态 - 清除备份数据和事务标志

        在事务提交或回滚后调用，清理所有临时数据。
        """
        app_logger.debug("清理事务状态")
        self._in_transaction = False
        self._backup_config = None
        self._backup_model_name = None
        self._backup_launch_at_login_state = None
        self._changes_applied = False

    def _flatten_config(
        self, config: Dict[str, Any], prefix: str = ""
    ) -> Dict[str, Any]:
        """展平配置字典 - 将嵌套字典转换为点分隔的键值对

        将嵌套的配置字典转换为扁平的键值对格式。
        例如: {"transcription": {"provider": "local"}} -> {"transcription.provider": "local"}

        Args:
            config: 要展平的配置字典
            prefix: 键名前缀（用于递归）

        Returns:
            展平后的配置字典
        """
        result: Dict[str, Any] = {}
        for key, value in config.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                # 递归展平嵌套字典
                result.update(self._flatten_config(value, full_key))
            else:
                result[full_key] = value
        return result

    def _resolve_launch_at_login_service(self):
        if self._launch_at_login_service is not None:
            return self._launch_at_login_service

        if hasattr(self._settings_service, "get_launch_at_login_service"):
            try:
                service = self._settings_service.get_launch_at_login_service()
                if service is not None:
                    self._launch_at_login_service = service
                return service
            except Exception:
                return None

        return None
