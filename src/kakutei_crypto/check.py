"""台帳の整合性チェック。calc の前に、計算を止める問題（error）と確認すべき点（warning）を洗い出す。"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from .engine import LedgerError, _effects
from .ledger import Entry

_REVIEW_MARKERS = ("要確認", "手数料が含まれません", "推定")
_MATCH_BEFORE = timedelta(days=7)
_MATCH_AFTER = timedelta(days=1)
_MATCH_MIN_RATIO = Decimal("0.9")


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
        for asset, qty, _ in fx.acquisitions + fx.openings:
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
    issues.extend(_unmatched_receives(entries))
    return issues


def _unmatched_receives(entries: list[Entry]) -> list[Issue]:
    """他の口座からの送付が台帳にない受取。取得価額が欠けたまま計算されるのを防ぐ。"""
    sends = [e for e in entries if e.kind == "transfer_out"]
    used: set[str] = set()
    issues = []
    for receive in sorted((e for e in entries if e.kind == "transfer_in"), key=lambda e: e.timestamp):
        for send in sends:
            if (send.id not in used and send.out_asset == receive.in_asset and send.out_qty and receive.in_qty
                    and send.timestamp - _MATCH_AFTER <= receive.timestamp <= send.timestamp + _MATCH_BEFORE
                    and send.out_qty * _MATCH_MIN_RATIO <= receive.in_qty <= send.out_qty):
                used.add(send.id)
                break
        else:
            issues.append(Issue("warning", receive.id,
                                f"{receive.id}: {receive.in_asset} {receive.in_qty} の受取に対応する送付が台帳にありません。"
                                f"送付元の交換業者の履歴を取り込むか、購入・報酬なら kind を直してください（{receive.source}）"))
    return issues
