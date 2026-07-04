"""sherpa-onnx 模型管理器

负责模型下载、缓存和配置管理
"""

import os
import sys
import tarfile
import threading
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests
from loguru import logger

from .. import __version__

try:
    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtWidgets import QApplication, QProgressDialog

    PYSIDE6_AVAILABLE = True
except ImportError:
    PYSIDE6_AVAILABLE = False
    logger.warning("PySide6 not available, progress dialog will not be shown")

from ..core.base.lifecycle_component import LifecycleComponent


class SherpaModelManager(LifecycleComponent):
    """sherpa-onnx 模型管理器"""

    CACHE_SCHEMA_VERSION = 2

    MODELS: Dict[str, Dict[str, Any]] = {
        "paraformer": {
            "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-paraformer-bilingual-zh-en.tar.bz2",
            "size_mb": 226,
            "language": ["zh", "en"],
            "description": "High-accuracy bilingual model (recommended)",
            "rtf": 0.15,
        },
        "zipformer-small": {
            "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-small-bilingual-zh-en-2023-02-16.tar.bz2",
            "size_mb": 112,
            "language": ["zh", "en"],
            "description": "Ultra-lightweight bilingual model",
            "rtf": 0.10,
        },
    }

    def __init__(self, cache_dir: Optional[str] = None):
        """初始化模型管理器

        Args:
            cache_dir: Optional model cache root. If not set, resolution order is:
                1) executable sibling models directory
                2) SONICINPUT_MODELS_DIR environment variable
                3) ~/.sonicinput/sherpa_models_v2
        """
        super().__init__("SherpaModelManager")

        if cache_dir:
            self.cache_dir = Path(cache_dir)
            self.cache_dir_source = "custom"
        else:
            self.cache_dir, self.cache_dir_source = self._resolve_cache_dir()

        logger.info(
            f"Model cache directory resolved to {self.cache_dir} "
            f"(source={self.cache_dir_source})"
        )

        self._model_cache: Dict[str, Path] = {}  # Cache for model directories

    @staticmethod
    def _resolve_cache_dir() -> tuple[Path, str]:
        exe_dir = Path(sys.executable).resolve().parent
        exe_models = exe_dir / "models"
        if exe_models.is_dir():
            return exe_models, "exe_models"

        env_dir = os.environ.get("SONICINPUT_MODELS_DIR")
        if env_dir:
            return Path(env_dir), "env"

        return (
            Path.home()
            / ".sonicinput"
            / f"sherpa_models_v{SherpaModelManager.CACHE_SCHEMA_VERSION}",
            "default",
        )

    def is_model_cached(self, model_name: str) -> bool:
        """检查模型是否已缓存

        Args:
            model_name: 模型名称

        Returns:
            True if cached, False otherwise
        """
        if model_name not in self.MODELS:
            logger.error(f"Unknown model: {model_name}")
            return False

        model_dir = self._get_model_dir(model_name)

        # 检查必要文件是否存在
        required_files = [
            "tokens.txt",
            "encoder-epoch-99-avg-1.onnx",
            "decoder-epoch-99-avg-1.onnx",
        ]
        if model_name == "paraformer":
            # Paraformer 特殊文件名
            required_files = ["tokens.txt", "encoder.int8.onnx", "decoder.int8.onnx"]

        try:
            return model_dir.is_dir() and all(
                self._is_readable_file(model_dir / f) for f in required_files
            )
        except OSError as e:
            logger.warning(
                f"Failed to inspect cached model '{model_name}' at {model_dir}: {e}"
            )
            return False

    @staticmethod
    def _is_readable_file(path: Path) -> bool:
        try:
            if not path.is_file():
                return False
            with open(path, "rb") as handle:
                handle.read(1)
            return True
        except OSError:
            return False

    @staticmethod
    def _validate_download_url(url: str) -> None:
        """Validate model download URL."""
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https":
            raise RuntimeError(
                f"Only HTTPS model URLs are allowed, got scheme: {parsed.scheme}"
            )
        if not parsed.netloc:
            raise RuntimeError("Model URL must include a valid host")

    @staticmethod
    def _should_show_progress_dialog() -> bool:
        """Only show Qt progress UI on the main GUI thread."""
        return (
            PYSIDE6_AVAILABLE
            and threading.current_thread() is threading.main_thread()
            and QApplication.instance() is not None
        )

    def _safe_extract_members(
        self, tar: tarfile.TarFile, members: list[tarfile.TarInfo]
    ) -> None:
        """Safely extract validated tar members to cache directory."""
        cache_root = Path(self.cache_dir).resolve()

        for member in members:
            target_path = (cache_root / member.name).resolve()

            try:
                target_path.relative_to(cache_root)
            except ValueError:
                logger.warning(f"Skipping out-of-root tar member: {member.name}")
                continue

            if member.isdir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue

            if not member.isfile():
                logger.warning(f"Skipping non-regular tar member: {member.name}")
                continue

            extracted_file = tar.extractfile(member)
            if extracted_file is None:
                logger.warning(f"Skipping unreadable tar member: {member.name}")
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with extracted_file as source, open(target_path, "wb") as destination:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    destination.write(chunk)

    def download_model(self, model_name: str, progress_callback=None) -> Path:
        """下载模型到本地缓存

        Args:
            model_name: 模型名称
            progress_callback: 进度回调函数 (bytes_downloaded, total_bytes)

        Returns:
            模型目录路径

        Raises:
            ValueError: 如果模型名称不存在
            RuntimeError: 如果下载失败
        """
        if model_name not in self.MODELS:
            raise ValueError(f"Unknown model: {model_name}")

        # 检查是否已缓存
        if self.is_model_cached(model_name):
            logger.info(f"Model {model_name} already cached")
            return self._get_model_dir(model_name)

        model_info = self.MODELS[model_name]
        url = model_info["url"]
        size_mb = model_info["size_mb"]
        self._validate_download_url(url)

        logger.info(f"Downloading model {model_name} from {url}")
        logger.info(f"Size: {size_mb} MB")

        # 创建进度对话框 (如果 PySide6 可用)
        progress_dialog = None
        if self._should_show_progress_dialog():
            try:

                def _tr(text: str) -> str:
                    return QCoreApplication.translate("ModelDownload", text)

                progress_dialog = QProgressDialog()
                progress_dialog.setWindowTitle(_tr("Model Download"))
                progress_dialog.setLabelText(
                    _tr("Downloading model: {model}\nSize: {size} MB").format(
                        model=model_name, size=size_mb
                    )
                )
                progress_dialog.setCancelButton(None)  # 隐藏取消按钮
                progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
                progress_dialog.setMinimum(0)
                progress_dialog.setMaximum(100)
                progress_dialog.setValue(0)
                progress_dialog.show()
                QApplication.processEvents()
            except Exception as e:
                logger.warning(f"Failed to create progress dialog: {e}")
                progress_dialog = None

        # 下载到临时文件
        archive_path = self.cache_dir / f"{model_name}.tar.bz2"

        try:
            # 下载
            headers = {"User-Agent": f"SonicInput/{__version__}"}
            with requests.get(
                url, headers=headers, stream=True, timeout=(10, 300)
            ) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))
                downloaded = 0

                with open(archive_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)

                        # 更新进度对话框
                        if progress_dialog:
                            try:
                                percent = (
                                    int(downloaded * 100 / total_size)
                                    if total_size > 0
                                    else 0
                                )
                                progress_dialog.setValue(percent)
                                downloaded_mb = downloaded / (1024 * 1024)
                                total_mb = total_size / (1024 * 1024)
                                progress_dialog.setLabelText(
                                    _tr(
                                        "Downloading model: {model}\n"
                                        "Progress: {downloaded:.1f} MB / {total:.1f} MB ({percent}%)"
                                    ).format(
                                        model=model_name,
                                        downloaded=downloaded_mb,
                                        total=total_mb,
                                        percent=percent,
                                    )
                                )
                                QApplication.processEvents()
                            except Exception as e:
                                logger.warning(f"Failed to update progress dialog: {e}")

                        # 保持旧的回调接口兼容性
                        if progress_callback:
                            progress_callback(downloaded, total_size)

            logger.info(f"Download complete: {archive_path}")

            # 解压
            logger.info("Extracting model files...")
            if progress_dialog:
                try:
                    progress_dialog.setValue(95)
                    progress_dialog.setLabelText(
                        _tr("Extracting model: {model}\nPlease wait...").format(
                            model=model_name
                        )
                    )
                    QApplication.processEvents()
                except Exception as e:
                    logger.warning(
                        f"Failed to update progress dialog during extraction: {e}"
                    )

            with tarfile.open(archive_path, "r:bz2") as tar:
                # Securely extract files with path validation (防止路径遍历攻击)
                safe_members = []
                for member in tar.getmembers():
                    # Normalize member path and resolve it relative to cache_dir
                    member_path = Path(self.cache_dir) / member.name
                    try:
                        # Check if resolved path is within cache_dir (防止../类攻击)
                        member_path.resolve().relative_to(
                            Path(self.cache_dir).resolve()
                        )
                        safe_members.append(member)
                    except ValueError:
                        logger.warning(
                            f"Skipping potentially unsafe tar member: {member.name}"
                        )

                self._safe_extract_members(tar, safe_members)

            # 删除压缩包
            archive_path.unlink()
            logger.info("Model extraction complete")

            # 关闭进度对话框
            if progress_dialog:
                try:
                    progress_dialog.setValue(100)
                    progress_dialog.close()
                except Exception:
                    pass

            return self._get_model_dir(model_name)

        except Exception as e:
            logger.error(f"Failed to download model: {e}")

            # 关闭进度对话框
            if progress_dialog:
                try:
                    progress_dialog.close()
                except Exception:
                    pass

            # 清理失败的下载
            if archive_path.exists():
                archive_path.unlink()
            raise RuntimeError(f"Failed to download model {model_name}: {e}")

    def ensure_model_available(
        self, model_name: str, download_if_missing: bool = True
    ) -> Path:
        """确保模型可用（如果不存在则下载）

        Args:
            model_name: 模型名称

        Returns:
            模型目录路径
        """
        if not self.is_model_cached(model_name):
            if not download_if_missing:
                raise RuntimeError(f"Model {model_name} not cached or incomplete")
            logger.info(f"Model {model_name} not cached, downloading...")
            return self.download_model(model_name)

        return self._get_model_dir(model_name)

    def get_model_config(
        self, model_name: str, download_if_missing: bool = True
    ) -> Dict[str, Any]:
        """获取模型配置（供 sherpa-onnx 使用）

        Args:
            model_name: 模型名称

        Returns:
            模型配置字典

        Raises:
            ValueError: 如果模型不存在
            RuntimeError: 如果模型文件缺失
        """
        model_dir = self.ensure_model_available(
            model_name, download_if_missing=download_if_missing
        )

        if model_name == "paraformer":
            # Paraformer 配置（只支持greedy_search）
            return {
                "tokens": str(model_dir / "tokens.txt"),
                "encoder": str(model_dir / "encoder.int8.onnx"),
                "decoder": str(model_dir / "decoder.int8.onnx"),
                "model_type": "paraformer",
                "num_threads": 4,
                "provider": "cpu",
                "decoding_method": "greedy_search",
            }
        elif model_name == "zipformer-small":
            # Zipformer 配置（保守使用greedy_search以确保兼容性）
            return {
                "tokens": str(model_dir / "tokens.txt"),
                "encoder": str(model_dir / "encoder-epoch-99-avg-1.onnx"),
                "decoder": str(model_dir / "decoder-epoch-99-avg-1.onnx"),
                "joiner": str(model_dir / "joiner-epoch-99-avg-1.onnx"),
                "model_type": "zipformer",
                "num_threads": 4,
                "provider": "cpu",
                "decoding_method": "greedy_search",
            }
        else:
            raise ValueError(f"Unknown model: {model_name}")

    def get_model_info(self, model_name: str) -> Dict[str, Any]:
        """获取模型信息

        Args:
            model_name: 模型名称

        Returns:
            模型信息字典
        """
        if model_name not in self.MODELS:
            raise ValueError(f"Unknown model: {model_name}")

        info = self.MODELS[model_name].copy()
        info["cached"] = self.is_model_cached(model_name)
        info["cache_path"] = str(self._get_model_dir(model_name))
        if "description" in info and PYSIDE6_AVAILABLE:
            info["description"] = QCoreApplication.translate(
                "ModelMetadata", info["description"]
            )

        return info

    def list_models(self) -> Dict[str, Dict[str, Any]]:
        """列出所有可用模型

        Returns:
            模型名称 -> 模型信息的字典
        """
        return {name: self.get_model_info(name) for name in self.MODELS.keys()}

    def _get_model_dir(self, model_name: str) -> Path:
        """获取模型目录路径

        Args:
            model_name: 模型名称

        Returns:
            模型目录路径
        """
        if model_name == "paraformer":
            # Paraformer 解压后的目录名
            return self.cache_dir / "sherpa-onnx-streaming-paraformer-bilingual-zh-en"
        elif model_name == "zipformer-small":
            # Zipformer 解压后的目录名
            return (
                self.cache_dir
                / "sherpa-onnx-streaming-zipformer-small-bilingual-zh-en-2023-02-16"
            )
        else:
            # 通用模式
            return self.cache_dir / f"sherpa-onnx-{model_name}"

    # LifecycleComponent implementation

    def _do_start(self) -> bool:
        """Initialize model manager - ensure cache directory exists

        Returns:
            True if initialization successful
        """
        try:
            # Create cache directory
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Model cache directory: {self.cache_dir}")

            # Verify directory is writable
            test_file = self.cache_dir / ".test_write"
            try:
                test_file.touch()
                test_file.unlink()
            except Exception as e:
                logger.error(f"Cache directory not writable: {e}")
                return False

            return True

        except Exception as e:
            logger.error(f"Failed to initialize model manager: {e}")
            return False

    def _do_stop(self) -> bool:
        """Cleanup model manager resources

        Returns:
            True if cleanup successful
        """
        try:
            # Clear cached model directories
            self._model_cache.clear()
            logger.info("Model manager stopped, cache cleared")
            return True

        except Exception as e:
            logger.error(f"Error stopping model manager: {e}")
            return False
