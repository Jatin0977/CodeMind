"""Data access repository implementations."""

from typing import Optional, List, Dict
from ..models.user import UserModel
from .connection import ConnectionManager

class BaseRepository:
    """Abstract base repository providing connection access."""
    def __init__(self, connection_manager: Optional[ConnectionManager] = None):
        self.db = connection_manager or ConnectionManager()

class UserRepository(BaseRepository):
    """Repository for managing UserModel persistence."""
    def __init__(self, connection_manager: Optional[ConnectionManager] = None):
        super().__init__(connection_manager)
        self._storage: Dict[str, UserModel] = {}

    def save_user(self, user: UserModel) -> UserModel:
        self._storage[user.user_id] = user
        self.db.execute("INSERT OR REPLACE INTO users", user.to_dict())
        return user

    def find_by_id(self, user_id: str) -> Optional[UserModel]:
        return self._storage.get(user_id)

    def find_by_email(self, email: str) -> Optional[UserModel]:
        for u in self._storage.values():
            if u.email.lower() == email.lower():
                return u
        return None

    def list_all(self) -> List[UserModel]:
        return list(self._storage.values())
