"""Password verification boundary used by the authentication consumer.

The public contract intentionally hides Argon2 and translates invalid stored
hashes into the same ``False`` result as an ordinary password mismatch.
"""

from typing import Protocol

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


class PasswordVerifier(Protocol):
    """Verify a submitted password against a stored password hash.

    Contract for ``verify``:
    - inputs are the submitted password and the stored opaque hash;
    - returns ``True`` only when the password matches;
    - returns ``False`` for a mismatch, an empty input, or a malformed hash;
    - does not mutate either input or perform application/database I/O;
    - callers must not use this operation to create or persist passwords.
    """

    def verify(self, password: str, password_hash: str) -> bool:
        """Return whether ``password`` matches ``password_hash``."""
        ...


class Argon2PasswordVerifier:
    """Production verifier backed by Argon2 password hashes."""

    def __init__(self, password_hasher: PasswordHasher | None = None) -> None:
        self._password_hasher = password_hasher or PasswordHasher()

    def verify(self, password: str, password_hash: str) -> bool:
        """Return ``False`` for mismatch or unusable stored hash.

        The method deliberately exposes no Argon2 exception to the auth route:
        a malformed legacy/seed hash is an authentication failure, not a
        server error or a reason to disclose storage details.
        """
        if not password or not password_hash:
            return False
        try:
            return bool(self._password_hasher.verify(password_hash, password))
        except (InvalidHashError, VerificationError, VerifyMismatchError, UnicodeError):
            return False


_DEFAULT_PASSWORD_VERIFIER = Argon2PasswordVerifier()


def get_password_verifier() -> PasswordVerifier:
    """Return the production verifier for the authentication consumer.

    Tests may override this dependency with any object implementing
    :class:`PasswordVerifier`; the login consumer remains unchanged.
    """
    return _DEFAULT_PASSWORD_VERIFIER
