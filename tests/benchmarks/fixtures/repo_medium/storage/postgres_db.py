"""PostgreSQL database driver with intentional upward architectural layer leak."""

from typing import Dict, Any
from ..services.notification_service import NotificationService

class PostgresDatabase:
    """Database connector with upward layer leak to NotificationService."""
    def __init__(self):
        self.notifier = NotificationService()

    def execute_query(self, sql: str) -> Dict[str, Any]:
        self.notifier.execute_step_1({"query": sql})
        return {"status": "ok", "rows": []}
