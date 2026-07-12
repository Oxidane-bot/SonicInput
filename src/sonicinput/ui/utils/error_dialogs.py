"""Error dialog utilities

Provides user-friendly error dialogs with actionable suggestions
"""

from typing import List, Optional

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QMessageBox, QPushButton, QWidget


def show_hotkey_conflict_error(
    parent: Optional[QWidget],
    conflicting_hotkey: str,
    suggestions: List[str],
) -> bool:
    """Show user-friendly hotkey conflict error dialog

    Args:
        parent: Parent widget
        conflicting_hotkey: The hotkey that conflicted
        suggestions: List of suggested alternative hotkeys

    Returns:
        True if the user clicked "Open Settings", False otherwise.
    """
    msg_box = QMessageBox(parent)
    msg_box.setIcon(QMessageBox.Icon.Warning)
    msg_box.setWindowTitle(
        QCoreApplication.translate("ErrorDialogs", "Hotkey Conflict")
    )

    # Build message
    message_lines = [
        QCoreApplication.translate(
            "ErrorDialogs",
            "The hotkey '{hotkey}' is already in use by another application.",
        ).format(hotkey=conflicting_hotkey),
        "",
        QCoreApplication.translate("ErrorDialogs", "Common causes:"),
        QCoreApplication.translate(
            "ErrorDialogs", "- Web browser developer tools (F12 is commonly used)"
        ),
        QCoreApplication.translate(
            "ErrorDialogs",
            "- Another application running with administrator privileges",
        ),
        QCoreApplication.translate(
            "ErrorDialogs", "- Game launchers or recording software"
        ),
        QCoreApplication.translate("ErrorDialogs", "- System shortcuts"),
        "",
        QCoreApplication.translate("ErrorDialogs", "Solutions:"),
        QCoreApplication.translate(
            "ErrorDialogs", "1. Change the hotkey in Settings (recommended)"
        ),
        QCoreApplication.translate(
            "ErrorDialogs",
            "2. Run Sonic Input as administrator (if the conflicting app is admin)",
        ),
        QCoreApplication.translate(
            "ErrorDialogs", "3. Close the conflicting application"
        ),
    ]

    if suggestions:
        message_lines.extend(
            [
                "",
                QCoreApplication.translate(
                    "ErrorDialogs", "Suggested alternative hotkeys:"
                ),
            ]
        )
        for suggestion in suggestions:
            message_lines.append(f"  - {suggestion.upper()}")

    msg_box.setText("\n".join(message_lines))

    # Add buttons
    open_settings_btn = msg_box.addButton(
        QCoreApplication.translate("ErrorDialogs", "Open Settings"),
        QMessageBox.ButtonRole.AcceptRole,
    )
    msg_box.addButton(
        QCoreApplication.translate("ErrorDialogs", "Close"),
        QMessageBox.ButtonRole.RejectRole,
    )

    if isinstance(open_settings_btn, QPushButton):
        msg_box.setDefaultButton(open_settings_btn)

    # Show dialog
    result = msg_box.exec()

    # If user chose to open settings, emit signal or return value
    # (Implementation depends on how settings are opened)
    # For now, we'll just show the dialog
    return result == QMessageBox.ButtonRole.AcceptRole


def show_hotkey_registration_error(
    parent: Optional[QWidget],
    error_message: str,
    recovery_suggestions: Optional[List[str]] = None,
) -> None:
    """Show generic hotkey registration error dialog

    Args:
        parent: Parent widget
        error_message: Error message to display
        recovery_suggestions: Optional list of recovery suggestions
    """
    msg_box = QMessageBox(parent)
    msg_box.setIcon(QMessageBox.Icon.Warning)
    msg_box.setWindowTitle(
        QCoreApplication.translate("ErrorDialogs", "Hotkey Registration Error")
    )

    message = error_message

    if recovery_suggestions:
        message += "\n\n"
        message += QCoreApplication.translate("ErrorDialogs", "Suggestions:")
        for i, suggestion in enumerate(recovery_suggestions, 1):
            message += f"\n{i}. {suggestion}"

    msg_box.setText(message)
    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg_box.exec()


def show_error_with_details(
    parent: Optional[QWidget],
    title: str,
    message: str,
    detailed_text: Optional[str] = None,
) -> None:
    """Show error dialog with optional detailed text

    Args:
        parent: Parent widget
        title: Dialog title
        message: Main error message
        detailed_text: Optional detailed technical information
    """
    msg_box = QMessageBox(parent)
    msg_box.setIcon(QMessageBox.Icon.Critical)
    msg_box.setWindowTitle(title)
    msg_box.setText(message)

    if detailed_text:
        msg_box.setDetailedText(detailed_text)

    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg_box.exec()
