import json

from sonicinput.core.services.config.config_reader import ConfigReader
from sonicinput.core.services.config.config_writer import ConfigWriter
from sonicinput.utils import secure_storage
from sonicinput.utils.secure_storage import SecureStorage


def _patch_dpapi(monkeypatch):
    def protect(self, data: bytes) -> bytes:
        return b"protected:" + data

    def unprotect(self, data: bytes) -> bytes:
        assert data.startswith(b"protected:")
        return data.removeprefix(b"protected:")

    monkeypatch.setattr(SecureStorage, "_protect_bytes", protect, raising=False)
    monkeypatch.setattr(SecureStorage, "_unprotect_bytes", unprotect, raising=False)
    monkeypatch.setattr(secure_storage, "_secure_storage", None)


def test_config_writer_encrypts_sensitive_values_and_reader_decrypts(
    tmp_path, monkeypatch
):
    _patch_dpapi(monkeypatch)
    config_path = tmp_path / "config.json"
    writer = ConfigWriter(config_path)
    writer.set_config(
        {
            "ai": {
                "groq": {
                    "api_key": "groq-secret",
                    "model_id": "llama",
                },
                "openrouter": {
                    "bearer": "bearer-secret",
                    "credential": "credential-secret",
                    "auth_header": "auth-secret",
                },
            }
        }
    )

    assert writer.save_config() is True

    raw_text = config_path.read_text(encoding="utf-8")
    assert "groq-secret" not in raw_text
    assert "bearer-secret" not in raw_text
    raw = json.loads(raw_text)
    assert raw["ai"]["groq"]["api_key"].startswith("dpapi:v1:")
    assert raw["ai"]["openrouter"]["bearer"].startswith("dpapi:v1:")
    assert raw["ai"]["openrouter"]["credential"].startswith("dpapi:v1:")
    assert raw["ai"]["openrouter"]["auth_header"].startswith("dpapi:v1:")

    reader = ConfigReader(config_path)
    assert reader.load_config() is True
    assert reader.get_setting("ai.groq.api_key") == "groq-secret"
    assert reader.get_setting("ai.openrouter.bearer") == "bearer-secret"
    assert reader.get_setting("ai.openrouter.credential") == "credential-secret"
    assert reader.get_setting("ai.openrouter.auth_header") == "auth-secret"
    assert reader.get_setting("ai.groq.model_id") == "llama"


def test_config_writer_does_not_silently_save_plaintext_when_encryption_fails(
    tmp_path, monkeypatch
):
    def fail_protect(self, data: bytes) -> bytes:
        raise RuntimeError("dpapi unavailable")

    monkeypatch.setattr(SecureStorage, "_protect_bytes", fail_protect, raising=False)
    monkeypatch.setattr(secure_storage, "_secure_storage", None)
    config_path = tmp_path / "config.json"
    writer = ConfigWriter(config_path)
    writer.set_config({"ai": {"groq": {"api_key": "groq-secret"}}})

    assert writer.save_config() is False
    if config_path.exists():
        assert "groq-secret" not in config_path.read_text(encoding="utf-8")
