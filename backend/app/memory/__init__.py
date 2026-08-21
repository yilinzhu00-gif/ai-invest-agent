"""Workspace-scoped structured memory.

The package intentionally keeps user preferences and research reports separate
from ``agent_memories``.  The latter is the existing human-confirmation gate
for reusable run summaries; these records are explicit, queryable domain data.
"""

from backend.app.memory.research_memory import (
    ResearchMemory,
    ResearchMemoryRecord,
    ResearchMemoryRepository,
)
from backend.app.memory.user_memory import UserMemory, UserMemoryProfile, UserMemoryRepository

__all__ = [
    "ResearchMemory",
    "ResearchMemoryRecord",
    "ResearchMemoryRepository",
    "UserMemory",
    "UserMemoryProfile",
    "UserMemoryRepository",
]
