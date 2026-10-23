from argon2 import PasswordHasher

from app.auth.passwords import get_password_verifier

password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return get_password_verifier().verify(password, password_hash)
