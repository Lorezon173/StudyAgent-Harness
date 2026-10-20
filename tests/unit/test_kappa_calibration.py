"""Regression coverage for calibration sample alignment."""

import sys

import pytest


def test_retest_pairs_only_scores_from_the_same_csv_row(tmp_path, monkeypatch, capsys):
    pytest.importorskip("pandas")
    pytest.importorskip("scipy")
    pytest.importorskip("sklearn")
    from scripts import kappa_calibration

    csv_path = tmp_path / "scores.csv"
    csv_path.write_text(
        "topic,student_question,tutor_response,human_score,human_score_t1\n"
        "a,q,r,1,1\nb,q,r,2,\nc,q,r,3,3\nd,q,r,4,4\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["kappa_calibration", "--input", str(csv_path), "--dry-run"])
    kappa_calibration.main()
    assert "Cohen's \u03ba = 1.000  (n=3)" in capsys.readouterr().out
