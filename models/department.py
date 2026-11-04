"""Department domain model."""

from dataclasses import dataclass


@dataclass(kw_only=True)
class Department:
    department_id: int | None = None
    name: str
    description: str = ""
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None
