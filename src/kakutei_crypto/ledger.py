"""統一台帳（ledger.csv）。

Coincheck の「様式1」に倣い、すべての取引を「何が増え、何が減ったか」で表す。
台帳より後ろの処理（check / engine / report）はこの形だけを扱う。
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, fields
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

KINDS = ("buy", "sell", "swap", "reward", "fork", "transfer_in", "transfer_out", "opening")

COLUMNS = ("id", "timestamp", "exchange", "kind", "in_asset", "in_qty", "out_asset", "out_qty",
           "jpy_value", "fee_asset", "fee_qty", "source", "note")

_DECIMAL_FIELDS = {"in_qty", "out_qty", "jpy_value", "fee_qty"}


def parse_decimal(text: str | None) -> Decimal | None:
    """交換業者の数値表記（前後の空白、引用符、桁区切りカンマ）を Decimal にする。空なら None。"""
    if text is None:
        return None
    cleaned = text.strip().strip('"').replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned).normalize() + Decimal(0)
    except InvalidOperation as exc:
        raise ValueError(f"数値として読めません: {text!r}") from exc


@dataclass
class Entry:
    id: str
    timestamp: datetime
    exchange: str
    kind: str
    in_asset: str = ""
    in_qty: Decimal | None = None
    out_asset: str = ""
    out_qty: Decimal | None = None
    jpy_value: Decimal | None = None
    fee_asset: str = ""
    fee_qty: Decimal | None = None
    source: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"未知の kind です: {self.kind!r}（{', '.join(KINDS)} のいずれか）")


def _format(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def write_ledger(entries: list[Entry], path: str | Path) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for e in sorted(entries, key=lambda e: (e.timestamp, e.id)):
            writer.writerow([_format(getattr(e, c)) for c in COLUMNS])


def read_ledger(path: str | Path) -> list[Entry]:
    entries = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            kwargs: dict[str, object] = {}
            for field in fields(Entry):
                raw = row.get(field.name, "") or ""
                if field.name == "timestamp":
                    kwargs[field.name] = datetime.fromisoformat(raw)
                elif field.name in _DECIMAL_FIELDS:
                    kwargs[field.name] = parse_decimal(raw)
                else:
                    kwargs[field.name] = raw
            entries.append(Entry(**kwargs))
    return sorted(entries, key=lambda e: (e.timestamp, e.id))
