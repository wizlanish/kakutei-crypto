"""パーサー共通の小道具。"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
_FORMATS = ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M")


def read_text(path: Path) -> str:
    """UTF-8（BOM あり・なし）と Shift_JIS（cp932）の両方を読む。"""
    data = Path(path).read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp932")


def read_rows(path: Path) -> list[tuple[int, dict[str, str]]]:
    """(ファイル上の行番号, 行) のリスト。BOM・CRLF・Shift_JIS を吸収する。"""
    reader = csv.DictReader(io.StringIO(read_text(path), newline=""))
    return [(reader.line_num, row) for row in reader]


def read_header(path: Path) -> list[str]:
    return [h.strip() for h in next(csv.reader(io.StringIO(read_text(path), newline="")), [])]


def parse_jst(text: str) -> datetime:
    text = text.strip()
    for fmt in _FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=JST)
        except ValueError:
            continue
    raise ValueError(f"日時として読めません: {text!r}")
