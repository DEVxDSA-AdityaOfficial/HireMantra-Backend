"""HireMantra FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database.database import Base, engine
from database import models  # noqa: F401 — register models for metadata
from middleware.auth_middleware import JWTAuthMiddleware
from modules.authentication.authentication_controller import authRouter
from modules.Broadcasting.broadcasting_controller import broadcastingRouter
from modules.onboarding.onboarding_controller import onboardRouter


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="HireMantra API", lifespan=lifespan)

app.add_middleware(JWTAuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(authRouter, prefix="/api/auth")
app.include_router(onboardRouter, prefix="/api/onboarding")
app.include_router(broadcastingRouter, prefix="/api/broadcasting")


@app.get("/health")
def health():
    return {"status": "ok"}
