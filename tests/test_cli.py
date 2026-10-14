from pathlib import Path

from openpyxl import load_workbook

from kakutei_crypto.cli import main

FIX = Path(__file__).parent / "fixtures"


def import_fixtures(tmp_path, *names):
    ledger = tmp_path / "ledger.csv"
    assert main(["import", *(str(FIX / n) for n in names), "-o", str(ledger)]) == 0
    return ledger


def test_import_reports_unknown_files_and_still_writes_known_ones(tmp_path, capsys):
    mystery = tmp_path / "mystery.csv"
    mystery.write_text("a,b\n1,2\n", encoding="utf-8")
    ledger = tmp_path / "ledger.csv"
    code = main(["import", str(FIX / "okj_orders.csv"), str(mystery), "-o", str(ledger)])
    assert code == 2
    assert "mystery.csv" in capsys.readouterr().err
    assert ledger.read_text(encoding="utf-8").count("\n") == 3  # ヘッダー + 2 件


def test_check_fails_when_fee_is_paid_from_coins_never_acquired(tmp_path, capsys):
    ledger = import_fixtures(tmp_path, "okj_transfers.csv")
    assert main(["check", str(ledger)]) == 1
    assert "HBAR" in capsys.readouterr().out


def test_calc_refuses_to_compute_a_ledger_with_errors(tmp_path, capsys):
    ledger = import_fixtures(tmp_path, "okj_transfers.csv")
    assert main(["calc", str(ledger)]) == 1
    assert "所得金額" not in capsys.readouterr().out


def test_calc_prints_income_and_writes_xlsx(tmp_path, capsys):
    ledger = import_fixtures(tmp_path, "okj_orders.csv", "coincheck_youshiki1.csv")
    xlsx = tmp_path / "out.xlsx"
    assert main(["calc", str(ledger), "--xlsx", str(xlsx)]) == 0
    out = capsys.readouterr().out
    # BTC: 収入 661,000 − 原価 600,000 ／ ETH: 原価 600（手数料分）／ 報酬 300 ／ 円手数料 10
    assert "所得金額" in out and "60,690" in out
    book = load_workbook(xlsx)
    assert {"計算書_2026", "明細"} <= set(book.sheetnames)


def test_calc_accepts_multiple_ledgers_and_moving_method(tmp_path, capsys):
    a = import_fixtures(tmp_path, "okj_orders.csv")
    b = tmp_path / "b.csv"
    assert main(["import", str(FIX / "coincheck_youshiki1.csv"), "-o", str(b)]) == 0
    assert main(["calc", str(a), str(b), "--method", "moving", "--year", "2026"]) == 0
    assert "移動平均法" in capsys.readouterr().out
