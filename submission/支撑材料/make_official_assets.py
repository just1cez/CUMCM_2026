"""Generate a compact table from user-supplied official practice observations."""

from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GENERATED = ROOT / "report" / "generated"


def fmt(value):
    return f"{float(value):.2f}"


def main():
    data = json.loads(
        (ROOT / "results" / "official_practice_analysis.json").read_text(
            encoding="utf-8"
        )
    )
    assert data["official_practice"] is True and data["formal_test"] is False
    assert (
        data["offline_analysis_only"] is True
        and data["hidden_truth_used_online"] is False
    )
    assert len(data["runs"]) == 20
    rows = []
    for row in data["runs"]:
        assert row["certificate_complete"] is True
        assert row["n_cleared"] == row["source_count"] == row["n_cleared"]
        assert (
            abs(
                float(row["average_time_s"])
                - float(row["virtual_time_s"]) / row["n_cleared"]
            )
            < 1e-5
        )
        assert (
            abs(float(row["accounted_virtual_time_s"]) - float(row["virtual_time_s"]))
            < 2e-5
        )
        rows.append(
            [
                f"Q{row['problem']}",
                str(row["round"]),
                row["case_code"],
                str(row["source_count"]),
                str(row["n_cleared"]),
                fmt(row["virtual_time_s"]),
                fmt(row["average_time_s"]),
            ]
        )
    lines = [
        r"\begin{tabular}{rrlrrrr}",
        r"\toprule",
        "题号 & 轮次 & 案例编码 & $N$ & $K$ & $T$/s & $T/K$/(s/源) \\\\",
        r"\midrule",
    ]
    lines += [" & ".join(row) + r" \\" for row in rows]
    lines += [r"\bottomrule", r"\end{tabular}"]
    (GENERATED / "official_practice_table.tex").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    q3 = data["summary"]["3"]
    q4 = data["summary"]["4"]
    macros = {
        "OfficialQThreeWeighted": fmt(q3["weighted_s_per_source"]),
        "OfficialQThreeMeanRun": fmt(q3["mean_per_source_s"]),
        "OfficialQThreeMedianRun": fmt(q3["median_per_source_s"]),
        "OfficialQThreeSourceTotal": str(q3["source_total"]),
        "OfficialQFourWeighted": fmt(q4["weighted_s_per_source"]),
        "OfficialQFourMeanRun": fmt(q4["mean_per_source_s"]),
        "OfficialQFourMedianRun": fmt(q4["median_per_source_s"]),
        "OfficialQFourSourceTotal": str(q4["source_total"]),
        "OfficialPracticeRuns": str(data["run_count"]),
    }
    (GENERATED / "official_practice_numbers.tex").write_text(
        "\n".join("\\newcommand{\\" + k + "}{" + v + "}" for k, v in macros.items())
        + "\n",
        encoding="utf-8",
    )
    (GENERATED / "official_practice_metadata.json").write_text(
        json.dumps(
            {
                "evidence": "user_supplied_official_practice_observations_not_formal_scores",
                "input_sha256": {
                    "results/official_practice_analysis.json": hashlib.sha256(
                        (ROOT / "results/official_practice_analysis.json").read_bytes()
                    ).hexdigest()
                },
                "run_count": data["run_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "evidence": data["evidence"],
                "runs": len(data["runs"]),
                "q3_weighted": q3["weighted_s_per_source"],
                "q4_weighted": q4["weighted_s_per_source"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
