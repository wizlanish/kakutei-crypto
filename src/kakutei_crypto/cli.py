"""kakutei コマンド: import / check / calc。"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from .check import check
from .engine import calculate
from .ledger import Entry, read_ledger, write_ledger
from .parsers import UnknownFormat, parse_file
from .report import render_text, write_xlsx


def _load(paths: list[str]) -> list[Entry]:
    entries: list[Entry] = []
    for path in paths:
        entries.extend(read_ledger(path))
    duplicates = sorted(i for i, n in Counter(e.id for e in entries).items() if n > 1)
    if duplicates:
        raise SystemExit(f"id が重複しています（同じファイルを二重に取り込んでいませんか）: {', '.join(duplicates[:5])}")
    return entries


def cmd_import(args: argparse.Namespace) -> int:
    if Path(args.output).exists() and not args.force:
        print(f"{args.output} は既に存在します。手で直した行が消えないよう、上書きしません。"
              f"別のファイル名に出力するか、上書きしてよければ --force を付けてください。", file=sys.stderr)
        return 1
    entries: list[Entry] = []
    unknown = []
    for path in args.files:
        try:
            parsed = parse_file(path)
        except UnknownFormat as exc:
            unknown.append(path)
            print(f"未対応: {exc}", file=sys.stderr)
            continue
        except (OSError, ValueError, KeyError) as exc:
            unknown.append(path)
            print(f"読めません: {path}: {exc}", file=sys.stderr)
            continue
        print(f"{path}: {len(parsed)} 件")
        entries.extend(parsed)
    write_ledger(entries, args.output)
    print(f"→ {args.output}（{len(entries)} 件）")
    return 2 if unknown else 0


def _report_issues(entries: list[Entry]) -> bool:
    issues = check(entries)
    for issue in issues:
        mark = "エラー" if issue.level == "error" else "注意"
        print(f"[{mark}] {issue.message}")
    errors = sum(1 for i in issues if i.level == "error")
    print(f"チェック: エラー {errors} 件、注意 {len(issues) - errors} 件")
    return errors == 0


def cmd_check(args: argparse.Namespace) -> int:
    return 0 if _report_issues(_load(args.ledgers)) else 1


def cmd_calc(args: argparse.Namespace) -> int:
    entries = _load(args.ledgers)
    if not entries:
        print("計算対象の取引がありません。")
        return 0
    if not _report_issues(entries):
        print("エラーを解消するまで計算しません。")
        return 1
    results, movements = calculate(entries, method=args.method)
    if args.year:
        results = [r for r in results if r.year == args.year]
    print(render_text(results, args.method))
    if args.xlsx:
        write_xlsx(results, movements, entries, args.method, args.xlsx)
        print(f"→ {args.xlsx}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kakutei", description="暗号資産の雑所得を計算する")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("import", help="交換業者のファイルを統一台帳に変換する")
    p.add_argument("files", nargs="+")
    p.add_argument("-o", "--output", default="ledger.csv")
    p.add_argument("--force", action="store_true", help="既存の出力ファイルを上書きする")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("check", help="台帳の整合性をチェックする")
    p.add_argument("ledgers", nargs="+")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("calc", help="所得を計算する")
    p.add_argument("ledgers", nargs="+")
    p.add_argument("--method", choices=["total", "moving"], default="total",
                   help="total=総平均法（届出なしの場合の法定評価方法）、moving=移動平均法")
    p.add_argument("--year", type=int)
    p.add_argument("--xlsx")
    p.set_defaults(func=cmd_calc)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError) as exc:  # 読めない台帳・壊れた行
        print(f"エラー: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
