from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "docs" / "NATIVE_STORE_ROUTE_MAPPING.md"
API = ROOT / "docs" / "API.md"


def test_native_store_route_mapping_is_checked_in_with_authoritative_routes():
    spec = SPEC.read_text(encoding="utf-8")

    for required in (
        "Hermes `projects.db`",
        "Hermes `state.db`",
        "Control API task store",
        "`GET /projects`",
        "`GET /projects/{project_id}`",
        "`GET /sessions`",
        "`POST /tasks`",
        "`POST /tasks/{task_id}/retry`",
        "`POST /tasks/{task_id}/continue`",
        "No live deployed profile or service-account inspection was available",
    ):
        assert required in spec


def test_public_api_documents_synthetic_project_id_migration_and_rejection():
    api = API.read_text(encoding="utf-8")

    for required in (
        "Synthetic task-derived project-ID migration",
        "`CONTROL_API_ALLOW_SYNTHETIC_PROJECTS=1`",
        "There is no server-side automatic ID migration or fallback",
        "Unknown Hermes project",
    ):
        assert required in api
