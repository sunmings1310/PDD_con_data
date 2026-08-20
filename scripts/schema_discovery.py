"""Aggregate PDD Raw Captures into evidence-backed schema-discovery artifacts."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.data_quality import evaluate, normalized_snapshot  # noqa: E402
from server.raw_capture import verify_capture  # noqa: E402


DYNAMIC_FIELDS = {
    "price", "display_price", "group_price", "deal_price", "original_price", "sales_num",
    "shop_sales_num", "comment_num", "coupon_info", "availability", "sku_prices", "sku_prices_text",
}
SNAPSHOT_FIELDS = {
    "title", "shop_name", "shop_id", "availability", "price", "display_price", "group_price",
    "deal_price", "original_price", "sales_num", "sku", "field_sources", "parser_version",
    "quality_rules_version", "parse_status", "page_status", "quality_status",
}
PERSISTED_FIELDS = {
    "platform_code", "keyword", "item_id", "sell_name", "product_name", "brand", "shop_name", "shop_id",
    "price", "display_price", "group_price", "deal_price", "original_price", "sales_num", "shop_sales_num",
    "comment_num", "spec", "sku_prices_text", "sku_prices", "dosage_form", "approval_no", "manufacturer",
    "expiry", "category", "coupon_info", "item_url", "pick_tag", "spec_list", "parse_status", "page_status",
    "quality_status", "field_sources", "parser_version", "quality_rules_version",
}
PARAM_LABELS = {
    "品牌", "发货地", "药品通用名", "通用名称", "商品名称", "产品名称", "药品规格", "规格", "规格类型",
    "产品剂型", "剂型", "批准文号", "国药准字", "化妆品批准文号", "药品分类", "药品类别", "类目",
    "所属类目", "生产企业", "生产企业名称", "生产厂家", "生产厂家名称", "上市许可持有人",
    "上市许可持有人名称", "制造商", "厂家", "有效期", "保质期", "产品类型", "香型", "净含量",
    "是否为特殊用途化妆品", "功效", "适用发质", "适用人群", "型号", "颜色", "尺码", "材质", "产地",
}

FIELD_MAP = {
    "platform_product_id": ("item_id", "platform_product_id", "SJZQ_PRODUCT.ITEM_ID", None, "Identity"),
    "title": ("sell_name", "title", "SJZQ_PRODUCT.SELL_NAME", "SJZQ_PRODUCT_SNAPSHOT.TITLE", "Stable Product"),
    "product_name": ("product_name", None, "SJZQ_PRODUCT.PRODUCT_NAME", None, "Stable Product"),
    "brand": ("brand", None, "SJZQ_PRODUCT.BRAND", None, "Stable Product"),
    "manufacturer": ("manufacturer", None, "SJZQ_PRODUCT.MANUFACTURER", None, "Stable Product"),
    "category": ("category", None, "SJZQ_PRODUCT.CATEGORY", None, "Stable Product"),
    "price": ("display_price", "display_price", "SJZQ_PRODUCT.DISPLAY_PRICE", "SJZQ_PRODUCT_SNAPSHOT.DISPLAY_PRICE", "Dynamic Snapshot"),
    "sales": ("sales_num", "sales_num", "SJZQ_PRODUCT.SALES_NUM", "SJZQ_PRODUCT_SNAPSHOT.SALES_NUM", "Dynamic Snapshot"),
    "comment_count": ("comment_num", None, "SJZQ_PRODUCT.COMMENT_NUM", None, "Dynamic Snapshot"),
    "shop": ("shop_name", "shop_name", "SJZQ_PRODUCT.SHOP_NAME", "SJZQ_PRODUCT_SNAPSHOT.SHOP_NAME", "Shop"),
    "promotion": ("coupon_info", None, "SJZQ_PRODUCT.COUPON_INFO", None, "Promotion"),
    "sku": ("sku_prices", "sku", "SJZQ_PRODUCT.SKU_PRICES_JSON", "SJZQ_PRODUCT_SNAPSHOT.SKU_JSON", "SKU Snapshot"),
    "spec": ("spec", None, "SJZQ_PRODUCT.SPEC_TEXT", None, "Attributes"),
    "media": ("image_urls", None, "SJZQ_PRODUCT_IMAGE", None, "Media"),
}


def json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def walk(value: Any, path: str = "$") -> Iterable[tuple[str, Any]]:
    if isinstance(value, Mapping):
        if not value:
            yield path, value
        for key, item in value.items():
            yield from walk(item, f"{path}.{key}")
    elif isinstance(value, list):
        if not value:
            yield path, value
        for item in value[:50]:
            yield from walk(item, f"{path}[*]")
    else:
        yield path, value


def text_observations(source_type: str, text: str) -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = [("$.text.present", bool(text.strip()))]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    title = next((line for line in lines if line.startswith("【") and len(line) >= 8), "")
    if title:
        rows.append(("$.ui.title", title[:160]))
    prices = list(dict.fromkeys(re.findall(r"[¥￥]\s*(\d+(?:\.\d{1,2})?)", text)))
    for value in prices[:10]:
        rows.append(("$.ui.price_candidates[*]", float(value)))
    sales = list(dict.fromkeys(re.findall(r"(?:总售|已拼|买过)\s*([\d.]+万?\+?)", text)))
    for value in sales[:10]:
        rows.append(("$.ui.sales_candidates[*]", value))
    rows.append(("$.ui.has_video_marker", "播放" in text or "tronplayer" in text.lower()))
    promo = [marker for marker in ("百亿补贴", "官方补贴", "优惠券", "领券", "立减", "折") if marker in text]
    if promo:
        for value in promo:
            rows.append(("$.ui.promotion_markers[*]", value))
    if source_type == "SKU":
        rows.append(("$.panel.raw_text", text[:240]))
    for index, line in enumerate(lines[:-1]):
        label = line.rstrip(":：")
        if label not in PARAM_LABELS:
            continue
        value = lines[index + 1]
        if value.rstrip(":：") in PARAM_LABELS or value in {"商品参数", "查看全部", "商品详情"}:
            continue
        rows.append((f"$.attributes.{label}", value[:240]))
    return rows


def source_to_raw(source: str) -> str:
    return {
        "list_card": "SEARCH", "detail_text": "DETAIL", "sku_panel": "SKU_PANEL", "share_link": "EMBEDDED",
        "embedded_json": "EMBEDDED", "network": "EMBEDDED", "dom": "DETAIL", "none": "NONE",
        "derived": "DERIVED", "inferred": "DERIVED",
    }.get(source, source.upper() if source else "UNKNOWN")


def observation_state(parsed: Mapping[str, Any], field: str) -> str:
    value = parsed.get(field)
    sources = parsed.get("field_sources") or {}
    if isinstance(sources, str):
        try:
            sources = json.loads(sources)
        except json.JSONDecodeError:
            sources = {}
    source = sources.get(field) or sources.get("title" if field in {"sell_name", "product_name"} else field)
    if value not in (None, "", [], {}, "[]"):
        return "VALUE"
    if str(parsed.get("parse_status") or "").lower() == "failed":
        return "PARSE_FAILED"
    if source == "none" or value in (None, "", [], {}, "[]"):
        return "NOT_OBSERVED"
    return "NOT_SUPPORTED"


def variability(values: set[str], occurrence: int) -> str:
    count = len(values)
    if count <= 1:
        return "constant"
    ratio = count / max(occurrence, 1)
    if count <= 3 or ratio < 0.25:
        return "low"
    if ratio < 0.75:
        return "medium"
    return "high"


@dataclass
class Capture:
    directory: Path
    manifest: dict[str, Any]
    parsed: dict[str, Any]
    normalized: dict[str, Any]
    sources: dict[str, list[tuple[str, Any]]]
    verification: dict[str, Any]


def load_captures(capture_root: Path, ids: list[str], replay_file: Path | None) -> list[Capture]:
    replay: dict[str, dict[str, Any]] = {}
    if replay_file:
        replay_doc = json.loads(replay_file.read_text(encoding="utf-8"))
        replay = {row["capture_id"]: row for row in replay_doc.get("results", [])}
    captures: list[Capture] = []
    for capture_id in ids:
        directory = capture_root / capture_id
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        parsed = replay.get(capture_id)
        if parsed is None:
            parsed = json.loads((directory / manifest["product_upload"]["storage_reference"]).read_text(encoding="utf-8"))
        decision = evaluate(parsed)
        normalized = normalized_snapshot(parsed, decision)
        sources: dict[str, list[tuple[str, Any]]] = defaultdict(list)
        for source in manifest["sources"]:
            path = directory / source["storage_reference"]
            if path.suffix.lower() == ".json":
                value = json.loads(path.read_text(encoding="utf-8"))
                sources[source["type"]].extend(walk(value))
            else:
                value = path.read_text(encoding="utf-8")
                sources[source["type"]].extend(text_observations(source["type"], value))
        sources["PARSED"].extend(walk(parsed))
        sources["NORMALIZED"].extend(walk(normalized))
        captures.append(Capture(directory, manifest, parsed, normalized, dict(sources), verify_capture(capture_id, root=capture_root)))
    return captures


def build_inventory(captures: list[Capture]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    total = len(captures)
    for capture in captures:
        for source, rows in capture.sources.items():
            for path, value in rows:
                kind = json_type(value)
                key = (source, path)
                bucket = buckets.setdefault(key, {"samples": set(), "null_samples": set(), "values": set(), "examples": [], "types": set()})
                bucket["types"].add(kind)
                bucket["samples"].add(capture.manifest["capture_id"])
                if value is None:
                    bucket["null_samples"].add(capture.manifest["capture_id"])
                else:
                    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True) if not isinstance(value, str) else value
                    bucket["values"].add(rendered[:500])
                    if rendered[:160] not in bucket["examples"] and len(bucket["examples"]) < 5:
                        bucket["examples"].append(rendered[:160])
    rows: list[dict[str, Any]] = []
    for (source, path), bucket in sorted(buckets.items()):
        count = len(bucket["samples"])
        top = path.removeprefix("$.").split(".", 1)[0].split("[", 1)[0]
        parser_used = source == "PARSED" or (
            source in {"DETAIL", "SEARCH", "SKU", "SHOP", "PROMOTION", "MEDIA", "EMBEDDED"} and
            (path.startswith("$.ui.") or path.startswith("$.attributes.") or top in PERSISTED_FIELDS)
        )
        rows.append({
            "field_path": path, "source": source, "data_type": "|".join(sorted(bucket["types"])), "occurrence_count": count,
            "occurrence_rate": round(count / total, 6), "null_rate": round(len(bucket["null_samples"]) / count, 6),
            "example_values": bucket["examples"], "distinct_value_count": len(bucket["values"]),
            "value_variability": variability(bucket["values"], count), "parser_used": parser_used,
            "persisted": top in PERSISTED_FIELDS or path in {"$.ui.title"},
            "snapshot": top in SNAPSHOT_FIELDS or any(x in path for x in ("price", "sales", "promotion")),
            "dynamic": top in DYNAMIC_FIELDS or any(x in path for x in ("price", "sales", "promotion")),
            "possibly_platform_specific": source not in {"PARSED", "NORMALIZED"},
        })
    return rows


def build_mapping(captures: list[Capture]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for capture in captures:
        parsed = capture.parsed
        sources = parsed.get("field_sources") or {}
        if isinstance(sources, str):
            try:
                sources = json.loads(sources)
            except json.JSONDecodeError:
                sources = {}
        for semantic, (parsed_field, normalized_field, product_field, snapshot_field, classification) in FIELD_MAP.items():
            src_key = "title" if parsed_field in {"sell_name", "product_name"} else ("sku" if parsed_field == "sku_prices" else parsed_field)
            src = sources.get(src_key) or sources.get("name" if src_key == "title" else src_key) or "none"
            rows.append({
                "capture_id": capture.manifest["capture_id"], "semantic_field": semantic,
                "raw_source": source_to_raw(str(src)), "parsed_field": parsed_field,
                "parsed_value": parsed.get(parsed_field), "observation_state": observation_state(parsed, parsed_field),
                "normalized_field": normalized_field, "normalized_value": capture.normalized.get(normalized_field) if normalized_field else None,
                "persisted_product_field": product_field, "persisted_snapshot_field": snapshot_field,
                "classification": classification,
            })
    return rows


def shop_type(name: str) -> str:
    for marker in ("官方旗舰店", "旗舰店", "专营店", "专卖店", "企业店"):
        if marker in name:
            return marker
    return "普通店铺" if name else "未观察"


def build_sample_matrix(captures: list[Capture]) -> list[dict[str, Any]]:
    rows = []
    for capture in captures:
        parsed = capture.parsed
        types = sorted(capture.sources)
        sku = parsed.get("sku_prices")
        if isinstance(sku, str):
            try:
                sku = json.loads(sku)
            except json.JSONDecodeError:
                sku = None
        detail_text = " ".join(str(v) for path, v in capture.sources.get("DETAIL", []) if path == "$.text.present")
        has_video = any(path == "$.ui.has_video_marker" and value for path, value in capture.sources.get("DETAIL", []))
        rows.append({
            "capture_id": capture.manifest["capture_id"], "platform_product_id": capture.manifest["platform_product_id"],
            "keyword": parsed.get("keyword"), "title": parsed.get("sell_name"), "brand": parsed.get("brand") or None,
            "brand_state": "有品牌" if parsed.get("brand") else "未观察品牌", "shop_name": parsed.get("shop_name") or None,
            "shop_type": shop_type(str(parsed.get("shop_name") or "")), "category": parsed.get("category") or None,
            "price": parsed.get("display_price"), "sales_num": parsed.get("sales_num"),
            "sales_band": "高销量" if isinstance(parsed.get("sales_num"), int) and parsed["sales_num"] >= 10000 else "普通/未观察销量",
            "promotion": "PROMOTION" in types, "video": has_video,
            "sku_raw_present": "SKU" in types, "sku_count": len(sku) if isinstance(sku, list) else 0,
            "spec_structure": "多SKU" if "SKU" in types and isinstance(sku, list) and len(sku) > 1 else ("SKU面板已捕获" if "SKU" in types else "无独立SKU Raw"),
            "raw_sources": types, "sha256_verified": capture.verification["hashes_valid"],
            "parser_version": parsed.get("parser_version"), "quality_status": parsed.get("quality_status"),
        })
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in row.items()})


def build_raw_only(inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep low-confidence platform observations in Raw Capture instead of schema."""
    rows: list[dict[str, Any]] = []
    for row in inventory:
        if row["source"] in {"PARSED", "NORMALIZED"}:
            continue
        reasons = []
        if not row["parser_used"]:
            reasons.append("Parser 未使用")
        if row["occurrence_rate"] < 0.5:
            reasons.append("样本出现率低于 50%")
        if row["possibly_platform_specific"]:
            reasons.append("平台特定原始观察")
        if not reasons:
            continue
        rows.append({**row, "raw_only_reason": "；".join(reasons)})
    return rows


def write_per_sample(output: Path, captures: list[Capture], mappings: list[dict[str, Any]]) -> None:
    by_capture: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in mappings:
        by_capture[row["capture_id"]].append(row)
    for capture in captures:
        capture_id = capture.manifest["capture_id"]
        sample_dir = output / "samples" / capture_id
        sample_dir.mkdir(parents=True, exist_ok=True)
        files = [
            {
                "type": source["type"],
                "storage_reference": source["storage_reference"],
                "sha256": source["sha256"],
                "verified": True,
            }
            for source in capture.manifest["sources"]
        ]
        evidence = {
            "capture_id": capture_id,
            "capture_directory": str(capture.directory.resolve()),
            "manifest": str((capture.directory / "manifest.json").resolve()),
            "product_upload": capture.manifest["product_upload"],
            "raw_sources": files,
            "sha256_verified": capture.verification["hashes_valid"],
        }
        (sample_dir / "capture-verification.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        sample_inventory = build_inventory([capture])
        (sample_dir / "field-inventory.json").write_text(
            json.dumps(sample_inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        write_csv(sample_dir / "field-inventory.csv", sample_inventory)
        sample_mapping = by_capture[capture_id]
        (sample_dir / "raw-parsed-normalized-persisted-mapping.json").write_text(
            json.dumps(sample_mapping, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        write_csv(sample_dir / "raw-parsed-normalized-persisted-mapping.csv", sample_mapping)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-root", type=Path, required=True)
    parser.add_argument("--capture-id", action="append", default=[])
    parser.add_argument("--capture-prefix", action="append", default=[])
    parser.add_argument("--replay-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ids = list(args.capture_id)
    for prefix in args.capture_prefix:
        ids.extend(path.name for path in sorted(args.capture_root.glob(f"{prefix}*")) if path.is_dir())
    ids = list(dict.fromkeys(ids))
    captures = load_captures(args.capture_root, ids, args.replay_file)
    inventory = build_inventory(captures)
    mapping = build_mapping(captures)
    matrix = build_sample_matrix(captures)
    raw_only = build_raw_only(inventory)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in (("sample-matrix", matrix), ("aggregate-field-inventory", inventory), ("raw-parsed-normalized-persisted-mapping", mapping)):
        (args.output / f"{name}.json").write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        write_csv(args.output / f"{name}.csv", value)
    (args.output / "raw-only-fields.json").write_text(
        json.dumps(raw_only, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_csv(args.output / "raw-only-fields.csv", raw_only)
    write_per_sample(args.output, captures, mapping)
    summary = {
        "sample_count": len(captures), "field_inventory_rows": len(inventory),
        "mapping_rows": len(mapping), "raw_only_rows": len(raw_only), "capture_ids": ids,
    }
    (args.output / "discovery-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
