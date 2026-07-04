"""配置备份服务 - 单一职责：配置备份和恢复"""

import json
from pathlib import Path
from typing import Dict, Any, List, Union, Optional
from datetime import datetime

from ....utils import app_logger


class ConfigBackupService:
    """配置备份服务 - 只负责配置备份"""

    def __init__(self, config_path: Path):
        """初始化配置备份服务

        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path

    def backup_config(self, config: Dict[str, Any]) -> Optional[str]:
        """创建配置备份

        Args:
            config: 要备份的配置字典

        Returns:
            备份文件路径，失败时返回None
        """
        try:
            backup_dir = self.config_path.parent / 'backups'
            backup_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"config_backup_{timestamp}.json"

            if self.export_config(config, backup_path):
                app_logger.log_audio_event("Configuration backed up", {
                    "backup_path": str(backup_path)
                })
                return str(backup_path)
            else:
                return None

        except Exception as e:
            app_logger.log_error(e, "config_backup_create")
            return None

    def list_backups(self) -> List[Dict[str, Any]]:
        """列出配置备份

        Returns:
            备份文件信息列表
        """
        try:
            backup_dir = self.config_path.parent / 'backups'
            if not backup_dir.exists():
                return []

            backups: List[Dict[str, Any]] = []
            for backup_file in backup_dir.glob("config_backup_*.json"):
                stat_info = backup_file.stat()
                backups.append({
                    "path": str(backup_file),
                    "name": backup_file.name,
                    "size": stat_info.st_size,
                    "modified": stat_info.st_mtime,
                    "modified_iso": datetime.fromtimestamp(stat_info.st_mtime).isoformat()
                })

            # 按修改时间排序（最新的在前）
            backups.sort(key=lambda x: x["modified"], reverse=True)
            return backups

        except Exception as e:
            app_logger.log_error(e, "config_backup_list")
            return []

    def export_config(self, config: Dict[str, Any], target_path: Union[str, Path]) -> bool:
        """导出配置到指定路径

        Args:
            config: 要导出的配置字典
            target_path: 目标文件路径

        Returns:
            是否导出成功
        """
        try:
            target_path = Path(target_path)
            export_data = {
                "version": "1.0",
                "exported_at": datetime.now().isoformat(),
                "config": config
            }

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

            app_logger.log_audio_event("Configuration exported", {
                "file_path": str(target_path)
            })

            return True

        except Exception as e:
            app_logger.log_error(e, "config_backup_export")
            return False

    def import_config(self, source_path: Union[str, Path]) -> Optional[Dict[str, Any]]:
        """从指定路径导入配置

        Args:
            source_path: 源文件路径

        Returns:
            导入的配置字典，失败返回None
        """
        try:
            source_path = Path(source_path)
            with open(source_path, 'r', encoding='utf-8') as f:
                import_data = json.load(f)

            imported_config = import_data.get("config", {})

            app_logger.log_audio_event("Configuration imported", {
                "file_path": str(source_path)
            })

            return imported_config

        except Exception as e:
            app_logger.log_error(e, "config_backup_import")
            return None
