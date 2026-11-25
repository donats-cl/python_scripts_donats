"""Local web UI: live flow list, request/response inspector, export."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .store import Store, to_jsonl

STATIC_DIR = Path(__file__).with_name("static")


def create_app(store: Store) -> FastAPI:
    app = FastAPI(title="readnet", version="0.1", docs_url=None, redoc_url=None)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index():
        f = STATIC_DIR / "index.html"
        if not f.exists():
            raise HTTPException(500, "static/index.html missing")
        return FileResponse(str(f))

    @app.get("/api/summary")
    def summary():
        return store.stats()

    @app.get("/api/flows")
    def flows(limit: int = Query(500, ge=1, le=5000), q: str | None = None):
        return {"flows": store.flows(limit=limit, query=q)}

    @app.get("/api/flows/{fid}")
    def flow_detail(fid: str, max_chunk: int = Query(262144, ge=1024, le=4 * 1024 * 1024)):
        detail = store.flow_detail(fid, max_chunk=max_chunk)
        if detail is None:
            raise HTTPException(404, "flow not found")
        return detail

    @app.get("/api/dns")
    def dns(limit: int = Query(300, ge=1, le=5000)):
        return {"dns": store.dns(limit=limit)}

    @app.get("/api/export")
    def export(format: str = "jsonl", max_chunk: int = Query(262144, ge=1024, le=4 * 1024 * 1024)):
        items = store.export_flows(max_chunk=max_chunk)
        if format == "json":
            return JSONResponse(items)
        body = to_jsonl(items)
        return Response(body, media_type="application/x-ndjson",
                        headers={"Content-Disposition": 'attachment; filename="readnet-export.jsonl"'})

    @app.get("/api/health")
    def health():
        return {"ok": True}

    return app


def serve(store: Store, host: str = "127.0.0.1", port: int = 8080):
    import uvicorn

    app = create_app(store)
    cfg = uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(cfg)
    server.run()
    return server


def serve_background(store: Store, host: str = "127.0.0.1", port: int = 8080):
    import threading

    import uvicorn

    app = create_app(store)
    cfg = uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(cfg)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    return server
