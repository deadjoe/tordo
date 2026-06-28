#!/usr/bin/env python3
"""Summarize `tordo doctor` for agents using the Tordo skill."""

import argparse
import json
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description="Run tordo doctor and print a concise JSON summary.")
    parser.add_argument("--tordo", default="tordo", help="tordo executable to run")
    parser.add_argument("--timeout", default=15.0, type=float, help="doctor bridge timeout in seconds")
    parser.add_argument("--include-raw", action="store_true", help="include full tordo doctor payload")
    args = parser.parse_args()

    executable = shutil.which(args.tordo)
    if not executable:
        print_json(
            {
                "ok": False,
                "error": {
                    "code": "tordo_not_found",
                    "message": "tordo executable was not found on PATH",
                },
            }
        )
        return 2

    result = subprocess.run(
        [executable, "doctor", "--timeout", str(args.timeout), "--compact"],
        check=False,
        capture_output=True,
        text=True,
    )

    if result.stderr.strip():
        sys.stderr.write(result.stderr)

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        print_json(
            {
                "ok": False,
                "error": {
                    "code": "doctor_output_not_json",
                    "message": "tordo doctor did not return JSON",
                    "stdout": result.stdout,
                },
            }
        )
        return result.returncode or 2

    checks = payload.get("checks") or []
    failed = [compact_check(check) for check in checks if check.get("status") == "failed"]
    warnings = [compact_check(check) for check in checks if check.get("status") == "warning"]
    summary = payload.get("summary") or summarize(checks)
    response = {
        "ok": bool(payload.get("ok")),
        "summary": summary,
        "failed_checks": failed,
        "warning_checks": warnings,
    }
    if args.include_raw:
        response["doctor"] = payload
    print_json(response)
    return result.returncode


def compact_check(check):
    return {
        "name": check.get("name"),
        "status": check.get("status"),
        "message": check.get("message"),
    }


def summarize(checks):
    summary = {}
    for check in checks:
        status = check.get("status") or "unknown"
        summary[status] = summary.get(status, 0) + 1
    return summary


def print_json(payload):
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
