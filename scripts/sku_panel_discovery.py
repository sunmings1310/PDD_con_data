"""Build evidence-only SKU panel discovery artifacts from stored Raw Captures."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def walk(value: Any, path: str = "$"):
    yield path, type_name(value), value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for child in value:
            yield from walk(child, f"{path}[]")


def type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_set(snapshot: dict[str, Any]) -> set[str]:
    return {
        str(node.get("text") or node.get("content_description") or "").strip()
        for node in snapshot.get("nodes", [])
        if str(node.get("text") or node.get("content_description") or "").strip()
    }


def build(raw_root: Path, output: Path, capture_ids: list[str]) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    samples: list[dict[str, Any]] = []
    combinations: list[dict[str, Any]] = []
    diffs: list[dict[str, Any]] = []
    spec_audit: list[dict[str, Any]] = []
    inventory: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"captures": set(), "types": set(), "nulls": 0, "values": []}
    )

    for capture_id in capture_ids:
        directory = raw_root / capture_id
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        source = next(item for item in manifest["sources"] if item["type"] == "SKU_PANEL")
        panel_path = directory / source["storage_reference"]
        panel = json.loads(panel_path.read_text(encoding="utf-8"))
        upload = json.loads((directory / manifest["product_upload"]["storage_reference"]).read_text(encoding="utf-8"))
        dimensions = panel.get("dimension_inventory") or []
        observations = panel.get("option_observations") or []
        guard = panel.get("interaction_guard") or {}
        samples.append(
            {
                "capture_id": capture_id,
                "task_id": manifest.get("task_id"),
                "platform_product_id": manifest.get("platform_product_id"),
                "title": panel.get("product_title"),
                "collector_version": manifest.get("collector_version"),
                "interaction_entry": panel.get("interaction_entry"),
                "raw_sha256": source["sha256"],
                "raw_size": source["size"],
                "dimension_count": len(dimensions),
                "raw_observation_count": len(observations),
                "sku_id_state": "NOT_OBSERVED",
                "order_confirmation_clicked": bool(guard.get("order_confirmation_clicked")),
                "order_submitted": bool(guard.get("order_submitted")),
                "payment_started": bool(guard.get("payment_started")),
            }
        )
        before = text_set(panel.get("before_interaction") or {})
        opened = text_set(panel.get("panel_opened") or {})
        diffs.append(
            {
                "capture_id": capture_id,
                "added_panel_text": sorted(opened - before),
                "removed_detail_text": sorted(before - opened),
                "dimensions_from_raw_structure": dimensions,
            }
        )
        for index, observation in enumerate(observations):
            combinations.append(
                {
                    "capture_id": capture_id,
                    "observation_index": index,
                    "selected_options": observation.get("selected_options"),
                    "selected_text": observation.get("selected_text"),
                    "available": observation.get("available"),
                    "selected_price": observation.get("selected_price"),
                    "sku_id": None,
                    "evidence_source": "SKU_PANEL",
                }
            )
        parsed_spec_list = upload.get("spec_list")
        if isinstance(parsed_spec_list, str):
            try:
                parsed_spec_list = json.loads(parsed_spec_list)
            except json.JSONDecodeError:
                pass
        spec_audit.append(
            {
                "capture_id": capture_id,
                "collector_version": manifest.get("collector_version"),
                "parsed_spec": upload.get("spec"),
                "parsed_spec_list": parsed_spec_list,
                "raw_panel_contains_4g": "4G" in panel_path.read_text(encoding="utf-8"),
                "classification": (
                    "PAGE_OTHER_SYSTEM_UI_MISRECOGNITION"
                    if parsed_spec_list and "4G" in json.dumps(parsed_spec_list, ensure_ascii=False)
                    else "NO_FALSE_SPEC"
                ),
            }
        )
        per_capture_paths: set[str] = set()
        for path, kind, value in walk(panel):
            item = inventory[path]
            item["types"].add(kind)
            if value is None:
                item["nulls"] += 1
            elif not isinstance(value, (dict, list)) and len(item["values"]) < 5:
                rendered = str(value)
                if rendered not in item["values"]:
                    item["values"].append(rendered[:160])
            per_capture_paths.add(path)
        for path in per_capture_paths:
            inventory[path]["captures"].add(capture_id)

    count = len(capture_ids)
    inventory_rows = [
        {
            "field_path": path,
            "source": "SKU_PANEL",
            "data_types": sorted(item["types"]),
            "occurrence_count": len(item["captures"]),
            "occurrence_rate": round(len(item["captures"]) / count, 4),
            "null_count": item["nulls"],
            "examples": item["values"],
        }
        for path, item in sorted(inventory.items())
    ]
    result = {
        "samples": samples,
        "field_inventory": inventory_rows,
        "panel_diffs": diffs,
        "raw_combinations": combinations,
        "spec_evidence_audit": spec_audit,
        "semantics": {
            "SKU": "VALUE only when SKU_PANEL has direct combination evidence; otherwise NOT_OBSERVED",
            "sku_id": "VALUE only when a platform SKU identifier is directly present; these samples are NOT_OBSERVED",
            "zero": "VALUE(0) and NOT_OBSERVED are distinct",
        },
    }
    (output / "sku-panel-analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, rows in (("sample-matrix.csv", samples), ("sku-combinations.csv", combinations), ("field-inventory.csv", inventory_rows)):
        with (output / name).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["empty"])
            writer.writeheader()
            for row in rows:
                writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value for key, value in row.items()})
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture_ids", nargs="+")
    parser.add_argument("--raw-root", type=Path, default=Path("server/data/raw-captures"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.raw_root, args.output, args.capture_ids)
    print(json.dumps({"samples": len(result["samples"]), "raw_combinations": len(result["raw_combinations"]), "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
