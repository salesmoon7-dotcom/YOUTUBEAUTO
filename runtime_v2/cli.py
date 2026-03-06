from __future__ import annotations

import argparse
from runtime_v2.control_plane import run_control_loop_once


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner", default="runtime_v2")
    args = parser.parse_args()
    result = run_control_loop_once(owner=args.owner)
    print(result)
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
