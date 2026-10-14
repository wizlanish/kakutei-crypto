"""計算エンジンのテスト。数値は国税庁「暗号資産等に関する税務上の取扱いについて（FAQ）」の計算例。"""
from datetime import datetime
from decimal import Decimal as D
from zoneinfo import ZoneInfo

import pytest

from kakutei_crypto.engine import LedgerError, calculate
from kakutei_crypto.ledger import Entry

JST = ZoneInfo("Asia/Tokyo")
_seq = iter(range(1, 10_000))


def e(date, kind, *, ex="A", **kw):
    y, m, d = date
    return Entry(id=f"t-{next(_seq)}", timestamp=datetime(y, m, d, 12, 0, tzinfo=JST),
                 exchange=ex, kind=kind, **kw)


def buy(date, asset, qty, jpy, **kw):
    return e(date, "buy", in_asset=asset, in_qty=D(qty), out_asset="JPY", out_qty=D(jpy),
             jpy_value=D(jpy), **kw)


def sell(date, asset, qty, jpy, **kw):
    return e(date, "sell", out_asset=asset, out_qty=D(qty), in_asset="JPY", in_qty=D(jpy),
             jpy_value=D(jpy), **kw)


def faq_2_4(ex_first="A", ex_second="A"):
    """FAQ 2-4：同じ年に BTC を数回売買した例。"""
    return [
        buy((2026, 3, 1), "BTC", "4", "1845000", ex=ex_first),
        buy((2026, 6, 20), "BTC", "2", "1650000", ex=ex_second),
        sell((2026, 7, 10), "BTC", "2", "2400000", ex=ex_second),
        buy((2026, 9, 15), "BTC", "0.5", "542800", ex=ex_first),
        sell((2026, 11, 30), "BTC", "3", "2895000", ex=ex_first),
    ]


def only_year(results, year=2026):
    [r] = [r for r in results if r.year == year]
    return r


def test_faq_2_4_total_average_method():
    results, _ = calculate(faq_2_4(), method="total")
    btc = only_year(results).assets["BTC"]
    assert (btc.C, btc.D) == (D("6.5"), D("4037800"))
    assert btc.E == D("621200")
    assert (btc.F, btc.H) == (D("5"), D("1.5"))
    assert btc.I == D("931800")
    assert btc.G == D("3106000")


def test_faq_2_4_moving_average_method():
    results, _ = calculate(faq_2_4(), method="moving")
    btc = only_year(results).assets["BTC"]
    assert btc.E == D("638400")
    assert btc.I == D("957600")
    assert btc.G == D("3080200")


def test_faq_2_8_two_exchanges_are_pooled_per_asset():
    results, _ = calculate(faq_2_4(ex_first="A取引所", ex_second="B取引所"), method="total")
    year = only_year(results)
    assert year.proceeds == D("5295000")
    assert year.cost_of_sales == D("3106000")
    assert year.income == D("2189000")


def test_faq_1_3_swap_disposes_at_market_value_and_acquires_at_same_value():
    entries = [
        buy((2026, 4, 2), "BTC", "4", "4000000"),
        e((2026, 11, 2), "swap", out_asset="BTC", out_qty=D("1"), in_asset="XRP", in_qty=D("40"),
          jpy_value=D("1200000")),
    ]
    year = only_year(calculate(entries, method="total")[0])
    assert year.income == D("200000")
    assert year.assets["XRP"].D == D("1200000")
    assert year.assets["XRP"].H == D("40")


def test_faq_1_5_purchase_fee_is_added_to_acquisition_cost():
    entries = [buy((2026, 10, 2), "BTC", "2", "2000000", fee_asset="JPY", fee_qty=D("550"))]
    year = only_year(calculate(entries, method="total")[0])
    assert year.assets["BTC"].D == D("2000550")
    assert year.fee_expense == 0


def test_sell_fee_in_jpy_is_necessary_expense():
    entries = [buy((2026, 1, 5), "BTC", "1", "1000000"),
               sell((2026, 2, 5), "BTC", "1", "1200000", fee_asset="JPY", fee_qty=D("300"))]
    year = only_year(calculate(entries, method="total")[0])
    assert year.fee_expense == D("300")
    assert year.income == D("199700")


def test_fee_taken_from_purchased_coin_reduces_quantity_not_cost():
    entries = [buy((2026, 1, 5), "BTC", "1", "10000000", fee_asset="BTC", fee_qty=D("0.001"))]
    btc = only_year(calculate(entries, method="total")[0]).assets["BTC"]
    assert (btc.C, btc.D) == (D("0.999"), D("10000000"))


def test_faq_1_7_reward_is_income_at_market_value_and_acquired_at_same_value():
    entries = [e((2026, 5, 1), "reward", in_asset="SOL", in_qty=D("10"), jpy_value=D("20000"))]
    year = only_year(calculate(entries, method="total")[0])
    assert year.reward_income == D("20000")
    assert year.assets["SOL"].D == D("20000")
    assert year.income == D("20000")


def test_faq_1_6_fork_is_acquired_at_zero_cost():
    entries = [e((2026, 5, 1), "fork", in_asset="BCH", in_qty=D("1"))]
    year = only_year(calculate(entries, method="total")[0])
    assert year.assets["BCH"].D == 0
    assert year.income == 0


def test_crypto_paid_transfer_fee_is_disposed_with_zero_proceeds():
    entries = [buy((2026, 10, 1), "HBAR", "100", "10000"),
               e((2026, 10, 7), "transfer_out", out_asset="HBAR", out_qty=D("30"),
                 fee_asset="HBAR", fee_qty=D("7"))]
    year = only_year(calculate(entries, method="total")[0])
    hbar = year.assets["HBAR"]
    assert hbar.H == D("93")
    assert hbar.G == D("700")
    assert year.income == D("-700")


def test_self_transfer_between_exchanges_has_no_effect():
    entries = [buy((2026, 1, 1), "ETH", "1", "500000", ex="A"),
               e((2026, 2, 1), "transfer_out", ex="A", out_asset="ETH", out_qty=D("1")),
               e((2026, 2, 1), "transfer_in", ex="B", in_asset="ETH", in_qty=D("1")),
               sell((2026, 3, 1), "ETH", "1", "600000", ex="B")]
    year = only_year(calculate(entries, method="total")[0])
    assert year.income == D("100000")


def test_year_end_holding_carries_into_next_year_opening():
    entries = [buy((2025, 6, 1), "BTC", "1", "1000000"),
               sell((2026, 3, 1), "BTC", "0.5", "600000")]
    results, _ = calculate(entries, method="total")
    y2025, y2026 = only_year(results, 2025), only_year(results, 2026)
    assert (y2026.assets["BTC"].A, y2026.assets["BTC"].B) == (y2025.assets["BTC"].H, y2025.assets["BTC"].I)
    assert y2026.income == D("100000")


def test_opening_entry_sets_initial_holding_at_book_value():
    entries = [e((2026, 1, 1), "opening", in_asset="ETH", in_qty=D("2"), jpy_value=D("600000")),
               sell((2026, 3, 1), "ETH", "1", "400000")]
    year = only_year(calculate(entries, method="total")[0])
    assert year.income == D("100000")


def test_total_method_rounds_year_end_value_down_and_keeps_identity():
    entries = [buy((2026, 1, 1), "ETH", "3", "1000000"), sell((2026, 2, 1), "ETH", "1", "400000")]
    eth = only_year(calculate(entries, method="total")[0]).assets["ETH"]
    assert eth.I == D("666666")
    assert eth.G == D("333334")
    assert eth.B + eth.D - eth.I == eth.G


def test_selling_more_than_held_raises_ledger_error_naming_the_entry():
    entries = [sell((2026, 1, 1), "BTC", "1", "1000000")]
    with pytest.raises(LedgerError, match=entries[0].id):
        calculate(entries, method="total")


def test_swap_without_market_value_raises_ledger_error():
    entries = [buy((2026, 1, 1), "BTC", "1", "1000000"),
               e((2026, 2, 1), "swap", out_asset="BTC", out_qty=D("1"), in_asset="XRP", in_qty=D("40"))]
    with pytest.raises(LedgerError, match="jpy_value"):
        calculate(entries, method="total")


def test_movements_record_every_acquisition_and_disposal():
    _, movements = calculate(faq_2_4(), method="total")
    kinds = [(m.kind, m.qty) for m in movements]
    assert kinds == [("acquire", D("4")), ("acquire", D("2")), ("dispose", D("2")),
                     ("acquire", D("0.5")), ("dispose", D("3"))]
