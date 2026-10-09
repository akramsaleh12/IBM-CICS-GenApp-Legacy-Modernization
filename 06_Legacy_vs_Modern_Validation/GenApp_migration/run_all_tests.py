#!/usr/bin/env python3
"""
run_all_tests.py
------------------
Runs the complete automated test suite for this project in the
correct order, from the project root:

    python3 run_all_tests.py

This runs:
  1. scripts/  - copybook parser, EBCDIC/COMP-3 decoding, loaders,
                  migration validation, sequence resync (49 tests)
  2. api/      - raw CRUD API, business services, meta endpoints
                  (63 tests, including legacy-vs-modern behavioral parity)

Requires a reachable PostgreSQL server with a freshly-migrated
`genapp` database (run `python3 scripts/run_migration.py` first if
starting from an empty server - see README.md "Run sequence").

Exits non-zero if either suite fails, so this is CI-friendly:
see .github/workflows/tests.yml for how it's used there.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run_suite(directory: str) -> int:
    print(f"\n{'=' * 70}\nRunning tests in {directory}/\n{'=' * 70}")
    result = subprocess.run([sys.executable, "-m", "pytest", "-v"], cwd=ROOT / directory)
    return result.returncode


def main():
    exit_codes = {
        "scripts": run_suite("scripts"),
        "api": run_suite("api"),
    }

    print(f"\n{'=' * 70}\nSUMMARY\n{'=' * 70}")
    overall_ok = True
    for suite, code in exit_codes.items():
        status = "PASSED" if code == 0 else "FAILED"
        if code != 0:
            overall_ok = False
        print(f"  {suite}/: {status}")

    sys.exit(0 if overall_ok else 1)


if __name__ == "__main__":
    main()
