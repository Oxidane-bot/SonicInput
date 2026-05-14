"""Formatting helpers for Fluent history UI surfaces."""

from typing import Any

from PySide6.QtCore import QCoreApplication


def diagnostics_collected(record: Any) -> bool:
    return bool(getattr(record, "diagnostics_collected", False))


def format_mode_for_table(record: Any) -> str:
    if not diagnostics_collected(record):
        return QCoreApplication.translate("HistoryTab", "Legacy")
    return str(getattr(record, "streaming_mode", "unknown") or "unknown")


def format_transcribe_for_table(record: Any) -> str:
    if not diagnostics_collected(record):
        return QCoreApplication.translate("HistoryTab", "Legacy")
    seconds = float(getattr(record, "transcription_duration", 0.0) or 0.0)
    return f"{seconds:.2f}s"


def format_fallback_for_table(record: Any) -> str:
    if not diagnostics_collected(record):
        return QCoreApplication.translate("HistoryTab", "Legacy")
    used_fallback = bool(getattr(record, "used_fallback", False))
    if not used_fallback:
        return QCoreApplication.translate("HistoryTab", "No")
    fallback_type = str(getattr(record, "fallback_type", "unknown") or "unknown")
    return QCoreApplication.translate("HistoryTab", "Yes ({type})").format(
        type=fallback_type
    )


def build_diagnostic_tooltip(record: Any) -> str:
    diagnostics_label = (
        QCoreApplication.translate("HistoryTab", "Captured")
        if diagnostics_collected(record)
        else QCoreApplication.translate("HistoryTab", "Legacy defaults")
    )
    fallback_reason = getattr(
        record, "fallback_reason", None
    ) or QCoreApplication.translate("HistoryTab", "None")
    timestamp = getattr(record, "timestamp", None)
    display_time = (
        timestamp.strftime("%Y-%m-%d %H:%M:%S")
        if hasattr(timestamp, "strftime")
        else ""
    )
    provider = getattr(record, "transcription_provider", None) or "N/A"
    return (
        f"{display_time}\n"
        f"Provider: {provider}\n"
        f"Diagnostics: {diagnostics_label}\n"
        f"Mode: {format_mode_for_table(record)}\n"
        f"Transcribe: {format_transcribe_for_table(record)}\n"
        f"Fallback: {format_fallback_for_table(record)}\n"
        f"Fallback Reason: {fallback_reason}"
    )


def get_status_display(status: str) -> str:
    status_map = {
        "success": QCoreApplication.translate("HistoryTab", "Success"),
        "failed": QCoreApplication.translate("HistoryTab", "Failed"),
        "skipped": QCoreApplication.translate("HistoryTab", "Skipped"),
        "pending": QCoreApplication.translate("HistoryTab", "Pending"),
    }
    return status_map.get(status, QCoreApplication.translate("HistoryTab", "Unknown"))


def get_ai_status_display(record: Any) -> str:
    return get_status_display(str(getattr(record, "ai_status", "") or ""))
