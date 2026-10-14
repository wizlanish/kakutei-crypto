# CLAUDE.md — kakutei-crypto の作業ガイド

> このファイルは Claude Code が自動で読む。新しいセッションで作業を始める前に、まず全部読むこと。
> やり残しと優先順位は [`docs/ROADMAP.md`](docs/ROADMAP.md)、設計の経緯は [`docs/superpowers/specs/`](docs/superpowers/specs/) にある。

## 1. 何のプロジェクトか

日本居住の個人が、国内の暗号資産交換業者の取引履歴（CSV・PDF）から**暗号資産の雑所得**を計算するローカルツール。
CLI（`kakutei`）と Claude Code プラグイン（`/crypto-tax` スキル）の 2 つでできている。

**「Claude が読み、コードが計算する」** — これがこのプロジェクトの存在理由。
- Claude（スキル）の仕事: 形式がバラバラな CSV・PDF を読み、統一台帳 `ledger.csv` の行にして、人に確認してもらう。
- コードの仕事: 台帳から先の整合性チェック・所得計算・帳票出力。すべて決定的で、テストで裏付けられている。

## 2. 絶対に守ること（不変条件）

壊すとツールの信頼性そのものが失われる。変更がこれらに触れるなら、先にユーザーに相談する。

1. **LLM に計算させない。** スキル（`plugin/skills/crypto-tax/SKILL.md`）は所得・原価・単価を自分で計算してはいけない。数字は `kakutei calc` の出力から引用する。
2. **金額・数量は `Decimal`。float は禁止**（xlsx に書くときも Decimal のまま渡す）。
3. **割り算は最後。** 年末金額 I は「掛けてから割る」。総平均法は `floor((B+D)×H÷(A+C))`、移動平均法は 60 桁精度で簿価を持ち、全量払出しのときは簿価を 0 にする。G は常に `B + D − I`（国税庁の計算書と同じ恒等式）。
4. **時刻は JST。** オフセットのない時刻は JST とみなす。年の区切りも JST。
5. **check を通らない台帳は計算しない。** `calc` は check のエラーがあれば止まる。警告で済ませて黙って続けるような変更はしない。
6. **実データはリポジトリに入れない。** テストの固定データと `examples/` はすべて合成データ。実在の交換業者の実ファイル・PDF・個人名・取引 ID をコミットしない（`.gitignore` で `*.pdf`、`*.xlsx`、`private/`、`out/` を除外済み）。

## 3. 構成

```
src/kakutei_crypto/
  ledger.py        統一台帳 Entry（様式1 準拠：増加/減少/手数料/jpy_value/source/note）と CSV 入出力
  parsers/         既知形式のパーサー。ヘッダーで判定（__init__.py の _FORMATS に登録）
    common.py        UTF-8 / Shift_JIS の読み込み、JST の日時
    okj.py           OKJ 注文履歴・入出金口座履歴
    coincheck.py     Coincheck 様式1（増減の組み合わせで種別を決める）
  engine.py        validate → _effects（取引を取得・譲渡・損益に分解）→ 総平均法 / 移動平均法
  check.py         エラー（必須項目、保有数量マイナス、時価の欠落）と警告（要確認、対応する送付がない受取）
  report.py        端末表示（全角幅で揃える）と xlsx（計算書_<年>、明細）
  cli.py           kakutei import / check / calc
plugin/            Claude Code プラグイン（skills/crypto-tax/SKILL.md）
.claude-plugin/    マーケットプレイス定義（/plugin marketplace add wizlanish/kakutei-crypto）
tests/             下の §5
examples/yamada-2025/   合成データ。EXPECTED.md に手計算
docs/demo.gif      README のデモ（実際のコマンド出力を描画したもの）
```

**check と engine は同じ `_effects()` を使う。** ルールを変えるときは `_effects` だけを直せば両方に効く。check 側に別のルールを書かない。

## 4. コマンド

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'   # 初回
.venv/bin/pytest -q                                          # 全テスト（1 秒未満）
.venv/bin/kakutei import examples/yamada-2025/*.csv -o /tmp/l.csv --force
.venv/bin/kakutei calc /tmp/l.csv examples/yamada-2025/manual/*.ledger.csv   # → 所得金額 722,400 円
claude plugin validate .                                      # プラグイン定義の検証
```

プラグインを実際の Claude Code で試す（グローバル設定を変えずに）:

```bash
cd <合成データのフォルダ> && PATH=<repo>/.venv/bin:$PATH \
  claude -p --plugin-dir <repo>/plugin --allowedTools "Bash(kakutei:*)" Read Write Edit Glob \
  -- "/crypto-tax このフォルダの2025年分を計算して。質問はできないので仮定を最後に列挙して"
```

## 5. テストの考え方

| テスト | 何を守るか |
|---|---|
| `test_engine.py` | 国税庁 FAQ の計算例（1-1, 1-3, 1-5, 1-6, 1-7, 2-4, 2-8）をそのまま。数値を変えてはいけない |
| `test_against_reference.py` | Fraction で厳密に書いた参照実装とランダム台帳（600 件 × 総平均法・移動平均法）で 1 円単位まで一致。**engine を触ったら必ず通す** |
| `test_parsers.py` | 実ファイルと同じヘッダー・書式の合成データ（空白埋め、桁区切り、BOM、CRLF） |
| `test_check.py` | 壊れた行・取込み漏れ・未分類を見逃さない |
| `test_cli.py` | 終了コード（0 正常 / 1 check エラー・上書き拒否 / 2 未対応・読めない）、xlsx、Shift_JIS |
| `test_examples.py` | examples の手計算（722,400 / 722,900）と、README のサンプル出力が実出力と一致すること |

進め方は TDD。バグを直すときは、まずそのバグを再現するテストを書いて失敗を確かめる。
計算の変更では、参照実装との突き合わせが本当にバグを捕まえるかどうか（わざと壊すと落ちるか）も確かめると安心。

## 6. 税務ルール（根拠）

根拠は国税庁「暗号資産等に関する税務上の取扱いについて（FAQ）」（令和7年12月改訂）。
https://www.nta.go.jp/publication/pamph/shotoku/kakuteishinkokukankei/kasoutuka/index.htm
取引ごとの扱いは README の「税務上の扱い」の表を参照。README と engine は常に一致させる。

設計上の判断（変えるならユーザーと相談）:
- **暗号資産で払った手数料**は「収入 0 円で譲渡」として扱う。「時価で譲渡し同額を経費にする」のと所得は同じで、時価が要らないため。
- **自分の口座間の送付**は所得に影響しない。銘柄ごとに全交換業者を合算して計算する（FAQ 2-8）。
- **opening** 行は計算開始時点の保有で、計算書の A/B（年始）に入る。

**未検証の前提（重要）**: Coincheck 様式1 と OKJ 入出金の「数量」は**手数料と別**（手数料は別途差し引かれる）とみなしている。
bitFlyer の PDF の数字はこれと合うが、約定のある実ファイルではまだ確かめていない。逆だった場合、手数料が二重に計上される。→ ROADMAP の P0。

## 7. よくある変更の手順

**新しい交換業者の形式を追加する**
1. 実ファイルのヘッダーと書式を確認する（実ファイルはリポジトリの外に置く。中身をコミットしない）。
2. `tests/fixtures/` に同じヘッダー・書式の**合成**データを作り、`test_parsers.py` に失敗するテストを書く。
3. `parsers/<業者>.py` を書き、`parsers/__init__.py` の `_FORMATS` に `(名前, 必須ヘッダー集合, 関数)` を登録する。
4. id は `<業者>-<元の ID または ファイル名-行番号>` で一意にし、`source` に `ファイル名#行番号` を必ず入れる。
5. 手数料が無い・意味が曖昧な列があるときは `note` に「要確認」や理由を書く（check が警告にする）。
6. README の「対応している形式」の表と、SKILL.md の「対応形式」を更新する。

**計算ルールを変える**: `engine._effects` を直す → `test_engine.py` にケースを追加 → `test_against_reference.py` の参照実装も同じルールに直す → README の税務表を更新する。

**出力を変える**: README のサンプルと `docs/demo.gif` が古くなる。`test_examples.py` が README のずれを検出する。GIF は実際の出力から作り直す（ROADMAP 参照）。

## 8. 公開・リリース

- GitHub: https://github.com/wizlanish/kakutei-crypto （公開、MIT）
- コミットの作者は `wizlanish <48376126+wizlanish@users.noreply.github.com>`。会社のメールアドレスをコミットに入れない。clone し直したら最初に
  `git config user.name wizlanish && git config user.email 48376126+wizlanish@users.noreply.github.com` を実行する。
- push は HTTPS と Personal Access Token（macOS のキーチェーンに保存）。`gh` は社内ネットワークでは brew からインストールできなかった。
- バージョンは `pyproject.toml`、`plugin/.claude-plugin/plugin.json`、`.claude-plugin/marketplace.json` の 3 か所にある。上げるときは揃える。

## 9. スタイル

- コード中のコメント・docstring・コミットメッセージは日本語。識別子は英語。
- 1 ファイル 1 責務。ランタイム依存は openpyxl だけにする（増やす前に相談）。
- コミットは小さく、`feat:` / `fix:` / `docs:` / `chore:` を付ける。
