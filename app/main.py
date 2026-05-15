from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from .config import get_settings
from .db import engine, SessionLocal
from .errors import install_error_handlers
from .middleware import RequestContextMiddleware
from .models import Base
from .routers import cart, catalog, events, favorites, home, orders, system
from .seed import seed_database
from .services import demo_metadata


settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.0")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app.add_middleware(RequestContextMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.cors_origins.strip() == "*" else [item.strip() for item in settings.cors_origins.split(",") if item.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[item.strip() for item in settings.trusted_hosts.split(",") if item.strip()] or ["*"],
)


install_error_handlers(app)

app.include_router(system.router)
app.include_router(catalog.router)
app.include_router(favorites.router)
app.include_router(cart.router)
app.include_router(home.router)
app.include_router(orders.router)
app.include_router(events.router)


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    if settings.auto_seed:
        with SessionLocal() as session:
            seed_database(session)


@app.get("/healthz")
def healthcheck() -> dict:
    return {"status": "ok", **demo_metadata()}


@app.get("/")
def root() -> dict:
    return {
        "service": settings.app_name,
        "docs": "/docs",
        "openapi": "/openapi.json",
        **demo_metadata(),
    }
