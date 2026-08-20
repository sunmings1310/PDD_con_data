"""Immutable, credential-minimized Raw Product Capture storage and offline replay."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Mapping

from server.config import DATA_DIR
from server.data_quality import evaluate, normalized_snapshot

SOURCE_TYPES = {"SEARCH", "DETAIL", "SKU", "SKU_PANEL", "SHOP", "PROMOTION", "MEDIA", "EMBEDDED", "OTHER"}
CAPTURE_ID_RE = re.compile(r"^cap-[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")
SENSITIVE_KEY_RE = re.compile(
    r"(?i)^(?:cookie|set-cookie|authorization|proxy-authorization|lease_token|device_key|"
    r"session(?:_token)?|access_token|refresh_token|password|credential)$"
)
SENSITIVE_TEXT_RE = re.compile(
    r"(?im)^(?:cookie|set-cookie|authorization|proxy-authorization|lease[_-]?token|device[_-]?key|"
    r"session[_-]?token|access[_-]?token|refresh[_-]?token|password|credential)\s*[:=].*$"
)
SENSITIVE_QUERY_RE = re.compile(
    r"(?i)([?&](?:token|access_token|auth|authorization|session|device_key|lease_token)=)[^&#\s]+"
)
PERSONAL_TEXT_RE = re.compile(
    r"(?im)^(?:.*1\d{2}\*{4}\d{4}.*|.*(?:\d+栋|\d+幢|\d+单元|\d+室|\d+号).*|"
    r".*(?:微信|支付宝|银行卡)支付.*)$"
)
UNRELATED_SYSTEM_UI_RE = re.compile(
    r"(?im)^(?:.*通知[:：].*|.*(?:短信同步|通话记录同步|设备备份失败).*|"
    r".*com\.android\.systemui:id/.*|.*联机工具通知.*|.*手机信号.*|.*电池电量.*|"
    r"蓝牙开启。?|(?:上午|下午|晚上)?\d{1,2}:\d{2}|[345]G)\s*$"
)

PARSER_FIELDS = {
    "platform_code", "keyword", "item_id", "sell_name", "product_name", "brand", "shop_name", "shop_id",
    "price", "display_price", "group_price", "deal_price", "original_price", "sales_num",
    "shop_sales_num", "comment_num", "spec", "sku_prices_text", "sku_prices", "dosage_form",
    "approval_no", "manufacturer", "expiry", "category", "coupon_info", "item_url", "pick_tag",
    "spec_list", "image_urls", "parse_status", "page_status", "quality_status", "field_sources",
    "parser_version", "quality_rules_version",
}
PERSISTED_FIELDS = PARSER_FIELDS - {"image_urls"}


class RawCaptureError(ValueError):
    pass


def capture_root() -> Path:
    return Path(os.environ.get("RAW_CAPTURE_DIR") or (DATA_DIR / "raw-captures"))


def _iso(epoch_ms: Any = None) -> str:
    try:
        value = float(epoch_ms) / 1000 if epoch_ms is not None else datetime.now(timezone.utc).timestamp()
    except (TypeError, ValueError):
        value = datetime.now(timezone.utc).timestamp()
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "<redacted>" if SENSITIVE_KEY_RE.match(str(key)) else sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        result = SENSITIVE_QUERY_RE.sub(r"\1<redacted>", SENSITIVE_TEXT_RE.sub("<redacted-sensitive-line>", value))
        result = PERSONAL_TEXT_RE.sub("<redacted-personal-line>", result)
        result = UNRELATED_SYSTEM_UI_RE.sub("", result)
        return re.sub(r"\n{3,}", "\n\n", result)
    return value


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_extension(content_type: str) -> str:
    return ".json" if "json" in content_type.lower() else ".txt"


def persist_raw_capture(body: Any, device: Mapping[str, Any], *, root: Path | None = None) -> dict[str, Any] | None:
    raw = getattr(body, "raw_capture", None)
    if not raw:
        return None
    raw = sanitize(dict(raw))
    capture_id = str(raw.get("capture_id") or "")
    if not CAPTURE_ID_RE.fullmatch(capture_id):
        raise RawCaptureError("invalid capture_id")
    platform = str(raw.get("platform") or getattr(body, "platform_code", "") or "").lower()
    product_id = str(raw.get("platform_product_id") or getattr(body, "item_id", "") or "")
    if platform != str(getattr(body, "platform_code", "") or "").lower() or product_id != str(getattr(body, "item_id", "") or ""):
        raise RawCaptureError("raw capture product identity mismatch")
    sources = raw.get("sources")
    if not isinstance(sources, list) or not sources:
        raise RawCaptureError("raw capture sources are required")

    base = (root or capture_root()).resolve()
    base.mkdir(parents=True, exist_ok=True)
    target = base / capture_id
    if target.exists():
        existing = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        if existing.get("platform_product_id") != product_id:
            raise RawCaptureError("capture_id already belongs to another product")
        return existing

    temp = Path(tempfile.mkdtemp(prefix=f".{capture_id}-", dir=base))
    manifest_sources: list[dict[str, Any]] = []
    try:
        source_dir = temp / "sources"
        source_dir.mkdir()
        for index, source in enumerate(sources, start=1):
            if not isinstance(source, Mapping):
                raise RawCaptureError("raw capture source must be an object")
            source_type = str(source.get("type") or "").upper()
            if source_type not in SOURCE_TYPES:
                raise RawCaptureError(f"unsupported raw source type: {source_type}")
            content_type = str(source.get("content_type") or "text/plain; charset=utf-8")[:128]
            payload = sanitize(str(source.get("payload") or ""))
            original_content_type = content_type
            parse_status = "captured"
            extension = _source_extension(content_type)
            if extension == ".json":
                try:
                    payload_object = json.loads(payload)
                except json.JSONDecodeError:
                    # Raw Capture must not lose the remaining sources because a client
                    # declared JSON after line-level redaction changed its syntax.
                    # Preserve the exact sanitized bytes as text and make the mismatch explicit.
                    extension = ".txt"
                    content_type = "text/plain; charset=utf-8"
                    parse_status = "invalid_json_preserved_as_text"
                    data = (payload + ("" if payload.endswith("\n") else "\n")).encode("utf-8")
                else:
                    data = _json_bytes(payload_object)
            else:
                data = (payload + ("" if payload.endswith("\n") else "\n")).encode("utf-8")
            filename = f"{index:02d}_{source_type}{extension}"
            (source_dir / filename).write_bytes(data)
            manifest_sources.append({
                "type": source_type,
                "source_identifier": str(source.get("source_identifier") or "")[:256],
                "captured_at": _iso(source.get("captured_at_epoch_ms")),
                "size": len(data),
                "sha256": _sha(data),
                "storage_reference": f"sources/{filename}",
                "content_type": content_type,
                "declared_content_type": original_content_type,
                "schema_hint": str(source.get("schema_hint") or "")[:128] or None,
                "parse_status": parse_status,
            })

        upload = sanitize(body.model_dump(mode="json") if hasattr(body, "model_dump") else dict(body))
        upload.pop("raw_capture", None)
        upload.pop("device_key", None)
        upload.pop("lease_token", None)
        parsed_dir = temp / "parsed"
        parsed_dir.mkdir()
        upload_bytes = _json_bytes(upload)
        (parsed_dir / "product_upload.json").write_bytes(upload_bytes)

        manifest = {
            "capture_id": capture_id,
            "platform": platform,
            "platform_product_id": product_id,
            "captured_at": _iso(raw.get("collected_at_epoch_ms")),
            "task_id": getattr(body, "task_id", None),
            "job_id": getattr(body, "job_id", None),
            "attempt_id": getattr(body, "attempt_id", None),
            "device_id": int(device["device_id"]),
            "enterprise_id": int(device.get("enterprise_id") or 1),
            "workspace_id": int(device.get("workspace_id") or 1),
            "collector_version": str(raw.get("collector_version") or "unknown")[:64],
            "parser_version": str(raw.get("parser_version") or getattr(body, "parser_version", "unknown"))[:64],
            "sources": manifest_sources,
            "product_upload": {
                "storage_reference": "parsed/product_upload.json",
                "size": len(upload_bytes),
                "sha256": _sha(upload_bytes),
            },
            "sensitive_data_filter": {
                "excluded": ["Cookie", "Authorization", "session/access/refresh token", "lease_token", "device_key", "password/credential"],
                "mode": "key and line filtering plus sensitive URL query redaction",
            },
        }
        inventory = build_field_inventory(temp, manifest)
        (temp / "field-inventory.json").write_bytes(_json_bytes(inventory))
        manifest["field_inventory"] = "field-inventory.json"
        (temp / "manifest.json").write_bytes(_json_bytes(manifest))
        temp.rename(target)
        return manifest
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def _walk(value: Any, path: str = "$"):
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield from _walk(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value[:20]):
            yield from _walk(item, f"{path}[{index}]")
    else:
        yield path, type(value).__name__, value


def build_field_inventory(capture_dir: Path, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in manifest["sources"]:
        path = capture_dir / source["storage_reference"]
        if path.suffix == ".json":
            value = json.loads(path.read_text(encoding="utf-8"))
            fields = _walk(value)
        else:
            value = path.read_text(encoding="utf-8")
            fields = [("$", "str", value)]
        for field_path, kind, example in fields:
            top = field_path.removeprefix("$.").split(".", 1)[0].split("[", 1)[0]
            used = top in PARSER_FIELDS
            rows.append({
                "field_path": field_path,
                "type": kind,
                "source": source["type"],
                "example": str(example)[:160],
                "parser_used": used,
                "currently_persisted_business_field": top in PERSISTED_FIELDS,
                "raw_persisted": True,
                "potential_business_value": source["type"] in {"DETAIL", "SKU", "SHOP", "PROMOTION", "MEDIA", "EMBEDDED"},
            })
    return rows


def verify_capture(capture_id: str, *, root: Path | None = None) -> dict[str, Any]:
    directory = (root or capture_root()) / capture_id
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    verified: list[str] = []
    combined = ""
    for source in manifest["sources"]:
        path = directory / source["storage_reference"]
        data = path.read_bytes()
        if len(data) != source["size"] or _sha(data) != source["sha256"]:
            raise RawCaptureError(f"source verification failed: {path.name}")
        if path.suffix == ".json":
            json.loads(data)
        combined += data.decode("utf-8", errors="replace")
        verified.append(source["type"])
    upload_ref = manifest["product_upload"]
    upload_data = (directory / upload_ref["storage_reference"]).read_bytes()
    if _sha(upload_data) != upload_ref["sha256"]:
        raise RawCaptureError("product upload hash mismatch")
    json.loads(upload_data)
    if (SENSITIVE_TEXT_RE.search(combined) or UNRELATED_SYSTEM_UI_RE.search(combined)
            or re.search(r'"(?:device_key|lease_token)"\s*:', upload_data.decode("utf-8"), re.I)):
        raise RawCaptureError("sensitive credential marker found")
    return {"capture_id": capture_id, "verified_sources": verified, "hashes_valid": True, "json_deserializable": True, "sensitive_credentials_found": False}


def resanitize_capture(capture_id: str, *, root: Path | None = None) -> dict[str, Any]:
    """Apply the current minimum filter to an existing capture and refresh hashes atomically."""
    directory = (root or capture_root()) / capture_id
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for source in manifest["sources"]:
        path = directory / source["storage_reference"]
        if path.suffix == ".json":
            data = _json_bytes(sanitize(json.loads(path.read_text(encoding="utf-8"))))
        else:
            filtered = sanitize(path.read_text(encoding="utf-8"))
            data = (filtered + ("" if filtered.endswith("\n") else "\n")).encode("utf-8")
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(path)
        source["size"] = len(data)
        source["sha256"] = _sha(data)
    inventory = build_field_inventory(directory, manifest)
    (directory / "field-inventory.json").write_bytes(_json_bytes(inventory))
    manifest["sensitive_data_filter"]["last_applied_at"] = _iso()
    temporary_manifest = manifest_path.with_suffix(".json.tmp")
    temporary_manifest.write_bytes(_json_bytes(manifest))
    temporary_manifest.replace(manifest_path)
    verify_capture(capture_id, root=root)
    return manifest


def replay_capture(capture_id: str, *, root: Path | None = None) -> dict[str, Any]:
    directory = (root or capture_root()) / capture_id
    verify = verify_capture(capture_id, root=root)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    upload = json.loads((directory / manifest["product_upload"]["storage_reference"]).read_text(encoding="utf-8"))
    parsed = {field: upload.get(field) for field in PARSER_FIELDS if field in upload}
    decision = evaluate(parsed)
    normalized = normalized_snapshot(parsed, decision)
    return {
        "mode": "dry-run-analysis",
        "network_access": False,
        "capture_id": capture_id,
        "parser": {"version": parsed.get("parser_version"), "result": parsed},
        "normalizer": normalized,
        "quality_gate": {
            "accepted": decision.accepted,
            "page_status": decision.page_status,
            "parse_status": decision.parse_status,
            "quality_status": decision.quality_status,
            "missing_fields": list(decision.missing_fields),
            "errors": list(decision.error_codes),
            "warnings": list(decision.warnings),
        },
        "verification": verify,
    }
