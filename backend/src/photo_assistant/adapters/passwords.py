"""PasswordHasher with argon2id (argon2-cffi)."""

from argon2 import PasswordHasher as _Argon2
from argon2.exceptions import InvalidHashError, VerificationError


class Argon2Hasher:
    def __init__(self, time_cost: int = 3, memory_kib: int = 65536, parallelism: int = 4) -> None:
        self._argon2 = _Argon2(time_cost=time_cost, memory_cost=memory_kib, parallelism=parallelism)

    def hash(self, password: str) -> str:
        return self._argon2.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._argon2.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False
