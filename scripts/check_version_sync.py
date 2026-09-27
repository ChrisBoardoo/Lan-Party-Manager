#!/usr/bin/env python3
"""Fail if the version declared in version.json isn't reflected everywhere.

`version.json` is the single source of truth. This is a *guard*, not a rewriter:
it verifies each of the display/config locations still contains the expected
version token so a bump can't silently desync. See build.md for the full list.

Two forms are checked:
  * FULL  — the semver-with-label string, e.g. "1.4.0-beta"
  * CORE  — MAJOR.MINOR.PATCH only, e.g. "1.4.0" (used where a "BETA" label is
            rendered separately)

Usage: python scripts/check_version_sync.py
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

full = json.loads((ROOT / "version.json").read_text(encoding="utf-8"))["version"]
core = re.match(r"^\d+\.\d+\.\d+", full).group(0)

# shields.io escapes a literal "-" as "--", so 1.0.0-rc3 renders as 1.0.0--rc3.
# Do that substitution BEFORE re.escape, so the dots get escaped and the "--"
# survives intact. (The other order happens to work on 3.11, where re.escape no
# longer escapes "-", but it's a landmine for the next reader.)
BADGE = re.compile(rf"badge/version-{re.escape(full.replace('-', '--'))}-")

# (relative path, expected str that must appear literally, or a regex to search)
CHECKS = [
    ("frontend/package.json", f'"version": "{full}"'),
    ("backend/main.py", f'version="{full}"'),
    ("frontend/src/components/Footer.tsx", f"{core}"),
    ("frontend/src/components/ui/AboutModal.tsx", f"{core}"),
    ("frontend/src/pages/Settings.tsx", f":{full}"),
    # Anchored to the badge, which is the one place README *claims* a version.
    # This used to be a bare `core` substring check — i.e. "does '1.0.0' appear
    # anywhere in a 28 KB file", which it does, in prose, dozens of times. That
    # check was unfalsifiable and never tested anything: it passed happily while
    # the badge still read 1.0.0--rc1, two releases stale.
    ("README.md", BADGE),
    ("CLAUDE.md", f"`{full}`"),
]

# Gitignored on purpose (the `*.md` rule in .gitignore keeps internal docs out
# of git): checked when present — a local checkout — and skipped when absent,
# i.e. in CI or a fresh clone, where they can never exist. Every other
# location is tracked, so a missing one is still a failure.
LOCAL_ONLY = {"CLAUDE.md"}

failures = []
checked = 0
for rel, token in CHECKS:
    path = ROOT / rel
    if not path.exists():
        if rel in LOCAL_ONLY:
            print(f"  (skipped {rel}: local-only file, not in this checkout)")
            continue
        failures.append(f"  - {rel}: file not found")
        continue
    checked += 1
    text = path.read_text(encoding="utf-8")
    found = token.search(text) if isinstance(token, re.Pattern) else token in text
    if not found:
        expected = token.pattern if isinstance(token, re.Pattern) else token
        failures.append(f"  - {rel}: expected to match {expected!r}")

if failures:
    print(f"Version desync — version.json says {full!r} (core {core!r}) but:")
    print("\n".join(failures))
    print("\nUpdate the file(s) above (see build.md) or version.json.")
    sys.exit(1)

print(f"Version sync OK — {full} present in all {checked} locations checked.")
