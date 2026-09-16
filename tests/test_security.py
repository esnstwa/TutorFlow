from app.core.security import hash_password, verify_password


def test_hash_password_does_not_store_plain_password() -> None:
    password = "strong-password"

    password_hash = hash_password(password)

    assert password_hash != password


def test_verify_password_accepts_correct_password() -> None:
    password = "strong-password"

    password_hash = hash_password(password)

    assert verify_password(password, password_hash)


def test_verify_password_rejects_wrong_password() -> None:
    password_hash = hash_password("strong-password")

    assert not verify_password("wrong-password", password_hash)


def test_same_password_can_have_different_hashes() -> None:
    password = "strong-password"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != second_hash
