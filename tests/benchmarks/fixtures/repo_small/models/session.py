"""User session and token model."""

from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class SessionModel:
    """Active authenticated session model."""
    session_id: str
    user_id: str
    token: str
    expires_at: datetime
    is_revoked: bool = False

    def is_expired(self) -> bool:
        return datetime.utcnow() >= self.expires_at

    def revoke(self) -> None:
        self.is_revoked = True
