from pathlib import Path

import pytest

from sonicinput.core.services.storage.history_storage_service import (
    HistoryStorageService,
)


class _DummyConfigService:
    def get_setting(self, _key, default=None):
        return default


class _FakeCursor:
    def __init__(self):
        self.query = ""
        self.params = ()

    def execute(self, query, params):
        self.query = query
        self.params = params

    def fetchall(self):
        return []


class _FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


@pytest.mark.parametrize(
    ("order_by", "expected_order_clause"),
    [
        ("timestamp DESC", "ORDER BY timestamp DESC"),
        ("duration ASC", "ORDER BY duration ASC"),
        ("Timestamp asc", "ORDER BY timestamp ASC"),
    ],
)
def test_get_records_uses_whitelisted_order_clause(
    order_by: str, expected_order_clause: str
) -> None:
    service = HistoryStorageService(_DummyConfigService())
    service._db_path = Path("dummy.db")
    fake_cursor = _FakeCursor()
    service._get_connection = lambda: _FakeConnection(fake_cursor)

    records = service.get_records(limit=5, offset=3, order_by=order_by)

    assert records == []
    assert expected_order_clause in fake_cursor.query
    assert fake_cursor.params == (5, 3)


def test_get_records_invalid_order_by_falls_back_to_default() -> None:
    service = HistoryStorageService(_DummyConfigService())
    service._db_path = Path("dummy.db")
    fake_cursor = _FakeCursor()
    service._get_connection = lambda: _FakeConnection(fake_cursor)

    service.get_records(order_by="timestamp DESC; DROP TABLE history_records")

    assert "ORDER BY timestamp DESC" in fake_cursor.query
