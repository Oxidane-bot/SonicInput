"""Secure storage helpers for sensitive configuration values."""

from __future__ import annotations

import base64
import copy
import re
import threading
from typing import Any, Dict

from . import app_logger


SENSITIVE_KEYWORDS = (
    "api_key",
    "apikey",
    "access_key",
    "secret_key",
    "private_key",
    "client_secret",
    "access_token",
    "refresh_token",
    "token",
    "secret",
    "password",
    "passwd",
    "bearer",
    "auth",
    "authorization",
    "credential",
    "credentials",
)

_SENSITIVE_TOKENS = {
    "token",
    "secret",
    "password",
    "passwd",
    "bearer",
    "auth",
    "authorization",
    "credential",
    "credentials",
}

_SENSITIVE_KEY_TOKEN_PAIRS = {
    ("api", "key"),
    ("access", "key"),
    ("secret", "key"),
    ("private", "key"),
}


class SecureStorage:
    """Protect sensitive values using Windows DPAPI."""

    PREFIX = "dpapi:v1:"

    def __init__(self, app_name: str = "SonicInput"):
        self.app_name = app_name
        self._available = self._check_dpapi_available()
        if self._available:
            app_logger.log_audio_event("SecureStorage initialized with DPAPI", {})
        else:
            app_logger.log_warning("SecureStorage DPAPI unavailable", {})

    def _check_dpapi_available(self) -> bool:
        try:
            import win32crypt  # noqa: F401

            return True
        except Exception as e:
            app_logger.log_error(e, "SecureStorage_init")
            return False

    @classmethod
    def is_sensitive_key(cls, key: str) -> bool:
        normalized = key.lower().replace("-", "_")
        compact = re.sub(r"[^a-z0-9]", "", normalized)
        tokens = tuple(token for token in re.split(r"[^a-z0-9]+", normalized) if token)
        token_set = set(tokens)

        if compact in {keyword.replace("_", "") for keyword in SENSITIVE_KEYWORDS}:
            return True
        if token_set & _SENSITIVE_TOKENS:
            return True
        return any(
            pair[0] in token_set and pair[1] in token_set
            for pair in _SENSITIVE_KEY_TOKEN_PAIRS
        )

    def _protect_bytes(self, data: bytes) -> bytes:
        import win32crypt

        return win32crypt.CryptProtectData(
            data,
            self.app_name,
            None,
            None,
            None,
            0,
        )

    def _unprotect_bytes(self, data: bytes) -> bytes:
        import win32crypt

        _description, plaintext = win32crypt.CryptUnprotectData(
            data,
            None,
            None,
            None,
            0,
        )
        return plaintext

    def encrypt(self, data: str) -> str:
        """Encrypt a string for persistence.

        Raises:
            RuntimeError: DPAPI is unavailable or encryption fails.
        """
        if not data or data.startswith(self.PREFIX):
            return data
        if not self._available:
            raise RuntimeError("DPAPI is not available")

        try:
            protected = self._protect_bytes(data.encode("utf-8"))
            encoded = base64.urlsafe_b64encode(protected).decode("ascii")
            return f"{self.PREFIX}{encoded}"
        except Exception as e:
            app_logger.log_error(e, "SecureStorage_encrypt")
            raise RuntimeError("Failed to protect sensitive value") from e

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt a DPAPI-prefixed string.

        Unprefixed values are legacy plaintext and are returned unchanged.
        """
        if not encrypted_data or not encrypted_data.startswith(self.PREFIX):
            return encrypted_data
        if not self._available:
            raise RuntimeError("DPAPI is not available")

        try:
            payload = encrypted_data[len(self.PREFIX) :]
            protected = base64.urlsafe_b64decode(payload.encode("ascii"))
            plaintext = self._unprotect_bytes(protected)
            return plaintext.decode("utf-8")
        except Exception as e:
            app_logger.log_error(e, "SecureStorage_decrypt")
            raise RuntimeError("Failed to unprotect sensitive value") from e

    def secure_store_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Return a copy with sensitive string values encrypted."""
        return self._transform_dict(copy.deepcopy(data), encrypt=True)

    def secure_load_dict(self, secure_data: Dict[str, Any]) -> Dict[str, Any]:
        """Return a copy with DPAPI-prefixed sensitive values decrypted."""
        return self._transform_dict(copy.deepcopy(secure_data), encrypt=False)

    def _transform_dict(self, data: Dict[str, Any], *, encrypt: bool) -> Dict[str, Any]:
        transformed: Dict[str, Any] = {}
        for key, value in data.items():
            transformed[key] = self._transform_value(
                key,
                value,
                encrypt=encrypt,
                sensitive_parent=self.is_sensitive_key(key),
            )
        return transformed

    def _transform_value(
        self,
        key: str,
        value: Any,
        *,
        encrypt: bool,
        sensitive_parent: bool,
    ) -> Any:
        if isinstance(value, dict):
            return {
                child_key: self._transform_value(
                    child_key,
                    child_value,
                    encrypt=encrypt,
                    sensitive_parent=sensitive_parent
                    or self.is_sensitive_key(child_key),
                )
                for child_key, child_value in value.items()
            }
        if isinstance(value, list):
            return [
                self._transform_value(
                    key,
                    item,
                    encrypt=encrypt,
                    sensitive_parent=sensitive_parent,
                )
                for item in value
            ]
        if isinstance(value, str) and value:
            if encrypt and sensitive_parent:
                return self.encrypt(value)
            if not encrypt and (sensitive_parent or value.startswith(self.PREFIX)):
                return self.decrypt(value)
        return value

    def is_encryption_available(self) -> bool:
        """Return whether DPAPI protection is available."""
        return self._available


_secure_storage: SecureStorage | None = None
_secure_storage_lock = threading.Lock()


def get_secure_storage() -> SecureStorage:
    """Get the process-wide secure storage instance."""
    global _secure_storage
    if _secure_storage is None:
        with _secure_storage_lock:
            if _secure_storage is None:
                _secure_storage = SecureStorage()
    return _secure_storage
