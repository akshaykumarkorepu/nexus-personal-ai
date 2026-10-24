"""Request and response models for the HTTP API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ID_PATTERN = r"^[0-9a-f]{32}$"


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation_id: str | None = Field(None, pattern=ID_PATTERN)
    message: str = Field(..., min_length=1, max_length=100_000)

    @field_validator("message")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Message cannot be empty")
        return v


class CreateConversation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(None, max_length=200)


class RenameConversation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(..., min_length=1, max_length=200)


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0


class ChatMessage(BaseModel):
    id: str
    conversation_id: str
    role: Literal["user", "assistant"]
    parts: list[dict[str, Any]]
    status: str
    error: str | None = None
    provider: str | None = None
    created_at: str
    updated_at: str


class ConversationDetail(ConversationSummary):
    messages: list[ChatMessage]


class FileEntry(BaseModel):
    name: str
    path: str
    type: Literal["file", "dir", "symlink"]
    size: int | None = None
    modified: str | None = None
    readable: bool = False
