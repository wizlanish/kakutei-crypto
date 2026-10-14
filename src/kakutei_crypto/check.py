"""台帳の整合性チェック。calc の前に、計算を止める問題（error）と確認すべき点（warning）を洗い出す。"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from .engine import LedgerError, _effects
from .ledger import Entry

_REVIEW_MARKERS = ("要確認", "手数料が含まれません", "推定")


@dataclass
class Issue:
    level: str  # "error" | "warning"
    entry_id: str
    message: str


def check(entries: list[Entry]) -> list[Issue]:
    issues: list[Issue] = []
    held: dict[str, Decimal] = defaultdict(Decimal)
    for entry in sorted(entries, key=lambda e: (e.timestamp, e.id)):
        try:
            fx = _effects(entry)
        except LedgerError as exc:
            issues.append(Issue("error", entry.id, str(exc)))
            continue
        for asset, qty, _ in fx.acquisitions:
            held[asset] += qty
        shortfalls = []
        for asset, qty, _ in fx.disposals:
            held[asset] -= qty
            if held[asset] < 0:
                shortfalls.append(f"{asset} が {-held[asset]} 不足")
                held[asset] = Decimal(0)
        if shortfalls:
            issues.append(Issue("error", entry.id,
                                f"{entry.id}: 全交換業者の合算で保有数量がマイナスになります（{', '.join(shortfalls)}）。"
                                f"取込み漏れか、opening が必要です（{entry.source}）"))
        if any(marker in entry.note for marker in _REVIEW_MARKERS):
            issues.append(Issue("warning", entry.id, f"{entry.id}: {entry.note}（{entry.source}）"))
    return issues
