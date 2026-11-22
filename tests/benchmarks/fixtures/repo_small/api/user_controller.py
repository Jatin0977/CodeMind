"""HTTP controller for user management."""

from typing import Dict, Any
from ..services.user_service import UserService

class UserController:
    """Handles user registration and profile management web endpoints."""
    def __init__(self, user_service: UserService = None):
        self.user_service = user_service or UserService()

    def register(self, payload: Dict[str, str]) -> Dict[str, Any]:
        username = payload.get("username", "")
        email = payload.get("email", "")
        password = payload.get("password", "")
        user, msg = self.user_service.register_user(username, email, password)
        if not user:
            return {"status": 400, "error": msg}
        return {"status": 201, "user": user.to_dict(), "message": msg}

    def get_profile(self, user_id: str) -> Dict[str, Any]:
        user = self.user_service.get_user_by_id(user_id)
        if not user:
            return {"status": 404, "error": "User not found"}
        return {"status": 200, "user": user.to_dict()}
