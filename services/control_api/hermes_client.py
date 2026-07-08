from __future__ import annotations

from dataclasses import dataclass

from .models import TaskCreateRequest, TaskSummary
from .projection import TaskProjection


@dataclass
class HermesTaskService:
    """Boundary for future Hermes integration.

    The MVP records tasks locally through the projection. Later implementations
    can replace or extend this class to call `hermes chat -q`, a Hermes gateway,
    or a dedicated local Hermes API without changing the mobile API shape.
    """

    projection: TaskProjection

    def submit_task(self, request: TaskCreateRequest) -> TaskSummary:
        return self.projection.create_task(request)
