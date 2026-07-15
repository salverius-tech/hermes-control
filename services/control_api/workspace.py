from __future__ import annotations

import re
import sqlite3
import time
import uuid
from pathlib import Path

from .models import ProjectCreateRequest, ProjectSummary, ProjectUpdateRequest, SessionSummary


class HermesWorkspaceStore:
    """Small projection over Hermes' per-profile project and session stores."""

    def __init__(self, hermes_home: str | Path | None = None) -> None:
        self.hermes_home = Path(hermes_home or "~/.hermes").expanduser()
        self.projects_path = self.hermes_home / "projects.db"
        self.state_path = self.hermes_home / "state.db"

    @property
    def available(self) -> bool:
        return self.projects_path.exists()

    def list_projects(self, *, include_archived: bool = False) -> list[ProjectSummary]:
        if not self.available:
            return []
        with sqlite3.connect(self.projects_path) as db:
            rows = db.execute(
                "SELECT id, slug, name, description, primary_path, archived FROM projects "
                + ("" if include_archived else "WHERE archived = 0 ")
                + "ORDER BY name COLLATE NOCASE"
            ).fetchall()
            projects: list[ProjectSummary] = []
            for project_id, slug, name, description, primary_path, archived in rows:
                folders = [row[0] for row in db.execute(
                    "SELECT path FROM project_folders WHERE project_id = ? ORDER BY is_primary DESC, path",
                    (project_id,),
                ).fetchall()]
                projects.append(ProjectSummary(
                    project_id=slug or project_id,
                    name=name,
                    description=description,
                    primary_folder=primary_path,
                    folders=folders,
                    archived=bool(archived),
                ))
            return projects

    def get_project(self, project_id: str) -> ProjectSummary | None:
        return next((project for project in self.list_projects(include_archived=True) if project.project_id == project_id), None)

    def create_project(self, request: ProjectCreateRequest) -> ProjectSummary:
        self._require_available()
        slug = request.slug or self._slugify(request.name)
        project_id = f"p_{uuid.uuid4().hex[:8]}"
        now = int(time.time())
        folders = list(dict.fromkeys(request.folders))
        primary = request.primary_folder or (folders[0] if folders else None)
        if primary is not None and primary not in folders:
            folders.insert(0, primary)
        self._validate_folders(folders)
        with sqlite3.connect(self.projects_path) as db:
            db.execute(
                "INSERT INTO projects (id, slug, name, description, primary_path, created_at, archived) VALUES (?, ?, ?, ?, ?, ?, 0)",
                (project_id, slug, request.name.strip(), request.description, primary, now),
            )
            for index, folder in enumerate(folders):
                db.execute(
                    "INSERT INTO project_folders (project_id, path, label, is_primary, added_at) VALUES (?, ?, ?, ?, ?)",
                    (project_id, folder, Path(folder).name, int(folder == primary), now),
                )
        return self.get_project(slug) or ProjectSummary(project_id=slug, name=request.name.strip(), primary_folder=primary, folders=folders)

    def update_project(self, project_id: str, request: ProjectUpdateRequest) -> ProjectSummary:
        self._require_available()
        project = self._get_row(project_id)
        if project is None:
            raise KeyError(project_id)
        updates: list[str] = []
        values: list[object] = []
        if request.name is not None:
            updates.append("name = ?")
            values.append(request.name.strip())
        if request.description is not None:
            updates.append("description = ?")
            values.append(request.description)
        if request.archived is not None:
            updates.append("archived = ?")
            values.append(int(request.archived))
        if request.primary_folder is not None:
            self._validate_folders([request.primary_folder])
            folder_paths = {row[0] for row in self._folder_rows(project[0])}
            if request.primary_folder not in folder_paths:
                raise ValueError("primary folder must belong to the project")
            updates.append("primary_path = ?")
            values.append(request.primary_folder)
        if updates:
            values.append(project[0])
            with sqlite3.connect(self.projects_path) as db:
                db.execute(f"UPDATE projects SET {', '.join(updates)} WHERE id = ?", values)
                if request.primary_folder is not None:
                    db.execute("UPDATE project_folders SET is_primary = (path = ?) WHERE project_id = ?", (request.primary_folder, project[0]))
        return self.get_project(project_id) or project_from_row(project, self._folder_rows(project[0]))

    def add_folder(self, project_id: str, path: str) -> ProjectSummary:
        self._require_available()
        project = self._get_row(project_id)
        if project is None:
            raise KeyError(project_id)
        self._validate_folders([path])
        folders = self._folder_rows(project[0])
        make_primary = not folders
        with sqlite3.connect(self.projects_path) as db:
            db.execute(
                "INSERT OR IGNORE INTO project_folders (project_id, path, label, is_primary, added_at) VALUES (?, ?, ?, ?, ?)",
                (project[0], path, Path(path).name, int(make_primary), int(time.time())),
            )
            if make_primary:
                db.execute("UPDATE projects SET primary_path = ? WHERE id = ?", (path, project[0]))
        return self.get_project(project_id) or project_from_row(project, self._folder_rows(project[0]))

    def remove_folder(self, project_id: str, path: str) -> ProjectSummary:
        self._require_available()
        project = self._get_row(project_id)
        if project is None:
            raise KeyError(project_id)
        folders = self._folder_rows(project[0])
        if len(folders) <= 1:
            raise ValueError("a project must retain at least one folder")
        if path == project[4]:
            raise ValueError("set another primary folder before removing the current primary folder")
        if path not in {folder[0] for folder in folders}:
            raise KeyError(path)
        with sqlite3.connect(self.projects_path) as db:
            db.execute("DELETE FROM project_folders WHERE project_id = ? AND path = ?", (project[0], path))
        return self.get_project(project_id) or project_from_row(project, self._folder_rows(project[0]))

    def list_sessions(self, *, project_id: str | None = None, limit: int = 100) -> list[SessionSummary]:
        if not self.state_path.exists():
            return []
        project = self.get_project(project_id) if project_id else None
        folders = set(project.folders if project else [])
        with sqlite3.connect(self.state_path) as db:
            rows = db.execute(
                "SELECT id, title, source, started_at, ended_at, cwd, parent_session_id, archived "
                "FROM sessions ORDER BY COALESCE(ended_at, started_at) DESC",
            ).fetchall()
        result: list[SessionSummary] = []
        for session_id, title, source, started_at, ended_at, cwd, parent_id, archived in rows:
            if project and not any(_is_within(cwd, folder) for folder in folders):
                continue
            result.append(SessionSummary(
                session_id=session_id,
                title=title,
                source=source,
                last_active_at=_timestamp(ended_at or started_at),
                cwd=cwd,
                project_id=project.project_id if project and any(_is_within(cwd, folder) for folder in folders) else None,
                parent_session_id=parent_id,
                archived=bool(archived),
            ))
            if len(result) >= limit:
                break
        return result

    def list_directories(self, path: str | None = None) -> list[str]:
        roots = [Path(item).expanduser().resolve() for item in __import__("os").getenv("CONTROL_API_PROJECT_ROOTS", str(Path.home() / "repos")).split(":") if item]
        current = Path(path).expanduser().resolve() if path else roots[0]
        if not any(current == root or root in current.parents for root in roots):
            raise ValueError("folder is outside approved project roots")
        if not current.is_dir():
            raise ValueError("folder does not exist")
        return sorted((str(child) for child in current.iterdir() if child.is_dir() and not child.name.startswith(".")), key=str.lower)

    def validate_execution_folder(self, path: str) -> str:
        resolved = Path(path).expanduser().resolve()
        roots = [Path(item).expanduser().resolve() for item in __import__("os").getenv("CONTROL_API_PROJECT_ROOTS", str(Path.home() / "repos")).split(":") if item]
        if not any(resolved == root or root in resolved.parents for root in roots):
            raise ValueError("execution folder is outside approved project roots")
        if not resolved.is_dir():
            raise ValueError("execution folder does not exist")
        return str(resolved)

    def _get_row(self, project_id: str) -> tuple | None:
        with sqlite3.connect(self.projects_path) as db:
            return db.execute(
                "SELECT id, slug, name, description, primary_path, archived FROM projects WHERE id = ? OR slug = ?",
                (project_id, project_id),
            ).fetchone()

    def _folder_rows(self, project_id: str) -> list[tuple]:
        with sqlite3.connect(self.projects_path) as db:
            return db.execute("SELECT path, is_primary FROM project_folders WHERE project_id = ?", (project_id,)).fetchall()

    def _validate_folders(self, folders: list[str]) -> None:
        roots = [Path(path).expanduser().resolve() for path in __import__("os").getenv("CONTROL_API_PROJECT_ROOTS", str(Path.home() / "repos")).split(":") if path]
        for raw in folders:
            path = Path(raw).expanduser().resolve()
            if not path.is_dir():
                raise ValueError(f"folder does not exist: {raw}")
            if not any(path == root or root in path.parents for root in roots):
                raise ValueError(f"folder is outside approved project roots: {raw}")

    def _require_available(self) -> None:
        if not self.available:
            raise RuntimeError(f"Hermes project store not found: {self.projects_path}")

    @staticmethod
    def _slugify(name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"


def _is_within(path: str | None, parent: str) -> bool:
    if not path:
        return False
    try:
        return Path(path).expanduser().resolve().is_relative_to(Path(parent).expanduser().resolve())
    except (OSError, RuntimeError, ValueError):
        return False


def _timestamp(value: float | int | None):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(value, timezone.utc) if value is not None else None


def project_from_row(row: tuple, folders: list[tuple]) -> ProjectSummary:
    return ProjectSummary(
        project_id=row[1] or row[0], name=row[2], description=row[3], primary_folder=row[4],
        folders=[folder[0] for folder in folders], archived=bool(row[5]),
    )
