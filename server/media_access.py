"""Short-lived tenant-scoped URLs for files previously exposed by StaticFiles."""

from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import quote

from server.config import settings


def _signature(path: str, enterprise_id: int, workspace_id: int, expires: int,
               device_id: int | None = None) -> str:
    message = f"{path}\n{enterprise_id}\n{workspace_id}\n{expires}\n{device_id or 0}".encode("utf-8")
    return hmac.new(settings.jwt_secret.get_secret_value().encode("utf-8"), message, hashlib.sha256).hexdigest()


def signed_media_url(path: str, enterprise_id: int, workspace_id: int, ttl_seconds: int = 300,
                     device_id: int | None = None) -> str:
    normalized = path.replace("\\", "/").lstrip("/")
    expires = int(time.time()) + max(30, min(ttl_seconds, 3600))
    signature = _signature(normalized, enterprise_id, workspace_id, expires, device_id)
    device_query = f"&device_id={device_id}" if device_id is not None else ""
    return (f"/media/{quote(normalized)}?enterprise_id={enterprise_id}&workspace_id={workspace_id}"
            f"&expires={expires}{device_query}&signature={signature}")


def verify_media_signature(path: str, enterprise_id: int, workspace_id: int,
                           expires: int, signature: str, device_id: int | None = None) -> bool:
    if expires < int(time.time()) or expires > int(time.time()) + 3605:
        return False
    expected = _signature(path.replace("\\", "/").lstrip("/"), enterprise_id, workspace_id,
                          expires, device_id)
    return hmac.compare_digest(expected, signature)
