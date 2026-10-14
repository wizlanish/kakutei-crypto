"""examples/ の合成データを import → calc し、EXPECTED.md の手計算と一致することを確かめる。"""
from pathlib import Path

import pytest

from kakutei_crypto.cli import main

EXAMPLE = Path(__file__).parent.parent / "examples" / "yamada-2025"


@pytest.mark.parametrize("method, income", [("total", "722,400"), ("moving", "722,900")])
def test_yamada_2025_matches_hand_calculation(tmp_path, capsys, method, income):
    ledger = tmp_path / "ledger.csv"
    assert main(["import", *map(str, sorted(EXAMPLE.glob("*.csv"))), "-o", str(ledger)]) == 0
    manual = map(str, sorted((EXAMPLE / "manual").glob("*.ledger.csv")))
    assert main(["calc", str(ledger), *manual, "--method", method]) == 0
    summary = capsys.readouterr().out.splitlines()[-2]
    assert "所得金額" in summary and income in summary


def test_readme_sample_output_matches_real_output(tmp_path, capsys):
    """README 冒頭のサンプル出力が実際の出力とずれていないこと。"""
    readme = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
    block = readme.split("$ kakutei calc ledger.csv manual/*.ledger.csv\n", 1)[1].split("```", 1)[0]
    sample = [l for l in block.splitlines() if l.strip() and l.strip() != "..."]
    ledger = tmp_path / "ledger.csv"
    main(["import", *map(str, sorted(EXAMPLE.glob("*.csv"))), "-o", str(ledger)])
    capsys.readouterr()
    main(["calc", str(ledger), *map(str, sorted((EXAMPLE / "manual").glob("*.ledger.csv")))])
    actual = capsys.readouterr().out.splitlines()
    for line in sample:
        assert line in actual, f"README のサンプルが実出力と違います: {line!r}"
