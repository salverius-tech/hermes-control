from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TaskStatus(StrEnum):
    AWAITING_APPROVAL = "awaiting_approval"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    REJECTED = "rejected"
    BLOCKED = "blocked"


class TaskCreateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    project_id: str = "default"
    priority: Literal["low", "normal", "high"] = "normal"
    source: str = "mobile"
    requires_approval: bool = False
    parent_task_id: str | None = None
    root_task_id: str | None = None
    session_id: str | None = None
    relation: Literal["original", "retry", "edited_retry", "continuation", "follow_up"] = "original"
    execution_folder: str | None = None
    idempotency_key: str | None = None

    @field_validator("prompt")
    @classmethod
    def prompt_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("prompt must not be blank")
        return stripped

    @field_validator("project_id")
    @classmethod
    def project_id_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("project_id must not be blank")
        return stripped


class TaskSummary(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    task_id: str
    title: str
    prompt: str
    status: TaskStatus = TaskStatus.QUEUED
    project_id: str = "default"
    source: str = "mobile"
    priority: Literal["low", "normal", "high"] = "normal"
    requires_approval: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    progress_log: list[str] = Field(default_factory=list)
    result_summary: str | None = None
    error: str | None = None
    blocker_category: str | None = None
    blocker_message: str | None = None
    blocker_retryable: bool = False
    parent_task_id: str | None = None
    root_task_id: str | None = None
    session_id: str | None = None
    relation: str = "original"
    execution_folder: str | None = None
    idempotency_key: str | None = None


class TaskEvent(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    task_id: str
    event_type: str
    status: TaskStatus | None = None
    message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentStatus(BaseModel):
    agent_id: str
    status: Literal["idle", "busy", "offline"] = "offline"
    current_task_id: str | None = None
    project_id: str = "default"
    last_seen_at: datetime | None = None


class ProjectSummary(BaseModel):
    project_id: str
    name: str
    queued_count: int = 0
    running_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    description: str | None = None
    primary_folder: str | None = None
    folders: list[str] = Field(default_factory=list)
    archived: bool = False


class SessionSummary(BaseModel):
    session_id: str
    title: str | None = None
    preview: str | None = None
    source: str | None = None
    last_active_at: datetime | None = None
    cwd: str | None = None
    project_id: str | None = None
    parent_session_id: str | None = None
    archived: bool = False


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    slug: str | None = None
    description: str | None = None
    folders: list[str] = Field(default_factory=list)
    primary_folder: str | None = None


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    archived: bool | None = None
    primary_folder: str | None = None


class FolderRequest(BaseModel):
    path: str = Field(min_length=1)


class GuidanceRequest(BaseModel):
    prompt: str = Field(min_length=1)
    requires_approval: bool = False
    new_session: bool = False
    relation: Literal["continuation", "edited_retry", "follow_up"] = "continuation"

    @field_validator("prompt")
    @classmethod
    def guidance_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("prompt must not be blank")
        return stripped


class ApprovalRequest(BaseModel):
    actor: str = "mobile-user"
    device_id: str | None = None
    reason: str | None = None

    @field_validator("actor")
    @classmethod
    def actor_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("actor must not be blank")
        return stripped
