from datetime import datetime
from decimal import Decimal as D
from zoneinfo import ZoneInfo

from kakutei_crypto.check import check
from kakutei_crypto.ledger import Entry

JST = ZoneInfo("Asia/Tokyo")


def entry(id, day, kind, **kw):
    return Entry(id=id, timestamp=datetime(2026, 1, day, tzinfo=JST), exchange="x", kind=kind, **kw)


def levels(issues):
    return {(i.level, i.entry_id) for i in issues}


def test_clean_ledger_has_no_issues():
    entries = [entry("b", 1, "buy", in_asset="BTC", in_qty=D(1), jpy_value=D(100)),
               entry("s", 2, "sell", out_asset="BTC", out_qty=D(1), jpy_value=D(120))]
    assert check(entries) == []


def test_missing_market_value_is_error():
    entries = [entry("r", 1, "reward", in_asset="SOL", in_qty=D(1)),
               entry("b", 2, "buy", in_asset="BTC", in_qty=D(1))]
    assert levels(check(entries)) == {("error", "r"), ("error", "b")}


def test_negative_holding_across_exchanges_is_error_at_the_offending_entry():
    entries = [entry("b", 1, "buy", in_asset="ETH", in_qty=D(1), jpy_value=D(100)),
               entry("o", 2, "sell", out_asset="ETH", out_qty=D(1), jpy_value=D(120),
                     fee_asset="ETH", fee_qty=D("0.01"))]
    issues = check(entries)
    assert levels(issues) == {("error", "o")}
    assert "ETH" in issues[0].message


def test_review_notes_are_warnings():
    entries = [entry("i", 1, "transfer_in", in_asset="HBAR", in_qty=D(5), note="要確認: 入出金内容「付与」"),
               entry("b", 2, "buy", in_asset="BTC", in_qty=D(1), jpy_value=D(1),
                     note="注文履歴には手数料が含まれません")]
    assert levels(check(entries)) == {("warning", "i"), ("warning", "b")}


def test_receive_without_matching_send_is_warning():
    entries = [entry("in", 5, "transfer_in", in_asset="BTC", in_qty=D("0.002"))]
    issues = check(entries)
    assert levels(issues) == {("warning", "in")}
    assert "送付" in issues[0].message


def test_receive_matched_by_send_from_another_exchange_is_clean():
    entries = [entry("b", 1, "buy", in_asset="ETH", in_qty=D(1), jpy_value=D(100)),
               entry("out", 2, "transfer_out", out_asset="ETH", out_qty=D(1), fee_asset="ETH", fee_qty=D("0.01")),
               entry("in", 3, "transfer_in", in_asset="ETH", in_qty=D("0.99"))]
    assert check(entries) == []
