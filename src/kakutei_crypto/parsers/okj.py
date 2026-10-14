"""OKJ（オーケーコイン・ジャパン）の「履歴データ（CSV）」。"""
from __future__ import annotations

from pathlib import Path

from ..ledger import Entry, parse_decimal
from .common import parse_jst, read_rows

ORDERS_HEADER = {"注文id", "注文日時", "注文銘柄", "売買", "約定数量", "約定代金", "ステータス"}
TRANSFERS_HEADER = {"入出金id", "日時", "資産", "入出金内容", "数量", "手数料"}

_KNOWN_TRANSFER = {"出金・出庫", "入金・入庫"}
_NO_FEE_NOTE = "注文履歴には手数料が含まれません。取引口座履歴での確認を推奨"


def parse_orders(path: Path) -> list[Entry]:
    entries = []
    for line, row in read_rows(path):
        filled = parse_decimal(row["約定数量"])
        if not filled:
            continue
        base, _, quote = row["注文銘柄"].strip().partition("/")
        amount = parse_decimal(row["約定代金"])
        common = dict(id=f"okj-order-{row['注文id'].strip()}", timestamp=parse_jst(row["注文日時"]),
                      exchange="okj", jpy_value=amount, source=f"{path.name}#{line}", note=_NO_FEE_NOTE)
        if quote != "JPY":
            raise ValueError(f"{path.name}#{line}: 円建て以外の銘柄 {row['注文銘柄']} は未対応です")
        side = row["売買"].strip()
        if side == "購入":
            entries.append(Entry(kind="buy", in_asset=base, in_qty=filled, out_asset="JPY",
                                 out_qty=amount, **common))
        elif side == "売却":
            entries.append(Entry(kind="sell", out_asset=base, out_qty=filled, in_asset="JPY",
                                 in_qty=amount, **common))
        else:
            raise ValueError(f"{path.name}#{line}: 未知の売買区分 {side!r}")
    return entries


def parse_transfers(path: Path) -> list[Entry]:
    entries = []
    for line, row in read_rows(path):
        asset = row["資産"].strip()
        qty = parse_decimal(row["数量"])
        if asset == "JPY" or not qty:
            continue
        fee = parse_decimal(row["手数料"])
        content = row["入出金内容"].strip()
        note = "" if content in _KNOWN_TRANSFER else f"要確認: 入出金内容「{content}」。報酬なら kind=reward と jpy_value を設定"
        common = dict(id=f"okj-io-{row['入出金id'].strip()}", timestamp=parse_jst(row["日時"]),
                      exchange="okj", fee_asset=asset if fee else "", fee_qty=abs(fee) if fee else None,
                      source=f"{path.name}#{line}", note=note)
        if qty < 0:
            entries.append(Entry(kind="transfer_out", out_asset=asset, out_qty=-qty, **common))
        else:
            entries.append(Entry(kind="transfer_in", in_asset=asset, in_qty=qty, **common))
    return entries
