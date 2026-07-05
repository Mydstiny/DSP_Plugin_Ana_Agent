"""Task Manager — deduplication, merging, sorting, and lifecycle management."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .models import TaskItem, TaskPriority, TaskCategory, TaskStatus

logger = logging.getLogger(__name__)

# Priority sort order: lower number = higher priority
_PRIORITY_ORDER = {
    TaskPriority.CRITICAL: 0,
    TaskPriority.HIGH: 1,
    TaskPriority.MEDIUM: 2,
    TaskPriority.LOW: 3,
}


class TaskManager:
    """Manages the lifecycle of optimization tasks.

    Handles adding new tasks (with deduplication), sorting by priority,
    status transitions, and serialization for WebSocket push.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, TaskItem] = {}

    # ── CRUD ──────────────────────────────────────────────────────

    def add_tasks(self, tasks: list[TaskItem]) -> list[TaskItem]:
        """Add new tasks with automatic deduplication.

        Returns only the tasks that were actually added (not duplicates).
        """
        added: list[TaskItem] = []
        for task in tasks:
            if not self._is_duplicate(task):
                self._tasks[task.id] = task
                added.append(task)
                logger.debug("Task added: %s", task.title)
            else:
                logger.debug("Task deduplicated: %s", task.title)
        return added

    def get_task(self, task_id: str) -> TaskItem | None:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    def get_active_tasks(
        self,
        sort_by: str = "priority",
        limit: int = 50,
    ) -> list[TaskItem]:
        """Get all active (not resolved/dismissed) tasks, sorted.

        Args:
            sort_by: "priority" (default) or "created"
            limit: Max number of tasks to return.
        """
        active = [t for t in self._tasks.values() if t.is_active]

        if sort_by == "created":
            active.sort(key=lambda t: t.created_at, reverse=True)
        else:
            # Sort by priority (critical first), then by created_at (newest first)
            active.sort(key=lambda t: (
                _PRIORITY_ORDER.get(t.priority, 99),
                -t.created_at.timestamp(),
            ))

        return active[:limit]

    def update_status(self, task_id: str, status: TaskStatus) -> TaskItem | None:
        """Update a task's lifecycle status."""
        task = self._tasks.get(task_id)
        if not task:
            logger.warning("Task not found: %s", task_id)
            return None

        task.status = status
        task.updated_at = datetime.now(timezone.utc)
        logger.info("Task %s → %s: %s", task_id, status.value, task.title)
        return task

    def dismiss_task(self, task_id: str) -> TaskItem | None:
        """Mark a task as dismissed (ignored by player)."""
        return self.update_status(task_id, TaskStatus.DISMISSED)

    def track_task(self, task_id: str) -> TaskItem | None:
        """Mark a task as tracked (player is working on it)."""
        return self.update_status(task_id, TaskStatus.TRACKED)

    def resolve_task(self, task_id: str) -> TaskItem | None:
        """Mark a task as resolved (player completed it)."""
        return self.update_status(task_id, TaskStatus.RESOLVED)

    # ── Deduplication ─────────────────────────────────────────────

    def _is_duplicate(self, task: TaskItem) -> bool:
        """Check if a task is a duplicate of an existing active task.

        Criteria:
        1. Same planet + same category → likely duplicate
        2. Jaccard similarity on title tokens > 0.7 → merge
        """
        for existing in self._tasks.values():
            if not existing.is_active:
                continue

            # Same planet and same category
            if task.planet == existing.planet and task.category == existing.category:
                similarity = _token_similarity(task.title, existing.title)
                if similarity > 0.5:
                    # Merge: update description, keep existing status
                    existing.description = task.description
                    existing.suggested_action = task.suggested_action
                    existing.updated_at = datetime.now(timezone.utc)
                    return True

            # Same title (case-insensitive)
            if task.title.lower().strip() == existing.title.lower().strip():
                existing.description = task.description
                existing.updated_at = datetime.now(timezone.utc)
                return True

        return False

    def merge_and_dedup(self, new_tasks: list[TaskItem]) -> list[TaskItem]:
        """Merge new tasks with existing ones.

        - New unique tasks are added
        - Duplicates are merged (description updated, status preserved)
        - Returns: list of truly new tasks added

        This is the main entry point for Agent results.
        """
        return self.add_tasks(new_tasks)

    # ── Serialization ─────────────────────────────────────────────

    def to_dict_list(
        self, tasks: list[TaskItem] | None = None
    ) -> list[dict[str, Any]]:
        """Serialize tasks to dict list for WebSocket push."""
        items = tasks or list(self._tasks.values())
        return [
            {
                "id": t.id,
                "priority": t.priority.value,
                "category": t.category.value,
                "title": t.title,
                "description": t.description,
                "suggested_action": t.suggested_action,
                "planet": t.planet,
                "planet_id": t.planet_id,
                "building_id": t.building_id,
                "estimated_effort": t.estimated_effort,
                "status": t.status.value,
                "created_at": t.created_at.isoformat(),
                "updated_at": t.updated_at.isoformat(),
            }
            for t in items
        ]

    @property
    def task_count(self) -> int:
        return len(self._tasks)

    @property
    def active_count(self) -> int:
        return len(self.get_active_tasks())


def _token_similarity(a: str, b: str) -> float:
    """Compute Jaccard similarity using word tokens, falling back to character bigrams."""
    import re

    a_lower = a.lower().strip()
    b_lower = b.lower().strip()

    # Exact match shortcut
    if a_lower == b_lower:
        return 1.0

    # Try word-level tokens first
    tokens_a = set(re.findall(r"[一-鿿]+|[a-zA-Z0-9]+", a_lower))
    tokens_b = set(re.findall(r"[一-鿿]+|[a-zA-Z0-9]+", b_lower))

    if tokens_a and tokens_b:
        word_intersection = tokens_a & tokens_b
        if word_intersection:
            word_union = tokens_a | tokens_b
            return len(word_intersection) / len(word_union)

    # Fallback: character bigram Jaccard (strip punctuation for cleaner matching)
    def _clean(s: str) -> str:
        return re.sub(r"[^一-鿿\w]", "", s)

    clean_a = _clean(a_lower)
    clean_b = _clean(b_lower)

    if len(clean_a) < 2 or len(clean_b) < 2:
        return 0.0

    def _bigrams(s: str) -> set[str]:
        return {s[i : i + 2] for i in range(len(s) - 1)}

    bigrams_a = _bigrams(clean_a)
    bigrams_b = _bigrams(clean_b)

    if not bigrams_a or not bigrams_b:
        return 0.0

    intersection = bigrams_a & bigrams_b
    union = bigrams_a | bigrams_b
    return len(intersection) / len(union)
