"""所得計算エンジン（総平均法・移動平均法）。

欄記号 A〜I は国税庁「暗号資産の計算書」に合わせている:
  A/B 年始数量/金額、C/D 年中取得数量/金額、E 平均単価、F 譲渡数量、
  G 売却原価、H/I 年末数量/金額。
I は円未満切り捨て、G = B + D − I（計算書と同じ恒等式）。I は割り算を最後に行う。
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_FLOOR, ROUND_HALF_EVEN, Decimal, localcontext
from zoneinfo import ZoneInfo

from .ledger import Entry

JST = ZoneInfo("Asia/Tokyo")
ZERO = Decimal(0)
JPY = "JPY"


class LedgerError(Exception):
    """台帳のままでは計算できない（保有数量がマイナス、時価の欠落など）。"""


@dataclass
class Movement:
    entry_id: str
    asset: str
    kind: str  # "acquire" | "dispose"
    qty: Decimal
    amount: Decimal  # 取得なら取得価額、譲渡なら収入金額


@dataclass
class AssetYear:
    asset: str
    year: int
    A: Decimal = ZERO
    B: Decimal = ZERO
    C: Decimal = ZERO
    D: Decimal = ZERO
    E: Decimal = ZERO
    F: Decimal = ZERO
    G: Decimal = ZERO
    H: Decimal = ZERO
    I: Decimal = ZERO
    proceeds: Decimal = ZERO


@dataclass
class YearResult:
    year: int
    assets: dict[str, AssetYear] = field(default_factory=dict)
    proceeds: Decimal = ZERO
    reward_income: Decimal = ZERO
    fee_expense: Decimal = ZERO
    cost_of_sales: Decimal = ZERO

    @property
    def income(self) -> Decimal:
        return self.proceeds + self.reward_income - self.cost_of_sales - self.fee_expense


@dataclass
class _Effects:
    acquisitions: list[tuple[str, Decimal, Decimal]] = field(default_factory=list)
    disposals: list[tuple[str, Decimal, Decimal]] = field(default_factory=list)
    openings: list[tuple[str, Decimal, Decimal]] = field(default_factory=list)
    fee_expense: Decimal = ZERO
    reward_income: Decimal = ZERO


def _require_value(entry: Entry) -> Decimal:
    if entry.jpy_value is None:
        raise LedgerError(f"{entry.id}: {entry.kind} には jpy_value（円換算額）が必要です（{entry.source}）")
    return entry.jpy_value


_NEEDS_IN = {"buy", "reward", "fork", "opening", "transfer_in", "swap"}
_NEEDS_OUT = {"sell", "transfer_out", "swap"}


def validate(entry: Entry) -> None:
    """種別ごとに必須の項目と符号を確かめる。欠けた行が黙って所得を変えないようにする。"""
    problems = []
    for name in ("in_qty", "out_qty", "fee_qty", "jpy_value"):
        value = getattr(entry, name)
        if value is not None and (not value.is_finite() or value < 0):
            problems.append(f"{name} は 0 以上の数値にしてください（{value}）")
    if entry.kind in _NEEDS_IN and not (entry.in_asset and entry.in_qty):
        problems.append(f"{entry.kind} には in_asset と正の in_qty が必要です")
    if entry.kind in _NEEDS_OUT and not (entry.out_asset and entry.out_qty):
        problems.append(f"{entry.kind} には out_asset と正の out_qty が必要です")
    if entry.fee_qty and not entry.fee_asset:
        problems.append("fee_qty があるのに fee_asset が空です")
    if (entry.kind in ("buy", "swap") and entry.fee_qty and entry.fee_asset == entry.in_asset
            and entry.in_qty is not None and entry.fee_qty >= entry.in_qty):
        problems.append("取得した通貨で払った手数料が、取得数量以上です")
    if problems:
        raise LedgerError(f"{entry.id}: {'; '.join(problems)}（{entry.source}）")


def _effects(entry: Entry) -> _Effects:
    """1 件の取引を、銘柄ごとの取得・譲渡と円の損益項目に分解する。"""
    validate(entry)
    fx = _Effects()
    fee_qty = entry.fee_qty.copy_abs() if entry.fee_qty else ZERO
    fee_in_jpy = fee_qty if entry.fee_asset == JPY else ZERO
    crypto_fee = entry.fee_asset if fee_qty and entry.fee_asset not in ("", JPY) else ""

    def acquire(asset: str, qty: Decimal | None, cost: Decimal) -> None:
        if asset and asset != JPY and qty:
            fx.acquisitions.append((asset, qty, cost))

    def dispose(asset: str, qty: Decimal | None, proceeds: Decimal) -> None:
        if asset and asset != JPY and qty:
            fx.disposals.append((asset, qty, proceeds))

    # 取得した通貨そのもので引かれた手数料は、取得数量を減らす（取得価額は変わらない。FAQ 1-5）。
    in_qty = entry.in_qty
    if crypto_fee and crypto_fee == entry.in_asset and entry.kind in ("buy", "swap") and in_qty is not None:
        in_qty -= fee_qty
        crypto_fee = ""

    kind = entry.kind
    if kind == "buy":
        acquire(entry.in_asset, in_qty, _require_value(entry) + fee_in_jpy)
    elif kind == "sell":
        dispose(entry.out_asset, entry.out_qty, _require_value(entry))
        fx.fee_expense += fee_in_jpy
    elif kind == "swap":
        value = _require_value(entry)
        dispose(entry.out_asset, entry.out_qty, value)
        acquire(entry.in_asset, in_qty, value)
        fx.fee_expense += fee_in_jpy
    elif kind == "reward":
        value = _require_value(entry)
        acquire(entry.in_asset, in_qty, value)
        fx.reward_income += value
    elif kind == "fork":
        acquire(entry.in_asset, in_qty, ZERO)
    elif kind == "opening":
        if entry.in_asset and entry.in_asset != JPY and in_qty:
            fx.openings.append((entry.in_asset, in_qty, _require_value(entry)))
    else:  # transfer_in / transfer_out：自分の口座間の移動は所得に影響しない
        fx.fee_expense += fee_in_jpy

    # 暗号資産で払った手数料は、収入 0 円で譲渡する（時価で譲渡し同額を経費にするのと所得は同じ）。
    if crypto_fee:
        dispose(crypto_fee, fee_qty, ZERO)
    return fx


_RESIDUE = Decimal("1e-12")


def _floor_yen(value: Decimal) -> Decimal:
    """円未満切り捨て。割り算の残差（1e-12 未満）で整数が 1 円下がらないよう、先に丸めてから切り捨てる。"""
    return value.quantize(_RESIDUE, rounding=ROUND_HALF_EVEN).quantize(Decimal(1), rounding=ROUND_FLOOR)


def calculate(entries: list[Entry], method: str = "total") -> tuple[list[YearResult], list[Movement]]:
    """台帳から年ごとの所得を計算する。method は "total"（総平均法）か "moving"（移動平均法）。"""
    with localcontext() as ctx:
        ctx.prec = 60  # 割り算の残差を 1e-12 よりずっと小さく抑える
        return _calculate(entries, method)


def _calculate(entries: list[Entry], method: str) -> tuple[list[YearResult], list[Movement]]:
    if method not in ("total", "moving"):
        raise ValueError("method は total か moving です")
    ordered = sorted(entries, key=lambda e: (e.timestamp, e.id))
    if not ordered:
        return [], []

    by_year: dict[int, list[Entry]] = defaultdict(list)
    for entry in ordered:
        by_year[entry.timestamp.astimezone(JST).year].append(entry)
    first, last = min(by_year), max(by_year)

    carry: dict[str, tuple[Decimal, Decimal]] = {}  # 銘柄 → (年末数量, 年末金額)
    results: list[YearResult] = []
    movements: list[Movement] = []

    for year in range(first, last + 1):
        result = YearResult(year=year)
        rows: dict[str, AssetYear] = {}
        moving_qty: dict[str, Decimal] = {}
        moving_book: dict[str, Decimal] = {}

        def row(asset: str) -> AssetYear:
            if asset not in rows:
                qty, amount = carry.get(asset, (ZERO, ZERO))
                rows[asset] = AssetYear(asset=asset, year=year, A=qty, B=amount)
                moving_qty[asset], moving_book[asset] = qty, amount
            return rows[asset]

        for asset in carry:
            row(asset)

        for entry in by_year.get(year, []):
            fx = _effects(entry)
            for asset, qty, cost in fx.openings:
                r = row(asset)
                r.A += qty
                r.B += cost
                moving_qty[asset] += qty
                moving_book[asset] += cost
                movements.append(Movement(entry.id, asset, "acquire", qty, cost))
            for asset, qty, cost in fx.acquisitions:
                r = row(asset)
                r.C += qty
                r.D += cost
                moving_qty[asset] += qty
                moving_book[asset] += cost
                movements.append(Movement(entry.id, asset, "acquire", qty, cost))
            for asset, qty, proceeds in fx.disposals:
                r = row(asset)
                held = moving_qty[asset]
                if qty > held:
                    raise LedgerError(
                        f"{entry.id}: {asset} の保有数量 {held} に対して {qty} を払い出しています。"
                        f"取込み漏れか、opening（計算開始時点の保有）が必要です（{entry.source}）")
                remaining = held - qty
                # 全量を払い出したら簿価は 0（割り算の残りを持ち越さない）
                moving_book[asset] = moving_book[asset] * remaining / held if remaining else ZERO
                moving_qty[asset] = remaining
                r.F += qty
                r.proceeds += proceeds
                movements.append(Movement(entry.id, asset, "dispose", qty, proceeds))
            result.fee_expense += fx.fee_expense
            result.reward_income += fx.reward_income

        for asset, r in sorted(rows.items()):
            r.H = r.A + r.C - r.F
            # I は「平均単価 × 数量」を先に掛けてから割る。E を先に求めると、
            # 割り切れない単価で I が 1 円少なくなることがある。
            if method == "total":
                pool = r.A + r.C
                r.E = (r.B + r.D) / pool if pool else ZERO
                r.I = _floor_yen((r.B + r.D) * r.H / pool) if pool else ZERO
            else:
                r.E = moving_book[asset] / r.H if r.H else ZERO
                r.I = _floor_yen(moving_book[asset]) if r.H else ZERO
            r.G = r.B + r.D - r.I
            result.assets[asset] = r
            result.proceeds += r.proceeds
            result.cost_of_sales += r.G

        carry = {asset: (r.H, r.I) for asset, r in result.assets.items() if r.H}
        results.append(result)

    return results, movements
