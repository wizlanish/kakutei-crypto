"""計算結果の出力（端末表示と xlsx）。円は円未満切り捨てで表示する。"""
from __future__ import annotations

from decimal import ROUND_FLOOR, Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

from .engine import Movement, YearResult
from .ledger import Entry

METHOD_NAMES = {"total": "総平均法", "moving": "移動平均法"}
_COLUMNS = [("A", "年始数量"), ("B", "年始金額"), ("C", "取得数量"), ("D", "取得金額"), ("E", "平均単価"),
            ("F", "譲渡数量"), ("G", "売却原価"), ("H", "年末数量"), ("I", "年末金額")]
_QTY = {"A", "C", "F", "H"}


def yen(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_FLOOR))


def qty(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text if text != "-0" else "0"


def _cell(key: str, value: Decimal):
    return qty(value) if key in _QTY else yen(value)


def summary_rows(result: YearResult) -> list[tuple[str, int]]:
    return [("売却価額（収入）", yen(result.proceeds)),
            ("報酬等（収入）", yen(result.reward_income)),
            ("売却原価（必要経費）", yen(result.cost_of_sales)),
            ("手数料等（必要経費）", yen(result.fee_expense)),
            ("所得金額", yen(result.income))]


def render_text(results: list[YearResult], method: str) -> str:
    lines = []
    for result in results:
        lines.append(f"■ {result.year}年分 暗号資産の計算書（{METHOD_NAMES[method]}）")
        for asset, r in result.assets.items():
            cells = "  ".join(f"{k}={_cell(k, getattr(r, k)):,}" if k not in _QTY else f"{k}={_cell(k, getattr(r, k))}"
                              for k, _ in _COLUMNS)
            lines.append(f"  {asset:<6} {cells}  収入={yen(r.proceeds):,}")
        for label, amount in summary_rows(result):
            lines.append(f"  {label:<14} {amount:>15,} 円")
        lines.append("")
    return "\n".join(lines)


def write_xlsx(results: list[YearResult], movements: list[Movement], entries: list[Entry],
               method: str, path: str | Path) -> None:
    book = Workbook()
    book.remove(book.active)
    bold = Font(bold=True)
    for result in results:
        sheet = book.create_sheet(f"計算書_{result.year}")
        sheet.append([f"{result.year}年分 暗号資産の計算書（{METHOD_NAMES[method]}）"])
        sheet["A1"].font = bold
        sheet.append(["銘柄", *(f"{k} {label}" for k, label in _COLUMNS), "売却価額"])
        for asset, r in result.assets.items():
            sheet.append([asset, *(_cell(k, getattr(r, k)) for k, _ in _COLUMNS), yen(r.proceeds)])
        sheet.append([])
        for label, amount in summary_rows(result):
            sheet.append([label, amount])
        sheet.cell(row=sheet.max_row, column=1).font = bold

    detail = book.create_sheet("明細")
    detail.append(["id", "日時", "交換業者", "種別", "銘柄", "取得/譲渡", "数量", "金額（取得価額/収入）", "出典", "備考"])
    by_id = {e.id: e for e in entries}
    for m in movements:
        e = by_id[m.entry_id]
        detail.append([e.id, e.timestamp.isoformat(), e.exchange, e.kind, m.asset,
                       "取得" if m.kind == "acquire" else "譲渡", qty(m.qty), float(m.amount), e.source, e.note])
    book.save(path)
