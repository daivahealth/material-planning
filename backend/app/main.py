from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import engine
from app.db import Base
import app.models  # noqa: F401 — register all ORM models

from app.api import masters, settings, imports, indents, classification, scheduler as scheduler_router
from app.api import data_mining as data_mining_router
from app.api import consumption as consumption_router
from app import scheduler as scheduler_svc

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Show DEBUG-level data_mining logs — change to INFO to quiet row-level detail
logging.getLogger("data_mining").setLevel(logging.DEBUG)
# Show DEBUG-level indent calculation logs — change to INFO to quiet per-item detail
logging.getLogger("indent").setLevel(logging.DEBUG)


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
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(masters.router)
app.include_router(settings.router)
app.include_router(imports.router)
app.include_router(indents.router)
app.include_router(classification.router)
app.include_router(scheduler_router.router)
app.include_router(data_mining_router.router)
app.include_router(consumption_router.router)


@app.get("/health")
def health():
    return {"status": "ok"}
