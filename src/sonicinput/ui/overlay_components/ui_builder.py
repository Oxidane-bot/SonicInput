"""UI构建器 - 单一职责：构建RecordingOverlay的UI界面"""

from typing import Any, Dict, List

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...utils import app_logger
from ..overlay import StatusIndicator
from ..styles.modern_styles import overlay_hud_style
from .position_manager import PositionManager


class OverlayUIBuilder:
    """RecordingOverlay UI构建器 - 负责创建所有UI组件

    职责：
    1. 创建Material Design背景框架
    2. 创建状态指示器
    3. 创建音频级别条
    4. 创建时间标签和关闭按钮
    5. 应用样式和阴影效果
    """

    def __init__(self):
        """初始化UI构建器"""
        app_logger.log_audio_event("OverlayUIBuilder initialized", {})

    def build_ui(self, parent: QWidget, stop_recording_callback) -> Dict[str, Any]:
        """构建完整的UI并返回组件字典

        Args:
            parent: 父窗口组件
            stop_recording_callback: 停止录音按钮的回调函数

        Returns:
            包含所有UI组件的字典
        """
        try:
            main_layout = QVBoxLayout()
            main_layout.setContentsMargins(8, 8, 8, 8)
            main_layout.setSpacing(0)

            background_frame = self._create_background_frame()

            frame_layout = QHBoxLayout(background_frame)
            frame_layout.setContentsMargins(14, 10, 12, 10)
            frame_layout.setSpacing(10)

            status_indicator = StatusIndicator(parent)
            frame_layout.addWidget(status_indicator, 0, Qt.AlignmentFlag.AlignCenter)

            text_layout = QVBoxLayout()
            text_layout.setContentsMargins(0, 0, 0, 0)
            text_layout.setSpacing(3)

            title_label = QLabel(
                QCoreApplication.translate("RecordingOverlay", "Recording")
            )
            title_label.setObjectName("overlayTitle")
            text_layout.addWidget(title_label)

            time_label = self._create_time_label()
            text_layout.addWidget(time_label)
            frame_layout.addLayout(text_layout)

            audio_level_bars = self._create_audio_level_bars(frame_layout)

            frame_layout.addStretch()

            stop_button = self._create_stop_button(stop_recording_callback)
            frame_layout.addWidget(stop_button, 0, Qt.AlignmentFlag.AlignCenter)

            main_layout.addWidget(background_frame)

            self._apply_shadow_effect(background_frame)

            self._setup_parent_widget(parent, main_layout)

            # 创建位置管理器
            position_manager = PositionManager(parent, config_service=None)

            app_logger.log_audio_event("UI components created successfully", {})

            return {
                "main_layout": main_layout,
                "background_frame": background_frame,
                "status_indicator": status_indicator,
                "audio_level_bars": audio_level_bars,
                "title_label": title_label,
                "time_label": time_label,
                "close_button": stop_button,
                "stop_button": stop_button,
                "position_manager": position_manager,
                "current_audio_level": 0.0,  # 初始音频级别
            }

        except Exception as e:
            app_logger.log_error(e, "ui_builder_build")
            raise

    def _create_background_frame(self) -> QFrame:
        """创建Material Design背景框架

        Returns:
            配置好的QFrame背景框架
        """
        background_frame = QFrame()
        background_frame.setObjectName("recordingOverlayHud")
        background_frame.setStyleSheet(overlay_hud_style())
        return background_frame

    def _create_audio_level_bars(self, layout: QHBoxLayout) -> List[QLabel]:
        """创建5个音频级别条

        Args:
            layout: 要添加级别条的布局

        Returns:
            音频级别条的列表
        """
        audio_level_bars = []

        for i in range(5):
            bar = QLabel()
            bar.setFixedSize(5, 24)
            bar.setStyleSheet("""
                QLabel {
                    background-color: rgba(92, 102, 128, 110);
                    border-radius: 2px;
                }
            """)
            audio_level_bars.append(bar)
            layout.addWidget(bar)

        return audio_level_bars

    def _create_time_label(self) -> QLabel:
        """创建时间标签

        Returns:
            配置好的时间标签
        """
        time_label = QLabel("00:00")
        time_label.setObjectName("overlayTimer")
        font = time_label.font()
        font.setPointSize(9)
        time_label.setFont(font)
        return time_label

    def _create_stop_button(self, stop_callback) -> QPushButton:
        """创建停止录音按钮

        Args:
            stop_callback: 点击回调函数

        Returns:
            配置好的停止按钮
        """
        stop_button = QPushButton("■")
        stop_button.setObjectName("overlay_stop_button")
        stop_button.setToolTip(
            QCoreApplication.translate("RecordingOverlay", "Stop Recording")
        )
        stop_button.clicked.connect(stop_callback)
        return stop_button

    def _apply_shadow_effect(self, frame: QFrame) -> None:
        """应用Material Design阴影效果

        Args:
            frame: 要应用阴影的框架
        """
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(26)
        shadow.setXOffset(0)
        shadow.setYOffset(6)
        shadow.setColor(QColor(0, 0, 0, 110))
        frame.setGraphicsEffect(shadow)

    def _setup_parent_widget(self, parent: QWidget, layout: QVBoxLayout) -> None:
        """设置父窗口的属性和样式

        Args:
            parent: 父窗口组件
            layout: 主布局
        """
        # 设置布局
        parent.setLayout(layout)

        parent.setFixedSize(300, 64)

        # 确保悬浮窗本身透明背景
        parent.setStyleSheet("""
            RecordingOverlay {
                background: transparent;
            }
        """)
