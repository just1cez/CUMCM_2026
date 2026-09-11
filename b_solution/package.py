"""Build an anonymous, reproducible RESEARCH archive; official runs are deferred."""

from __future__ import annotations

import argparse
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
    "http_verification.json",
    "http_deadline_verification.json",
    "review_resolutions.json",
    "operation_bound.json",
    "paper_review.json",
    "visual_review.json",
    "final_review.json",
    "environment_manifest.json",
)


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
        baseline = json.loads(
            (extracted / "results/final_experiments.json").read_text()
        )
        enhanced_baseline = json.loads((extracted / "results/enhancement_experiments.json").read_text())
        ring_baseline = json.loads((extracted / "results/ring_sweep.json").read_text())
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
            [sys.executable, "make_assets.py"],
            [sys.executable, "make_enhancement_assets.py"],
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
        for command in commands:
            started = time.monotonic()
            cwd = extracted / "report" if command[0] == "latexmk" else extracted
            completed = subprocess.run(
                command,
                cwd=cwd,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=240,
                check=False,
                env={**os.environ, "MPLBACKEND": "Agg"},
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
        replay = json.loads((extracted / "results/final_experiments.json").read_text())
        assert baseline["total_runs"] == replay["total_runs"] == 4430
        assert len(baseline["runs"]) == len(replay["runs"])
        for old, new in zip(baseline["runs"], replay["runs"]):
            for key in old:
                if key != "real_duration_s":
                    assert old[key] == new[key], (old["seed"], key, old[key], new[key])
        enhanced_replay = json.loads((extracted / "results/enhancement_experiments.json").read_text())
        assert enhanced_baseline["total_runs"] == enhanced_replay["total_runs"] == 3080
        for old, new in zip(enhanced_baseline["runs"], enhanced_replay["runs"], strict=True):
            assert {k: v for k, v in old.items() if k != "real_duration_s"} == {
                k: v for k, v in new.items() if k != "real_duration_s"}
        ring_replay = json.loads((extracted / "results/ring_sweep.json").read_text())
        assert ring_baseline == ring_replay
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
        "excluded_nondeterminism": "wall-clock real_duration_s only",
        "commands": records,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    for metadata_name in ("metadata.json", "enhancement_metadata.json"):
        metadata = json.loads((ROOT / "report/generated" / metadata_name).read_text())
        for name, expected in metadata["input_sha256"].items():
            actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError(f"Stale generated asset input: {name}")
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
        if path.suffix in (".py", ".txt", ".tex", ".json") and anonymous_pattern.search(
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
        "status": "VERIFIED_RESEARCH_VERSION_OFFICIAL_TESTS_DEFERRED",
        "not_ready_for_contest_submission": True,
        "deferred_by_user": "Official simulator practice/formal runs and six encrypted logs",
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
        "official_tests": "DEFERRED_BY_USER",
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
