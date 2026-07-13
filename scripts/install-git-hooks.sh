#!/bin/sh
set -eu
repo_root=$(git rev-parse --show-toplevel)
git -C "$repo_root" config core.hooksPath .githooks
chmod +x "$repo_root/.githooks/pre-commit" "$repo_root/.githooks/pre-push"
printf '%s\n' 'Git hooks installed: pre-commit and pre-push secret scans enabled.'
