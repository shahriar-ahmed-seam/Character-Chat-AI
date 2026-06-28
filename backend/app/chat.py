"""Chat turn orchestration.

Implements Requirement 3: validate -> verify persona -> assemble -> call LLM (30s)
-> persist. On success persist both messages; on failure persist only the user
message (Requirements 3.3-3.7), and 2.6 (unknown persona never mutates state).
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import AppError, GenerationFailed, MessageInvalid
from .llm import LLMClient
from .memory import MemoryManager
from .personas.manager import PersonaManager
from .persistence.repositories import MessageDTO, MessageRepository, SessionRepository

MAX_MESSAGE_CHARS = 4000


@dataclass
class ChatTurnResult:
    assistant_message: MessageDTO


def validate_message(content: str) -> None:
    """Reject empty/whitespace-only or over-length messages (Requirement 3.5)."""
    if content is None or content.strip() == "":
        raise MessageInvalid("Message content must not be empty")
    if len(content) > MAX_MESSAGE_CHARS:
        raise MessageInvalid(
            f"Message content must not exceed {MAX_MESSAGE_CHARS} characters"
        )


class ChatService:
    def __init__(
        self,
        persona_manager: PersonaManager,
        memory: MemoryManager,
        llm: LLMClient,
        sessions: SessionRepository,
        messages: MessageRepository,
        ltm=None,
    ):
        self._personas = persona_manager
        self._memory = memory
        self._llm = llm
        self._sessions = sessions
        self._messages = messages
        self._ltm = ltm  # optional LongTermMemoryService

    async def handle_turn(self, session_id: str, content: str) -> ChatTurnResult:
        # 1. Validate input first; no persistence or LLM call on failure (Req 3.5).
        validate_message(content)

        # 2. Resolve the session and its persona; unknown -> error, no mutation.
        session = await self._sessions.require(session_id)
        persona = self._personas.require(session.persona_id)

        # 3. Assemble the model request (Requirements 3.1, 3.2).
        model_request = await self._memory.assemble(persona, session_id, content)

        # 4. Call the provider; on any provider failure persist only the user message
        #    and surface a generation error (Requirements 3.6, 3.7).
        try:
            reply = await self._llm.chat_completion(model_request)
        except AppError:
            await self._messages.add_turn(
                session_id, persona.id, user_content=content, assistant_content=None
            )
            raise
        except Exception as exc:  # noqa: BLE001 - defensive: unexpected provider error
            await self._messages.add_turn(
                session_id, persona.id, user_content=content, assistant_content=None
            )
            raise GenerationFailed("Model generation failed") from exc

        if reply is None or reply.strip() == "":
            await self._messages.add_turn(
                session_id, persona.id, user_content=content, assistant_content=None
            )
            raise GenerationFailed("Model returned an empty reply")

        # 5. Persist both messages atomically and return the assistant message.
        persisted = await self._messages.add_turn(
            session_id, persona.id, user_content=content, assistant_content=reply
        )
        # Store embeddings for long-term recall (no-op when disabled / non-fatal).
        if self._ltm is not None and self._ltm.enabled:
            for m in persisted:
                await self._ltm.store(m.id, session_id, m.content)
        assistant = next(m for m in persisted if m.role == "assistant")
        return ChatTurnResult(assistant_message=assistant)
