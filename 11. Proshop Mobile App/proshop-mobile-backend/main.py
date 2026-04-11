"""
ProShop Mobile Backend — FastAPI Application
Wraps ProShop ERP GraphQL API with clean REST endpoints.

Run with: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from graphql.client import get_client
from api import workorders, parts, search, chat, qr, dashboard, count_parts
from models.schemas import StandardResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: authenticate with ProShop. Shutdown: cleanup."""
    logger.info("Starting ProShop Mobile Backend...")
    try:
        client = get_client()
        if client.is_connected():
            logger.info("ProShop connection established")
        else:
            logger.warning("Could not connect to ProShop on startup — will retry on first request")
    except Exception as e:
        logger.warning(f"ProShop startup connection failed: {e} — will retry on first request")
    yield
    logger.info("Shutting down ProShop Mobile Backend")


app = FastAPI(
    title="ProShop Mobile API",
    description="REST API for querying ProShop ERP from the shop floor",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow requests from local network devices and the PWA frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount PWA frontend if it exists
frontend_path = os.path.join(os.path.dirname(__file__), "..", "proshop-mobile-frontend")
if os.path.isdir(frontend_path):
    # Serve sw.js and index.html with no-cache headers so browser always gets fresh versions
    @app.get("/app/sw.js")
    async def service_worker():
        return FileResponse(
            os.path.join(frontend_path, "sw.js"),
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.get("/app/")
    @app.get("/app/index.html")
    async def frontend_index():
        return FileResponse(
            os.path.join(frontend_path, "index.html"),
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    app.mount("/app", StaticFiles(directory=frontend_path, html=True), name="frontend")

# Include API routers
app.include_router(workorders.router)
app.include_router(parts.router)
app.include_router(search.router)
app.include_router(chat.router)
app.include_router(qr.router)
app.include_router(dashboard.router)
app.include_router(count_parts.router)


@app.get("/api/health", response_model=StandardResponse, tags=["System"])
async def health():
    """Health check — server status and ProShop connection."""
    start = time.time()
    client = get_client()
    connected = client.is_connected()
    cache_stats = client.get_cache_stats()

    return StandardResponse(
        success=connected,
        data={
            "status": "ok" if connected else "degraded",
            "proshop_connected": connected,
            "cache": cache_stats,
        },
        meta={"query_time_ms": round((time.time() - start) * 1000)},
    )


@app.post("/api/cache/clear", response_model=StandardResponse, tags=["System"])
async def clear_cache():
    """Clear the response cache."""
    client = get_client()
    client.clear_cache()
    return StandardResponse(data={"message": "Cache cleared"})


if __name__ == "__main__":
    import uvicorn
    import ssl

    cert_dir = os.path.join(os.path.dirname(__file__), "certs")
    cert_file = os.path.join(cert_dir, "cert.pem")
    key_file = os.path.join(cert_dir, "key.pem")

    # Use HTTPS if certs exist (required for camera access on mobile)
    if os.path.exists(cert_file) and os.path.exists(key_file):
        logger.info("Starting with HTTPS (camera access enabled for mobile)")
        uvicorn.run(
            "main:app", host="0.0.0.0", port=8000, reload=True,
            ssl_certfile=cert_file, ssl_keyfile=key_file,
        )
    else:
        logger.info("Starting with HTTP (no certs found — camera won't work on mobile)")
        uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
