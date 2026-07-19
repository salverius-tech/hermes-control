#!/usr/bin/env python3
"""Build a self-contained Hermes Control Extension source bundle."""

from __future__ import annotations

import argparse
import re
import tarfile
from pathlib import Path

FILES = (
    "plugin.yaml",
    "__init__.py",
    "services/__init__.py",
    "services/hermes_extension/__init__.py",
    "services/hermes_extension/host.py",
    "services/hermes_extension/protocol.py",
    "services/hermes_extension/server.py",
    "services/hermes_extension/README.md",
    "scripts/install_extension_runtime.sh",
)


def version(root: Path) -> str:
    manifest = (root / "plugin.yaml").read_text(encoding="utf-8")
    match = re.search(r"^version:\s*([^\s]+)\s*$", manifest, re.MULTILINE)
    if match is None:
        raise ValueError("plugin.yaml does not declare a version")
    return match.group(1)


def build(root: Path, output: Path) -> Path:
    plugin_version = version(root)
    bundle_name = f"hermes-control-extension-{plugin_version}"
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for relative in FILES:
            source = root / relative
            if not source.is_file():
                raise FileNotFoundError(source)
            archive.add(source, arcname=f"{bundle_name}/{relative}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    path = build(root, args.output)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
