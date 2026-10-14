"""エンジンと、分数（Fraction）で厳密に書いた参照実装とのランダム突き合わせ。

参照実装は国税庁 FAQ 2-4 の定義をそのまま書いたもので、丸め誤差がない。
年末金額の割り算誤差（I が 1 円ずれる、全量売却後に -1 円になる）はこのテストで見つかった。
エンジンの計算を変えたら必ずこのテストが通ることを確かめる。
"""
import math
import random
from datetime import datetime, timedelta
from decimal import Decimal as D
from fractions import Fraction as Fr
from zoneinfo import ZoneInfo

import pytest

from kakutei_crypto.engine import calculate
from kakutei_crypto.ledger import Entry

JST = ZoneInfo("Asia/Tokyo")
ASSETS = ["BTC", "ETH", "XRP"]


def random_ledger(rng: random.Random) -> list[Entry]:
    t = datetime(2025, 1, 1, tzinfo=JST)
    held = {a: D(0) for a in ASSETS}
    out: list[Entry] = []
    for n in range(rng.randint(1, 60)):
        t += timedelta(hours=rng.randint(1, 400))
        a = rng.choice(ASSETS)
        q = D(rng.randint(1, 5000)) / D(1000)
        v = D(rng.randint(1, 10**7))
        fee = dict(fee_asset="JPY", fee_qty=D(rng.randint(0, 500))) if rng.random() < 0.3 else {}
        kind = rng.choice(["buy", "buy", "sell", "swap", "reward", "transfer", "fork"])
        if kind == "buy":
            out.append(Entry(f"e{n}", t, "x", "buy", in_asset=a, in_qty=q, jpy_value=v, **fee))
            held[a] += q
        elif kind == "reward":
            out.append(Entry(f"e{n}", t, "x", "reward", in_asset=a, in_qty=q, jpy_value=v))
            held[a] += q
        elif kind == "fork":
            out.append(Entry(f"e{n}", t, "x", "fork", in_asset=a, in_qty=q))
            held[a] += q
        elif kind == "sell" and held[a] > 0:
            q = min(q, held[a])
            out.append(Entry(f"e{n}", t, "x", "sell", out_asset=a, out_qty=q, jpy_value=v, **fee))
            held[a] -= q
        elif kind == "swap" and held[a] > 0:
            b = rng.choice([x for x in ASSETS if x != a])
            q = min(q, held[a])
            out.append(Entry(f"e{n}", t, "x", "swap", out_asset=a, out_qty=q, in_asset=b, in_qty=q * 3,
                             jpy_value=v))
            held[a] -= q
            held[b] += q * 3
        elif kind == "transfer" and held[a] > D("0.01"):
            q = min(q, held[a] - D("0.001"))
            out.append(Entry(f"e{n}", t, "x", "transfer_out", out_asset=a, out_qty=q,
                             fee_asset=a, fee_qty=D("0.001")))
            held[a] -= D("0.001")
    return out


def reference_income(entries: list[Entry], method: str) -> dict[int, Fr]:
    """FAQ 2-4 の定義どおりの年別所得。すべて Fraction で計算する。"""
    if not entries:
        return {}
    years = sorted({e.timestamp.year for e in entries})
    carry = {a: (Fr(0), Fr(0)) for a in ASSETS}
    result: dict[int, Fr] = {}
    for year in range(years[0], years[-1] + 1):
        start = dict(carry)
        acq = {a: [Fr(0), Fr(0)] for a in ASSETS}
        disposed = {a: Fr(0) for a in ASSETS}
        qty = {a: start[a][0] for a in ASSETS}
        book = {a: start[a][1] for a in ASSETS}
        proceeds = rewards = fees = Fr(0)

        def acquire(a, q, cost):
            acq[a][0] += Fr(q)
            acq[a][1] += Fr(cost)
            qty[a] += Fr(q)
            book[a] += Fr(cost)

        def dispose(a, q, value):
            nonlocal proceeds
            q = Fr(q)
            disposed[a] += q
            proceeds += Fr(value)
            book[a] -= book[a] * q / qty[a]
            qty[a] -= q

        for e in (e for e in entries if e.timestamp.year == year):
            jpy_fee = Fr(e.fee_qty) if e.fee_asset == "JPY" and e.fee_qty else Fr(0)
            if e.kind == "buy":
                acquire(e.in_asset, e.in_qty, Fr(e.jpy_value) + jpy_fee)
            elif e.kind == "reward":
                acquire(e.in_asset, e.in_qty, e.jpy_value)
                rewards += Fr(e.jpy_value)
            elif e.kind == "fork":
                acquire(e.in_asset, e.in_qty, 0)
            elif e.kind == "sell":
                dispose(e.out_asset, e.out_qty, e.jpy_value)
                fees += jpy_fee
            elif e.kind == "swap":
                dispose(e.out_asset, e.out_qty, e.jpy_value)
                acquire(e.in_asset, e.in_qty, e.jpy_value)
            elif e.kind == "transfer_out" and e.fee_qty:
                dispose(e.fee_asset, e.fee_qty, 0)

        cost_of_sales = Fr(0)
        for a in ASSETS:
            q0, b0 = start[a]
            end_qty = q0 + acq[a][0] - disposed[a]
            if method == "total":
                pool = q0 + acq[a][0]
                end_value = Fr(math.floor((b0 + acq[a][1]) * end_qty / pool)) if pool else Fr(0)
            else:
                end_value = Fr(math.floor(book[a])) if end_qty else Fr(0)
            cost_of_sales += b0 + acq[a][1] - end_value
            carry[a] = (end_qty, end_value)
        result[year] = proceeds + rewards - cost_of_sales - fees
    return result


@pytest.mark.parametrize("method", ["total", "moving"])
@pytest.mark.parametrize("seed", range(4))
def test_engine_matches_exact_reference_to_the_yen(method, seed):
    rng = random.Random(seed)
    for _ in range(150):
        entries = random_ledger(rng)
        expected = reference_income(entries, method)
        got = {r.year: r.income for r in calculate(entries, method)[0]}
        for year, income in expected.items():
            assert Fr(got[year]) == income, (method, year, [vars(e) for e in entries])
