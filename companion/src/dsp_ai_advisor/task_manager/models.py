"""Task data models for the DSP optimization task manager."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class TaskPriority(str, Enum):
    """Task urgency level."""

    CRITICAL = "critical"  # 电力崩溃, 停产
    HIGH = "high"          # 产能缺口 >30%
    MEDIUM = "medium"      # 物流, 配平
    LOW = "low"            # 升级建议


class TaskCategory(str, Enum):
    """Task domain category."""

    POWER = "power"
    PRODUCTION = "production"
    LOGISTICS = "logistics"
    UPGRADE = "upgrade"


class TaskStatus(str, Enum):
    """Task lifecycle state."""

    NEW = "new"
    TRACKED = "tracked"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class TaskItem(BaseModel):
    """A single optimization task for the player."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    priority: TaskPriority = TaskPriority.MEDIUM
    category: TaskCategory = TaskCategory.PRODUCTION
    title: str = ""
    description: str = ""
    suggested_action: str = ""
    planet: str | None = None
    planet_id: int | None = None
    building_id: int | None = None
    estimated_effort: str = "未估"  # "5 min", "30 min", "1 hour+"
    status: TaskStatus = TaskStatus.NEW
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_active(self) -> bool:
        """Whether this task is still actionable."""
        return self.status in (TaskStatus.NEW, TaskStatus.TRACKED)
