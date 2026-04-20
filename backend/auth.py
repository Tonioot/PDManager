"""
Authentication module for PDManager.

- Passwords are hashed with bcrypt and stored in ~/.pdmanager/credentials
- JWTs are signed with HS256, expire after 1 hour
- Tokens are delivered as httpOnly, SameSite=Strict cookies (not localStorage)
  so they cannot be stolen by XSS attacks
- Login endpoint is rate-limited to 10 attempts per minute per IP
"""

import os
import secrets
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt as _bcrypt
from fastapi import Cookie, Depends, HTTPException, Request, status
from jose import JWTError, jwt

# ── Config ────────────────────────────────────────────────────────────────────
CREDENTIALS_FILE = os.path.expanduser("~/.pdmanager/credentials")
TOKEN_EXPIRE_SECONDS = 3600          # 1 hour
ALGORITHM = "HS256"

# ── Secret key (generated once, stored alongside credentials) ─────────────────
_SECRET_KEY_FILE = os.path.expanduser("~/.pdmanager/secret_key")


def _load_secret_key() -> str:
    os.makedirs(os.path.dirname(_SECRET_KEY_FILE), exist_ok=True)
    if os.path.exists(_SECRET_KEY_FILE):
        with open(_SECRET_KEY_FILE) as f:
            return f.read().strip()
    key = secrets.token_hex(48)
    with open(_SECRET_KEY_FILE, "w") as f:
        f.write(key)
    os.chmod(_SECRET_KEY_FILE, 0o600)
    return key


SECRET_KEY: str = _load_secret_key()


# ── Password helpers ──────────────────────────────────────────────────────────
def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def load_hashed_password() -> Optional[str]:
    if not os.path.exists(CREDENTIALS_FILE):
        return None
    with open(CREDENTIALS_FILE) as f:
        return f.read().strip() or None


def save_hashed_password(hashed: str) -> None:
    os.makedirs(os.path.dirname(CREDENTIALS_FILE), exist_ok=True)
    with open(CREDENTIALS_FILE, "w") as f:
        f.write(hashed)
    os.chmod(CREDENTIALS_FILE, 0o600)


# ── JWT helpers ───────────────────────────────────────────────────────────────
def create_access_token() -> str:
    expire = datetime.now(timezone.utc) + timedelta(seconds=TOKEN_EXPIRE_SECONDS)
    payload = {"sub": "admin", "exp": expire, "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> bool:
    """Return True if the token is valid and not expired."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub") == "admin"
    except JWTError:
        return False


# ── Rate limiter (in-memory, per IP) ─────────────────────────────────────────
_login_attempts: dict[str, list[float]] = defaultdict(list)
MAX_ATTEMPTS = 10
WINDOW_SECONDS = 60


def _check_rate_limit(ip: str) -> None:
    now = time.time()
    attempts = _login_attempts[ip]
    attempts[:] = [t for t in attempts if now - t < WINDOW_SECONDS]
    if len(attempts) >= MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many login attempts. Try again in {WINDOW_SECONDS} seconds.",
        )
    attempts.append(now)


# ── FastAPI dependency: require valid session cookie ─────────────────────────
_COOKIE_NAME = "pdm_token"


def require_auth(pdm_token: Optional[str] = Cookie(default=None)) -> None:
    if not pdm_token or not decode_token(pdm_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
