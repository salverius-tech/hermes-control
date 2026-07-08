from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskCreateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    project_id: str = "default"
    priority: Literal["low", "normal", "high"] = "normal"
    source: str = "mobile"

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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    progress_log: list[str] = Field(default_factory=list)
    result_summary: str | None = None
    error: str | None = None


class TaskEvent(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    task_id: str
    event_type: str
    status: TaskStatus | None = None
    message: str | None = None
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
