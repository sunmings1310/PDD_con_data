"""APK 版本元数据：内存 + 落盘，供 App 校验 / Web 状态页。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from server.cast_state import cast_state
from server.config import settings


def apk_dir() -> Path:
    p = Path(settings.image_dir) / "apk"
    p.mkdir(parents=True, exist_ok=True)
    return p


def meta_path() -> Path:
    return apk_dir() / "meta.json"


def save_meta(version_name: str, version_code: int, size: int) -> dict[str, Any]:
    meta = {
        "version_name": (version_name or "").strip()[:32],
        "version_code": int(version_code or 0),
        "size": int(size or 0),
    }
    cast_state.set_apk_meta(meta["version_name"], meta["version_code"], meta["size"])
    try:
        meta_path().write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return meta


def load_meta() -> dict[str, Any]:
    mem = dict(cast_state.apk_meta or {})
    if mem.get("version_name"):
        return {
            "version_name": str(mem.get("version_name") or ""),
            "version_code": int(mem.get("version_code") or 0),
            "size": int(mem.get("size") or 0),
        }
    p = meta_path()
    if p.is_file():
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                meta = {
                    "version_name": str(obj.get("version_name") or ""),
                    "version_code": int(obj.get("version_code") or 0),
                    "size": int(obj.get("size") or 0),
                }
                cast_state.set_apk_meta(
                    meta["version_name"], meta["version_code"], meta["size"]
                )
                return meta
        except Exception:  # noqa: BLE001
            pass
    apk = apk_dir() / "latest.apk"
    if apk.is_file():
        return {"version_name": "", "version_code": 0, "size": apk.stat().st_size}
    return {"version_name": "", "version_code": 0, "size": 0}


def latest_payload() -> dict[str, Any]:
    apk = apk_dir() / "latest.apk"
    meta = load_meta()
    has = apk.is_file()
    size = apk.stat().st_size if has else int(meta.get("size") or 0)
    ver = str(meta.get("version_name") or "")
    code = int(meta.get("version_code") or 0)
    # 带版本查询串，避免花生壳/浏览器缓存一直下到旧 APK
    apk_url = ""
    if has:
        q = f"v={ver or '0'}&c={code}&s={size}"
        apk_url = f"/media/apk/latest.apk?{q}"
    return {
        "has_apk": has,
        "version_name": ver,
        "version_code": code,
        "size": size,
        "apk_url": apk_url,
    }
