"""FastAPI 入口：对接 Vue 管理端 + App API。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server.config import IMAGE_DIR, settings
from server.db import close_pool, init_pool
from server.routers import accounts, auth, cast, dashboard, devices, excel_match, ota, platforms, products, reports, tasks, users
from server.ws_hub import router as ws_router

STATIC_DIR = Path(__file__).resolve().parent / "static"
WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    init_pool()
    from server.migrate import ensure_schema_patches

    ensure_schema_patches()
    yield
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
app.include_router(users.router)
app.include_router(dashboard.router)
app.include_router(platforms.router)
app.include_router(devices.router)
app.include_router(tasks.router)
app.include_router(products.router)
app.include_router(excel_match.router)
app.include_router(accounts.router)
app.include_router(reports.router)
app.include_router(ota.router)
app.include_router(cast.router)
app.include_router(ws_router)

app.mount("/media", StaticFiles(directory=str(IMAGE_DIR)), name="media")
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
