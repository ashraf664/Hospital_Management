"""SQLite repository for audit event metadata."""

from models import AuditLog
from repositories.base_repository import BaseRepository
from repositories.exceptions import PersistenceIntegrityError


class AuditLogRepository(BaseRepository):
    """Persist audit metadata without managing transactions."""

    def create(self, audit_log: AuditLog) -> AuditLog:
        """Insert an audit event and return its generated identity and time."""
        cursor = self._execute(
            """
            INSERT INTO audit_logs (
                user_id, actor_type, action, entity_type, entity_id,
                occurred_at, details
            )
            VALUES (?, ?, ?, ?, ?, COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')), ?)
            """,
            (
                audit_log.user_id,
                audit_log.actor_type.value,
                audit_log.action,
                audit_log.entity_type,
                audit_log.entity_id,
                audit_log.occurred_at,
                audit_log.details,
            ),
        )
        row = self._fetchone(
            """
            SELECT occurred_at
            FROM audit_logs
            WHERE audit_log_id = ?
            """,
            (int(cursor.lastrowid),),
        )
        if row is None:
            raise PersistenceIntegrityError(
                "Inserted audit event could not be read back from SQLite."
            )
        return AuditLog(
            audit_log_id=int(cursor.lastrowid),
            actor_type=audit_log.actor_type,
            action=audit_log.action,
            entity_type=audit_log.entity_type,
            user_id=audit_log.user_id,
            entity_id=audit_log.entity_id,
            occurred_at=str(row["occurred_at"]),
            details=audit_log.details,
        )
