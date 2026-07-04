from pathlib import Path
import sys

from sonicinput.speech.sherpa_models import SherpaModelManager


def test_cache_dir_prefers_exe_models(tmp_path, monkeypatch):
    exe_dir = tmp_path / "bin"
    exe_dir.mkdir()
    models_dir = exe_dir / "models"
    models_dir.mkdir()
    fake_exe = exe_dir / "app.exe"
    fake_exe.write_text("", encoding="utf-8")

    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.delenv("SONICINPUT_MODELS_DIR", raising=False)

    cache_dir, source = SherpaModelManager._resolve_cache_dir()
    assert cache_dir == models_dir
    assert source == "exe_models"


def test_cache_dir_uses_env_when_no_exe_models(tmp_path, monkeypatch):
    exe_dir = tmp_path / "bin"
    exe_dir.mkdir()
    fake_exe = exe_dir / "app.exe"
    fake_exe.write_text("", encoding="utf-8")

    env_dir = tmp_path / "models_root"
    env_dir.mkdir()

    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.setenv("SONICINPUT_MODELS_DIR", str(env_dir))

    cache_dir, source = SherpaModelManager._resolve_cache_dir()
    assert cache_dir == env_dir
    assert source == "env"


def test_cache_dir_default_when_no_exe_or_env(tmp_path, monkeypatch):
    exe_dir = tmp_path / "bin"
    exe_dir.mkdir()
    fake_exe = exe_dir / "app.exe"
    fake_exe.write_text("", encoding="utf-8")

    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.delenv("SONICINPUT_MODELS_DIR", raising=False)

    cache_dir, source = SherpaModelManager._resolve_cache_dir()
    assert isinstance(cache_dir, Path)
    assert cache_dir.name == "sherpa_models_v2"
    assert source == "default"
