from __future__ import annotations

import pathlib
import re
import sys

import yaml


root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
for workflow in (root / ".github" / "workflows").glob("*.yml"):
    yaml.safe_load(workflow.read_text(encoding="utf-8"))

files = list(root.glob("*.md"))
files += list((root / "docs").rglob("*.md"))
files += list((root / "server").glob("*.md"))
files += list((root / "android_collector").glob("*.md"))
files += list((root / "web").glob("*.md"))
files += list((root / ".github").glob("*.md"))
files = sorted(set(files))
failures: list[str] = []
pattern = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
for source in files:
    for raw in pattern.findall(source.read_text(encoding="utf-8")):
        target = raw.strip().split()[0].strip("<>")
        if not target or target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path_text = target.split("#", 1)[0]
        if path_text and not (source.parent / path_text).resolve().exists():
            failures.append(f"{source.relative_to(root)}: missing link target {target}")
if failures:
    print("\n".join(failures))
    raise SystemExit(1)
print(f"Validated {len(files)} Markdown files")
print("Validated workflow YAML")
print("RESULT: PASS")
