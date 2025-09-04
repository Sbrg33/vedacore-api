#!/usr/bin/env python3
"""
Fail commits that add direct swisseph/pyswisseph imports outside approved modules.

Approved locations (temporary):
- src/refactor/** (legacy)
- src/interfaces/** (adapters)
- src/api/middleware/ephemeris_headers.py (middleware)

All new usage should go via a centralized ephemeris core facade.
"""
from __future__ import annotations

import sys
from pathlib import Path

APPROVED_PREFIXES = {
    "src/refactor/",
    "src/interfaces/",
    "src/api/middleware/ephemeris_headers.py",
}


def is_approved(path: Path) -> bool:
    p = str(path.as_posix())
    return any(p.startswith(prefix) for prefix in APPROVED_PREFIXES)


def main(argv: list[str]) -> int:
    bad: list[str] = []
    for arg in argv:
        p = Path(arg)
        if not p.exists() or p.is_dir() or p.suffix != ".py":
            continue
        if is_approved(p):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "import swisseph" in text or "import pyswisseph" in text:
            bad.append(str(p))
    if bad:
        print(
            "::error::Direct swisseph/pyswisseph imports are restricted. Use the ephemeris core facade.\n"
            + "\n".join(f" - {b}" for b in bad)
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

