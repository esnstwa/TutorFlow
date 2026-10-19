from collections.abc import Mapping


class FixedPasswordVerifier:
    """Test-only substitute implementing the auth password-verifier contract."""

    def __init__(self, answers: Mapping[tuple[str, str], bool]) -> None:
        self._answers = dict(answers)

    def verify(self, password: str, password_hash: str) -> bool:
        return self._answers.get((password, password_hash), False)
