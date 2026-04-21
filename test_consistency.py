#!/usr/bin/env python3
"""
Consistency test: run scorecard research N times per service and compare outputs.
Reports any fields that differ across runs.
"""
from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

SERVICES = [
    "Amazon S3",
    "Amazon SQS",
    "Amazon DynamoDB",
    "AWS Lambda",
    "Amazon SNS",
]
RUNS = 4


def run_once(service: str) -> list[dict[str, Any]] | None:
    result = subprocess.run(
        [sys.executable, "scorecard.py", "research", service, "-f", "json"],
        capture_output=True,
        text=True,
        cwd="/home/parolin/script/scorecard_agent",
        timeout=120,
    )
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr.strip()[:200]}")
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}\n  stdout: {result.stdout[:200]}")
        return None


def compare_runs(service: str, runs: list[list[dict]]) -> bool:
    """Return True if all runs produce identical output."""
    baseline = runs[0]
    all_same = True
    for run_idx, run in enumerate(runs[1:], start=2):
        if run is None:
            print(f"  run {run_idx}: FAILED (no output)")
            all_same = False
            continue
        if len(run) != len(baseline):
            print(f"  run {run_idx}: row count differs ({len(run)} vs {len(baseline)})")
            all_same = False
            continue
        for row_b, row_r in zip(baseline, run):
            if row_b != row_r:
                all_same = False
                b_score, r_score = row_b.get("score"), row_r.get("score")
                b_info, r_info = row_b.get("info"), row_r.get("info")
                row_id = row_b.get("id", "?")
                if b_score != r_score:
                    print(f"  run {run_idx} [{row_id}] SCORE differs:")
                    print(f"    baseline: {b_score!r}")
                    print(f"    run {run_idx}:  {r_score!r}")
                if b_info != r_info:
                    print(f"  run {run_idx} [{row_id}] INFO differs:")
                    print(f"    baseline: {b_info!r}")
                    print(f"    run {run_idx}:  {r_info!r}")
    return all_same


def main() -> None:
    total_pass = 0
    total_fail = 0

    for service in SERVICES:
        print(f"\n{'='*60}")
        print(f"Service: {service}  ({RUNS} runs)")
        print("="*60)

        results: list[list[dict] | None] = []
        for i in range(1, RUNS + 1):
            print(f"  run {i}/{RUNS}...", end=" ", flush=True)
            out = run_once(service)
            if out is not None:
                print(f"OK ({len(out)} rows)")
            results.append(out)

        valid = [r for r in results if r is not None]
        if not valid:
            print("  ALL RUNS FAILED — cannot compare")
            total_fail += 1
            continue

        # Use first successful run as baseline
        baseline = valid[0]
        passed = compare_runs(service, valid)

        if passed:
            print(f"  CONSISTENT across all {len(valid)} valid runs")
            total_pass += 1
        else:
            total_fail += 1

    print(f"\n{'='*60}")
    print(f"SUMMARY: {total_pass} services consistent, {total_fail} with differences")
    print("="*60)


if __name__ == "__main__":
    main()
