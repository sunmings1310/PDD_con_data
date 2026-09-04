from __future__ import annotations

import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[3]
PRODUCT = ROOT / "PRODUCT.md"
TEMPLATE = ROOT / "docs" / "tasks" / "TEMPLATE.md"


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


text = PRODUCT.read_text(encoding="utf-8")
pattern = re.compile(r"^#### ([A-Z]+-\d{3}) — (.+)$", re.MULTILINE)
matches = list(pattern.finditer(text))
if not matches:
    fail("no Requirement IDs found")

ids = [match.group(1) for match in matches]
if len(ids) != len(set(ids)):
    fail("duplicate Requirement ID")

required_prefixes = {
    "MED", "EXCEL", "LINEAGE", "OBS", "TASK", "PROD", "QLT", "SKU",
    "MEDIA", "TENANT", "DEVICE", "PLAT", "GOV",
}
actual_prefixes = {item.split("-", 1)[0] for item in ids}
missing_prefixes = sorted(required_prefixes - actual_prefixes)
if missing_prefixes:
    fail(f"missing prefixes: {','.join(missing_prefixes)}")

valid_statuses = {"Accepted", "Planned", "Deferred", "Unknown"}
required_labels = ("- **状态**：", "- **目标/价值**：", "- **范围**：", "- **验收**：", "- **约束**：")
for index, match in enumerate(matches):
    end = matches[index + 1].start() if index + 1 < len(matches) else text.find("\n## ", match.end())
    if end < 0:
        end = len(text)
    block = text[match.end():end]
    for label in required_labels:
        if label not in block:
            fail(f"{match.group(1)} missing {label}")
    status_match = re.search(r"^- \*\*状态\*\*：(.+)$", block, re.MULTILINE)
    if not status_match or status_match.group(1).strip() not in valid_statuses:
        fail(f"{match.group(1)} has invalid status")

template = TEMPLATE.read_text(encoding="utf-8")
if "Requirement IDs" not in template or "## Requirement Trace" not in template:
    fail("Task template does not require Requirement trace")

print(f"Validated {len(ids)} unique requirements across {len(actual_prefixes)} modules")
print("Task template Requirement trace: PRESENT")
print("RESULT: PASS")
sys.exit(0)
