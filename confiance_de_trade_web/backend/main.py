"""FastAPI entry point for Confiance de Trade."""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from .engine.inference import InferenceEngine
from .engine.risk import RiskEventPayload
from .engine.score import ScoreEngine
from .ia.reasoner import ReasonerClient
from .watchers import exchange_status, macro, microstructure, onchain, regulatory, sessions, twitter_stream
from .watchers.router import EventRouter

LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"

load_dotenv(BASE_DIR / ".env", override=False)
load_dotenv(BASE_DIR / ".env.local", override=False)
load_dotenv(BASE_DIR / ".env.dev", override=False)
load_dotenv(BASE_DIR / ".env.example", override=False)

app = FastAPI(title="Confiance de Trade", version="0.1.0")


class AppState:
    def __init__(self) -> None:
        score_config = KNOWLEDGE_DIR / "score.yaml"
        self.score_engine = ScoreEngine(score_config)
        self.event_router = EventRouter(self.score_engine)
        self.reasoner = ReasonerClient()
        self.inference = InferenceEngine(self.reasoner)
        self.tasks: List[asyncio.Task] = []

    async def start(self) -> None:
        LOGGER.info("Starting background tasks")
        self.tasks.append(asyncio.create_task(self._score_loop(), name="score-loop"))
        self.tasks.append(sessions.create_task(KNOWLEDGE_DIR / "sessions.yaml", self.event_router))
        self.tasks.append(exchange_status.create_task(self.event_router))
        self.tasks.append(onchain.create_task(self.event_router))
        self.tasks.append(microstructure.create_task(self.event_router))
        self.tasks.append(macro.create_task(self.event_router, KNOWLEDGE_DIR / "scenarios.yaml"))
        self.tasks.append(regulatory.create_task(self.event_router, KNOWLEDGE_DIR / "scenarios.yaml"))
        self.tasks.append(
            twitter_stream.create_task(self.event_router, self.inference, KNOWLEDGE_DIR / "twitter_sources.yaml")
        )

    async def stop(self) -> None:
        LOGGER.info("Stopping background tasks")
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        await self.reasoner.close()

    async def _score_loop(self) -> None:
        while True:
            try:
                await self.score_engine.tick()
            except Exception as exc:  # pragma: no cover
                LOGGER.exception("Score loop error: %s", exc)
            await asyncio.sleep(1)


app.state.runtime = AppState()


@app.on_event("startup")
async def on_startup() -> None:
    await app.state.runtime.start()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await app.state.runtime.stop()


async def get_score_engine() -> ScoreEngine:
    return app.state.runtime.score_engine


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/api/score")
async def get_score(engine: ScoreEngine = Depends(get_score_engine)):
    state = await engine.get_state()
    return state.dict()


@app.post("/api/ingest")
async def ingest_event(payload: RiskEventPayload, engine: ScoreEngine = Depends(get_score_engine)):
    accepted = await engine.add_event(payload.to_risk_event())
    if not accepted:
        raise HTTPException(status_code=202, detail="Duplicate ignored")
    return {"status": "accepted"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, engine: ScoreEngine = Depends(get_score_engine)):
    await websocket.accept()
    try:
        while True:
            state = await engine.get_state()
            await websocket.send_json(state.dict())
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        LOGGER.info("WebSocket disconnected")
    except Exception as exc:  # pragma: no cover
        LOGGER.exception("WebSocket error: %s", exc)
    finally:
        await websocket.close()
