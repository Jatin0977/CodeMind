"""User domain model and status enums."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any

@dataclass
class UserModel:
    """User account entity representing a registered developer."""
    user_id: str
    username: str
    email: str
    password_hash: str
    password_salt: str
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserModel":
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            email=data["email"],
            password_hash=data.get("password_hash", ""),
            password_salt=data.get("password_salt", ""),
            is_active=data.get("is_active", True),
        )
