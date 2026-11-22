"""Authentication and credential validation service."""

import uuid
from datetime import datetime, timedelta
from typing import Optional, Tuple
from ..models.user import UserModel
from ..models.session import SessionModel
from ..db.repository import UserRepository
from ..utils.crypto import hash_password, verify_password, generate_token

class AuthService:
    """Handles user authentication, password verification, and token issuance."""
    def __init__(self, user_repo: Optional[UserRepository] = None):
        self.user_repo = user_repo or UserRepository()
        self._sessions: dict = {}

    def authenticate(self, email: str, password: str) -> Optional[SessionModel]:
        """Verify email and password; return SessionModel on success."""
        user = self.user_repo.find_by_email(email)
        if not user or not user.is_active:
            return None
        if not verify_password(password, user.password_hash, user.password_salt):
            return None
        token = generate_token()
        session = SessionModel(
            session_id=str(uuid.uuid4()),
            user_id=user.user_id,
            token=token,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        self._sessions[token] = session
        return session

    def validate_session(self, token: str) -> Optional[SessionModel]:
        """Validate whether an active session token is valid and unexpired."""
        session = self._sessions.get(token)
        if not session or session.is_revoked or session.is_expired():
            return None
        return session
