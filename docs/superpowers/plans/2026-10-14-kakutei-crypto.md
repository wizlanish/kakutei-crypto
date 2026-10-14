# kakutei-crypto Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 日本の個人向けに、交換業者の取引履歴から暗号資産の雑所得（総平均法・移動平均法）を計算するローカル CLI と Claude Code プラグインを作る。

**Architecture:** 統一台帳 `ledger.csv`（様式1 準拠）を境界にする。台帳より前（取込み）は決定的パーサーと Claude Code スキル、台帳より後（check / engine / report）はすべて Decimal で書いたテスト済みのコード。

**Tech Stack:** Python 3.12、標準ライブラリ（csv, decimal, dataclasses, argparse, zoneinfo）、openpyxl（xlsx 出力）、pytest。

**Spec:** `docs/superpowers/specs/2026-10-14-kakutei-crypto-design.md`

## Global Constraints

- 金額・数量はすべて `decimal.Decimal`。float は禁止。
- 円の表示は円未満切り捨て。総平均法では I = floor(E × H)、G = B + D − I。
- 時刻は JST（`Asia/Tokyo`）。年の区切りも JST。
- 実データはリポジトリに入れない。テストの固定データとサンプルは合成データのみ。
- Claude（スキル）は所得を計算しない。計算は `kakutei calc` だけが行う。
- ランタイム依存は openpyxl だけ。

## Review Focus

1. 全交換業者の合算で保有数量がマイナスになる（取込み漏れ）→ calc は推測で続行せず、check がエラーにして行を示す。
2. 時価のない swap / reward → check がエラーにする。calc も拒否する。
3. 年をまたぐ保有 → 翌年の A/B が前年の H/I と一致する。
4. 数値の表記揺れ（空白埋め、桁区切りカンマ、BOM、CRLF）→ パーサーが正しく Decimal にする。
5. 手数料が取得した通貨そのもので引かれた buy → 取得数量が減り、取得価額は変わらない。

---

### Task 1: プロジェクト雛形 + 台帳（ledger.py）

**Files:** Create `pyproject.toml`, `.gitignore`, `src/kakutei_crypto/__init__.py`, `src/kakutei_crypto/ledger.py`, `tests/test_ledger.py`

**Interfaces — Produces:**
- `KINDS = ("buy","sell","swap","reward","fork","transfer_in","transfer_out","opening")`
- `@dataclass Entry(id, timestamp: datetime, exchange, kind, in_asset="", in_qty: Decimal|None=None, out_asset="", out_qty=None, jpy_value=None, fee_asset="", fee_qty=None, source="", note="")`
- `read_ledger(path) -> list[Entry]`（timestamp でソート）、`write_ledger(entries, path)`、`parse_decimal(s) -> Decimal|None`（空白・カンマを除去し、空なら None）

- [ ] テスト: CSV の往復で同じ Entry に戻ること、`parse_decimal("  1,011.12 ")==Decimal("1011.12")`、空文字 → None、未知の kind → ValueError
- [ ] 実装 → pytest PASS → commit

### Task 2: エンジン（engine.py）— 国税庁ゴールデンテスト

**Files:** Create `src/kakutei_crypto/engine.py`, `tests/test_engine.py`

**Interfaces — Produces:**
- `@dataclass AssetYear(asset, year, A, B, C, D, E, F, G, H, I, proceeds, reward_income)`（F = 年中の譲渡数量）
- `@dataclass YearResult(year, assets: dict[str, AssetYear], proceeds, reward_income, fee_expense, cost_of_sales, income)`、`income = proceeds + reward_income − cost_of_sales − fee_expense`
- `@dataclass Movement(entry_id, asset, kind: "acquire"|"dispose", qty, amount)`（明細用）
- `calculate(entries, method: "total"|"moving") -> tuple[list[YearResult], list[Movement]]`
- `class LedgerError(Exception)`（保有数量がマイナス、時価の欠落）

**ゴールデンテスト（FAQ の数値をそのまま使う）:**
- FAQ 2-4: 3/1 4BTC 1,845,000 購入、6/20 2BTC 1,650,000 購入、7/10 2BTC 2,400,000 売却、9/15 0.5BTC 542,800 購入、11/30 3BTC 2,895,000 売却 → total: E=621,200、I=931,800、G=3,106,000 / moving: G=3,080,200、I=957,600
- FAQ 2-8: 同じ取引を交換業者 A・B に分けても所得は 2,189,000
- FAQ 1-3: 4/2 4BTC 4,000,000 購入、11/2 1BTC→40XRP、jpy_value 1,200,000 → 年の所得 200,000、XRP の D=1,200,000
- FAQ 1-5: 2BTC 2,000,000 購入、手数料 550 円 → D=2,000,550
- 報酬: 10 SOL を jpy_value 20,000 で受取 → reward_income=20,000、D=20,000
- 暗号資産の手数料: 100 HBAR を 10,000 円で購入、30 HBAR を送付・手数料 7 HBAR → H=93、所得 = −700（簿価 7 HBAR 分）
- 繰越: 2025 年に 1BTC 1,000,000 購入 → 2026 年の A=1、B=1,000,000
- 取得通貨で手数料: 1BTC 購入（fee_asset=BTC、fee_qty=0.001）→ C=0.999、D=jpy_value
- マイナス保有: 購入なしで 1BTC 売却 → LedgerError

- [ ] テストを書く → FAIL を確認 → 実装 → PASS → commit

### Task 3: パーサー（parsers/okj.py, parsers/coincheck.py, parsers/__init__.py）

**Files:** Create `src/kakutei_crypto/parsers/{__init__,okj,coincheck}.py`, `tests/test_parsers.py`, `tests/fixtures/*.csv`（合成）

**Interfaces — Produces:** `parse_file(path) -> list[Entry]`（ヘッダーで判定し、未知の形式なら `UnknownFormat` を送出）、`detect(path) -> str|None`

- OKJ 注文履歴: 空白埋め・カンマ・BOM。約定数量 0 の行はスキップ。注文銘柄 `ETH/JPY` → in_asset=ETH。note に手数料なしの警告を入れる。
- OKJ 入出金: JPY 行はスキップ。符号で in/out を決める。手数料は abs を fee として記録。未知の入出金内容は note に「要確認」と書く。
- Coincheck 様式1: CRLF、残高セクションは読み飛ばす。増減の組み合わせで kind を決める（spec §4.4）。

- [ ] テストを書く（各形式 2〜4 行の合成データ。実ファイルと同じヘッダーと書式）→ 実装 → PASS → commit

### Task 4: check.py

**Interfaces — Produces:** `@dataclass Issue(level: "error"|"warning", entry_id, message)`、`check(entries) -> list[Issue]`

- エラー: swap / reward で jpy_value が空、buy / sell で jpy_value が空、時系列でたどった保有数量がマイナス
- 警告: note に「要確認」または「手数料なし」を含む行
- [ ] テスト → 実装 → commit

### Task 5: report.py + cli.py

**Interfaces — Produces:** `render_text(results) -> str`、`write_xlsx(results, movements, entries, path)`、CLI `kakutei import FILES... -o ledger.csv`、`kakutei check LEDGER`（エラーがあれば exit 1）、`kakutei calc LEDGER [--method total|moving] [--year Y] [--xlsx PATH]`

- [ ] テスト: CLI を subprocess でなく `main(argv)` で呼ぶ。import → calc の出力に所得額が含まれること。xlsx に `計算書_2026` と `明細` シートがあること
- [ ] 実装 → commit

### Task 6: examples（合成データ）+ E2E テスト

架空ユーザー「山田花子」の 2026 年分。OKJ 注文履歴（BTC・ETH の売買）、OKJ 入出金（HBAR の送付・手数料）、Coincheck 様式1（swap、報酬、送付）。期待される所得を手計算して `examples/EXPECTED.md` に書き、テストで照合する。

- [ ] 作成 → `tests/test_examples.py` → commit

### Task 7: Claude Code プラグイン + README

**Files:** `.claude-plugin/marketplace.json`、`plugin/.claude-plugin/plugin.json`、`plugin/skills/crypto-tax/SKILL.md`、`README.md`（日本語 + 英語の要約）、`LICENSE`（MIT）

- SKILL.md: spec §5 の手順。bitFlyer の月次 PDF を台帳の行に変換する例を入れる。
- README: 30 秒で分かる構成（何をするか → なぜ信頼できるか → 使い方 → 税務ルール表 → 対象外 → 免責）。
- [ ] 作成 → claude plugin の JSON が正しいか確認 → commit
