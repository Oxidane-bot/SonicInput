"""音频录制器"""

import threading
import time
import wave
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pyaudio

from ..core.base.lifecycle_component import LifecycleComponent
from ..core.interfaces import IAudioService
from ..core.services.config import ConfigKeys
from ..utils import AudioRecordingError, app_logger


class AudioRecorder(LifecycleComponent, IAudioService):
    """音频录制引擎"""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 4096,  # 256ms @ 16kHz，提供更多上下文
        config_service=None,
    ):
        # Initialize LifecycleComponent
        super().__init__("AudioRecorder")

        self._sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.format = pyaudio.paInt16

        self._audio: Optional[pyaudio.PyAudio] = None
        self._stream: Optional[Any] = None
        self._recording = False
        self._audio_data: List[np.ndarray] = []
        self._record_thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[np.ndarray], None]] = None
        self._device_id: Optional[int] = None  # Initialize device_id
        self._config_service = config_service  # 保存配置服务引用

        # 线程安全：保护 _audio_data 的并发访问
        self._data_lock = threading.Lock()

        # 流式转录块时长（从配置读取，默认15秒）
        if config_service:
            self.chunk_duration = config_service.get_setting(
                ConfigKeys.AUDIO_STREAMING_CHUNK_DURATION, 15.0
            )
        else:
            self.chunk_duration = 15.0
        self.chunk_callback = None  # 外部回调，用于流式转录块
        self._chunked_samples_sent = 0  # 追踪已发送给chunk_callback的样本数量

        # 优化: 累积音频缓存,避免重复拼接 (v0.5.1 性能优化)
        self._accumulated_audio: Optional[np.ndarray] = None  # 累积的完整音频数据

        # Auto-start to maintain backward compatibility
        # (old code called _initialize_audio() in __init__)
        self.start()

        # 启动时验证配置的设备
        if config_service:
            self._validate_configured_device()

    def _do_start(self) -> bool:
        """Initialize PyAudio resources

        Returns:
            True if initialization successful
        """
        try:
            self._audio = pyaudio.PyAudio()
            app_logger.log_audio_event(
                "Audio system initialized",
                {
                    "sample_rate": self._sample_rate,
                    "channels": self.channels,
                    "chunk_size": self.chunk_size,
                },
            )
            return True
        except Exception as init_error:
            # 确保PyAudio资源正确清理
            cleanup_error = None

            if hasattr(self, "_audio") and self._audio is not None:
                try:
                    self._audio.terminate()
                except Exception as e:
                    cleanup_error = e
                    app_logger.log_error(
                        e,
                        "audio_initialization_cleanup_failed",
                    )
                finally:
                    self._audio = None

            # Report both errors if cleanup also failed
            error_msg = f"Failed to initialize audio system: {init_error}"
            if cleanup_error:
                error_msg += f". Cleanup also failed: {cleanup_error}"

            app_logger.error(error_msg, init_error, component="audio_recorder_do_start")
            return False

    def _do_stop(self) -> bool:
        """Cleanup PyAudio resources

        Returns:
            True if cleanup successful
        """
        try:
            # Stop any active recording first
            if self._recording:
                self.stop_recording()

            # Ensure recording thread terminates
            if hasattr(self, "_record_thread") and self._record_thread:
                try:
                    self._record_thread.join(timeout=2.0)
                    if self._record_thread.is_alive():
                        app_logger.warning("Recording thread did not terminate cleanly")
                except Exception as e:
                    app_logger.log_error(e, "do_stop_thread_join")

            # Cleanup PyAudio resources
            if self._audio:
                try:
                    self._audio.terminate()
                    app_logger.log_audio_event("PyAudio terminated successfully", {})
                except Exception as e:
                    app_logger.log_error(e, "do_stop_pyaudio_terminate")
                    return False
                finally:
                    self._audio = None

            # Clear audio data buffer
            with self._data_lock:
                if hasattr(self, "_audio_data"):
                    self._audio_data.clear()
                    self._audio_data = []

            return True
        except Exception as e:
            app_logger.log_error(e, "audio_recorder_do_stop")
            return False

    def _validate_configured_device(self) -> None:
        """验证配置中保存的设备 ID 是否仍然有效

        如果无效，自动清除配置（下次将使用默认设备）
        """
        try:
            device_id = self._config_service.get_setting(ConfigKeys.AUDIO_DEVICE_ID)

            # None 表示使用默认设备，始终有效
            if device_id is None:
                app_logger.log_audio_event("Using system default audio device", {})
                return

            # 验证设备是否存在
            if not self.validate_device(device_id):
                app_logger.log_audio_event(
                    "Configured audio device no longer available, resetting to default",
                    {"invalid_device_id": device_id},
                )

                # 清除无效的设备配置，下次使用默认设备
                self._config_service.set_setting("audio.device_id", None)
            else:
                app_logger.log_audio_event(
                    "Configured audio device validated", {"device_id": device_id}
                )

        except Exception as e:
            app_logger.log_error(e, "validate_configured_device")

    def _require_audio(self) -> "pyaudio.PyAudio":
        """确保 PyAudio 已初始化并返回实例（必要时启动）。

        Returns:
            已初始化的 PyAudio 实例

        Raises:
            AudioRecordingError: 音频系统未能初始化时抛出
        """
        if self._audio is None:
            self.start()
        if self._audio is None:
            raise AudioRecordingError("Audio system is not initialized")
        return self._audio

    def get_audio_devices(self) -> List[Dict[str, Any]]:
        """Get available audio input devices

        Returns:
            List of device dictionaries with keys: index, name, channels, sample_rate
        """
        devices = []
        try:
            audio = self._require_audio()

            for i in range(audio.get_device_count()):
                try:
                    info = audio.get_device_info_by_index(i)
                    if info["maxInputChannels"] > 0:
                        devices.append(
                            {
                                "index": i,
                                "name": info["name"],
                                "channels": info["maxInputChannels"],
                                "sample_rate": info["defaultSampleRate"],
                            }
                        )
                except Exception as e:
                    app_logger.log_error(e, f"get_device_info_{i}")
                    continue
        except Exception as e:
            app_logger.log_error(e, "get_audio_devices")
        return devices

    def validate_device(self, device_id: int) -> bool:
        """验证音频设备是否可用"""
        try:
            if device_id is None:
                return True  # Use default device

            audio = self._require_audio()

            # Check if device exists and has input channels
            device_info = audio.get_device_info_by_index(device_id)
            return device_info["maxInputChannels"] > 0
        except Exception as e:
            app_logger.log_error(e, f"validate_device_{device_id}")
            return False

    def set_callback(self, callback: Callable[[np.ndarray], None]) -> None:
        """设置实时音频数据回调"""
        self._callback = callback

    def start_recording(self, device_id: Optional[int] = None) -> bool:
        """开始录音

        Args:
            device_id: 音频设备ID，None 表示使用默认设备

        Returns:
            是否成功开始录音

        Raises:
            AudioRecordingError: 启动录音失败时抛出
        """
        if self._recording:
            app_logger.log_audio_event("Recording already in progress", {})
            return False

        # 尝试打开指定设备，失败时fallback到默认设备
        attempted_devices = []
        last_error = None
        audio = self._require_audio()

        # 尝试1：使用指定的设备
        if device_id is not None:
            try:
                self._stream = audio.open(
                    format=self.format,
                    channels=self.channels,
                    rate=self._sample_rate,
                    input=True,
                    input_device_index=device_id,
                    frames_per_buffer=self.chunk_size,
                )
                attempted_devices.append(f"Device {device_id} (specified)")
                app_logger.log_audio_event(
                    "Opened specified audio device", {"device_id": device_id}
                )

                # 成功，继续启动录音
                self._device_id = device_id
                self._start_recording_thread()
                return True

            except Exception as e:
                last_error = e
                attempted_devices.append(f"Device {device_id} (failed: {str(e)})")
                app_logger.log_audio_event(
                    "Failed to open specified device, trying fallback",
                    {"device_id": device_id, "error": str(e)},
                )

        # 尝试2：Fallback到系统默认设备
        try:
            self._stream = audio.open(
                format=self.format,
                channels=self.channels,
                rate=self._sample_rate,
                input=True,
                input_device_index=None,  # None = 系统默认设备
                frames_per_buffer=self.chunk_size,
            )
            attempted_devices.append("System Default (fallback)")
            app_logger.log_audio_event(
                "Fallback to system default device succeeded",
                {"attempted_devices": attempted_devices},
            )

            # 成功，继续启动录音
            self._device_id = None
            self._start_recording_thread()
            return True

        except Exception as e:
            last_error = e
            attempted_devices.append(f"System Default (failed: {str(e)})")
            app_logger.log_error(e, "start_recording_fallback_failed")

            # 所有尝试都失败
            error_msg = (
                f"Failed to start recording after trying: {', '.join(attempted_devices)}. "
                f"Last error: {str(last_error)}"
            )
            raise AudioRecordingError(error_msg)

    def _start_recording_thread(self) -> None:
        """启动录音线程（从 start_recording 中提取的辅助方法）"""
        self._recording = True
        self._audio_data = []
        self._chunked_samples_sent = 0  # 重置chunk追踪计数器
        self._accumulated_audio = None  # 重置累积缓冲区 (性能优化)

        # 启动录音线程（30秒计时在线程内部实现）
        self._record_thread = threading.Thread(target=self._record_audio)
        self._record_thread.daemon = True
        self._record_thread.start()

        app_logger.log_audio_event(
            "Recording started",
            {
                "device_id": self._device_id,
                "sample_rate": self._sample_rate,
                "streaming_mode_enabled": True,
            },
        )

    def _record_audio(self) -> None:
        """录音线程函数

        性能优化：将 try-except 移出热路径循环，只保护关键的音频流读取操作
        """
        chunk_count = 0
        last_log_time = time.time()
        last_chunk_time = time.time()  # 30秒分块计时

        try:
            while self._recording and self._stream:
                chunk_start_time = time.time()

                # 只保护可能抛出 IOError 的音频流读取
                try:
                    data = self._stream.read(
                        self.chunk_size, exception_on_overflow=False
                    )
                except (OSError, IOError) as stream_error:
                    app_logger.log_error(stream_error, "_record_audio_stream_read")
                    break

                chunk_read_time = time.time()

                audio_chunk = (
                    np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                )

                # 保存音频数据（线程安全）
                with self._data_lock:
                    self._audio_data.append(audio_chunk)
                chunk_count += 1

                # 每隔1秒记录一次详细的块处理信息
                if chunk_read_time - last_log_time >= 1.0:
                    app_logger.log_audio_event(
                        "Recording chunk batch processed",
                        {
                            "chunks_processed": chunk_count,
                            "last_chunk_read_time_ms": (
                                chunk_read_time - chunk_start_time
                            )
                            * 1000,
                            "recording_still_active": self._recording,
                            "timestamp": chunk_read_time,
                        },
                    )
                    last_log_time = chunk_read_time

                # 每隔指定时间提取音频块进行流式转录
                if chunk_read_time - last_chunk_time >= self.chunk_duration:
                    self._on_chunk_ready()
                    last_chunk_time = chunk_read_time

                # 如果有回调函数，调用它（保护录音线程不被回调异常崩溃）
                if self._callback:
                    try:
                        self._callback(audio_chunk)
                    except Exception as callback_error:
                        app_logger.log_error(callback_error, "_record_audio_callback")
                        # 继续录音，不中断

        except Exception as e:
            # 捕获循环外的意外错误（如 numpy/threading 错误）
            app_logger.log_error(e, "_record_audio_unexpected")

        # 记录录音线程结束
        final_time = time.time()
        app_logger.log_audio_event(
            "Recording thread ended",
            {
                "total_chunks_captured": chunk_count,
                "recording_flag": self._recording,
                "final_timestamp": final_time,
            },
        )

    def stop_recording(self) -> Tuple[np.ndarray, float]:
        """Stop audio recording and return captured audio data

        Performs graceful shutdown of recording thread and audio stream,
        then concatenates all captured audio chunks into a single array.

        Returns:
            Tuple of (audio_samples, duration_seconds).
            audio_samples is a numpy array of float32 samples in [-1.0, 1.0].
            Returns (empty array, 0.0) if no recording was in progress.

        Timing Analysis:
            Logs detailed timing metrics to identify any delays:
            - Flag set to thread join duration
            - Thread join to stream close duration
            - Total stop process duration
            - Theoretical chunk delay (based on chunk_size/sample_rate)

        Performance Notes:
            - Waits up to 1.0 second for recording thread to exit
            - Thread-safe: Uses _data_lock for audio_data access
            - Last chunk may have up to chunk_size/sample_rate ms latency

        Side Effects:
            - Sets _recording flag to False
            - Closes audio stream
            - Waits for _record_thread to exit
            - Does NOT clear _audio_data (preserved for final return)

        Example:
            >>> recorder.start_recording()
            >>> time.sleep(3.0)
            >>> audio, duration = recorder.stop_recording()
            >>> print(f"Recorded {duration:.2f} seconds")

        Thread Safety:
            Multiple calls are safe - first call stops recording, subsequent
            calls return empty array.
        """
        stop_time_start = time.time()

        if not self._recording:
            app_logger.log_audio_event("No recording in progress", {})
            return np.array([]), 0.0

        app_logger.log_audio_event(
            "Recording stop initiated",
            {
                "timestamp": stop_time_start,
                "chunk_size": self.chunk_size,
                "sample_rate": self._sample_rate,
                "potential_delay_ms": (self.chunk_size / self._sample_rate) * 1000,
            },
        )

        self._recording = False
        stop_flag_set_time = time.time()

        # 等待录音线程结束
        if self._record_thread and self._record_thread.is_alive():
            thread_join_start = time.time()
            self._record_thread.join(timeout=1.0)
            thread_join_end = time.time()

            app_logger.log_audio_event(
                "Recording thread joined",
                {
                    "join_duration_ms": (thread_join_end - thread_join_start) * 1000,
                    "thread_was_alive": True,
                },
            )

        # 关闭音频流
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception as e:
                app_logger.log_error(e, "stop_recording")
            finally:
                self._stream = None
        stream_close_end = time.time()

        # 合并音频数据（线程安全）
        with self._data_lock:
            if self._audio_data:
                audio_array = np.concatenate(self._audio_data)
                chunks_count = len(self._audio_data)
            else:
                return np.array([]), 0.0

        # 计算实际音频时长（基于采样数）
        actual_duration = len(audio_array) / self._sample_rate

        stop_time_end = time.time()
        total_stop_duration = stop_time_end - stop_time_start
        flag_to_stream_close = stream_close_end - stop_flag_set_time

        app_logger.log_audio_event(
            "Recording stopped with timing analysis",
            {
                "audio_duration_seconds": actual_duration,
                "audio_samples": len(audio_array),
                "chunks_recorded": chunks_count,
                "stop_process_duration_ms": total_stop_duration * 1000,
                "flag_to_stream_close_ms": flag_to_stream_close * 1000,
                "theoretical_chunk_delay_ms": (self.chunk_size / self._sample_rate)
                * 1000,
                "last_chunk_timestamp": stop_time_start,
            },
        )
        return audio_array, actual_duration

    def _on_chunk_ready(self) -> None:
        """流式转录块就绪，提取增量音频块进行转录（性能优化版本）

        关键优化：使用累积缓冲区避免 O(n²) 重复拼接。
        关键修复：不再清空 _audio_data，而是追踪已发送的样本数，
        这样既能保留完整录音，又能提取增量chunk用于流式转录。
        """
        if not self._recording or not self.chunk_callback:
            return

        # 线程安全：读取并累积音频数据
        chunk_audio = None
        with self._data_lock:
            if len(self._audio_data) == 0:
                return

            # 优化: 仅拼接新增的块到累积缓冲区
            if self._accumulated_audio is None:
                # 首次拼接: 拼接所有现有数据
                self._accumulated_audio = np.concatenate(
                    self._audio_data, axis=0
                ).flatten()
            else:
                # 增量拼接: 仅拼接新块
                # 计算已累积的块数（每个块大小为 chunk_size）
                accumulated_chunks = len(self._accumulated_audio) // self.chunk_size
                new_chunks = self._audio_data[accumulated_chunks:]

                if new_chunks:
                    new_audio = np.concatenate(new_chunks, axis=0).flatten()
                    self._accumulated_audio = np.concatenate(
                        [self._accumulated_audio, new_audio]
                    )

            total_samples = len(self._accumulated_audio)

            # 只提取新增的部分（自上次chunk_callback以来的增量）
            if total_samples > self._chunked_samples_sent:
                chunk_audio = self._accumulated_audio[
                    self._chunked_samples_sent :
                ].copy()
                self._chunked_samples_sent = total_samples
            else:
                return

        app_logger.log_audio_event(
            f"Streaming chunk ready ({self.chunk_duration}s)",
            {
                "chunk_samples": len(chunk_audio),
                "chunk_duration_seconds": len(chunk_audio) / self._sample_rate,
                "configured_duration": self.chunk_duration,
                "total_samples_tracked": self._chunked_samples_sent,
            },
        )

        # 调用外部回调（异步转录）- 保护录音线程
        if self.chunk_callback:
            try:
                self.chunk_callback(chunk_audio)
            except Exception as callback_error:
                app_logger.log_error(callback_error, "_on_chunk_ready_callback")
                # 继续录音，不中断

    def get_audio_data(self) -> np.ndarray:
        """获取当前音频数据（不停止录音）"""
        with self._data_lock:
            if self._audio_data:
                return np.concatenate(self._audio_data)
            return np.array([])

    def get_remaining_audio_for_streaming(self) -> np.ndarray:
        """获取剩余未发送到流式转录的音频数据（性能优化版本）

        使用累积缓冲区避免重复拼接。

        Returns:
            剩余的音频数据（自上次 chunk_callback 以来的增量）
        """
        with self._data_lock:
            if not self._audio_data:
                return np.array([])

            # 优化: 使用累积缓冲区或按需拼接
            if self._accumulated_audio is not None:
                # 已有累积缓冲区,直接切片
                full_audio = self._accumulated_audio
            else:
                # 首次访问,拼接一次
                full_audio = np.concatenate(self._audio_data, axis=0).flatten()

            # 关键修复：stop_recording 可能发生在两个 chunk 回调之间，
            # 此时 _accumulated_audio 只包含上一次 _on_chunk_ready() 时刻的数据。
            # 如果这里直接复用 _accumulated_audio，会误判“无剩余音频”，导致最后一个分块不被发送。
            if self._accumulated_audio is not None and self.chunk_size > 0:
                accumulated_chunks = len(self._accumulated_audio) // self.chunk_size
                if accumulated_chunks < len(self._audio_data):
                    new_chunks = self._audio_data[accumulated_chunks:]
                    if new_chunks:
                        new_audio = np.concatenate(new_chunks, axis=0).flatten()
                        if len(new_audio) > 0:
                            self._accumulated_audio = np.concatenate(
                                [self._accumulated_audio, new_audio]
                            )
                            full_audio = self._accumulated_audio

            total_samples = len(full_audio)

            # 返回未发送的部分
            if total_samples > self._chunked_samples_sent:
                remaining_audio = full_audio[self._chunked_samples_sent :].copy()
                app_logger.log_audio_event(
                    "Remaining audio extracted for final chunk",
                    {
                        "remaining_samples": len(remaining_audio),
                        "remaining_duration_seconds": len(remaining_audio)
                        / self._sample_rate,
                        "already_sent_samples": self._chunked_samples_sent,
                        "total_samples": total_samples,
                    },
                )
                return remaining_audio
            else:
                return np.array([])

    def save_to_file(
        self, file_path: str, audio_data: Optional[np.ndarray] = None
    ) -> bool:
        """保存音频数据到WAV文件

        Args:
            file_path: 目标文件路径
            audio_data: 音频数据（如果为None，则使用当前录音数据）

        Returns:
            保存是否成功
        """
        try:
            # 如果没有提供音频数据，使用当前录音数据
            if audio_data is None:
                audio_data = self.get_audio_data()

            # 检查是否有音频数据
            if audio_data is None or len(audio_data) == 0:
                app_logger.log_error(Exception("No audio data to save"), "save_to_file")
                return False

            # 将音频数据转换为int16格式
            audio_int16 = (audio_data * 32767).astype(np.int16)

            # 保存为WAV文件
            with wave.open(file_path, "wb") as wav_file:
                wav_file.setnchannels(self.channels)
                wav_file.setsampwidth(2)  # 16-bit = 2 bytes
                wav_file.setframerate(self._sample_rate)
                wav_file.writeframes(audio_int16.tobytes())

            app_logger.log_audio_event(
                "Audio saved to file",
                {
                    "file_path": file_path,
                    "duration": len(audio_data) / self._sample_rate,
                    "sample_rate": self._sample_rate,
                },
            )

            return True

        except Exception as e:
            app_logger.log_error(e, "save_to_file")
            return False

    @staticmethod
    def load_audio_from_file(file_path: str) -> Optional[np.ndarray]:
        """从WAV文件加载音频数据

        Args:
            file_path: WAV文件路径

        Returns:
            音频数据的numpy数组（float32格式，范围[-1.0, 1.0]），如果失败则返回None

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 文件格式不支持
        """
        try:
            # 检查文件是否存在
            if not Path(file_path).exists():
                raise FileNotFoundError(f"Audio file not found: {file_path}")

            # 打开WAV文件
            with wave.open(file_path, "rb") as wav_file:
                # 获取音频参数
                channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                framerate = wav_file.getframerate()
                n_frames = wav_file.getnframes()

                # 读取音频数据
                audio_bytes = wav_file.readframes(n_frames)

                # 根据采样宽度转换为numpy数组
                if sample_width == 2:  # 16-bit
                    audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
                    # 转换为float32格式 [-1.0, 1.0]
                    audio_data = audio_int16.astype(np.float32) / 32768.0
                elif sample_width == 4:  # 32-bit
                    audio_int32 = np.frombuffer(audio_bytes, dtype=np.int32)
                    audio_data = audio_int32.astype(np.float32) / 2147483648.0
                else:
                    raise ValueError(
                        f"Unsupported sample width: {sample_width} bytes. "
                        f"Only 16-bit and 32-bit WAV files are supported."
                    )

                # 如果是立体声，转换为单声道（取平均）
                if channels == 2:
                    audio_data = audio_data.reshape(-1, 2).mean(axis=1)
                elif channels > 2:
                    # 多声道取第一个声道
                    audio_data = audio_data.reshape(-1, channels)[:, 0]

                app_logger.log_audio_event(
                    "Audio loaded from file",
                    {
                        "file_path": file_path,
                        "duration": len(audio_data) / framerate,
                        "sample_rate": framerate,
                        "channels": channels,
                        "sample_width": sample_width,
                    },
                )

                return audio_data

        except FileNotFoundError:
            app_logger.log_error(
                FileNotFoundError(f"Audio file not found: {file_path}"),
                "load_audio_from_file",
            )
            raise
        except Exception as e:
            app_logger.log_error(e, "load_audio_from_file")
            raise ValueError(f"Failed to load audio file: {str(e)}")

    @property
    def is_recording(self) -> bool:
        """检查是否正在录音"""
        return self._recording

    @property
    def current_device_id(self) -> Optional[int]:
        """当前使用的音频设备ID"""
        return getattr(self, "_device_id", None)

    @property
    def sample_rate(self) -> int:
        """采样率"""
        return self._sample_rate if hasattr(self, "_sample_rate") else 16000

    def cleanup(self) -> None:
        """清理资源 - delegates to LifecycleComponent.stop()"""
        self.stop()
