"""音频可视化器"""

from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..utils import app_logger


class AudioVisualizer(QWidget):
    """实时音频波形显示"""

    def __init__(
        self, parent: Optional[QWidget] = None, width: int = 300, height: int = 100
    ):
        super().__init__(parent)

        self.setFixedSize(width, height)
        # 使用私有属性存储尺寸，避免遮蔽 QWidget.width()/height() 方法
        self._width = width
        self._height = height

        # 音频数据缓冲区
        self.audio_buffer = np.zeros(1024)
        self.buffer_size = 1024

        # 显示参数
        self.background_color = QColor(40, 40, 40)
        self.waveform_color = QColor(0, 255, 150)
        self.grid_color = QColor(80, 80, 80)

        # 录音状态
        self.is_recording = False

        # 更新定时器
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update)
        self.update_timer.start(50)  # 20fps更新

        # 动画参数
        self.animation_phase = 0

        app_logger.log_audio_event(
            "Audio visualizer initialized",
            {"width": width, "height": height, "buffer_size": self.buffer_size},
        )

    def update_waveform(self, audio_data: np.ndarray) -> None:
        """更新波形数据"""
        if len(audio_data) == 0:
            return

        try:
            # 重采样到缓冲区大小
            if len(audio_data) != self.buffer_size:
                # 简单的重采样
                indices = np.linspace(
                    0, len(audio_data) - 1, self.buffer_size, dtype=int
                )
                self.audio_buffer = audio_data[indices]
            else:
                self.audio_buffer = audio_data.copy()

            # 标准化到[-1, 1]范围
            max_val = np.max(np.abs(self.audio_buffer))
            if max_val > 0:
                self.audio_buffer = self.audio_buffer / max_val

        except Exception as e:
            app_logger.log_error(e, "update_waveform")

    def show_recording_indicator(self) -> None:
        """显示录音状态"""
        self.is_recording = True
        self.update()

    def hide_recording_indicator(self) -> None:
        """隐藏录音状态"""
        self.is_recording = False
        self.audio_buffer = np.zeros(self.buffer_size)
        self.update()

    def paintEvent(self, event):
        """绘制波形"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 清空背景
        painter.fillRect(self.rect(), self.background_color)

        if not self.is_recording:
            self._draw_idle_state(painter)
        else:
            self._draw_waveform(painter)
            self._draw_recording_indicator(painter)

        # 更新动画相位
        self.animation_phase += 0.1
        if self.animation_phase > 2 * np.pi:
            self.animation_phase = 0

    def _draw_idle_state(self, painter: QPainter) -> None:
        """绘制闲置状态"""
        painter.setPen(QPen(self.grid_color, 1))

        # 绘制中心线
        center_y = self._height // 2
        painter.drawLine(0, center_y, self._width, center_y)

        # 绘制提示文本
        painter.setPen(QPen(QColor(120, 120, 120), 1))
        painter.drawText(
            self.rect(), Qt.AlignmentFlag.AlignCenter, "Press hotkey to start recording"
        )

    def _draw_waveform(self, painter: QPainter) -> None:
        """绘制波形"""
        if len(self.audio_buffer) == 0:
            return

        painter.setPen(QPen(self.waveform_color, 2))

        # 计算波形点
        points = []
        for i in range(len(self.audio_buffer)):
            x = int(i * self._width / len(self.audio_buffer))
            y = int(self._height / 2 - self.audio_buffer[i] * self._height / 3)
            points.append((x, y))

        # 绘制波形线
        for i in range(len(points) - 1):
            painter.drawLine(
                points[i][0], points[i][1], points[i + 1][0], points[i + 1][1]
            )

    def _draw_recording_indicator(self, painter: QPainter) -> None:
        """绘制录音指示器"""
        # 绘制录音点
        size = 8 + 4 * np.sin(self.animation_phase * 2)  # 脉动效果
        # 修复alpha溢出问题：确保透明度在有效范围[0, 255]内
        alpha_raw = 150 + 100 * np.sin(self.animation_phase * 3)
        alpha = int(min(255, max(0, alpha_raw)))  # 边界保护

        color = QColor(255, 50, 50, alpha)
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color, 2))

        # 在左上角绘制录音指示点
        painter.drawEllipse(10, 10, int(size), int(size))

        # 绘制"REC"文本
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.drawText(25, 20, "REC")

    def get_current_level(self) -> float:
        """获取当前音频级别"""
        if len(self.audio_buffer) == 0:
            return 0.0
        return float(np.sqrt(np.mean(self.audio_buffer**2)))

    def set_colors(
        self,
        background: Optional[QColor] = None,
        waveform: Optional[QColor] = None,
        grid: Optional[QColor] = None,
    ) -> None:
        """设置颜色主题"""
        if background:
            self.background_color = background
        if waveform:
            self.waveform_color = waveform
        if grid:
            self.grid_color = grid

        self.update()


class MiniAudioVisualizer(QWidget):
    """迷你音频可视化器（用于系统托盘等）"""

    def __init__(self, parent: Optional[QWidget] = None, size: int = 32):
        super().__init__(parent)

        self.setFixedSize(size, size)
        # 使用私有属性存储尺寸，避免遮蔽 QWidget.size() 方法
        self._size = size

        # 简化的音频数据
        self.level = 0.0
        self.is_recording = False

        # 更新定时器
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update)
        self.update_timer.start(100)  # 10fps更新

        self.animation_phase = 0

    def update_level(self, level: float) -> None:
        """更新音频级别"""
        self.level = max(0.0, min(1.0, level))

    def set_recording(self, recording: bool) -> None:
        """设置录音状态"""
        self.is_recording = recording
        if not recording:
            self.level = 0.0

    def paintEvent(self, event):
        """绘制迷你可视化"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 背景
        painter.fillRect(self.rect(), QColor(40, 40, 40))

        if self.is_recording:
            # 绘制音频级别指示器
            level_height = int(self.level * (self._size - 4))

            # 渐变色表示音频级别
            if self.level < 0.3:
                color = QColor(0, 255, 0)  # 绿色
            elif self.level < 0.7:
                color = QColor(255, 255, 0)  # 黄色
            else:
                color = QColor(255, 0, 0)  # 红色

            painter.setBrush(QBrush(color))
            painter.setPen(QPen(color, 1))

            # 从底部向上绘制级别条
            painter.drawRect(
                2, self._size - 2 - level_height, self._size - 4, level_height
            )
        else:
            # 静态状态
            painter.setPen(QPen(QColor(120, 120, 120), 1))
            painter.drawRect(2, 2, self._size - 4, self._size - 4)

        self.animation_phase += 0.2
