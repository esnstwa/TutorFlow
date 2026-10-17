from pathlib import Path
from zipfile import ZipFile

from scripts import verify_wheel_runtime


def test_invalid_utf8_build_metadata_returns_verification_error(
    tmp_path: Path, capsys
) -> None:
    wheel = tmp_path / "invalid-metadata.whl"
    with ZipFile(wheel, "w") as package:
        package.writestr("app/build-info.json", b"\xff")

    result = verify_wheel_runtime._verify_wheel(wheel, "0123456789ab")

    captured = capsys.readouterr()
    assert result == 2
    assert "cannot read app/build-info.json" in captured.err
