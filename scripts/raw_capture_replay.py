"""Offline Raw Product Capture verifier/replayer (dry-run; no PDD access)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.raw_capture import replay_capture  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("capture_id")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--enterprise-id", type=int)
    parser.add_argument("--workspace-id", type=int)
    parser.add_argument("--version", default="original", help="original, latest_safe, or a derived_capture_id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = replay_capture(
        args.capture_id,
        root=args.root,
        enterprise_id=args.enterprise_id,
        workspace_id=args.workspace_id,
        version=args.version,
    )
    rendered = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
