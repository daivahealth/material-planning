from contextlib import asynccontextmanager
import logging
import os
import uuid

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.db import engine
from app.db import Base
import app.models  # noqa: F401 — register all ORM models

from app.api import masters, settings, imports, indents, classification, scheduler as scheduler_router
from app.api import data_mining as data_mining_router
from app.api import consumption as consumption_router
from app.api import outbound as outbound_router
from app.api import purchase_requests as purchase_requests_router
from app.api import auth as auth_router
from app.api import users as users_router
from app.api import audit as audit_router
from app.api import security as security_router
from app import scheduler as scheduler_svc

from app.config import settings as app_settings

_LEVEL = getattr(logging, (app_settings.log_level or "INFO").upper(), logging.INFO)
logging.basicConfig(
    level=_LEVEL,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Row-level mining detail and per-item indent detail are DEBUG. They are noisy
# and can surface source data in logs, so they follow LOG_LEVEL (default INFO)
# instead of being pinned to DEBUG.
logging.getLogger("data_mining").setLevel(_LEVEL)
logging.getLogger("indent").setLevel(_LEVEL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables (handled by Alembic in production; keep for tests/dev)
    Base.metadata.create_all(bind=engine)
    scheduler_svc.start_scheduler()
    yield
    scheduler_svc.stop_scheduler()


app = FastAPI(
    title="Hospital Material Planning",
    version="1.0.0",
    lifespan=lifespan,
    # When served under a reverse-proxy context path, set ROOT_PATH (e.g.
    # "/material-planning") so /docs and generated URLs include the prefix.
    root_path=os.getenv("ROOT_PATH", ""),
)

# Paths reachable regardless of the IP allowlist. `/health` must stay open so
# container/load-balancer health probes keep working when the filter is on.
_IP_FILTER_EXEMPT = {"/health"}


def client_ip_for(request) -> str | None:
    """Source address used by the IP filter.

    Uses the real socket peer unless TRUST_PROXY_HEADERS is enabled — the
    X-Forwarded-For header is attacker-controlled unless a trusted proxy
    overwrites it, so honouring it by default would make the filter bypassable.
    """
    if app_settings.trust_proxy_headers:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return getattr(getattr(request, "client", None), "host", None)


@app.middleware("http")
async def ip_allowlist_middleware(request, call_next):
    """Reject requests from addresses outside the configured allowlist.

    Inactive while no entries are configured (see services/ip_allowlist), so
    the default deployment is unaffected.
    """
    if request.url.path not in _IP_FILTER_EXEMPT:
        from app.db import SessionLocal
        from app.services import ip_allowlist

        ip = client_ip_for(request)
        db = SessionLocal()
        try:
            allowed, enforcing = ip_allowlist.is_allowed(db, ip)
        finally:
            db.close()
        if enforcing and not allowed:
            logging.getLogger("security").warning(
                "blocked request from %s to %s (not in IP allowlist)", ip, request.url.path
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Access from your network address is not permitted."},
            )
    return await call_next(request)


# Paths that legitimately need CDN-loaded assets (Swagger UI / ReDoc); a strict
# CSP would break them, so they are excluded from that one header.
_DOCS_PATHS = {"/docs", "/redoc", "/openapi.json"}


@app.middleware("http")
async def security_headers_middleware(request, call_next):
    """Baseline hardening headers on every response.

    HSTS is emitted **only for HTTPS requests** — sending it over plain HTTP is
    ignored by browsers and would wrongly pin clients that legitimately reach
    the API over http (e.g. an internal deployment without TLS).
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    if request.url.path not in _DOCS_PATHS:
        # This is a JSON API: it should load nothing and never be framed.
        response.headers.setdefault(
            "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
    forwarded_proto = request.headers.get("x-forwarded-proto") if app_settings.trust_proxy_headers else None
    scheme = (forwarded_proto or request.url.scheme or "").lower()
    if scheme == "https":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception):
    """Never return raw exception text to a client.

    Driver/connection errors carry internal hostnames, credentials fragments and
    stack context. The full detail is logged with a correlation id the caller
    can quote to support; the response body stays generic.
    """
    error_id = uuid.uuid4().hex[:12]
    logging.getLogger("app").exception(
        "unhandled error %s on %s %s", error_id, request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal error occurred. Quote reference "
                           f"{error_id} if you contact support.",
                 "error_id": error_id},
    )


app.add_middleware(
    CORSMiddleware,
    # Explicit origin allowlist — a wildcard with credentials is insecure and
    # rejected by browsers. Configure via CORS_ALLOW_ORIGINS.
    allow_origins=app_settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(audit_router.router)
app.include_router(security_router.router)
app.include_router(security_router.throttle_router)
app.include_router(masters.router)
app.include_router(settings.router)
app.include_router(imports.router)
app.include_router(indents.router)
app.include_router(classification.router)
app.include_router(scheduler_router.router)
app.include_router(data_mining_router.router)
app.include_router(consumption_router.router)
app.include_router(outbound_router.router)
app.include_router(purchase_requests_router.router)


@app.get("/health")
def health():
    return {"status": "ok"}
