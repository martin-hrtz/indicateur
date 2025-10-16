"""FastAPI entry point for Confiance de Trade."""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Awaitable, Callable, Dict, List

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

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


def _resolve_version() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=BASE_DIR.parent)
            .decode("utf-8")
            .strip()
        )
    except Exception:  # pragma: no cover - git not available in packaged builds
        return "unknown"


VERSION_HASH = _resolve_version()

load_dotenv(BASE_DIR / ".env", override=False)
load_dotenv(BASE_DIR / ".env.local", override=False)
load_dotenv(BASE_DIR / ".env.dev", override=False)
load_dotenv(BASE_DIR / ".env.example", override=False)

app = FastAPI(title="Confiance de Trade", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:8081",
        "http://127.0.0.1:8081",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8001",
        "http://127.0.0.1:8001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


class BroadcastHub:
    """Minimal pub/sub hub shared by WebSocket and SSE clients."""

    def __init__(self) -> None:
        self._subscribers: List[asyncio.Queue[Dict[str, object]]] = []
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue[Dict[str, object]]:
        queue: asyncio.Queue[Dict[str, object]] = asyncio.Queue(maxsize=4)
        async with self._lock:
            self._subscribers.append(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[Dict[str, object]]) -> None:
        async with self._lock:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    async def publish(self, payload: Dict[str, object]) -> None:
        async with self._lock:
            for queue in list(self._subscribers):
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    # Drop the oldest update if the client is slow.
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    queue.put_nowait(payload)


class AppState:
    def __init__(self) -> None:
        score_config = KNOWLEDGE_DIR / "score.yaml"
        self.score_engine = ScoreEngine(score_config)
        self.broadcast = BroadcastHub()
        self.reasoner = ReasonerClient()
        self.inference = InferenceEngine(self.reasoner)
        self.tasks: List[asyncio.Task] = []
        self.event_router = EventRouter(self.score_engine, self.recompute_and_broadcast)

    async def start(self) -> None:
        LOGGER.info("Starting background tasks")
        self.tasks.append(asyncio.create_task(self._score_loop(), name="score-loop"))
        self.tasks.append(asyncio.create_task(self._heartbeat_loop(), name="heartbeat-loop"))
        self.tasks.append(sessions.create_task(KNOWLEDGE_DIR / "sessions.yaml", self.event_router))
        self.tasks.append(exchange_status.create_task(self.event_router))
        self.tasks.append(onchain.create_task(self.event_router))
        self.tasks.append(microstructure.create_task(self.event_router))
        self.tasks.append(macro.create_task(self.event_router, KNOWLEDGE_DIR / "scenarios.yaml"))
        self.tasks.append(regulatory.create_task(self.event_router, KNOWLEDGE_DIR / "scenarios.yaml"))
        self.tasks.append(
            twitter_stream.create_task(self.event_router, self.inference, KNOWLEDGE_DIR / "twitter_sources.yaml")
        )
        await self.recompute_and_broadcast()

    async def stop(self) -> None:
        LOGGER.info("Stopping background tasks")
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        await self.reasoner.close()

    async def subscribe(self) -> asyncio.Queue[Dict[str, object]]:
        queue = await self.broadcast.subscribe()
        state = await self.score_engine.get_state()
        await queue.put({"type": "score_update", "payload": state.dict()})
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[Dict[str, object]]) -> None:
        await self.broadcast.unsubscribe(queue)

    async def recompute_and_broadcast(self) -> None:
        state = await self.score_engine.tick()
        await self.broadcast.publish({"type": "score_update", "payload": state.dict()})

    async def _score_loop(self) -> None:
        while True:
            try:
                await self.recompute_and_broadcast()
            except Exception as exc:  # pragma: no cover
                LOGGER.exception("Score loop error: %s", exc)
            await asyncio.sleep(1)

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(10)
            payload = {"type": "heartbeat", "ts": time.time()}
            try:
                await self.broadcast.publish(payload)
            except Exception as exc:  # pragma: no cover
                LOGGER.exception("Heartbeat loop error: %s", exc)


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


@app.get("/version")
async def version() -> Dict[str, str]:
    return {"version": VERSION_HASH}


@app.get("/api/score")
async def get_score(engine: ScoreEngine = Depends(get_score_engine)):
    state = await engine.get_state()
    return state.dict()


@app.post("/api/ingest")
async def ingest_event(payload: RiskEventPayload, engine: ScoreEngine = Depends(get_score_engine)):
    accepted = await engine.add_event(payload.to_risk_event())
    if not accepted:
        raise HTTPException(status_code=202, detail="Duplicate ignored")
    await app.state.runtime.recompute_and_broadcast()
    return {"status": "accepted"}


@app.get("/sse")
async def sse_endpoint() -> StreamingResponse:
    async def event_stream():
        queue = await app.state.runtime.subscribe()
        try:
            while True:
                message = await queue.get()
                yield f"data: {json.dumps(message, ensure_ascii=False)}\\n\\n"
        finally:
            await app.state.runtime.unsubscribe(queue)

    headers = {"Cache-Control": "no-cache", "Connection": "keep-alive"}
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    queue = await app.state.runtime.subscribe()
    try:
        while True:
            message = await queue.get()
            await websocket.send_json(message)
    except WebSocketDisconnect:
        LOGGER.info("WebSocket disconnected")
    except Exception as exc:  # pragma: no cover
        LOGGER.exception("WebSocket error: %s", exc)
    finally:
        await app.state.runtime.unsubscribe(queue)
        with contextlib.suppress(RuntimeError):
            await websocket.close()
