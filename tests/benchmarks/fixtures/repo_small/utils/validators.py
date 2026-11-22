"""Data validation utilities."""

import re
from typing import Tuple

EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')

def validate_email(email: str) -> bool:
    """Validate email address format using standard regex."""
    if not email:
        return False
    return bool(EMAIL_REGEX.match(email.strip()))

def validate_password_strength(password: str) -> Tuple[bool, str]:
    """Check password length and complexity requirements."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not any(c.isupper() for c in password):
        return False, "Must contain uppercase letter"
    if not any(c.isdigit() for c in password):
        return False, "Must contain a number"
    return True, "Valid password"
