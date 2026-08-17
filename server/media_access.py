"""Short-lived tenant-scoped URLs for files previously exposed by StaticFiles."""

from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import quote

from server.config import settings


def _signature(path: str, enterprise_id: int, workspace_id: int, expires: int) -> str:
    message = f"{path}\n{enterprise_id}\n{workspace_id}\n{expires}".encode("utf-8")
    return hmac.new(settings.jwt_secret.get_secret_value().encode("utf-8"), message, hashlib.sha256).hexdigest()


def signed_media_url(path: str, enterprise_id: int, workspace_id: int, ttl_seconds: int = 300) -> str:
    normalized = path.replace("\\", "/").lstrip("/")
    expires = int(time.time()) + max(30, min(ttl_seconds, 3600))
    signature = _signature(normalized, enterprise_id, workspace_id, expires)
    return (f"/media/{quote(normalized)}?enterprise_id={enterprise_id}&workspace_id={workspace_id}"
            f"&expires={expires}&signature={signature}")


def verify_media_signature(path: str, enterprise_id: int, workspace_id: int,
                           expires: int, signature: str) -> bool:
    if expires < int(time.time()) or expires > int(time.time()) + 3605:
        return False
    expected = _signature(path.replace("\\", "/").lstrip("/"), enterprise_id, workspace_id, expires)
    return hmac.compare_digest(expected, signature)
