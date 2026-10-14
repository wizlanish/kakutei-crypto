"""パーサーのテスト。固定データは実ファイルと同じヘッダー・書式で作った合成データ。"""
from decimal import Decimal as D
from pathlib import Path

import pytest

from kakutei_crypto.parsers import UnknownFormat, detect, parse_file

FIX = Path(__file__).parent / "fixtures"


def by_id(entries):
    return {e.id: e for e in entries}


def test_detects_each_format_by_header():
    assert detect(FIX / "okj_orders.csv") == "okj_orders"
    assert detect(FIX / "okj_transfers.csv") == "okj_transfers"
    assert detect(FIX / "coincheck_youshiki1.csv") == "coincheck_youshiki1"


def test_unknown_format_raises(tmp_path):
    path = tmp_path / "mystery.csv"
    path.write_text("date,amount\n2026-01-01,1\n", encoding="utf-8")
    with pytest.raises(UnknownFormat):
        parse_file(path)


def test_okj_orders_parses_filled_orders_and_skips_unfilled():
    entries = by_id(parse_file(FIX / "okj_orders.csv"))
    assert set(entries) == {"okj-order-900000000000000001", "okj-order-900000000000000002"}

    bought = entries["okj-order-900000000000000001"]
    assert bought.kind == "buy"
    assert (bought.in_asset, bought.in_qty) == ("BTC", D("0.1"))
    assert (bought.out_asset, bought.out_qty, bought.jpy_value) == ("JPY", D("1000000"), D("1000000"))
    assert bought.timestamp.isoformat() == "2026-03-16T15:37:34+09:00"
    assert "手数料" in bought.note
    assert bought.source == "okj_orders.csv#4"

    sold = entries["okj-order-900000000000000002"]
    assert sold.kind == "sell"
    assert (sold.out_asset, sold.out_qty, sold.jpy_value) == ("BTC", D("0.05"), D("550000"))


def test_okj_transfers_maps_sign_to_direction_and_skips_jpy():
    entries = by_id(parse_file(FIX / "okj_transfers.csv"))
    assert "okj-io-80000000" not in entries  # JPY 入金は対象外

    out = entries["okj-io-80000003"]
    assert out.kind == "transfer_out"
    assert (out.out_asset, out.out_qty) == ("HBAR", D("33.9"))
    assert (out.fee_asset, out.fee_qty) == ("HBAR", D("7"))

    deposit = entries["okj-io-80000001"]
    assert deposit.kind == "transfer_in"
    assert deposit.fee_qty is None


def test_okj_transfers_flags_unfamiliar_content_for_review():
    campaign = by_id(parse_file(FIX / "okj_transfers.csv"))["okj-io-80000002"]
    assert campaign.kind == "transfer_in"
    assert "要確認" in campaign.note and "キャンペーン付与" in campaign.note


def test_coincheck_youshiki1_classifies_by_increase_and_decrease():
    entries = parse_file(FIX / "coincheck_youshiki1.csv")
    assert [e.kind for e in entries] == ["buy", "swap", "reward", "transfer_out", "transfer_in", "sell"]
    buy, swap, reward, send, receive, sell = entries

    assert (buy.in_asset, buy.in_qty, buy.jpy_value) == ("BTC", D("0.01"), D("100000"))
    assert (swap.out_asset, swap.out_qty, swap.in_asset, swap.in_qty) == ("BTC", D("0.005"), "ETH", D("0.2"))
    assert swap.jpy_value == D("60000")
    assert (reward.in_asset, reward.jpy_value) == ("ETH", D("300"))
    assert (send.out_asset, send.fee_asset, send.fee_qty) == ("ETH", "ETH", D("0.002"))
    assert (sell.jpy_value, sell.fee_asset, sell.fee_qty) == (D("51000"), "JPY", D("10"))
    assert buy.fee_qty is None  # 手数料 0 は記録しない
    assert buy.source.endswith("#2")
