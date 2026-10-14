from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from kakutei_crypto.ledger import Entry, parse_decimal, read_ledger, write_ledger

JST = ZoneInfo("Asia/Tokyo")


def test_parse_decimal_strips_padding_and_thousand_separators():
    assert parse_decimal('  "1,011.12220000" ') == Decimal("1011.1222")
    assert parse_decimal("            10,111,222.00000000") == Decimal("10111222")
    assert parse_decimal("-7.00000000") == Decimal("-7")


def test_parse_decimal_blank_is_none():
    assert parse_decimal("") is None
    assert parse_decimal("   ") is None


def test_ledger_round_trip_preserves_entries_sorted_by_time(tmp_path):
    later = Entry(id="okj-2", timestamp=datetime(2026, 5, 1, 9, 0, tzinfo=JST), exchange="okj",
                  kind="sell", out_asset="BTC", out_qty=Decimal("0.5"), jpy_value=Decimal("5000000"),
                  fee_asset="JPY", fee_qty=Decimal("100"), source="a.csv#3", note="メモ")
    earlier = Entry(id="okj-1", timestamp=datetime(2026, 4, 1, 9, 0, tzinfo=JST), exchange="okj",
                    kind="buy", in_asset="BTC", in_qty=Decimal("1"), out_asset="JPY",
                    out_qty=Decimal("9000000"), jpy_value=Decimal("9000000"), source="a.csv#2")
    path = tmp_path / "ledger.csv"
    write_ledger([later, earlier], path)
    assert read_ledger(path) == [earlier, later]


def test_unknown_kind_is_rejected():
    with pytest.raises(ValueError, match="kind"):
        Entry(id="x", timestamp=datetime(2026, 1, 1, tzinfo=JST), exchange="okj", kind="magic")
