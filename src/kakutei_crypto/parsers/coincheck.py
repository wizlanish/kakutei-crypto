"""Coincheck の取引履歴「様式1」。

増加通貨・減少通貨の組み合わせで取引種別を決める。取引種別の文言には依存しない
（報酬の判定だけに使う）。
"""
from __future__ import annotations

from pathlib import Path

from ..ledger import Entry, parse_decimal
from .common import parse_jst, read_rows

HEADER = {"取引日時", "取引種別", "増加通貨名", "増加数量", "減少通貨名", "減少数量", "約定代金", "手数料通貨", "手数料数量"}

_REWARD_WORDS = ("報酬", "ステーキング", "貸", "配布", "付与", "エアドロップ")


def parse(path: Path) -> list[Entry]:
    entries = []
    for line, row in read_rows(path):
        when = (row.get("取引日時") or "").strip()
        if not when:  # 月末残高などのセクション
            continue
        up, up_qty = row["増加通貨名"].strip().upper(), parse_decimal(row["増加数量"])
        down, down_qty = row["減少通貨名"].strip().upper(), parse_decimal(row["減少数量"])
        fee_qty = parse_decimal(row["手数料数量"])
        kind_text = row["取引種別"].strip()
        common = dict(id=f"coincheck-{path.stem}-{line}", timestamp=parse_jst(when), exchange="coincheck",
                      in_asset=up if up_qty else "", in_qty=up_qty or None,
                      out_asset=down if down_qty else "", out_qty=down_qty or None,
                      fee_asset=row["手数料通貨"].strip().upper() if fee_qty else "",
                      fee_qty=fee_qty or None, source=f"{path.name}#{line}")
        contract = parse_decimal(row["約定代金"])
        if up_qty and down_qty:
            if down == "JPY":
                kind, value = "buy", down_qty
            elif up == "JPY":
                kind, value = "sell", up_qty
            else:
                kind, value = "swap", contract
        elif up_qty:
            reward = any(w in kind_text for w in _REWARD_WORDS)
            kind, value = ("reward", contract) if reward else ("transfer_in", None)
        elif down_qty:
            kind, value = "transfer_out", None
        else:
            raise ValueError(f"{path.name}#{line}: 増加・減少どちらの数量もありません")
        entries.append(Entry(kind=kind, jpy_value=value, **common))
    return entries
