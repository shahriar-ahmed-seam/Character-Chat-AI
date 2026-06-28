"""Shared Pydantic request/response models (Requirements 13.1-13.4)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    persona_id: str = Field(min_length=1, max_length=64)


class PostMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class PersonaSummaryResponse(BaseModel):
    id: str
    name: str
    archetype: str


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    persona_id: str
    created_at: datetime


class SessionResponse(BaseModel):
    session_id: str
    persona_id: str


class HistoryResponse(BaseModel):
    session_id: str
    messages: list[MessageResponse]


class ChatResponse(BaseModel):
    session_id: str
    message: MessageResponse


class HealthResponse(BaseModel):
    status: str
    dependencies: dict[str, str]
