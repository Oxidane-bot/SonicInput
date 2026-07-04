"""音频处理器"""

import numpy as np
from samplerate import converters as sr_converters

from ..utils import AudioRecordingError, app_logger


class AudioProcessor:
    """音频预处理和格式转换"""

    def __init__(self):
        pass

    def resample_to_16khz(
        self, audio_data: np.ndarray, original_rate: int = 44100
    ) -> np.ndarray:
        """重采样到16kHz"""
        if original_rate == 16000:
            return audio_data

        try:
            # 计算重采样比例
            resample_ratio = 16000 / original_rate

            # 性能优化：使用更高效的重采样方法
            if abs(resample_ratio - 1.0) < 0.01:  # 如果采样率差异很小，跳过重采样
                app_logger.log_audio_event(
                    "Audio resampling skipped (rate too similar)",
                    {
                        "original_rate": original_rate,
                        "target_rate": 16000,
                        "ratio_diff": abs(resample_ratio - 1.0),
                    },
                )
                return audio_data.astype(np.float32)

            # 使用samplerate的高质量重采样，保持内存效率优化
            try:
                # 对于大型音频，分块处理以减少内存使用
                if len(audio_data) > 480000:  # 30秒以上音频分块处理
                    resampled = self._resample_large_audio(
                        audio_data, original_rate, 16000
                    )
                else:
                    # 小音频直接处理
                    resampled = sr_converters.resample(
                        audio_data.astype(np.float32),
                        resample_ratio,
                        converter_type="sinc_best",
                    )

                app_logger.log_audio_event(
                    "Audio resampled efficiently",
                    {
                        "original_rate": original_rate,
                        "target_rate": 16000,
                        "original_length": len(audio_data),
                        "new_length": len(resampled),
                        "method": "chunked" if len(audio_data) > 480000 else "direct",
                    },
                )
            except (MemoryError, ValueError) as exc:
                # 内存不足或重采样失败时，使用更简单的方法
                app_logger.warning(
                    "High-quality resampling failed, using linear fallback",
                    context={"error": str(exc)},
                )
                resampled = self._resample_linear(audio_data, resample_ratio)

            return resampled.astype(np.float32)

        except Exception as e:
            raise AudioRecordingError(f"Failed to resample audio: {e}")

    def _resample_large_audio(
        self,
        audio_data: np.ndarray,
        original_rate: int,
        target_rate: int,
        chunk_size: int = 240000,
    ) -> np.ndarray:
        """分块重采样大型音频，减少内存使用

        Args:
            audio_data: 原始音频数据
            original_rate: 原始采样率
            target_rate: 目标采样率
            chunk_size: 每块的样本数（默认15秒）

        Returns:
            重采样后的音频数据
        """

        resampled_chunks = []
        resample_ratio = target_rate / original_rate

        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i : i + chunk_size]

            # 重采样当前块
            resampled_chunk = sr_converters.resample(
                chunk.astype(np.float32),
                resample_ratio,
                converter_type="sinc_best",
            )
            resampled_chunks.append(resampled_chunk)

            # 释放内存
            del chunk, resampled_chunk

        # 连接所有重采样后的块
        return np.concatenate(resampled_chunks, axis=0)

    def _resample_linear(
        self, audio_data: np.ndarray, resample_ratio: float
    ) -> np.ndarray:
        """线性插值重采样（降级路径）。"""
        if audio_data.ndim == 1:
            original_length = len(audio_data)
            if original_length == 0:
                return audio_data
            target_length = int(original_length * resample_ratio)
            x_old = np.linspace(0.0, 1.0, original_length, endpoint=False)
            x_new = np.linspace(0.0, 1.0, target_length, endpoint=False)
            return np.interp(x_new, x_old, audio_data).astype(np.float32)

        channels = []
        for channel_idx in range(audio_data.shape[1]):
            channel = audio_data[:, channel_idx]
            channels.append(self._resample_linear(channel, resample_ratio))
        return np.stack(channels, axis=1)

    def normalize_audio(
        self, audio_data: np.ndarray, target_level: float = 0.8
    ) -> np.ndarray:
        """音频标准化"""
        try:
            if len(audio_data) == 0:
                return audio_data

            # 计算RMS
            rms = np.sqrt(np.mean(audio_data**2))

            if rms > 0:
                # 计算增益
                gain = target_level / rms
                # 限制增益避免过度放大
                gain = min(gain, 10.0)
                normalized = audio_data * gain

                # 防止削波
                max_val = np.max(np.abs(normalized))
                if max_val > 1.0:
                    normalized = normalized / max_val

                app_logger.log_audio_event(
                    "Audio normalized",
                    {
                        "original_rms": float(rms),
                        "gain": float(gain),
                        "final_max": float(np.max(np.abs(normalized))),
                    },
                )

                return normalized.astype(np.float32)
            else:
                return audio_data

        except Exception as e:
            raise AudioRecordingError(f"Failed to normalize audio: {e}")

    def remove_silence(
        self,
        audio_data: np.ndarray,
        threshold: float = 0.01,
        min_silence_duration: float = 0.5,
        sample_rate: int = 16000,
    ) -> np.ndarray:
        """Remove silence segments from audio using energy-based VAD

        Implements simple Voice Activity Detection (VAD) using frame-level
        RMS energy thresholding. Segments below threshold for more than
        min_silence_duration are removed.

        Args:
            audio_data: Input audio samples (float32, range [-1.0, 1.0])
            threshold: RMS energy threshold for silence (default: 0.01 = very quiet)
            min_silence_duration: Minimum silence length to remove in seconds (default: 0.5s)
            sample_rate: Audio sample rate in Hz (default: 16000)

        Returns:
            Trimmed audio with silence removed. Returns original audio if:
            - Input is empty
            - No voice segments detected
            - Error during processing

        Algorithm:
            1. Split audio into 25ms frames with 10ms hop (50% overlap)
            2. Calculate RMS energy for each frame: sqrt(mean(frame^2))
            3. Mark frames above threshold as "voice"
            4. Find contiguous voice segments
            5. Merge segments and remove gaps >min_silence_duration
            6. Concatenate voice segments into output

        Performance:
            - O(n) time complexity where n = audio samples
            - Frame processing: (len(audio) / hop_length) iterations
            - Memory: O(n) for storing frames and segments

        Example:
            >>> # Remove silence longer than 0.5 seconds
            >>> audio = np.random.randn(48000).astype(np.float32)
            >>> trimmed = processor.remove_silence(audio, threshold=0.01)
            >>> reduction = 100 * (1 - len(trimmed) / len(audio))
            >>> print(f"Reduced audio by {reduction:.1f}%")

        Note:
            This is a simple energy-based VAD. For better results, consider
            using WebRTC VAD or other ML-based voice detection methods.
            The algorithm may fail to detect very quiet speech or remove
            breathing sounds if threshold is too high.
        """
        try:
            if len(audio_data) == 0:
                return audio_data

            # 计算每个样本的能量
            frame_length = int(0.025 * sample_rate)  # 25ms frames
            hop_length = int(0.01 * sample_rate)  # 10ms hop

            frames = []
            for i in range(0, len(audio_data) - frame_length, hop_length):
                frame = audio_data[i : i + frame_length]
                energy = np.sqrt(np.mean(frame**2))
                frames.append(energy > threshold)

            # 找到语音段
            voice_frames = np.array(frames)
            min_silence_frames = int(min_silence_duration / (hop_length / sample_rate))

            # 简单的语音活动检测
            voice_segments = []
            start = None

            for i, is_voice in enumerate(voice_frames):
                if is_voice and start is None:
                    start = i
                elif not is_voice and start is not None:
                    if i - start > min_silence_frames:
                        voice_segments.append((start * hop_length, i * hop_length))
                    start = None

            # 如果录音结束时还在说话
            if start is not None:
                voice_segments.append((start * hop_length, len(audio_data)))

            # 合并语音段
            if voice_segments:
                result: list[float] = []
                for start_idx, end_idx in voice_segments:
                    result.extend(audio_data[start_idx:end_idx])

                trimmed = np.array(result, dtype=np.float32)

                app_logger.log_audio_event(
                    "Silence removed",
                    {
                        "original_length": len(audio_data),
                        "trimmed_length": len(trimmed),
                        "voice_segments": len(voice_segments),
                    },
                )

                return trimmed
            else:
                # 没有检测到语音，返回原始音频
                return audio_data

        except Exception as e:
            app_logger.log_error(e, "remove_silence")
            return audio_data  # 发生错误时返回原始音频

    def apply_noise_reduction(self, audio_data: np.ndarray) -> np.ndarray:
        """简单的噪声减少"""
        try:
            if len(audio_data) == 0:
                return audio_data

            # 轻量高通滤波器去除低频噪音
            filtered = self._high_pass_filter(
                audio_data, cutoff=80.0, sample_rate=16000
            )

            app_logger.log_audio_event(
                "Noise reduction applied",
                {"original_length": len(audio_data), "filtered_length": len(filtered)},
            )

            return filtered.astype(np.float32)

        except Exception as e:
            app_logger.log_error(e, "apply_noise_reduction")
            return audio_data  # 发生错误时返回原始音频

    def _high_pass_filter(
        self, audio_data: np.ndarray, cutoff: float, sample_rate: int
    ) -> np.ndarray:
        """Lightweight one-pole high-pass filter."""
        if audio_data.size == 0:
            return audio_data

        dt = 1.0 / sample_rate
        rc = 1.0 / (2 * np.pi * cutoff)
        alpha = rc / (rc + dt)

        if audio_data.ndim == 1:
            output = np.empty_like(audio_data, dtype=np.float32)
            output[0] = audio_data[0]
            prev_output = output[0]
            prev_input = audio_data[0]
            for idx in range(1, len(audio_data)):
                current = audio_data[idx]
                prev_output = alpha * (prev_output + current - prev_input)
                output[idx] = prev_output
                prev_input = current
            return output

        channels = []
        for channel_idx in range(audio_data.shape[1]):
            channel = audio_data[:, channel_idx]
            channels.append(self._high_pass_filter(channel, cutoff, sample_rate))
        return np.stack(channels, axis=1)

    def convert_to_whisper_format(
        self,
        audio_data: np.ndarray,
        sample_rate: int = 16000,
        remove_silence: bool = False,
    ) -> np.ndarray:
        """转换为Whisper所需的格式"""
        try:
            # Whisper期望16kHz, float32, 单声道, 范围[-1, 1]
            processed = audio_data.copy()

            # 确保是float32
            if processed.dtype != np.float32:
                processed = processed.astype(np.float32)

            # 确保在正确范围内
            if np.max(np.abs(processed)) > 1.0:
                processed = processed / np.max(np.abs(processed))

            # Apply audio processing pipeline
            processed = self.normalize_audio(processed)
            processed = self.apply_noise_reduction(processed)

            # Only remove silence if explicitly requested (disabled by default)
            if remove_silence:
                processed = self.remove_silence(processed, sample_rate=sample_rate)

            app_logger.log_audio_event(
                "Audio converted for Whisper",
                {
                    "final_length": len(processed),
                    "final_duration": len(processed) / sample_rate,
                    "final_range": [float(np.min(processed)), float(np.max(processed))],
                },
            )

            return processed

        except Exception as e:
            raise AudioRecordingError(f"Failed to convert audio for Whisper: {e}")

    def get_audio_statistics(
        self, audio_data: np.ndarray, sample_rate: int = 16000
    ) -> dict:
        """获取音频统计信息"""
        if len(audio_data) == 0:
            return {}

        return {
            "duration": len(audio_data) / sample_rate,
            "sample_count": len(audio_data),
            "sample_rate": sample_rate,
            "rms": float(np.sqrt(np.mean(audio_data**2))),
            "peak": float(np.max(np.abs(audio_data))),
            "zero_crossings": int(np.sum(np.diff(np.signbit(audio_data)))),
            "mean": float(np.mean(audio_data)),
            "std": float(np.std(audio_data)),
        }
