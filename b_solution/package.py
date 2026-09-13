"""Build anonymous research materials; replay local studies and supplied practice."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath

import pymupdf

ROOT = Path(__file__).resolve().parent
SOURCES = (
    "geometry.py",
    "coverage.py",
    "planner.py",
    "environment.py",
    "client.py",
    "run.py",
    "official_run.py",
    "intersection.py",
    "second_point.py",
    "experiments.py",
    "compare_recovery.py",
    "compare_routes.py",
    "compare_probes.py",
    "verify_geometry.py",
    "verify_coverage_limits.py",
    "verify_refinements.py",
    "verify_terminal.py",
    "verify_http.py",
    "make_enhancement_assets.py",
    "make_assets.py",
    "audit_pdf.py",
    "package.py",
    "active_policy_candidate.py",
    "route_policy_candidate.py",
    "active_policy_notes.txt",
    "route_policy_notes.txt",
    "polar_coverage_candidate.py",
    "polar_coverage_notes.txt",
    "joint_dispatch_candidate.py",
    "joint_dispatch_notes.txt",
    "optical_policy_candidate.py",
    "optical_policy_notes.txt",
    "refinement_study.py",
    "research_experiments.py",
    "verify_research.py",
    "make_research_assets.py",
    "make_official_assets.py",
    "fast_vs_compact_410.py",
    "field_policy.py",
    "negative_geometry.py",
    "route_portfolio.py",
    "field_study.py",
    "field_confirmation.py",
    "verify_field.py",
    "official_analysis.py",
    "make_field_assets.py",
    "make_competition_assets.py",
    "redraw_q1q2.py",
    "redraw_q34.py",
    "redraw_results.py",
    "negative_geometry_notes.txt",
    "route_portfolio_notes.txt",
    "contracts.json",
    "report_contracts.json",
    "enhancements.py",
    "ring_sweep.py",
    "develop_anchors.py",
    "theory_additions.txt",
    "paper_expansion.txt",
    "coverage_notes.txt",
    "coverage_limits.tex",
    "requirements.txt",
    "reproduce.txt",
    "official_status.json",
    "audit/route_exact_audit.py",
    "audit/q3_ablation_audit.py",
    "audit/distribution_audit.py",
    "audit/correctness_audit.py",
    "audit/alternative_screen.py",
    "audit/freeze_compare.py",
)
RESULTS = (
    "final_experiments.json",
    "geometry_verification.json",
    "intersection_verification.json",
    "second_point_example.json",
    "recovery_development.json",
    "route_candidate_comparison.json",
    "adaptive_candidate_comparison.json",
    "terminal_verification.json",
    "ring_sweep.json",
    "enhancement_experiments.json",
    "anchor_development.json",
    "enhancement_review.json",
    "coverage_limits.json",
    "refinement_verification.json",
    "refinement_development.json",
    "research_experiments.json",
    "research_verification.json",
    "research_review.json",
    "field_development.json",
    "field_confirmation.json",
    "field_verification.json",
    "field_review.json",
    "official_practice_analysis.json",
    "fast_vs_compact_410.json",
    "practice_optimization_screen.json",
    "http_verification.json",
    "http_deadline_verification.json",
    "review_resolutions.json",
    "operation_bound.json",
    "paper_review.json",
    "visual_review.json",
    "final_review.json",
    "user_supplied_field_practice_summary.json",
    "environment_manifest.json",
    "audit_route_exact.json",
    "audit_q3_ablation.json",
    "audit_distribution.json",
    "audit_correctness.json",
    "audit_alternatives.json",
    "audit_freeze_compare.json",
)

def verify_asset_inputs(root: Path):
    for metadata_name in ("metadata.json", "enhancement_metadata.json", "research_metadata.json", "official_practice_metadata.json", "field_metadata.json"):
        metadata = json.loads((root / "report/generated" / metadata_name).read_text())
        for name, expected in metadata["input_sha256"].items():
            actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError(f"Stale generated asset input: {name}")


def deterministic_content(value):
    """Exclude measured wall clocks and their maximum, not behavioral statistics."""
    if isinstance(value, dict):
        return {key: deterministic_content(item) for key, item in value.items()
                if key not in ("real_duration_s", "max_real_duration_s", "max_real_s")}
    if isinstance(value, list):
        return [deterministic_content(item) for item in value]
    return value


def practice_files(root: Path):
    """Allow only the manifest's 60 sanitized practice files, never private raw logs."""
    root = root.resolve()
    manifest = root / "manifest.csv"
    if manifest.is_symlink():
        raise ValueError("Practice manifest must not be a symbolic link")
    with manifest.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 20 or {(int(r["problem"]), int(r["round"])) for r in rows} != {
        (p, n) for p in (3, 4) for n in range(1, 11)
    }:
        raise ValueError("Expected exactly ten supplied practice rounds per problem")
    files = {"manifest.csv": manifest}

    def check_identifiers(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "robot_id" and item != "TEAM_REDACTED":
                    raise ValueError("Unredacted robot_id in practice data")
                check_identifiers(item)
        elif isinstance(value, list):
            for item in value:
                check_identifiers(item)

    for row in rows:
        controller = f"data/controller/q{int(row['problem'])}/round_{int(row['round']):02d}"
        for key in ("private_requests", "observed_result", "simulator_result"):
            name = row[key]
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or "\\" in name:
                raise ValueError(f"Unsafe practice path: {name}")
            if key == "simulator_result":
                allowed = (relative.parent == PurePosixPath("data/simulator_results")
                           and re.fullmatch(r"practice-p[34]-[0-9]+-[A-Z0-9-]+\.result\.json", relative.name))
            else:
                filename = "private_requests.jsonl" if key == "private_requests" else "observed_result.json"
                allowed = name == f"{controller}/{filename}"
            path = root / relative
            if not allowed or path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError(f"Practice path outside permitted source scope: {name}")
            if name in files:
                raise ValueError(f"Repeated practice source: {name}")
            text = path.read_text(encoding="utf-8")
            values = [json.loads(line) for line in text.splitlines()] if key == "private_requests" else [json.loads(text)]
            for value in values:
                check_identifiers(value)
                if key == "private_requests" and value.get("event") == "request":
                    if value["body"].get("robot_id") != "TEAM_REDACTED":
                        raise ValueError(f"Missing sanitized request identity: {name}")
                if isinstance(value, dict) and "body_utf8" in value:
                    check_identifiers(json.loads(value["body_utf8"]))
            files[name] = path
    if len(files) != 61:
        raise ValueError("Expected 60 distinct practice files plus manifest")
    return files


def verify_practice_inputs(root: Path):
    files = practice_files(root / "practice_data")
    analysis = json.loads((root / "results/official_practice_analysis.json").read_text())
    actual = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()}
    if actual != analysis["input_sha256"]:
        raise ValueError("Official practice source hashes do not match analysis")
    return actual

def verify_archive(archive: Path):
    records = []
    with tempfile.TemporaryDirectory(prefix="b-reproduce-") as directory:
        extracted = Path(directory)
        with zipfile.ZipFile(archive) as bundle:
            for item in bundle.infolist():
                relative = PurePosixPath(item.filename)
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("Unsafe member in generated archive")
            bundle.extractall(extracted)
        manifest = json.loads((extracted / "MANIFEST.json").read_text())
        for name, information in manifest["files"].items():
            raw = (extracted / name).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == information["sha256"], name
        verify_asset_inputs(extracted)
        practice_hashes = verify_practice_inputs(extracted)
        immutable_names = [name for name in manifest["files"]
                           if name in SOURCES or name.startswith("practice_data/")
                           or (name.startswith("report/") and name.endswith(".tex")
                               and not name.startswith("report/generated/"))]
        expected_runs = {
            "final_experiments.json": 4430,
            "enhancement_experiments.json": 3080,
            "ring_sweep.json": 2200,
            "refinement_development.json": 2550,
            "research_experiments.json": 10700,
            "field_development.json": 2250,
            "field_confirmation.json": 9400,
        }
        baselines = {
            name: json.loads((extracted / "results" / name).read_text())
            for name in (*expected_runs, "research_verification.json", "field_verification.json", "official_practice_analysis.json", "fast_vs_compact_410.json", "practice_optimization_screen.json")
        }
        commands = [
            [sys.executable, "verify_geometry.py"],
            [sys.executable, "intersection.py"],
            [sys.executable, "second_point.py"],
            [
                sys.executable,
                "experiments.py",
                "--cases",
                "500",
                "--output",
                "results/final_experiments.json",
            ],
            [sys.executable, "enhancements.py"],
            [sys.executable, "ring_sweep.py"],
            [sys.executable, "verify_terminal.py"],
            [sys.executable, "verify_refinements.py"],
            [sys.executable, "verify_coverage_limits.py"],
            [sys.executable, "compare_routes.py"],
            [sys.executable, "compare_probes.py"],
            [sys.executable, "verify_research.py"],
            [sys.executable, "official_analysis.py", "--handoff", "practice_data"],
            [sys.executable, "make_official_assets.py"],
            [sys.executable, "fast_vs_compact_410.py"],
            [sys.executable, "refinement_study.py", "--cases", "150", "--seed", "3100000"],
            [sys.executable, "research_experiments.py"],
            [sys.executable, "verify_field.py"],
            [sys.executable, "field_study.py", "--cases", "150", "--seed", "6100000"],
            [sys.executable, "field_confirmation.py"],
            [sys.executable, "make_assets.py"],
            [sys.executable, "make_enhancement_assets.py"],
            [sys.executable, "make_research_assets.py"],
            [sys.executable, "make_field_assets.py"],
            [sys.executable, "redraw_q1q2.py"],
            [sys.executable, "redraw_q34.py"],
            [sys.executable, "redraw_results.py"],
            [
                "latexmk",
                "-xelatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "paper.tex",
            ],
            [
                "latexmk",
                "-xelatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "ai_usage.tex",
            ],
        ]
        environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        environment["MPLBACKEND"] = "Agg"
        for command in commands:
            started = time.monotonic()
            cwd = extracted / "report" if command[0] == "latexmk" else extracted
            completed = subprocess.run(
                command,
                cwd=cwd,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=1800,
                check=False,
                env=environment,
            )
            records.append(
                {
                    "command": [Path(command[0]).name, *command[1:]],
                    "returncode": completed.returncode,
                    "seconds": time.monotonic() - started,
                }
            )
            if completed.returncode:
                raise RuntimeError(
                    f"Extracted archive command failed: {command}\n{completed.stdout[-12000:]}"
                )
        reproduced_runs = {}
        auxiliary_runs = {}
        for name, baseline in baselines.items():
            replay = json.loads((extracted / "results" / name).read_text())
            if name in expected_runs:
                expected = expected_runs[name]
                assert baseline["total_runs"] == replay["total_runs"] == expected, name
                if name == "ring_sweep.json":
                    count = sum(len(group["runs"]) for phase in ("development", "held_out")
                                for group in replay[phase].values())
                else:
                    count = len(replay["runs"])
                    for old, new in zip(baseline["runs"], replay["runs"], strict=True):
                        assert deterministic_content(old) == deterministic_content(new), (name, old["seed"])
                assert count == expected, (name, count)
                reproduced_runs[name] = count
            if name == "fast_vs_compact_410.json":
                assert baseline["total_runs"] == replay["total_runs"] == 2000
                for label in ("compact25", "fast25"):
                    old_rows = [r for r in baseline["runs"] if r["configuration"] == label]
                    new_rows = [r for r in replay["runs"] if r["configuration"] == label]
                    assert [r["seed"] for r in old_rows] == list(range(4100000, 4101000))
                    assert [r["seed"] for r in new_rows] == list(range(4100000, 4101000))
                    for old, new in zip(old_rows, new_rows, strict=True):
                        assert deterministic_content(old) == deterministic_content(new)
                auxiliary_runs[name] = len(replay["runs"])
            assert deterministic_content(baseline) == deterministic_content(replay), name
        verify_asset_inputs(extracted)
        assert verify_practice_inputs(extracted) == practice_hashes
        for name in immutable_names:
            assert hashlib.sha256((extracted / name).read_bytes()).hexdigest() == manifest["files"][name]["sha256"], name
        assert sum(reproduced_runs.values()) == 34610
        for filename in ("paper", "ai_usage"):
            log = (extracted / "report" / f"{filename}.log").read_text(errors="replace")
            assert "Missing character:" not in log and "Overfull" not in log
            assert (
                "undefined references" not in log and "undefined citations" not in log
            )
            assert len(pymupdf.open(extracted / "report" / f"{filename}.pdf")) > 0
    return {
        "status": "passed",
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "manifest_hashes_verified": True,
        "all_4430_behavioral_runs_reproduced_exactly": True,
        "all_3080_enhancement_runs_reproduced_exactly": True,
        "ring_sweep_reproduced_exactly": True,
        "all_2200_ring_runs_reproduced_exactly": True,
        "all_10700_research_runs_reproduced_exactly": True,
        "all_2550_development_runs_reproduced_exactly": True,
        "research_verification_reproduced_exactly": True,
        "all_2250_field_development_runs_reproduced_exactly": True,
        "all_9400_field_confirmation_runs_reproduced_exactly": True,
        "field_verification_reproduced_exactly": True,
        "practice_source_hashes_verified_before_and_after": practice_hashes,
        "immutable_source_hashes_verified_after_replay": True,
        "pythonpath_removed": True,
        "official_practice_analysis_reproduced_exactly": True,
        "fast_vs_compact_screen_reproduced_exactly": True,
        "generated_asset_input_hashes_verified": True,
        "experiment_runs_reproduced_by_dataset": reproduced_runs,
        "experiment_runs_reproduced_total": sum(reproduced_runs.values()),
        "auxiliary_runs_excluded_from_core_total": auxiliary_runs,
        "excluded_nondeterminism": "local measured wall-clock real_duration_s, max_real_duration_s and max_real_s only; official timestamp/runtime observations remain exact",
        "commands": records,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--handoff", type=Path, default=(ROOT / "practice_data" if (ROOT / "practice_data").is_dir()
                                                       else ROOT.parent / "ai_optimization_handoff_20260912"))
    args = parser.parse_args()
    verify_asset_inputs(ROOT)
    for prefix, name in (("paper", "paper"), ("ai", "ai_usage")):
        audit = json.loads((ROOT / "report/visual" / f"{prefix}_audit.json").read_text())
        actual = hashlib.sha256((ROOT / "report" / f"{name}.pdf").read_bytes()).hexdigest()
        if audit["sha256"] != actual or audit["out_of_page_spans"] or audit["replacement_characters"]:
            raise ValueError(f"Missing or stale PDF audit: {name}")
        if prefix == "paper" and not (audit["abstract_keywords_on_first_page"]
                                      and 0 < audit["body_pages_excluding_abstract"] <= 30):
            raise ValueError("Paper abstract/body page rule violated")
    environment = {
        "python": sys.version,
        "environment": "conda py314",
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "scipy", "matplotlib", "pymupdf")
        },
    }
    (ROOT / "results/environment_manifest.json").write_text(
        json.dumps(environment, indent=2) + "\n"
    )
    files = {name: ROOT / name for name in SOURCES}
    files.update({"results/" + name: ROOT / "results" / name for name in RESULTS})
    supplied_practice = practice_files(args.handoff)
    analysis = json.loads((ROOT / "results/official_practice_analysis.json").read_text())
    practice_hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest()
                       for name, path in supplied_practice.items()}
    if practice_hashes != analysis["input_sha256"]:
        raise ValueError("Supplied practice files do not match official analysis input hashes")
    files.update({"practice_data/" + name: path for name, path in supplied_practice.items()})
    files["AI工具使用详情.pdf"] = ROOT / "report/ai_usage.pdf"
    for path in (ROOT / "report").iterdir():
        if path.suffix in (".tex", ".pdf"):
            files[path.relative_to(ROOT).as_posix()] = path
    for folder in ("generated", "figures"):
        for path in (ROOT / "report" / folder).iterdir():
            if path.is_file() and not path.name.startswith("."):
                files[path.relative_to(ROOT).as_posix()] = path
    for filename in ("paper_audit.json", "ai_audit.json"):
        path = ROOT / "report" / "visual" / filename
        files[path.relative_to(ROOT).as_posix()] = path
    missing = [name for name, path in files.items() if not path.is_file()]
    if missing:
        raise RuntimeError(f"Deliverable proof is missing: {missing}")
    anonymous_pattern = re.compile(r"/Users/[A-Za-z0-9._-]+/")
    for name, path in files.items():
        if path.suffix in (".py", ".txt", ".tex", ".json", ".jsonl", ".csv") and anonymous_pattern.search(
            path.read_text(encoding="utf-8")
        ):
            raise ValueError(f"Personal absolute path in anonymous material: {name}")
        if path.suffix == ".pdf":
            document = pymupdf.open(path)
            if anonymous_pattern.search(
                "\n".join(page.get_text() for page in document)
            ):
                raise ValueError(f"Personal absolute path in PDF: {name}")
    manifest = {
        "status": "RESEARCH_VERSION_OFFICIAL_PRACTICE_COMPLETE_FORMAL_TESTS_PENDING",
        "not_ready_for_contest_submission": True,
        "official_practice": "Twenty user-supplied Q3/Q4 practice observations were analyzed offline; formal tests and encrypted exports remain pending",
        "official_practice_replay_boundary": "All 20 supplied traces are independently costed; strict baseline policy replay matches only 8/20. Divergence stops replay, with no fabricated responses.",
        "practice_source_files": 60,
        "default_strategy": "Q3 refined, Q4 field; explicit --strategy overrides",
        "official_practice_control": "refined, probe_scale=0.22 for Q3 and Q4",
        "human_review": "No actual contestant review record; AI review is not human review",
        "python_environment": "conda py314",
        "python_version": sys.version.split()[0],
        "files": {
            name: {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size,
            }
            for name, path in sorted(files.items())
        },
    }
    destination = ROOT / "delivery"
    destination.mkdir(exist_ok=True)
    archive = destination / "B题研究支撑材料.zip"
    with zipfile.ZipFile(
        archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as bundle:
        for name, path in sorted(files.items()):
            bundle.write(path, name)
        bundle.writestr(
            "MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        )
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        for name, information in manifest["files"].items():
            assert hashlib.sha256(bundle.read(name)).hexdigest() == information["sha256"], name
    verify_asset_inputs(ROOT)
    for name, path in supplied_practice.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == practice_hashes[name], name
    shutil.copy2(ROOT / "report/paper.pdf", destination / "B题研究论文.pdf")
    shutil.copy2(ROOT / "report/ai_usage.pdf", destination / "AI工具使用详情.pdf")
    for path in (
        archive,
        destination / "B题研究论文.pdf",
        destination / "AI工具使用详情.pdf",
    ):
        assert path.stat().st_size <= 20 * 2**20, path.name
    status = {
        "status": manifest["status"],
        "official_tests": "PRACTICE_COMPLETE_FORMAL_PENDING",
        "human_review": "OUTSTANDING",
        "source_files": len(files),
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    }
    if args.verify:
        proof = verify_archive(archive)
        (destination / "复现验证.json").write_text(
            json.dumps(proof, ensure_ascii=False, indent=2) + "\n"
        )
        status["extracted_archive_reproduction"] = "passed"
    (destination / "交付状态.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
