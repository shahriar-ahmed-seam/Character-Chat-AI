"""FastAPI application: lifespan, dependency wiring, middleware, and routes.

Ties together config (fail-fast), database, Persona_Manager, Memory_Manager,
LLM_Client, and Chat_Service behind the shared HTTP contract.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .chat import ChatService
from .config import ConfigurationError, load_settings
from .db import make_engine, make_session_factory, verify_connection
from .errors import AppError, ErrorResponse, RateLimited
from .llm import LLMClient, REQUEST_TIMEOUT_SECONDS
from .longterm import LongTermMemoryService
from .memory import MemoryManager, resolve_n
from .models import Base, CharacterRow
from .personas.manager import PersonaManager
from .persistence.repositories import (
    MessageRepository,
    SessionRepository,
    TelegramRepository,
)
from .telegram import TelegramService
from .schemas import (
    ChatResponse,
    CreateSessionRequest,
    HealthResponse,
    HistoryResponse,
    MessageResponse,
    PersonaSummaryResponse,
    PostMessageRequest,
    SessionResponse,
)
from .security import Authenticator, RateLimiter

logger = logging.getLogger("character_chat")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Fail-fast configuration (Requirements 7.5, 12.5).
    settings = load_settings()
    for warning in settings.warnings:
        logger.warning("config: %s", warning)
    app.state.settings = settings

    # 2. Database engine + connection verification (Requirement 12.6).
    engine = make_engine(settings.database_url)
    app.state.engine = engine
    app.state.db_ok = False
    try:
        await verify_connection(engine)
        # Dev convenience: ensure tables exist. Production uses Alembic migrations.
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        app.state.db_ok = True
    except Exception as exc:  # noqa: BLE001
        logger.error("database unavailable at startup: %s", exc)

    app.state.session_factory = make_session_factory(engine)

    # 3. Persona loading + validation (Requirements 1.6, 1.7).
    pm = PersonaManager()
    result = pm.initialize(settings.persona_dir)
    if not result.ok:
        for err in result.rejected:
            logger.error("persona rejected (%s): %s", err.source, err.reason)
    app.state.persona_manager = pm

    # Mirror validated personas into the characters table for referential integrity.
    if app.state.db_ok and pm.ready:
        async with app.state.session_factory() as db:
            for p in result.loaded:
                existing = await db.get(CharacterRow, p.id)
                if existing is None:
                    db.add(CharacterRow(
                        id=p.id, name=p.name, archetype=p.archetype,
                        system_directive=p.system_directive,
                    ))
            await db.commit()

    # 4. Effective N + LLM client + shared HTTP client.
    effective_n, _ = resolve_n(settings.short_term_n)
    app.state.effective_n = effective_n
    app.state.http_client = httpx.AsyncClient(timeout=settings.llm_timeout_seconds)
    app.state.llm = LLMClient(settings.provider, client=app.state.http_client)

    # 5. Security primitives.
    app.state.authenticator = Authenticator(settings.auth_enabled, settings.api_keys)
    app.state.rate_limiter = RateLimiter(
        settings.rate_limit_max_requests, settings.rate_limit_window_seconds
    )

    # 6. Optional Telegram bot (webhook mode, aiogram). Enabled only when a token
    #    is configured, so it never affects local web/API development.
    app.state.telegram_bot = None
    if settings.telegram_bot_token:
        from aiogram import Bot  # imported lazily so aiogram is optional at runtime

        app.state.telegram_bot = Bot(token=settings.telegram_bot_token)
        logger.info("Telegram webhook enabled")

    try:
        yield
    finally:
        await app.state.http_client.aclose()
        if app.state.telegram_bot is not None:
            await app.state.telegram_bot.session.close()
        await engine.dispose()


app = FastAPI(title="Character Chat AI", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────── error handling ───────────────────────────

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    headers = {}
    if isinstance(exc, RateLimited):
        headers["Retry-After"] = str(exc.retry_after_seconds)
    return JSONResponse(
        status_code=exc.http_status,
        content=exc.to_response().model_dump(exclude_none=True),
        headers=headers,
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error")
    body = ErrorResponse(error_id="internal_error", message="An internal error occurred")
    return JSONResponse(status_code=500, content=body.model_dump(exclude_none=True))


# ─────────────────────────── dependencies ───────────────────────────

async def get_db(request: Request) -> AsyncSession:
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


def require_auth(request: Request) -> str:
    return request.app.state.authenticator.authenticate(request.headers)


def enforce_rate_limit(request: Request, credential: str = Depends(require_auth)) -> str:
    request.app.state.rate_limiter.check(credential)
    return credential


# ─────────────────────────── routes ───────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    deps: dict[str, str] = {}
    # Datastore reachability.
    try:
        async with request.app.state.session_factory() as db:
            await db.execute(text("SELECT 1"))
        deps["datastore"] = "ok"
    except Exception:  # noqa: BLE001
        deps["datastore"] = "unavailable"
    # Persona readiness reflects startup validation.
    deps["personas"] = "ok" if request.app.state.persona_manager.ready else "error"
    status = "ok" if all(v == "ok" for v in deps.values()) else "error"
    response = HealthResponse(status=status, dependencies=deps)
    if status != "ok":
        return JSONResponse(status_code=503, content=response.model_dump())
    return response


@app.get("/personas", response_model=list[PersonaSummaryResponse])
async def list_personas(request: Request) -> list[PersonaSummaryResponse]:
    summaries = request.app.state.persona_manager.list_personas()
    return [PersonaSummaryResponse(**s.model_dump()) for s in summaries]


@app.post("/sessions", response_model=SessionResponse)
async def create_session(
    body: CreateSessionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    credential: str = Depends(enforce_rate_limit),
) -> SessionResponse:
    # Unknown persona -> error, no session created (Requirements 2.5, 2.6).
    request.app.state.persona_manager.require(body.persona_id)
    repo = SessionRepository(db)
    session = await repo.create(persona_id=body.persona_id, owner_key=credential)
    return SessionResponse(session_id=session.id, persona_id=session.persona_id)


@app.get("/sessions/{session_id}/history", response_model=HistoryResponse)
async def get_history(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    credential: str = Depends(enforce_rate_limit),
) -> HistoryResponse:
    sessions = SessionRepository(db)
    await sessions.require(session_id)  # not-found if missing (Requirement 6.5)
    messages = MessageRepository(db)
    history = await messages.history(session_id)
    return HistoryResponse(
        session_id=session_id,
        messages=[MessageResponse(**m.__dict__) for m in history],
    )


@app.post("/sessions/{session_id}/messages", response_model=ChatResponse)
async def post_message(
    session_id: str,
    body: PostMessageRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    credential: str = Depends(enforce_rate_limit),
) -> ChatResponse:
    sessions = SessionRepository(db)
    messages = MessageRepository(db)
    ltm = LongTermMemoryService(
        db, request.app.state.llm.embeddings,
        request.app.state.settings.long_term_memory_enabled,
    )
    memory = MemoryManager(messages, request.app.state.effective_n, ltm=ltm)
    service = ChatService(
        persona_manager=request.app.state.persona_manager,
        memory=memory,
        llm=request.app.state.llm,
        sessions=sessions,
        messages=messages,
        ltm=ltm,
    )
    result = await service.handle_turn(session_id, body.content)
    return ChatResponse(
        session_id=session_id,
        message=MessageResponse(**result.assistant_message.__dict__),
    )


# ─────────────────────────── telegram webhook ───────────────────────────

async def _process_telegram(app: FastAPI, chat_id: str, text_in: str) -> None:
    """Process a Telegram message and send the reply. Runs as a background task so the
    webhook returns immediately even though CPU inference can be slow."""
    try:
        async with app.state.session_factory() as db:
            messages = MessageRepository(db)
            ltm = LongTermMemoryService(
                db, app.state.llm.embeddings, app.state.settings.long_term_memory_enabled,
            )
            memory = MemoryManager(messages, app.state.effective_n, ltm=ltm)
            service = ChatService(
                persona_manager=app.state.persona_manager,
                memory=memory,
                llm=app.state.llm,
                sessions=SessionRepository(db),
                messages=messages,
                ltm=ltm,
            )
            tg_service = TelegramService(
                persona_manager=app.state.persona_manager,
                telegram_repo=TelegramRepository(db),
                session_repo=SessionRepository(db),
                chat_service=service,
            )
            reply = await tg_service.handle(chat_id, text_in)
        await app.state.telegram_bot.send_message(chat_id=int(chat_id), text=reply)
    except Exception:  # noqa: BLE001
        logger.exception("telegram processing failed")


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    settings = request.app.state.settings
    if request.app.state.telegram_bot is None:
        raise HTTPException(status_code=404, detail="Telegram webhook is not enabled")
    # Verify Telegram's secret token header when configured.
    if settings.telegram_webhook_secret:
        provided = request.headers.get("x-telegram-bot-api-secret-token")
        if provided != settings.telegram_webhook_secret:
            return JSONResponse(status_code=403, content={"ok": False})

    update = await request.json()
    message = update.get("message") or update.get("edited_message")
    if message and "text" in message:
        chat_id = str(message["chat"]["id"])
        background_tasks.add_task(_process_telegram, request.app, chat_id, message["text"])
    return {"ok": True}
