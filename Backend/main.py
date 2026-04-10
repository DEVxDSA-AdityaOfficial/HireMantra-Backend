"""HireMantra FastAPI application entrypoint."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database.database import Base, engine
from database import models  # noqa: F401 — register models for metadata
from middleware.auth_middleware import JWTAuthMiddleware
from modules.authentication.authentication_controller import authRouter
from modules.Broadcasting.broadcasting_controller import broadcastingRouter
from modules.Careers.careers_controller import careersRouter
from modules.onboarding.onboarding_controller import onboardRouter
from modules.communication.communication_controller import communicationRouter
from modules.parser.parser_controller import parserRouter


def _configure_app_logging() -> None:
    """
    Uvicorn leaves the root logger at WARNING, so logger.info() from app code is hidden.
    Attach INFO handlers to ``utils`` and ``modules`` so OTP/SMTP and auth logs appear.
    """
    level_name = (os.getenv("LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    fmt = logging.Formatter("%(levelname)s [%(name)s] %(message)s")
    for name in ("utils", "modules"):
        lg = logging.getLogger(name)
        if lg.handlers:
            lg.setLevel(level)
            continue
        h = logging.StreamHandler()
        h.setFormatter(fmt)
        h.setLevel(level)
        lg.addHandler(h)
        lg.setLevel(level)
        lg.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_app_logging()
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
app.include_router(careersRouter, prefix="/api/careers")
app.include_router(parserRouter, prefix="/api/parser")
app.include_router(communicationRouter, prefix="/api/communication")


@app.get("/health")
def health():
    return {"status": "ok"}
