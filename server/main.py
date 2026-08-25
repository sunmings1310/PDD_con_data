"""FastAPI 入口：对接 Vue 管理端 + App API。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from contextlib import suppress
import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server.config import IMAGE_DIR, settings
from server.db import close_pool, init_pool
from server.routers import accounts, auth, cast, dashboard, devices, excel_match, ota, platforms, products, reports, tasks, users, jobs, management, enterprises
from server.ws_hub import hub as realtime_hub, router as ws_router
from server.media_access import verify_media_signature

STATIC_DIR = Path(__file__).resolve().parent / "static"
WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


def _reconcile_once() -> None:
    from server.db import get_conn
    from server.job_reconciliation import reconcile_oracle

    with get_conn() as conn:
        reconcile_oracle(conn.cursor(), limit=100)


async def _reconciliation_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(_reconcile_once)
        except Exception:  # reconciliation failures must not stop API serving
            import logging
            logging.getLogger("sjzq.reconciliation").exception("periodic reconciliation failed")
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(_: FastAPI):
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    init_pool()
    from server.migrate import ensure_schema_patches

    ensure_schema_patches()
    app_loop = asyncio.get_running_loop()
    realtime_hub.bind_loop(app_loop)
    reconciliation_task = asyncio.create_task(_reconciliation_loop())
    try:
        yield
    finally:
        realtime_hub.unbind_loop(app_loop)
        reconciliation_task.cancel()
        with suppress(asyncio.CancelledError):
            await reconciliation_task
        close_pool()


app = FastAPI(title="多平台APP采集调度系统", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(enterprises.router)
app.include_router(users.router)
app.include_router(dashboard.router)
app.include_router(platforms.router)
app.include_router(devices.router)
app.include_router(tasks.router)
app.include_router(jobs.router)
app.include_router(management.router)
app.include_router(products.router)
app.include_router(excel_match.router)
app.include_router(accounts.router)
app.include_router(reports.router)
app.include_router(ota.router)
app.include_router(cast.router)
app.include_router(ws_router)

@app.get("/media/{media_path:path}")
def tenant_media(media_path: str, enterprise_id: int = Query(...), workspace_id: int = Query(...),
                 expires: int = Query(...), signature: str = Query(...),
                 device_id: int | None = Query(None)):
    normalized = media_path.replace("\\", "/").lstrip("/")
    if not verify_media_signature(normalized, enterprise_id, workspace_id, expires, signature, device_id):
        raise HTTPException(status_code=403, detail="media access denied")
    candidate = (IMAGE_DIR / normalized).resolve()
    if IMAGE_DIR.resolve() not in candidate.parents or not candidate.is_file():
        raise HTTPException(status_code=404, detail="media not found")
    if device_id is not None:
        from server.db import get_conn
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""SELECT COUNT(*) FROM SJZQ_DEVICE
                             WHERE DEVICE_ID=:device_id AND ENTERPRISE_ID=:enterprise_id
                               AND WORKSPACE_ID=:workspace_id AND REVOKED_AT IS NULL""",
                        {"device_id": device_id, "enterprise_id": enterprise_id,
                         "workspace_id": workspace_id})
            if int(cur.fetchone()[0] or 0) == 0:
                raise HTTPException(status_code=403, detail="media access denied")
    if not normalized.startswith("apk/"):
        from server.db import get_conn
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""SELECT COUNT(*) FROM SJZQ_PRODUCT_IMAGE
                             WHERE REL_PATH=:path AND ENTERPRISE_ID=:enterprise_id
                               AND WORKSPACE_ID=:workspace_id""",
                        {"path": normalized, "enterprise_id": enterprise_id,
                         "workspace_id": workspace_id})
            if int(cur.fetchone()[0] or 0) == 0:
                raise HTTPException(status_code=404, detail="media not found")
    return FileResponse(candidate)
if STATIC_DIR.exists():
    app.mount("/legacy-static", StaticFiles(directory=str(STATIC_DIR)), name="legacy_static")


@app.get("/api/health")
def health():
    ocr_ok = False
    try:
        from server.image_filter import _ocr_ready

        ocr_ok = bool(_ocr_ready())
    except Exception:  # noqa: BLE001
        ocr_ok = False
    return {
        "ok": True,
        "oracle": settings.oracle_dsn,
        "image_dir": str(IMAGE_DIR),
        "web_dist": WEB_DIST.exists(),
        "ocr_license_filter": ocr_ok,
    }


@app.get("/")
def index():
    index_file = WEB_DIST / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    # 开发期未 build 时回退提示
    legacy = STATIC_DIR / "index.html"
    if legacy.exists():
        return FileResponse(legacy)
    return {"ok": True, "message": "请先在 web/ 执行 npm run build，或 npm run dev 开发"}


if WEB_DIST.exists():
    assets = WEB_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        # API / media / ws 不走 SPA
        if full_path.startswith(("api/", "media/", "ws", "docs", "openapi")):
            return {"ok": False, "message": "not found"}
        candidate = WEB_DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(WEB_DIST / "index.html")


def run() -> None:
    import uvicorn

    uvicorn.run(
        "server.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    run()
