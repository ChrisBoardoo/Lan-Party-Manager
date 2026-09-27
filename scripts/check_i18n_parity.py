#!/usr/bin/env python3
"""Fail if the EN and FR translation files don't have identical key sets.

Flattens both locale JSON files to dotted key paths and compares them. Exits
non-zero (listing the offending keys) when they diverge, so CI catches a new
string added to one language but not the other.

Usage: python scripts/check_i18n_parity.py
"""

import json
import sys
from pathlib import Path

LOCALES = Path(__file__).resolve().parent.parent / "frontend" / "src" / "i18n" / "locales"


def flatten(obj, prefix=""):
    keys = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            keys |= flatten(v, path)
    else:
        keys.add(prefix)
    return keys


def main():
    en_path = LOCALES / "en.json"
    fr_path = LOCALES / "fr.json"

    en_keys = flatten(json.loads(en_path.read_text(encoding="utf-8")))
    fr_keys = flatten(json.loads(fr_path.read_text(encoding="utf-8")))

    only_en = sorted(en_keys - fr_keys)
    only_fr = sorted(fr_keys - en_keys)

    if only_en or only_fr:
        if only_en:
            print(f"Keys in en.json but missing from fr.json ({len(only_en)}):")
            for k in only_en:
                print(f"  - {k}")
        if only_fr:
            print(f"Keys in fr.json but missing from en.json ({len(only_fr)}):")
            for k in only_fr:
                print(f"  - {k}")
        sys.exit(1)

    print(f"i18n parity OK — {len(en_keys)} keys, EN/FR match.")


if __name__ == "__main__":
    main()
