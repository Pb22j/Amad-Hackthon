"""Safe, provider-neutral financial-agent service primitives.

The package is deliberately usable in mock mode without bank credentials.  A
live provider is enabled only by the application bootstrap after its separate
consent and authorization requirements are configured.
"""

from .config import AgenticSettings
from .domain import ActionPlan, ActionType, Money, TaskRecord, TaskState
from .providers import BankingProviderRuntime
from .storage import SQLiteRepository

__all__ = [
    "ActionPlan",
    "ActionType",
    "AgenticSettings",
    "BankingProviderRuntime",
    "Money",
    "SQLiteRepository",
    "TaskRecord",
    "TaskState",
]
