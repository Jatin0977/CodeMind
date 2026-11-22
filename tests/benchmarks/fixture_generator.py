"""
Deterministic repository fixture generator for CodeMind Phase 10 Benchmarks.

Generates three standardized test repositories:
- repo_small:  10 source files (~500 LOC), clean 3-tier layering.
- repo_medium: 50 source files (~5,000 LOC), package cycles, layer leaks, god classes, churn history.
- repo_large:  250 source files (~30,000 LOC), scalability dependency network.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional


def _run_git_cmd(repo_dir: Path, args: List[str]) -> bool:
    try:
        subprocess.run(
            ["git"] + args,
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return True
    except Exception:
        return False


def _init_git_repo(repo_dir: Path, commit_batches: Optional[List[List[str]]] = None):
    """Initialize a git repo with deterministic commit history if git is available."""
    if not _run_git_cmd(repo_dir, ["init"]):
        return
    _run_git_cmd(repo_dir, ["config", "user.name", "CodeMind Benchmark"])
    _run_git_cmd(repo_dir, ["config", "user.email", "benchmark@codemind.internal"])
    _run_git_cmd(repo_dir, ["config", "commit.gpgsign", "false"])

    if commit_batches:
        for idx, batch_files in enumerate(commit_batches):
            for rel_file in batch_files:
                _run_git_cmd(repo_dir, ["add", rel_file])
            _run_git_cmd(repo_dir, ["commit", "-m", f"feat: commit batch {idx + 1}"])
        _run_git_cmd(repo_dir, ["add", "."])
        _run_git_cmd(repo_dir, ["commit", "-m", "chore: add remaining fixture modules and __init__ files"])
    else:
        _run_git_cmd(repo_dir, ["add", "."])
        _run_git_cmd(repo_dir, ["commit", "-m", "feat: initial benchmark baseline commit"])


def generate_small_repo(base_dir: Path, init_git: bool = False) -> Path:
    """Generate repo_small: 10 source files (~500 LOC) with clean 3-tier layering."""
    repo_dir = base_dir / "repo_small"
    if repo_dir.exists():
        shutil.rmtree(repo_dir)
    repo_dir.mkdir(parents=True, exist_ok=True)

    # 1. utils/crypto.py (~50 lines)
    (repo_dir / "utils").mkdir(exist_ok=True)
    (repo_dir / "utils" / "__init__.py").write_text('"""Utility modules."""\n', encoding="utf-8")
    (repo_dir / "utils" / "crypto.py").write_text(
        '"""Cryptographic hashing and token verification utilities."""\n\n'
        "import hashlib\nimport hmac\nimport secrets\nfrom typing import Tuple\n\n"
        "SALT_SIZE = 16\nDEFAULT_ITERATIONS = 100000\n\n"
        "def hash_password(password: str, salt: bytes = None) -> Tuple[str, str]:\n"
        '    """Hash a plaintext password with PBKDF2-HMAC-SHA256."""\n'
        '    if not password:\n        raise ValueError("Password cannot be empty")\n'
        '    salt = salt or secrets.token_bytes(SALT_SIZE)\n'
        '    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, DEFAULT_ITERATIONS)\n'
        '    return key.hex(), salt.hex()\n\n'
        "def verify_password(password: str, key_hex: str, salt_hex: str) -> bool:\n"
        '    """Verify whether a candidate password matches the hashed key."""\n'
        '    salt = bytes.fromhex(salt_hex)\n'
        '    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, DEFAULT_ITERATIONS)\n'
        '    return hmac.compare_digest(candidate.hex(), key_hex)\n\n'
        "def generate_token(prefix: str = 'cm') -> str:\n"
        '    """Generate a random cryptographic bearer token."""\n'
        '    return f"{prefix}_{secrets.token_urlsafe(32)}"\n',
        encoding="utf-8",
    )

    # 2. utils/validators.py (~40 lines)
    (repo_dir / "utils" / "validators.py").write_text(
        '"""Data validation utilities."""\n\n'
        "import re\nfrom typing import Tuple\n\n"
        "EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+$')\n\n"
        "def validate_email(email: str) -> bool:\n"
        '    """Validate email address format using standard regex."""\n'
        '    if not email:\n        return False\n'
        '    return bool(EMAIL_REGEX.match(email.strip()))\n\n'
        "def validate_password_strength(password: str) -> Tuple[bool, str]:\n"
        '    """Check password length and complexity requirements."""\n'
        '    if len(password) < 8:\n        return False, "Password must be at least 8 characters"\n'
        '    if not any(c.isupper() for c in password):\n        return False, "Must contain uppercase letter"\n'
        '    if not any(c.isdigit() for c in password):\n        return False, "Must contain a number"\n'
        '    return True, "Valid password"\n',
        encoding="utf-8",
    )

    # 3. models/user.py (~50 lines)
    (repo_dir / "models").mkdir(exist_ok=True)
    (repo_dir / "models" / "__init__.py").write_text('"""Domain models."""\n', encoding="utf-8")
    (repo_dir / "models" / "user.py").write_text(
        '"""User domain model and status enums."""\n\n'
        "from dataclasses import dataclass, field\nfrom datetime import datetime\nfrom typing import Optional, Dict, Any\n\n"
        "@dataclass\nclass UserModel:\n"
        '    """User account entity representing a registered developer."""\n'
        '    user_id: str\n    username: str\n    email: str\n'
        '    password_hash: str\n    password_salt: str\n'
        '    is_active: bool = True\n'
        '    created_at: datetime = field(default_factory=datetime.utcnow)\n\n'
        '    def to_dict(self) -> Dict[str, Any]:\n'
        '        return {\n'
        '            "user_id": self.user_id,\n            "username": self.username,\n'
        '            "email": self.email,\n            "is_active": self.is_active,\n'
        '            "created_at": self.created_at.isoformat(),\n        }\n\n'
        '    @classmethod\n'
        '    def from_dict(cls, data: Dict[str, Any]) -> "UserModel":\n'
        '        return cls(\n'
        '            user_id=data["user_id"],\n            username=data["username"],\n'
        '            email=data["email"],\n            password_hash=data.get("password_hash", ""),\n'
        '            password_salt=data.get("password_salt", ""),\n            is_active=data.get("is_active", True),\n        )\n',
        encoding="utf-8",
    )

    # 4. models/session.py (~40 lines)
    (repo_dir / "models" / "session.py").write_text(
        '"""User session and token model."""\n\n'
        "from dataclasses import dataclass\nfrom datetime import datetime, timedelta\n\n"
        "@dataclass\nclass SessionModel:\n"
        '    """Active authenticated session model."""\n'
        '    session_id: str\n    user_id: str\n    token: str\n'
        '    expires_at: datetime\n    is_revoked: bool = False\n\n'
        '    def is_expired(self) -> bool:\n'
        '        return datetime.utcnow() >= self.expires_at\n\n'
        '    def revoke(self) -> None:\n'
        '        self.is_revoked = True\n',
        encoding="utf-8",
    )

    # 5. db/connection.py (~45 lines)
    (repo_dir / "db").mkdir(exist_ok=True)
    (repo_dir / "db" / "__init__.py").write_text('"""Database infrastructure."""\n', encoding="utf-8")
    (repo_dir / "db" / "connection.py").write_text(
        '"""Database connection pool manager."""\n\n'
        "from typing import Dict, Any, Optional\n\n"
        "class ConnectionManager:\n"
        '    """Manages simulated pooled connections to persistent storage."""\n'
        '    def __init__(self, connection_string: str = "sqlite:///:memory:"):\n'
        '        self.connection_string = connection_string\n'
        '        self._pool: Dict[str, Any] = {}\n'
        '        self._is_connected = False\n\n'
        '    def connect(self) -> bool:\n'
        '        self._is_connected = True\n        return True\n\n'
        '    def disconnect(self) -> None:\n'
        '        self._pool.clear()\n        self._is_connected = False\n\n'
        '    def execute(self, query: str, params: Optional[Dict[str, Any]] = None) -> Any:\n'
        '        if not self._is_connected:\n            self.connect()\n'
        '        return {"status": "executed", "query": query, "params": params or {}}\n',
        encoding="utf-8",
    )

    # 6. db/repository.py (~65 lines)
    (repo_dir / "db" / "repository.py").write_text(
        '"""Data access repository implementations."""\n\n'
        "from typing import Optional, List, Dict\n"
        "from ..models.user import UserModel\n"
        "from .connection import ConnectionManager\n\n"
        "class BaseRepository:\n"
        '    """Abstract base repository providing connection access."""\n'
        '    def __init__(self, connection_manager: Optional[ConnectionManager] = None):\n'
        '        self.db = connection_manager or ConnectionManager()\n\n'
        "class UserRepository(BaseRepository):\n"
        '    """Repository for managing UserModel persistence."""\n'
        '    def __init__(self, connection_manager: Optional[ConnectionManager] = None):\n'
        '        super().__init__(connection_manager)\n'
        '        self._storage: Dict[str, UserModel] = {}\n\n'
        '    def save_user(self, user: UserModel) -> UserModel:\n'
        '        self._storage[user.user_id] = user\n'
        '        self.db.execute("INSERT OR REPLACE INTO users", user.to_dict())\n'
        '        return user\n\n'
        '    def find_by_id(self, user_id: str) -> Optional[UserModel]:\n'
        '        return self._storage.get(user_id)\n\n'
        '    def find_by_email(self, email: str) -> Optional[UserModel]:\n'
        '        for u in self._storage.values():\n'
        '            if u.email.lower() == email.lower():\n                return u\n'
        '        return None\n\n'
        '    def list_all(self) -> List[UserModel]:\n'
        '        return list(self._storage.values())\n',
        encoding="utf-8",
    )

    # 7. services/auth_service.py (~70 lines)
    (repo_dir / "services").mkdir(exist_ok=True)
    (repo_dir / "services" / "__init__.py").write_text('"""Business service layer."""\n', encoding="utf-8")
    (repo_dir / "services" / "auth_service.py").write_text(
        '"""Authentication and credential validation service."""\n\n'
        "import uuid\nfrom datetime import datetime, timedelta\nfrom typing import Optional, Tuple\n"
        "from ..models.user import UserModel\n"
        "from ..models.session import SessionModel\n"
        "from ..db.repository import UserRepository\n"
        "from ..utils.crypto import hash_password, verify_password, generate_token\n\n"
        "class AuthService:\n"
        '    """Handles user authentication, password verification, and token issuance."""\n'
        '    def __init__(self, user_repo: Optional[UserRepository] = None):\n'
        '        self.user_repo = user_repo or UserRepository()\n'
        '        self._sessions: dict = {}\n\n'
        '    def authenticate(self, email: str, password: str) -> Optional[SessionModel]:\n'
        '        """Verify email and password; return SessionModel on success."""\n'
        '        user = self.user_repo.find_by_email(email)\n'
        '        if not user or not user.is_active:\n            return None\n'
        '        if not verify_password(password, user.password_hash, user.password_salt):\n'
        '            return None\n'
        '        token = generate_token()\n'
        '        session = SessionModel(\n'
        '            session_id=str(uuid.uuid4()),\n            user_id=user.user_id,\n'
        '            token=token,\n            expires_at=datetime.utcnow() + timedelta(hours=24),\n        )\n'
        '        self._sessions[token] = session\n        return session\n\n'
        '    def validate_session(self, token: str) -> Optional[SessionModel]:\n'
        '        """Validate whether an active session token is valid and unexpired."""\n'
        '        session = self._sessions.get(token)\n'
        '        if not session or session.is_revoked or session.is_expired():\n'
        '            return None\n        return session\n',
        encoding="utf-8",
    )

    # 8. services/user_service.py (~65 lines)
    (repo_dir / "services" / "user_service.py").write_text(
        '"""User lifecycle management service."""\n\n'
        "import uuid\nfrom typing import Optional, Tuple, List\n"
        "from ..models.user import UserModel\n"
        "from ..db.repository import UserRepository\n"
        "from ..utils.crypto import hash_password\n"
        "from ..utils.validators import validate_email, validate_password_strength\n\n"
        "class UserService:\n"
        '    """Manages user registration, profiles, and account validation."""\n'
        '    def __init__(self, user_repo: Optional[UserRepository] = None):\n'
        '        self.user_repo = user_repo or UserRepository()\n\n'
        '    def register_user(self, username: str, email: str, password: str) -> Tuple[Optional[UserModel], str]:\n'
        '        """Register a new user after email and password checks."""\n'
        '        if not validate_email(email):\n            return None, "Invalid email address format"\n'
        '        valid_pwd, msg = validate_password_strength(password)\n'
        '        if not valid_pwd:\n            return None, msg\n'
        '        if self.user_repo.find_by_email(email):\n            return None, "Email already registered"\n'
        '        key_hex, salt_hex = hash_password(password)\n'
        '        user = UserModel(\n'
        '            user_id=str(uuid.uuid4()),\n            username=username,\n'
        '            email=email,\n            password_hash=key_hex,\n            password_salt=salt_hex,\n        )\n'
        '        self.user_repo.save_user(user)\n        return user, "User registered successfully"\n\n'
        '    def get_user_by_id(self, user_id: str) -> Optional[UserModel]:\n'
        '        return self.user_repo.find_by_id(user_id)\n',
        encoding="utf-8",
    )

    # 9. api/auth_controller.py (~60 lines)
    (repo_dir / "api").mkdir(exist_ok=True)
    (repo_dir / "api" / "__init__.py").write_text('"""API presentation layer."""\n', encoding="utf-8")
    (repo_dir / "api" / "auth_controller.py").write_text(
        '"""HTTP controller for authentication routes."""\n\n'
        "from typing import Dict, Any\n"
        "from ..services.auth_service import AuthService\n\n"
        "class AuthController:\n"
        '    """Handles authentication web endpoints."""\n'
        '    def __init__(self, auth_service: AuthService = None):\n'
        '        self.auth_service = auth_service or AuthService()\n\n'
        '    def login(self, payload: Dict[str, str]) -> Dict[str, Any]:\n'
        '        email = payload.get("email", "")\n        password = payload.get("password", "")\n'
        '        session = self.auth_service.authenticate(email, password)\n'
        '        if not session:\n            return {"status": 401, "error": "Invalid credentials"}\n'
        '        return {"status": 200, "token": session.token, "expires_at": session.expires_at.isoformat()}\n\n'
        '    def verify(self, token: str) -> Dict[str, Any]:\n'
        '        session = self.auth_service.validate_session(token)\n'
        '        if not session:\n            return {"valid": False}\n'
        '        return {"valid": True, "user_id": session.user_id}\n',
        encoding="utf-8",
    )

    # 10. api/user_controller.py (~60 lines)
    (repo_dir / "api" / "user_controller.py").write_text(
        '"""HTTP controller for user management."""\n\n'
        "from typing import Dict, Any\n"
        "from ..services.user_service import UserService\n\n"
        "class UserController:\n"
        '    """Handles user registration and profile management web endpoints."""\n'
        '    def __init__(self, user_service: UserService = None):\n'
        '        self.user_service = user_service or UserService()\n\n'
        '    def register(self, payload: Dict[str, str]) -> Dict[str, Any]:\n'
        '        username = payload.get("username", "")\n'
        '        email = payload.get("email", "")\n'
        '        password = payload.get("password", "")\n'
        '        user, msg = self.user_service.register_user(username, email, password)\n'
        '        if not user:\n            return {"status": 400, "error": msg}\n'
        '        return {"status": 201, "user": user.to_dict(), "message": msg}\n\n'
        '    def get_profile(self, user_id: str) -> Dict[str, Any]:\n'
        '        user = self.user_service.get_user_by_id(user_id)\n'
        '        if not user:\n            return {"status": 404, "error": "User not found"}\n'
        '        return {"status": 200, "user": user.to_dict()}\n',
        encoding="utf-8",
    )

    if init_git:
        # Initialize Git with 3 commits for churn & history testing
        commits = [
            ["utils/crypto.py", "utils/validators.py", "models/user.py", "models/session.py"],
            ["db/connection.py", "db/repository.py"],
            ["services/auth_service.py", "services/user_service.py", "api/auth_controller.py", "api/user_controller.py"],
        ]
        _init_git_repo(repo_dir, commit_batches=commits)
    return repo_dir


def generate_medium_repo(base_dir: Path, init_git: bool = False) -> Path:
    """
    Generate repo_medium: 50 source files (~5,000 LOC) across 8 packages.
    Features:
    - Intentional package cycle: billing <-> services
    - Intentional layer violation: storage imports services (upward layer leak)
    - Known God class: MegaOrderProcessor in services/order_processor.py with high McCabe complexity (>20)
    - 15 git commits creating historical churn and logical coupling.
    """
    repo_dir = base_dir / "repo_medium"
    if repo_dir.exists():
        shutil.rmtree(repo_dir)
    repo_dir.mkdir(parents=True, exist_ok=True)

    packages = [
        "core", "auth", "billing", "services", "domain", "adapters", "storage", "utils"
    ]
    for pkg in packages:
        pkg_dir = repo_dir / pkg
        pkg_dir.mkdir(exist_ok=True)
        (pkg_dir / "__init__.py").write_text(f'"""Package {pkg}."""\n', encoding="utf-8")

    # Helper to generate standard boilerplate module
    def _create_module(pkg: str, name: str, class_name: str, doc: str, imports: List[str], methods_count: int = 4):
        p = repo_dir / pkg / f"{name}.py"
        lines = [f'"""{doc}"""\n']
        for imp in imports:
            lines.append(imp)
        lines.append("\n\nclass " + class_name + ":\n")
        lines.append(f'    """{class_name} service or component."""\n')
        lines.append("    def __init__(self):\n        self.initialized = True\n        self.metrics = {}\n\n")
        for i in range(1, methods_count + 1):
            lines.append(f"    def execute_step_{i}(self, data: dict = None) -> dict:\n")
            lines.append(f'        """Execute operation step {i}."""\n')
            lines.append("        data = data or {}\n")
            lines.append(f'        return {{"step": {i}, "status": "ok", "processed": True}}\n\n')
        p.write_text("".join(lines), encoding="utf-8")

    # 1. core (6 modules)
    _create_module("core", "config", "AppConfig", "Application configuration", ["import os"], 4)
    _create_module("core", "logger", "AppLogger", "Centralized logging service", ["import logging"], 4)
    _create_module("core", "exceptions", "CoreExceptions", "System exception hierarchy", [], 3)
    _create_module("core", "constants", "SystemConstants", "Global system constants", [], 2)
    _create_module("core", "telemetry", "TelemetryCollector", "Performance metrics telemetry", ["import time"], 4)
    _create_module("core", "event_bus", "EventBus", "Asynchronous in-memory event bus", ["from typing import Dict, List"], 5)

    # 2. auth (6 modules)
    _create_module("auth", "tokens", "TokenManager", "JWT and bearer token manager", ["import secrets"], 4)
    _create_module("auth", "password", "PasswordHasher", "Secure password hashing provider", ["import hashlib"], 4)
    _create_module("auth", "permissions", "PermissionMatrix", "Role-based access control evaluator", [], 5)
    _create_module("auth", "middleware", "AuthMiddleware", "Request authentication middleware", ["from .tokens import TokenManager"], 4)
    _create_module("auth", "session_store", "SessionStore", "Redis-backed session storage", ["from typing import Dict"], 4)
    _create_module("auth", "oauth_provider", "OAuthProvider", "OAuth2 identity provider integration", ["import urllib.parse"], 4)

    # 3. billing (6 modules)
    # Intentional package cycle: billing/invoices.py imports services/account_service.py
    (repo_dir / "billing" / "invoices.py").write_text(
        '"""Invoice generation and tax calculation."""\n\n'
        "from typing import Dict, Any, List\n"
        "from ..services.account_service import AccountService\n\n"
        "class InvoiceService:\n"
        '    """Manages invoice lifecycle and calls AccountService."""\n'
        '    def __init__(self):\n'
        '        self.account_service = AccountService()\n\n'
        '    def generate_invoice(self, user_id: str, amount: float) -> Dict[str, Any]:\n'
        '        account = self.account_service.get_account(user_id)\n'
        '        return {"invoice_id": "INV-100", "user_id": user_id, "amount": amount, "account": account}\n',
        encoding="utf-8",
    )
    _create_module("billing", "tax", "TaxCalculator", "Regional sales tax computation", [], 4)
    _create_module("billing", "subscriptions", "SubscriptionEngine", "Recurring subscription billing engine", ["from .invoices import InvoiceService"], 4)
    _create_module("billing", "payment_gateway", "PaymentGateway", "Credit card gateway processor", [], 4)
    _create_module("billing", "discounts", "DiscountCalculator", "Promotional discount validation", [], 3)
    _create_module("billing", "ledger", "BillingLedger", "Double-entry bookkeeping ledger", ["from typing import List"], 4)

    # 4. services (7 modules)
    # Intentional package cycle part 2: services/account_service.py imports billing/ledger.py
    (repo_dir / "services" / "account_service.py").write_text(
        '"""User account management service."""\n\n'
        "from typing import Dict, Any\n"
        "from ..billing.ledger import BillingLedger\n\n"
        "class AccountService:\n"
        '    """Manages account balances and interacts with BillingLedger."""\n'
        '    def __init__(self):\n'
        '        self.ledger = BillingLedger()\n\n'
        '    def get_account(self, user_id: str) -> Dict[str, Any]:\n'
        '        return {"user_id": user_id, "balance": 150.0, "status": "active"}\n\n'
        '    def update_balance(self, user_id: str, delta: float) -> bool:\n'
        '        return True\n',
        encoding="utf-8",
    )

    # Known God Class: services/order_processor.py with high cyclomatic complexity (McCabe > 20) and 20 methods
    god_class_lines = [
        '"""Order processing pipeline with complex decision branches."""\n\n',
        "from typing import Dict, Any, List, Optional\n",
        "from ..core.logger import AppLogger\n",
        "from ..billing.payment_gateway import PaymentGateway\n\n",
        "class MegaOrderProcessor:\n",
        '    """God class: Coordinates entire checkout, payment, inventory, and fraud checks."""\n',
        "    def __init__(self):\n",
        "        self.logger = AppLogger()\n",
        "        self.gateway = PaymentGateway()\n",
        "        self.order_cache = {}\n\n",
    ]
    # High cyclomatic complexity method (McCabe > 22)
    god_class_lines.append(
        "    def complex_order_evaluation(self, order: Dict[str, Any]) -> str:\n"
        '        """High cyclomatic complexity evaluation method with numerous nested branches."""\n'
        '        score = 0\n'
        '        amount = order.get("amount", 0)\n'
        '        country = order.get("country", "US")\n'
        '        vip = order.get("vip", False)\n'
        '        risk_level = order.get("risk", "low")\n'
        '        if amount > 1000:\n            score += 10\n'
        '            if country == "US":\n                score += 5\n'
        '            elif country == "CA":\n                score += 4\n'
        '            elif country == "UK":\n                score += 3\n'
        '            else:\n                score += 1\n'
        '        elif amount > 500:\n            score += 6\n'
        '            if vip:\n                score += 3\n'
        '            else:\n                score += 1\n'
        '        else:\n            score += 2\n\n'
        '        if risk_level == "high":\n            score -= 15\n'
        '            if not vip:\n                return "REJECT_HIGH_RISK"\n'
        '        elif risk_level == "medium":\n            score -= 5\n'
        '            if amount > 2000:\n                return "MANUAL_REVIEW"\n'
        '        else:\n            score += 5\n\n'
        '        if score > 20:\n            return "APPROVED_PRIORITY"\n'
        '        elif score > 10:\n            return "APPROVED_STANDARD"\n'
        '        elif score > 5:\n            return "REQUIRES_2FA"\n'
        '        else:\n            return "REJECTED_LOW_SCORE"\n\n'
    )
    for m_i in range(1, 19):
        god_class_lines.append(
            f"    def order_pipeline_substage_{m_i}(self, item_id: str, quantity: int) -> bool:\n"
            f'        """Pipeline sub-stage {m_i}."""\n'
            f'        if quantity <= 0:\n            return False\n'
            f'        self.order_cache[item_id] = {{"stage": {m_i}, "qty": quantity}}\n'
            f'        return True\n\n'
        )
    (repo_dir / "services" / "order_processor.py").write_text("".join(god_class_lines), encoding="utf-8")

    _create_module("services", "catalog_service", "CatalogService", "Product catalog querying", [], 4)
    _create_module("services", "delivery_service", "DeliveryService", "Shipping and delivery logistics", [], 4)
    _create_module("services", "notification_service", "NotificationService", "User notification dispatcher", [], 4)
    _create_module("services", "recommendation_service", "RecommendationService", "Product recommendation ML", [], 3)
    _create_module("services", "audit_service", "AuditService", "Compliance audit trail logging", [], 4)

    # 5. domain (6 modules)
    _create_module("domain", "customer", "CustomerDomain", "Customer entity and lifecycle", [], 4)
    _create_module("domain", "product", "ProductDomain", "Product inventory domain entity", [], 4)
    _create_module("domain", "cart", "CartDomain", "Shopping cart state entity", [], 5)
    _create_module("domain", "order", "OrderDomain", "Purchase order domain entity", [], 5)
    _create_module("domain", "payment", "PaymentDomain", "Payment transaction entity", [], 4)
    _create_module("domain", "address", "AddressDomain", "Physical delivery address entity", [], 3)

    # 6. adapters (6 modules)
    _create_module("adapters", "email_adapter", "EmailAdapter", "SMTP email gateway adapter", ["import smtplib"], 4)
    _create_module("adapters", "sms_adapter", "SmsAdapter", "Twilio SMS messaging adapter", [], 3)
    _create_module("adapters", "stripe_adapter", "StripeAdapter", "Stripe API payment adapter", [], 4)
    _create_module("adapters", "redis_adapter", "RedisAdapter", "Redis caching client adapter", [], 4)
    _create_module("adapters", "s3_adapter", "S3StorageAdapter", "AWS S3 object storage adapter", [], 4)
    _create_module("adapters", "sqs_adapter", "QueueAdapter", "Message broker queue adapter", [], 3)

    # 7. storage (6 modules)
    # Intentional Layer Violation: storage/postgres_db.py imports services/notification_service.py (upward layer leak)
    (repo_dir / "storage" / "postgres_db.py").write_text(
        '"""PostgreSQL database driver with intentional upward architectural layer leak."""\n\n'
        "from typing import Dict, Any\n"
        "from ..services.notification_service import NotificationService\n\n"
        "class PostgresDatabase:\n"
        '    """Database connector with upward layer leak to NotificationService."""\n'
        '    def __init__(self):\n'
        '        self.notifier = NotificationService()\n\n'
        '    def execute_query(self, sql: str) -> Dict[str, Any]:\n'
        '        self.notifier.execute_step_1({"query": sql})\n'
        '        return {"status": "ok", "rows": []}\n',
        encoding="utf-8",
    )
    _create_module("storage", "sql_repo", "SqlRepository", "Relational database repository pattern", [], 4)
    _create_module("storage", "migrations", "SchemaMigration", "Database DDL migration runner", [], 4)
    _create_module("storage", "cache_store", "CacheStore", "In-memory caching abstraction", [], 4)
    _create_module("storage", "blob_store", "BlobStore", "Binary blob storage engine", [], 3)
    _create_module("storage", "query_builder", "QueryBuilder", "SQL query builder utility", [], 5)

    # 8. utils (7 modules)
    _create_module("utils", "formatters", "DataFormatter", "String and currency formatters", [], 4)
    _create_module("utils", "date_utils", "DateUtilities", "Timestamp and calendar math", ["from datetime import datetime"], 4)
    _create_module("utils", "math_utils", "MathUtilities", "Statistical math functions", ["import math"], 4)
    _create_module("utils", "validation", "ValidatorUtils", "Schema validation helpers", [], 4)
    _create_module("utils", "encoding", "EncodingUtils", "Base64 and URL encoding utilities", ["import base64"], 3)
    _create_module("utils", "retry", "RetryHelper", "Exponential backoff retry wrapper", ["import time"], 3)
    _create_module("utils", "serializers", "JsonSerializer", "JSON and YAML serializers", ["import json"], 4)

    # Total files: 6 + 6 + 6 + 7 + 6 + 6 + 6 + 7 = 50 source files!

    if init_git:
        # Create 15 commits with intentional co-change patterns
        commits = [
            ["core/config.py", "core/logger.py", "core/constants.py"],
            ["core/exceptions.py", "core/telemetry.py", "core/event_bus.py"],
            ["auth/tokens.py", "auth/password.py"],
            ["auth/permissions.py", "auth/middleware.py"],
            ["auth/session_store.py", "auth/oauth_provider.py"],
            ["domain/customer.py", "domain/product.py"],
            ["domain/cart.py", "domain/order.py", "services/order_processor.py"],  # Co-change 1
            ["billing/invoices.py", "billing/tax.py"],
            ["billing/subscriptions.py", "billing/payment_gateway.py"],
            ["services/account_service.py", "billing/ledger.py"],
            ["domain/cart.py", "services/order_processor.py"],  # Co-change 2 (churn coupling)
            ["adapters/email_adapter.py", "adapters/stripe_adapter.py"],
            ["storage/postgres_db.py", "storage/sql_repo.py"],
            ["domain/cart.py", "services/order_processor.py"],  # Co-change 3 (high Jaccard coupling)
            ["utils/formatters.py", "utils/date_utils.py", "utils/validation.py"],
        ]
        _init_git_repo(repo_dir, commit_batches=commits)
    return repo_dir


def generate_large_repo(base_dir: Path, init_git: bool = False) -> Path:
    """
    Generate repo_large: 250 source files (~30,000 LOC) across 15 packages.
    Used for scalability benchmarking: parallel ingestion, AST parsing, and graph traversal.
    """
    repo_dir = base_dir / "repo_large"
    if repo_dir.exists():
        shutil.rmtree(repo_dir)
    repo_dir.mkdir(parents=True, exist_ok=True)

    packages = [
        "analytics", "auth", "billing", "cache", "compute", "core", "data", "gateway",
        "ingestion", "models", "monitoring", "network", "storage", "telemetry", "workers"
    ]
    # 250 files distributed: 10 packages with 17 files, 5 packages with 16 files (17*10 + 16*5 = 170 + 80 = 250)
    files_per_pkg = [17 if i < 10 else 16 for i in range(15)]

    for idx, (pkg, count) in enumerate(zip(packages, files_per_pkg)):
        pkg_dir = repo_dir / pkg
        pkg_dir.mkdir(exist_ok=True)
        (pkg_dir / "__init__.py").write_text(f'"""Package {pkg}."""\n', encoding="utf-8")

        for f_idx in range(1, count + 1):
            file_name = f"module_{pkg}_{f_idx}.py"
            class_name = f"{pkg.capitalize()}Component{f_idx}"
            lines = [
                f'"""Scalability module {f_idx} for package {pkg}."""\n\n',
                "import os\nimport sys\nimport time\nimport math\nfrom typing import Dict, List, Any, Optional\n\n",
            ]
            # Cross-import other packages deterministically
            dep_pkg = packages[(idx + 1) % len(packages)]
            dep_file = f"module_{dep_pkg}_1"
            lines.append(f"# Dependency to {dep_pkg}\n")
            lines.append(f"class {class_name}:\n")
            lines.append(f'    """Component {class_name} performing distributed operations."""\n')
            lines.append("    def __init__(self, name: str = 'component'):\n")
            lines.append("        self.name = name\n")
            lines.append("        self.active = True\n")
            lines.append("        self.execution_count = 0\n\n")

            # Generate 8 methods with realistic logic (~120 LOC per file)
            for m in range(1, 9):
                lines.append(f"    def process_operation_{m}(self, payload: Dict[str, Any]) -> Dict[str, Any]:\n")
                lines.append(f'        """Process sub-operation {m} with conditional branches."""\n')
                lines.append("        self.execution_count += 1\n")
                lines.append(f"        factor = math.sqrt({m} * 100)\n")
                lines.append("        if payload.get('priority', False):\n")
                lines.append("            result = {'code': 200, 'priority': True, 'factor': factor}\n")
                lines.append("        elif self.execution_count > 10:\n")
                lines.append("            result = {'code': 202, 'priority': False, 'factor': factor * 1.5}\n")
                lines.append("        else:\n")
                lines.append("            result = {'code': 204, 'priority': False, 'factor': factor}\n")
                lines.append("        return result\n\n")

            (pkg_dir / file_name).write_text("".join(lines).rstrip() + "\n", encoding="utf-8")

    if init_git:
        _init_git_repo(repo_dir)
    return repo_dir


def ensure_fixtures(base_dir: Optional[Path] = None, init_git: bool = False) -> Dict[str, Path]:
    """Ensure all three deterministic fixtures exist; generate them if missing."""
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent / "fixtures"
    base_dir.mkdir(parents=True, exist_ok=True)

    small_dir = base_dir / "repo_small"
    if not small_dir.exists() or len(list(small_dir.glob("**/*.py"))) < 10:
        generate_small_repo(base_dir, init_git=init_git)

    med_dir = base_dir / "repo_medium"
    if not med_dir.exists() or len(list(med_dir.glob("**/*.py"))) < 50:
        generate_medium_repo(base_dir, init_git=init_git)

    large_dir = base_dir / "repo_large"
    if not large_dir.exists() or len(list(large_dir.glob("**/*.py"))) < 250:
        generate_large_repo(base_dir, init_git=init_git)

    return {
        "small": small_dir,
        "medium": med_dir,
        "large": large_dir,
    }


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "fixtures"
    print(f"Generating deterministic fixtures in {target}...")
    fixtures = ensure_fixtures(target)
    for name, p in fixtures.items():
        py_count = len(list(p.glob("**/*.py")))
        print(f"  {name}: {p} ({py_count} Python files)")
