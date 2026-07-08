import pytest

from services.control_api.hermes_client import FakeHermesExecutor, HermesTaskService
from services.control_api.models import TaskCreateRequest, TaskStatus
from services.control_api.projection import TaskProjection


pytestmark = pytest.mark.unit


@pytest.mark.anyio
async def test_task_service_runs_executor_and_records_successful_result():
    projection = TaskProjection()
    service = HermesTaskService(
        projection=projection,
        executor=FakeHermesExecutor(result_summary="Finished from Hermes", log_messages=["accepted", "working"]),
    )

    task = await service.submit_task(TaskCreateRequest(prompt="Execute for real"), run_inline=True)

    saved = projection.get_task(task.task_id)
    assert saved is not None
    assert saved.status == TaskStatus.COMPLETED
    assert saved.progress_log == ["Hermes task started", "accepted", "working"]
    assert saved.result_summary == "Finished from Hermes"


@pytest.mark.anyio
async def test_task_service_records_executor_failure():
    projection = TaskProjection()
    service = HermesTaskService(
        projection=projection,
        executor=FakeHermesExecutor(error="Hermes command failed"),
    )

    task = await service.submit_task(TaskCreateRequest(prompt="Fail visibly"), run_inline=True)

    saved = projection.get_task(task.task_id)
    assert saved is not None
    assert saved.status == TaskStatus.FAILED
    assert saved.error == "Hermes command failed"
    assert projection.list_task_events(task.task_id)[-1].event_type == "task.failed"
