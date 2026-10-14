"""既知形式のパーサー。ヘッダーで形式を判定して振り分ける。

未知の形式や PDF は Claude Code スキル（plugin/）が台帳の行に変換する。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..ledger import Entry
from . import coincheck, okj
from .common import read_header


class UnknownFormat(Exception):
    """どの既知形式にも当てはまらないファイル。"""


_FORMATS: list[tuple[str, set[str], Callable[[Path], list[Entry]]]] = [
    ("okj_orders", okj.ORDERS_HEADER, okj.parse_orders),
    ("okj_transfers", okj.TRANSFERS_HEADER, okj.parse_transfers),
    ("coincheck_youshiki1", coincheck.HEADER, coincheck.parse),
]


def detect(path: str | Path) -> str | None:
    path = Path(path)
    if path.suffix.lower() != ".csv":
        return None
    header = set(read_header(path))
    for name, required, _ in _FORMATS:
        if required <= header:
            return name
    return None


def parse_file(path: str | Path) -> list[Entry]:
    path = Path(path)
    name = detect(path)
    for fmt, _, parser in _FORMATS:
        if fmt == name:
            return parser(path)
    raise UnknownFormat(f"{path.name}: 既知の形式ではありません。Claude Code の /crypto-tax で台帳に変換してください")
