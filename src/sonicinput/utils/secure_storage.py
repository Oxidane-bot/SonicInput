"""安全存储工具 - 用于敏感信息加密存储"""

import base64
import hashlib
import os
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from . import app_logger


class SecureStorage:
    """安全存储类 - 提供敏感信息的加密存储功能"""

    def __init__(self, app_name: str = "SonicInput"):
        """
        初始化安全存储

        Args:
            app_name: 应用程序名称，用于生成唯一的加密密钥
        """
        self.app_name = app_name
        self._key: Optional[bytes] = None
        self._cipher: Optional[Fernet] = None
        self._init_encryption()

    def _init_encryption(self) -> None:
        """初始化加密器"""
        try:
            # 基于系统信息和应用程序名称生成密钥
            machine_id = self._get_machine_id()
            key_material = f"{self.app_name}:{machine_id}".encode()

            # 使用PBKDF2生成密钥
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b"sonicinput_salt_2025",  # 固定salt，确保同一机器上密钥一致
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(key_material))

            self._cipher = Fernet(key)
            app_logger.log_audio_event("SecureStorage initialized successfully", {})

        except Exception as e:
            app_logger.log_error(e, "SecureStorage_init")
            # 降级到不安全存储（仅在Windows环境中）
            self._cipher = None
            app_logger.warning("SecureStorage falling back to plain text")

    def _get_machine_id(self) -> str:
        """获取机器唯一标识"""
        try:
            import platform
            import uuid

            # 尝试多种方式获取机器ID
            machine_id_sources = [
                lambda: str(uuid.getnode()),  # MAC地址
                lambda: platform.node(),  # 计算机名
                lambda: os.environ.get("COMPUTERNAME", ""),  # Windows计算机名
                lambda: os.environ.get("USERNAME", ""),  # 用户名
            ]

            combined_id = ""
            for idx, source in enumerate(machine_id_sources):
                try:
                    combined_id += source() + "|"
                except Exception as e:
                    app_logger.error(
                        f"Failed to get machine ID from source #{idx}",
                        e,
                        context={"source_index": idx},
                        component="machine_id_source_failed",
                    )
                    continue

            # 如果所有方法都失败，使用默认值
            if not combined_id:
                combined_id = "default_machine_id"

            # 生成最终ID的hash
            return hashlib.sha256(combined_id.encode()).hexdigest()[:32]

        except Exception:
            return "fallback_machine_id"

    def encrypt(self, data: str) -> str:
        """
        加密数据

        Args:
            data: 要加密的字符串

        Returns:
            加密后的base64字符串，如果加密失败则返回原始数据
        """
        if not self._cipher or not data:
            return data

        try:
            encrypted_data = self._cipher.encrypt(data.encode())
            return base64.urlsafe_b64encode(encrypted_data).decode()
        except Exception as e:
            app_logger.log_error(e, "SecureStorage_encrypt")
            return data  # 降级到原始数据

    def decrypt(self, encrypted_data: str) -> str:
        """
        解密数据

        Args:
            encrypted_data: 加密的base64字符串

        Returns:
            解密后的原始字符串，如果解密失败则返回原始数据
        """
        if not self._cipher or not encrypted_data:
            return encrypted_data

        try:
            # 尝试解密
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted_data = self._cipher.decrypt(encrypted_bytes)
            return decrypted_data.decode()
        except Exception:
            # 如果解密失败，可能是未加密的数据，直接返回
            return encrypted_data

    def secure_store_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        安全存储字典（加密所有字符串值）

        Args:
            data: 要存储的字典

        Returns:
            加密后的字典
        """
        secure_data = {}
        for key, value in data.items():
            if isinstance(value, str) and value:  # 只加密非空字符串
                # 检测是否是API密钥（包含'key', 'token', 'secret'等关键词）
                if any(
                    keyword in key.lower()
                    for keyword in ["key", "token", "secret", "password"]
                ):
                    secure_data[key] = self.encrypt(value)
                else:
                    secure_data[key] = value
            else:
                secure_data[key] = value
        return secure_data

    def secure_load_dict(self, secure_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        安全加载字典（解密所有加密值）

        Args:
            secure_data: 加密的字典

        Returns:
            解密后的字典
        """
        data = {}
        for key, value in secure_data.items():
            if isinstance(value, str) and value:
                # 检测是否是API密钥字段
                if any(
                    keyword in key.lower()
                    for keyword in ["key", "token", "secret", "password"]
                ):
                    data[key] = self.decrypt(value)
                else:
                    data[key] = value
            else:
                data[key] = value
        return data

    def is_encryption_available(self) -> bool:
        """检查加密是否可用"""
        return self._cipher is not None


# 全局安全存储实例
_secure_storage = None


def get_secure_storage() -> SecureStorage:
    """获取全局安全存储实例"""
    global _secure_storage
    if _secure_storage is None:
        _secure_storage = SecureStorage()
    return _secure_storage
