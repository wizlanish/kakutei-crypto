"""パーサー共通の小道具。"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
_FORMATS = ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M")


def read_rows(path: Path) -> list[tuple[int, dict[str, str]]]:
    """(ファイル上の行番号, 行) のリスト。BOM と CRLF を吸収する。"""
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [(reader.line_num, row) for row in reader]


def read_header(path: Path) -> list[str]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [h.strip() for h in next(csv.reader(f), [])]


def parse_jst(text: str) -> datetime:
    text = text.strip()
    for fmt in _FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=JST)
        except ValueError:
            continue
    raise ValueError(f"日時として読めません: {text!r}")
