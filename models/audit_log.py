"""Audit-event metadata domain model."""

from dataclasses import dataclass

from models.enums import AuditActorType


@dataclass(kw_only=True)
class AuditLog:
    audit_log_id: int | None = None
    actor_type: AuditActorType
    action: str
    entity_type: str
    user_id: int | None = None
    entity_id: str | None = None
    occurred_at: str | None = None
    details: str = ""
