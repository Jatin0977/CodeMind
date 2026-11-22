"""HTTP controller for authentication routes."""

from typing import Dict, Any
from ..services.auth_service import AuthService

class AuthController:
    """Handles authentication web endpoints."""
    def __init__(self, auth_service: AuthService = None):
        self.auth_service = auth_service or AuthService()

    def login(self, payload: Dict[str, str]) -> Dict[str, Any]:
        email = payload.get("email", "")
        password = payload.get("password", "")
        session = self.auth_service.authenticate(email, password)
        if not session:
            return {"status": 401, "error": "Invalid credentials"}
        return {"status": 200, "token": session.token, "expires_at": session.expires_at.isoformat()}

    def verify(self, token: str) -> Dict[str, Any]:
        session = self.auth_service.validate_session(token)
        if not session:
            return {"valid": False}
        return {"valid": True, "user_id": session.user_id}
