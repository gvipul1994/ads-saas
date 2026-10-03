import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import auth, accounts, google_oauth, recommendations, audit
from app.core.scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Ads Optimizer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(google_oauth.router)
app.include_router(accounts.router)
app.include_router(recommendations.router)
app.include_router(audit.router)


@app.on_event("startup")
def on_startup():
    # For a real deployment, replace create_all with Alembic migrations
    # (alembic/ is scaffolded but not yet populated with a first migration).
    Base.metadata.create_all(bind=engine)
    if settings.environment != "test":
        start_scheduler()


@app.get("/health")
def health():
    return {"status": "ok"}
