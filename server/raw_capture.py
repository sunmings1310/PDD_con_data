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
DERIVED_ID_RE = re.compile(r"^cap-[A-Za-z0-9][A-Za-z0-9._-]{7,191}$")
FILTER_VERSION = "raw-sanitize-v2"
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
    def __init__(self, message: str, *, code: str = "RAW_CAPTURE_INVALID"):
        super().__init__(message)
        self.code = code


def capture_root() -> Path:
    return Path(os.environ.get("RAW_CAPTURE_DIR") or (DATA_DIR / "raw-captures"))


def _positive_id(value: Any, name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise RawCaptureError(f"{name} is required") from exc
    if parsed <= 0:
        raise RawCaptureError(f"{name} must be positive")
    return parsed


def _tenant_capture_dir(base: Path, enterprise_id: int, workspace_id: int, capture_id: str) -> Path:
    return base / f"enterprise-{enterprise_id}" / f"workspace-{workspace_id}" / capture_id


def _resolve_capture_dir(
    capture_id: str,
    *,
    root: Path | None,
    enterprise_id: int | None,
    workspace_id: int | None,
) -> Path:
    base = (root or capture_root()).resolve()
    if (enterprise_id is None) != (workspace_id is None):
        raise RawCaptureError("enterprise_id and workspace_id must be provided together")
    if enterprise_id is not None and workspace_id is not None:
        return _tenant_capture_dir(
            base,
            _positive_id(enterprise_id, "enterprise_id"),
            _positive_id(workspace_id, "workspace_id"),
            capture_id,
        )
    # Explicit legacy-only fallback. New tenant captures are never searched by capture_id.
    return base / capture_id


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


def _capture_identity(
    body: Any,
    device: Mapping[str, Any],
    *,
    capture_id: str,
    platform: str,
    product_id: str,
) -> dict[str, Any]:
    return {
        "capture_id": capture_id,
        "enterprise_id": _positive_id(device.get("enterprise_id"), "enterprise_id"),
        "workspace_id": _positive_id(device.get("workspace_id"), "workspace_id"),
        "platform": platform,
        "platform_product_id": product_id,
        "task_id": getattr(body, "task_id", None),
        "job_id": getattr(body, "job_id", None),
        "attempt_id": getattr(body, "attempt_id", None),
        "device_id": _positive_id(device.get("device_id"), "device_id"),
    }


def _upload_bytes(body: Any) -> bytes:
    upload = sanitize(body.model_dump(mode="json") if hasattr(body, "model_dump") else dict(body))
    for field in ("raw_capture", "device_key", "lease_token", "idempotency_key", "worker_id"):
        upload.pop(field, None)
    return _json_bytes(upload)


def _manifest_contract(manifest: Mapping[str, Any]) -> tuple[str, str]:
    return str(manifest.get("identity_sha256") or ""), str(manifest.get("content_sha256") or "")


def _raise_capture_conflict(capture_id: str) -> None:
    raise RawCaptureError(
        f"capture_id identity or content conflict: {capture_id}",
        code="RAW_CAPTURE_CONFLICT",
    )


def persist_raw_capture(body: Any, device: Mapping[str, Any], *, root: Path | None = None) -> dict[str, Any] | None:
    raw_input = getattr(body, "raw_capture", None)
    if not raw_input:
        return None
    raw = sanitize(dict(raw_input))
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

    identity = _capture_identity(body, device, capture_id=capture_id, platform=platform, product_id=product_id)
    base = (root or capture_root()).resolve()
    target = _tenant_capture_dir(base, identity["enterprise_id"], identity["workspace_id"], capture_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{capture_id}-", dir=target.parent))
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
                "captured_at": (
                    _iso(source.get("captured_at_epoch_ms") or raw.get("collected_at_epoch_ms"))
                    if source.get("captured_at_epoch_ms") is not None or raw.get("collected_at_epoch_ms") is not None
                    else None
                ),
                "size": len(data),
                "sha256": _sha(data),
                "storage_reference": f"sources/{filename}",
                "content_type": content_type,
                "declared_content_type": original_content_type,
                "schema_hint": str(source.get("schema_hint") or "")[:128] or None,
                "parse_status": parse_status,
            })

        upload_bytes = _upload_bytes(body)
        parsed_dir = temp / "parsed"
        parsed_dir.mkdir()
        (parsed_dir / "product_upload.json").write_bytes(upload_bytes)
        source_inventory_sha256 = _sha(_json_bytes(manifest_sources))
        identity_sha256 = _sha(_json_bytes(identity))
        content_sha256 = _sha(_json_bytes({
            "source_inventory_sha256": source_inventory_sha256,
            "product_upload_sha256": _sha(upload_bytes),
        }))
        manifest = {
            **identity,
            "identity_contract_version": "raw-capture-identity-v1",
            "identity_sha256": identity_sha256,
            "source_inventory_sha256": source_inventory_sha256,
            "content_sha256": content_sha256,
            "captured_at": _iso(raw.get("collected_at_epoch_ms")),
            "collector_version": str(raw.get("collector_version") or "unknown")[:64],
            "parser_version": str(raw.get("parser_version") or getattr(body, "parser_version", "unknown"))[:64],
            "sources": manifest_sources,
            "product_upload": {
                "storage_reference": "parsed/product_upload.json",
                "size": len(upload_bytes),
                "sha256": _sha(upload_bytes),
            },
            "sensitive_data_filter": {
                "version": FILTER_VERSION,
                "excluded": ["Cookie", "Authorization", "session/access/refresh token", "lease_token", "device_key", "password/credential"],
                "mode": "key and line filtering plus sensitive URL query redaction",
            },
        }
        inventory = build_field_inventory(temp, manifest)
        (temp / "field-inventory.json").write_bytes(_json_bytes(inventory))
        manifest["field_inventory"] = "field-inventory.json"
        (temp / "manifest.json").write_bytes(_json_bytes(manifest))

        if target.exists():
            existing = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
            if _manifest_contract(existing) != (identity_sha256, content_sha256):
                _raise_capture_conflict(capture_id)
            return existing
        try:
            temp.rename(target)
        except FileExistsError:
            existing = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
            if _manifest_contract(existing) != (identity_sha256, content_sha256):
                _raise_capture_conflict(capture_id)
            return existing
        return manifest
    finally:
        if temp.exists():
            shutil.rmtree(temp, ignore_errors=True)


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


def _select_evidence_dir(original: Path, version: str) -> tuple[Path, str]:
    if version == "original":
        return original, "original"
    derived_root = original / "derived"
    if version == "latest_safe":
        candidates = sorted(
            (path for path in derived_root.iterdir() if path.is_dir()),
            key=lambda path: path.name,
        ) if derived_root.is_dir() else []
        if not candidates:
            raise RawCaptureError("no derived evidence is available")
        return candidates[-1], candidates[-1].name
    if not DERIVED_ID_RE.fullmatch(version):
        raise RawCaptureError("invalid derived evidence version")
    return derived_root / version, version


def verify_capture(
    capture_id: str,
    *,
    root: Path | None = None,
    enterprise_id: int | None = None,
    workspace_id: int | None = None,
    version: str = "original",
) -> dict[str, Any]:
    original = _resolve_capture_dir(
        capture_id,
        root=root,
        enterprise_id=enterprise_id,
        workspace_id=workspace_id,
    )
    directory, selected_version = _select_evidence_dir(original, version)
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
    return {
        "capture_id": capture_id,
        "evidence_version": selected_version,
        "verified_sources": verified,
        "hashes_valid": True,
        "json_deserializable": True,
        "sensitive_credentials_found": False,
    }


def resanitize_capture(
    capture_id: str,
    *,
    root: Path | None = None,
    enterprise_id: int | None = None,
    workspace_id: int | None = None,
    filter_version: str = FILTER_VERSION,
    reason: str = "sensitive-data-filter-upgrade",
) -> dict[str, Any]:
    """Create a derived safe version without changing original evidence bytes or manifest."""
    original = _resolve_capture_dir(
        capture_id,
        root=root,
        enterprise_id=enterprise_id,
        workspace_id=workspace_id,
    )
    original_manifest_path = original / "manifest.json"
    original_manifest_bytes = original_manifest_path.read_bytes()
    manifest = json.loads(original_manifest_bytes)
    original_file_hashes = {
        source["storage_reference"]: _sha((original / source["storage_reference"]).read_bytes())
        for source in manifest["sources"]
    }
    upload_reference = manifest["product_upload"]["storage_reference"]
    original_file_hashes[upload_reference] = _sha((original / upload_reference).read_bytes())
    verify_capture(
        capture_id,
        root=root,
        enterprise_id=enterprise_id,
        workspace_id=workspace_id,
    )

    created_at = _iso()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    version_seed = _sha(_json_bytes({
        "capture_id": capture_id,
        "filter_version": filter_version,
        "created_at": created_at,
        "reason": reason,
    }))[:12]
    derived_id = f"{capture_id}.resanitized.{stamp}.{version_seed}"
    derived_root = original / "derived"
    derived_root.mkdir(exist_ok=True)
    target = derived_root / derived_id
    temp = Path(tempfile.mkdtemp(prefix=f".{derived_id}-", dir=derived_root))
    try:
        (temp / "sources").mkdir()
        derived_sources: list[dict[str, Any]] = []
        for source in manifest["sources"]:
            source_path = original / source["storage_reference"]
            target_path = temp / source["storage_reference"]
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if source_path.suffix == ".json":
                data = _json_bytes(sanitize(json.loads(source_path.read_text(encoding="utf-8"))))
            else:
                filtered = sanitize(source_path.read_text(encoding="utf-8"))
                data = (filtered + ("" if filtered.endswith("\n") else "\n")).encode("utf-8")
            target_path.write_bytes(data)
            derived_sources.append({**source, "size": len(data), "sha256": _sha(data)})

        source_upload = original / upload_reference
        derived_upload = temp / upload_reference
        derived_upload.parent.mkdir(parents=True, exist_ok=True)
        upload_data = _json_bytes(sanitize(json.loads(source_upload.read_text(encoding="utf-8"))))
        derived_upload.write_bytes(upload_data)
        derived_manifest = {
            **{key: value for key, value in manifest.items() if key not in {
                "sources", "product_upload", "field_inventory", "sensitive_data_filter",
            }},
            "evidence_kind": "derived_resanitized",
            "derived_capture_id": derived_id,
            "original_capture_id": capture_id,
            "original_manifest_sha256": _sha(original_manifest_bytes),
            "original_source_hashes": original_file_hashes,
            "filter_version": str(filter_version)[:128],
            "created_at": created_at,
            "derivation_reason": str(reason)[:512],
            "sources": derived_sources,
            "product_upload": {
                **manifest["product_upload"],
                "size": len(upload_data),
                "sha256": _sha(upload_data),
            },
            "sensitive_data_filter": {
                **manifest.get("sensitive_data_filter", {}),
                "version": str(filter_version)[:128],
                "applied_at": created_at,
            },
        }
        derived_manifest["source_inventory_sha256"] = _sha(_json_bytes(derived_sources))
        derived_manifest["content_sha256"] = _sha(_json_bytes({
            "source_inventory_sha256": derived_manifest["source_inventory_sha256"],
            "product_upload_sha256": derived_manifest["product_upload"]["sha256"],
        }))
        inventory = build_field_inventory(temp, derived_manifest)
        (temp / "field-inventory.json").write_bytes(_json_bytes(inventory))
        derived_manifest["field_inventory"] = "field-inventory.json"
        (temp / "manifest.json").write_bytes(_json_bytes(derived_manifest))
        temp.rename(target)
    finally:
        if temp.exists():
            shutil.rmtree(temp, ignore_errors=True)

    if original_manifest_path.read_bytes() != original_manifest_bytes:
        raise RawCaptureError("original manifest changed during derivation")
    for reference, expected_hash in original_file_hashes.items():
        if _sha((original / reference).read_bytes()) != expected_hash:
            raise RawCaptureError("original evidence changed during derivation")
    verify_capture(
        capture_id,
        root=root,
        enterprise_id=enterprise_id,
        workspace_id=workspace_id,
        version=derived_id,
    )
    return derived_manifest


def replay_capture(
    capture_id: str,
    *,
    root: Path | None = None,
    enterprise_id: int | None = None,
    workspace_id: int | None = None,
    version: str = "original",
) -> dict[str, Any]:
    original = _resolve_capture_dir(
        capture_id,
        root=root,
        enterprise_id=enterprise_id,
        workspace_id=workspace_id,
    )
    directory, selected_version = _select_evidence_dir(original, version)
    verify = verify_capture(
        capture_id,
        root=root,
        enterprise_id=enterprise_id,
        workspace_id=workspace_id,
        version=selected_version,
    )
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    upload = json.loads((directory / manifest["product_upload"]["storage_reference"]).read_text(encoding="utf-8"))
    parsed = {field: upload.get(field) for field in PARSER_FIELDS if field in upload}
    decision = evaluate(parsed)
    normalized = normalized_snapshot(parsed, decision)
    return {
        "mode": "dry-run-analysis",
        "network_access": False,
        "capture_id": capture_id,
        "evidence_version": selected_version,
        "derived": selected_version != "original",
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
