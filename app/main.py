from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.asr import router as asr_router

from app.api import (
    auth,
    crash_test,
    datasets,
    evaluations,
    playground,
    projects,
    sdk,
)
from app.core.config import settings
from app.core.database import init_db
from app.services.natlas import NAtlasService


@asynccontextmanager
async def lifespan(
    app: FastAPI,
):
    init_db()

    yield


app = FastAPI(
    title=settings.app_name,
    description=(
        "Developer infrastructure for "
        "building, testing, evaluating, "
        "adapting and integrating applications "
        "powered by N-ATLAS."
    ),
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(
    auth.router
)

app.include_router(
    projects.router
)

app.include_router(
    playground.router
)

app.include_router(
    crash_test.router
)

app.include_router(
    asr_router
)

app.include_router(
    datasets.router
)

app.include_router(
    evaluations.router
)

app.include_router(
    sdk.router
)


@app.get("/")
def root():

    return {
        "name": settings.app_name,
        "status": "online",
        "version": "0.2.0",
        "message": (
            "N-ATLAS Forge backend is running."
        ),
    }


@app.get("/health")
def health():

    natlas = NAtlasService()

    return {
        "status": "healthy",
        "service": "natlas-forge-api",
        "environment": settings.app_env,
        "natlas_configured": natlas.configured,
    }