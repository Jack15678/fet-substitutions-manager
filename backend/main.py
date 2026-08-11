"""
FastAPI Backend per Gestor de Substitucions
Versió modularitzada amb routes, schemas i helpers separats
"""
# IMPORTANT: Carregar variables d'entorn ABANS de qualsevol altre import
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, Request
import logging
import time
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# SQLAlchemy imports
from database import create_auth_tables
from auth_utils import ensure_default_users, get_current_user, require_admin
from config.auth import IS_DEVELOPMENT
from rate_limit import limiter

from auth_utils import decode_access_token
from time_utils import hong_kong_now

access_logger = logging.getLogger("uvicorn.error")
access_logger.setLevel(logging.INFO)

# Crear taules si no existeixen
create_auth_tables()
ensure_default_users()

# Les taules de dades (exam_*, etc.) es creen automàticament
# dins de get_data_db_session() la primera vegada que s'usa

# Fora de desenvolupament no es publica ni la documentació interactiva ni
# l'esquema OpenAPI: donen el mapa complet de l'API a qui no ha entrat.
app = FastAPI(
    title="Gestor Substitucions API",
    description="API REST per gestionar substitucions i vigilàncies",
    version="1.0.0",
    docs_url="/docs" if IS_DEVELOPMENT else None,
    redoc_url="/redoc" if IS_DEVELOPMENT else None,
    openapi_url="/openapi.json" if IS_DEVELOPMENT else None,
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = int((time.perf_counter() - start) * 1000)
        _log_request(request, duration_ms, 500)
        raise
    duration_ms = int((time.perf_counter() - start) * 1000)
    _log_request(request, duration_ms, response.status_code)
    return response


def _log_request(request: Request, duration_ms: int, status_code: int) -> None:
    username = "-"
    role = "-"
    instit = "-"
    token = request.cookies.get("gestor_token")
    if token:
        try:
            payload = decode_access_token(token)
            username = payload.get("sub") or "-"
            role = payload.get("role") or "-"
            instit = payload.get("institucio") or "-"
        except Exception:
            pass

    path = request.url.path
    query = request.url.query
    full_path = f"{path}?{query}" if query else path
    ip = request.client.host if request.client else "-"
    timestamp = hong_kong_now().strftime("%Y-%m-%d %H:%M:%S %Z")
    access_logger.info(
        f"{timestamp} | {username} ({role}@{instit}) | {ip} | {request.method} {full_path} | {status_code} | {duration_ms}ms"
    )

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS - permet crides des del frontend Vue (localhost:5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== Registre de routers modularitzats =====
from routes import auth, settings, users, cursos, dades, rescheduling

app.include_router(auth.router)
app.include_router(settings.router, dependencies=[Depends(require_admin)])
app.include_router(users.router, dependencies=[Depends(get_current_user)])
app.include_router(cursos.router, dependencies=[Depends(get_current_user)])
app.include_router(dades.router, dependencies=[Depends(require_admin)])
app.include_router(rescheduling.router, dependencies=[Depends(get_current_user)])


# ===== Endpoints generals (no modularitzats) =====

@app.get("/")
async def root():
    """Health check"""
    return {
        "status": "ok",
        "message": "Gestor Substitucions API",
        "docs": "/docs"
    }


@app.get("/api/health")
async def health():
    """Health check per l'API"""
    return {"status": "ok"}


# ===== Punt d'entrada per executar amb uvicorn =====
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
