#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print("Usage: python scripts/git_plain.py <git args...>")
        print("Example: python scripts/git_plain.py status --short")
        print('Example: python scripts/git_plain.py commit -m "docs: add wrapper"')
        return 2

    git_exe = shutil.which("git")
    if git_exe is None:
        print("[git-plain] git executable not found in PATH.", file=sys.stderr)
        return 127

    proc = subprocess.run([git_exe, *args], cwd=PROJECT_ROOT, shell=False)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
