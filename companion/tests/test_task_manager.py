"""Tests for Task Manager — dedup, sort, lifecycle."""

from dsp_ai_advisor.task_manager.models import (
    TaskItem, TaskPriority, TaskCategory, TaskStatus,
)
from dsp_ai_advisor.task_manager.manager import TaskManager


class TestTaskManager:
    def test_add_and_get_active(self):
        """New tasks should appear in active list."""
        mgr = TaskManager()

        tasks = [
            TaskItem(
                title="电力不足",
                priority=TaskPriority.CRITICAL,
                category=TaskCategory.POWER,
                planet="母星",
            ),
            TaskItem(
                title="产能不足",
                priority=TaskPriority.HIGH,
                category=TaskCategory.PRODUCTION,
                planet="铸星",
            ),
        ]

        added = mgr.merge_and_dedup(tasks)
        assert len(added) == 2

        active = mgr.get_active_tasks()
        assert len(active) == 2
        # Critical should be first
        assert active[0].priority == TaskPriority.CRITICAL

    def test_deduplication_same_planet_category(self):
        """Tasks on same planet with same category and similar title are merged."""
        mgr = TaskManager()

        t1 = TaskItem(
            title="产能不足 — 处理器产线",
            priority=TaskPriority.HIGH,
            category=TaskCategory.PRODUCTION,
            planet="母星",
            description="Need more assemblers",
        )
        t2 = TaskItem(
            title="处理器产线产能不足",
            priority=TaskPriority.HIGH,
            category=TaskCategory.PRODUCTION,
            planet="母星",
            description="Updated: need 5 more assemblers",
        )

        added1 = mgr.merge_and_dedup([t1])
        assert len(added1) == 1

        added2 = mgr.merge_and_dedup([t2])
        assert len(added2) == 0  # duplicate, should not add

        active = mgr.get_active_tasks()
        assert len(active) == 1
        assert active[0].description == "Updated: need 5 more assemblers"

    def test_status_transitions(self):
        """Task status should transition correctly."""
        mgr = TaskManager()
        task = TaskItem(title="测试任务")
        mgr.merge_and_dedup([task])

        # Track
        mgr.track_task(task.id)
        assert mgr.get_task(task.id).status == TaskStatus.TRACKED

        # Resolve
        mgr.resolve_task(task.id)
        assert mgr.get_task(task.id).status == TaskStatus.RESOLVED

        # Resolved tasks should not be active
        active = mgr.get_active_tasks()
        assert len(active) == 0

    def test_priority_sorting(self):
        """Tasks should sort by priority (critical → high → medium → low)."""
        mgr = TaskManager()
        tasks = [
            TaskItem(title="Low", priority=TaskPriority.LOW, category=TaskCategory.UPGRADE),
            TaskItem(title="Critical", priority=TaskPriority.CRITICAL, category=TaskCategory.POWER),
            TaskItem(title="Medium", priority=TaskPriority.MEDIUM, category=TaskCategory.LOGISTICS),
            TaskItem(title="High", priority=TaskPriority.HIGH, category=TaskCategory.PRODUCTION),
        ]
        mgr.merge_and_dedup(tasks)

        active = mgr.get_active_tasks()
        priorities = [t.priority for t in active]
        assert priorities == [
            TaskPriority.CRITICAL,
            TaskPriority.HIGH,
            TaskPriority.MEDIUM,
            TaskPriority.LOW,
        ]
