"""User lifecycle management service."""

import uuid
from typing import Optional, Tuple, List
from ..models.user import UserModel
from ..db.repository import UserRepository
from ..utils.crypto import hash_password
from ..utils.validators import validate_email, validate_password_strength

class UserService:
    """Manages user registration, profiles, and account validation."""
    def __init__(self, user_repo: Optional[UserRepository] = None):
        self.user_repo = user_repo or UserRepository()

    def register_user(self, username: str, email: str, password: str) -> Tuple[Optional[UserModel], str]:
        """Register a new user after email and password checks."""
        if not validate_email(email):
            return None, "Invalid email address format"
        valid_pwd, msg = validate_password_strength(password)
        if not valid_pwd:
            return None, msg
        if self.user_repo.find_by_email(email):
            return None, "Email already registered"
        key_hex, salt_hex = hash_password(password)
        user = UserModel(
            user_id=str(uuid.uuid4()),
            username=username,
            email=email,
            password_hash=key_hex,
            password_salt=salt_hex,
        )
        self.user_repo.save_user(user)
        return user, "User registered successfully"

    def get_user_by_id(self, user_id: str) -> Optional[UserModel]:
        return self.user_repo.find_by_id(user_id)
