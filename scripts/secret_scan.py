#!/usr/bin/env python3
"""Scan staged or tracked text files for high-confidence leaked secrets."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

PLACEHOLDER = re.compile(r"(?:replace|change|example|redact|dummy|test|your)[-_ ]", re.I)
PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(?:sk|ghp|github_pat|xox[baprs])-[-_A-Za-z0-9]{16,}\b"),
    re.compile(
        r"\b(?:api[_-]?key|access[_-]?token|secret|password|webhook[_-]?url)\b"
        r"\s*[:=]\s*[\"']?([A-Za-z0-9_./+=:-]{16,})",
        re.I,
    ),
)


def files_from_git(staged: bool) -> list[Path]:
    command = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"] if staged else ["git", "ls-files"]
    output = subprocess.check_output(command, text=True)
    return [Path(line) for line in output.splitlines() if line]


def scan(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    findings = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if PLACEHOLDER.search(line):
            continue
        if any(pattern.search(line) for pattern in PATTERNS):
            findings.append(f"{path}:{line_number}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="scan all tracked files instead of staged files")
    args = parser.parse_args()
    findings = [finding for path in files_from_git(not args.all) for finding in scan(path)]
    if findings:
        print("Potential secrets detected:")
        print("\n".join(findings))
        return 1
    print("Secret scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
