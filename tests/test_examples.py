"""examples/ の合成データを import → calc し、EXPECTED.md の手計算と一致することを確かめる。"""
from pathlib import Path

import pytest

from kakutei_crypto.cli import main

EXAMPLE = Path(__file__).parent.parent / "examples" / "yamada-2026"


@pytest.mark.parametrize("method, income", [("total", "722,400"), ("moving", "722,900")])
def test_yamada_2026_matches_hand_calculation(tmp_path, capsys, method, income):
    ledger = tmp_path / "ledger.csv"
    assert main(["import", *map(str, sorted(EXAMPLE.glob("*.csv"))), "-o", str(ledger)]) == 0
    manual = map(str, sorted((EXAMPLE / "manual").glob("*.ledger.csv")))
    assert main(["calc", str(ledger), *manual, "--method", method]) == 0
    summary = capsys.readouterr().out.splitlines()[-2]
    assert "所得金額" in summary and income in summary
