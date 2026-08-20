"""Aggregate category-neutral SKU evidence from verified Raw Captures."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def json_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def dimension_rows(capture_id: str, panel: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for fallback_index, raw in enumerate(panel.get("dimension_inventory") or []):
        options = raw.get("options") or []
        values = [item.get("raw_value") if isinstance(item, dict) else item for item in options]
        rows.append({
            "capture_id": capture_id,
            "dimension_index": raw.get("dimension_index", fallback_index),
            "raw_name": raw.get("raw_name", raw.get("name")),
            "option_count": len(values),
            "options": values,
            "observation_state": raw.get("observation_state", "VALUE"),
        })
    return rows


def combination_rows(capture_id: str, panel: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, observation in enumerate(panel.get("option_observations") or []):
        selected = observation.get("selected_options") or []
        if selected and not isinstance(selected[0], dict):
            selected = [
                {"dimension_index": option_index, "dimension_name": None, "value": value}
                for option_index, value in enumerate(selected)
            ]
        else:
            selected = [
                {
                    "dimension_index": item.get("dimension_index"),
                    "dimension_name": item.get("dimension_name", item.get("raw_name")),
                    "value": item.get("value", item.get("raw_value")),
                }
                for item in selected
            ]
        available = observation.get("available")
        rows.append({
            "capture_id": capture_id,
            "combination_index": index,
            "selected_options": selected,
            "price": observation.get("selected_price"),
            "original_price": observation.get("original_price"),
            "promotion_price": observation.get("promotion_price"),
            "availability": "AVAILABLE" if available is True else "UNAVAILABLE" if available is False else "NOT_OBSERVED",
            "disabled": observation.get("disabled"),
            "default_selected": observation.get("selected_default"),
            "platform_sku_id": observation.get("platform_sku_id"),
            "media_evidence": observation.get("media_ref"),
            "observation_state": observation.get("observation_state", "VALUE"),
            "captured_at_epoch_ms": observation.get("captured_at_epoch_ms"),
        })
    return rows


def build(raw_root: Path, output: Path, capture_ids: list[str]) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    samples, dimensions, combinations, medicine = [], [], [], []
    for capture_id in capture_ids:
        directory = raw_root / capture_id
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        upload = json.loads((directory / manifest["product_upload"]["storage_reference"]).read_text(encoding="utf-8"))
        sku_source = next((source for source in manifest["sources"] if source["type"] == "SKU_PANEL"), None)
        panel = json.loads((directory / sku_source["storage_reference"]).read_text(encoding="utf-8")) if sku_source else {}
        drows = dimension_rows(capture_id, panel)
        crows = combination_rows(capture_id, panel)
        dimensions.extend(drows)
        combinations.extend(crows)
        prices = [row["price"] for row in crows if isinstance(row["price"], (int, float))]
        selected_nodes = [
            node for node in (panel.get("panel_opened") or {}).get("nodes", [])
            if node.get("selected") or node.get("checked")
        ]
        disabled_nodes = [
            node for node in (panel.get("panel_opened") or {}).get("nodes", [])
            if node.get("enabled") is False and (node.get("text") or node.get("content_description"))
        ]
        spec_list = json_value(upload.get("spec_list")) or []
        attribute_text = json.dumps(spec_list, ensure_ascii=False)
        title = panel.get("product_title") or upload.get("product_name") or upload.get("title") or ""
        is_medicine = bool(upload.get("approval_no") or upload.get("dosage_form") or "药" in title)
        samples.append({
            "capture_id": capture_id,
            "task_id": manifest.get("task_id"),
            "platform_product_id": manifest.get("platform_product_id"),
            "title": title,
            "category": "medicine" if is_medicine else "general",
            "is_medicine": is_medicine,
            "dimension_count": len(drows),
            "option_count": sum(row["option_count"] for row in drows),
            "combination_count": len(crows),
            "price_variation": len(set(prices)) > 1,
            "unavailable_observed": any(row["availability"] == "UNAVAILABLE" for row in crows),
            "default_observed": bool(selected_nodes) or any(row["default_selected"] is True for row in crows),
            "sku_image_observed": any(row["media_evidence"] not in (None, {}, "") for row in crows),
            "platform_sku_id_observed": any(row["platform_sku_id"] not in (None, {}, "") for row in crows),
            "sku_panel_state": "VALUE" if sku_source else "NOT_OBSERVED",
            "sku_panel_sha256": sku_source.get("sha256") if sku_source else None,
            "guard_confirm": (panel.get("interaction_guard") or {}).get("order_confirmation_clicked", False),
            "guard_submit": (panel.get("interaction_guard") or {}).get("order_submitted", False),
            "guard_payment": (panel.get("interaction_guard") or {}).get("payment_started", False),
        })
        if is_medicine:
            medicine.append({
                "capture_id": capture_id,
                "product_attributes": spec_list,
                "attribute_spec": upload.get("spec"),
                "dosage_form": upload.get("dosage_form"),
                "approval_no": upload.get("approval_no"),
                "manufacturer": upload.get("manufacturer"),
                "purchase_dimensions": drows,
                "separation_check": (
                    "PASS: ProductAttribute remained separate from SKU_PANEL"
                    if not drows or all(str(row["raw_name"]) not in attribute_text or row["options"] for row in drows)
                    else "REVIEW"
                ),
            })
    result = {"samples": samples, "dimensions": dimensions, "combinations": combinations, "medicine": medicine}
    (output / "generic-sku-evidence.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for filename, rows in (("sample-matrix.csv", samples), ("dynamic-dimension-matrix.csv", dimensions), ("combination-matrix.csv", combinations), ("medicine-attribute-analysis.csv", medicine)):
        with (output / filename).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["empty"])
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
    print(json.dumps({"samples": len(result["samples"]), "dimensions": len(result["dimensions"]), "combinations": len(result["combinations"]), "medicine": len(result["medicine"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
