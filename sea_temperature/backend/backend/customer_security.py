"""Opaque session credentials and salted, versioned scrypt password hashes."""
import hashlib
import hmac
import secrets
from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from fastapi import HTTPException

SCRYPT = dict(n=2**15, r=8, p=3, maxmem=64 * 1024 * 1024, dklen=32)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, **SCRYPT)
    return f"scrypt$v1${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    try:
        algorithm, version, salt, digest = (stored or "").split("$")
        if (algorithm, version) != ("scrypt", "v1"):
            return False
        salt_bytes, digest_bytes = bytes.fromhex(salt), bytes.fromhex(digest)
        if len(salt_bytes) != 16 or len(digest_bytes) != 32:
            return False
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt_bytes, **SCRYPT)
        return hmac.compare_digest(actual, digest_bytes)
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class LoginLimiter:
    """Single-process attempt cap; replace with a shared limiter for multiple workers."""
    def __init__(self):
        self.attempts = defaultdict(deque)
        self.lock = Lock()

    def check(self, key: str):
        now = monotonic()
        with self.lock:
            for stale in [k for k, entries in self.attempts.items() if entries[-1] <= now - 300]:
                del self.attempts[stale]
            entries = self.attempts[key]
            while entries and entries[0] <= now - 300:
                entries.popleft()
            if len(entries) >= 10:
                raise HTTPException(429, "잠시 후 다시 로그인해 주세요.", headers={"Retry-After": "300"})
            entries.append(now)


login_limiter = LoginLimiter()
