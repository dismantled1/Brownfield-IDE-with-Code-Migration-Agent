"""
Brownfield IDE — FastAPI Application Entry Point
================================================
Phase 1: IDE Foundation

Future phases will register additional routers here:
  - Phase 2: /api/analysis/
  - Phase 3: /api/search/
  - Phase 4: /api/impact/
  - Phase 5: /api/agent/
  - Phase 6: /api/validation/
"""

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.routers import filesystem, workspace, terminal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Brownfield IDE API",
    description=(
        "Backend API for the Brownfield Development Environment. "
        "Phases 1-4: IDE Foundation, Analysis, Search, Impact."
    ),
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # NOTE: wildcard origins are incompatible with credentialed requests
    # (browsers reject "*" + credentials). The frontend is served same-origin
    # and sends no credentials, so this stays False.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# API Routers
# ---------------------------------------------------------------------------

# Phase 1
app.include_router(filesystem.router, prefix="/api/fs",        tags=["Filesystem"])
app.include_router(workspace.router,  prefix="/api/workspace", tags=["Workspace"])
app.include_router(terminal.router,                            tags=["Terminal"])

# ---------------------------------------------------------------------------
# Phase 2–6 Extension Points (register here when implemented)
# ---------------------------------------------------------------------------
from backend.routers import analysis   # Phase 2
app.include_router(analysis.router, prefix="/api/analysis", tags=["Analysis"])
from backend.routers import search     # Phase 3
app.include_router(search.router, prefix="/api/search", tags=["Search"])
from backend.routers import impact     # Phase 4
app.include_router(impact.router, prefix="/api/impact", tags=["Impact"])
from backend.routers import agent       # Phase 5
app.include_router(agent.router, prefix="/api/agent", tags=["Agent"])
from backend.routers import validation  # Phase 6
app.include_router(validation.router, prefix="/api/validation", tags=["Validation"])
from backend.routers import source       # Phase 7
app.include_router(source.router, prefix="/api/source", tags=["Source Update"])
from backend.routers import migration    # Phase 2 Code Migration Agent
app.include_router(migration.router, prefix="/api/migration", tags=["Migration Agent"])
from backend.routers import migration_agent  # Phase 3 AI Migration Agent (code generation)
app.include_router(migration_agent.router, prefix="/api/migration", tags=["Migration Agent (Phase 3)"])
from backend.routers import migration_validation  # Phase 4 Migration Validation & Approval
app.include_router(migration_validation.router, prefix="/api/migration", tags=["Migration Validation (Phase 4)"])
from backend.routers import migration_apply  # Phase 5 Migration Application Engine
app.include_router(migration_apply.router, prefix="/api/migration", tags=["Migration Apply (Phase 5)"])
from backend.routers import migration_orchestrator  # Phase 6 Migration Orchestrator & Workflow
app.include_router(migration_orchestrator.router, prefix="/api/migration", tags=["Migration Orchestrator (Phase 6)"])

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health", tags=["System"])
async def health():
    return {"status": "ok", "phase": 7, "name": "Brownfield IDE"}

# ---------------------------------------------------------------------------
# Static frontend (must be LAST so API routes take precedence)
# ---------------------------------------------------------------------------

_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

if _FRONTEND_DIR.exists():
    # Serve index.html for the root
    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse(str(_FRONTEND_DIR / "index.html"))

    # Mount everything else as static files
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR)), name="frontend")
else:
    logger.warning(f"Frontend directory not found: {_FRONTEND_DIR}")

# ---------------------------------------------------------------------------
# Global error handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Log the full traceback server-side, but don't leak internal details
    # (exception messages can expose absolute paths, etc.) to the client.
    logger.error(f"Unhandled error on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error"},
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_excludes=["frontend/*"],
    )
