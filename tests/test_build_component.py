import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts import build_component


def test_staging_copy_omits_untracked_app_files(tmp_path: Path, monkeypatch) -> None:
    repository = tmp_path / "repository"
    tracked_app = repository / "app" / "tracked.py"
    untracked_app = repository / "app" / "untracked.py"
    tracked_app.parent.mkdir(parents=True)
    tracked_app.write_text("tracked = True\n", encoding="utf-8")
    untracked_app.write_text("secret = 'must not ship'\n", encoding="utf-8")
    subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
    subprocess.run(["git", "-C", str(repository), "add", "app/tracked.py"], check=True)
    monkeypatch.setattr(build_component, "ROOT", repository)

    destination = tmp_path / "staging"
    build_component.copy_tracked_app(destination)

    assert (destination / "app" / "tracked.py").read_text(encoding="utf-8") == "tracked = True\n"
    assert not (destination / "app" / "untracked.py").exists()


@pytest.mark.parametrize("symlink_location", ["file", "parent"])
def test_staging_copy_rejects_tracked_symlinks(
    tmp_path: Path, monkeypatch, symlink_location: str
) -> None:
    repository = tmp_path / "repository"
    tracked_app = repository / "app" / "linked.py"
    tracked_app.parent.mkdir(parents=True)
    tracked_app.write_text("external = True\n", encoding="utf-8")
    subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
    subprocess.run(["git", "-C", str(repository), "add", "app/linked.py"], check=True)
    monkeypatch.setattr(build_component, "ROOT", repository)

    original_is_symlink = Path.is_symlink
    symlink_path = tracked_app if symlink_location == "file" else tracked_app.parent

    def is_symlink(path: Path) -> bool:
        return path == symlink_path or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", is_symlink)

    with pytest.raises(ValueError, match="Символическая ссылка"):
        build_component.copy_tracked_app(tmp_path / "staging")


def test_staging_copy_rejects_sources_resolving_outside_repository(
    tmp_path: Path, monkeypatch
) -> None:
    repository = tmp_path / "repository"
    tracked_app = repository / "app" / "linked-parent.py"
    tracked_app.parent.mkdir(parents=True)
    tracked_app.write_text("outside = True\n", encoding="utf-8")
    subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
    subprocess.run(["git", "-C", str(repository), "add", "app/linked-parent.py"], check=True)
    monkeypatch.setattr(build_component, "ROOT", repository)

    original_resolve = Path.resolve
    outside = tmp_path / "outside.py"

    def resolve(path: Path, *args, **kwargs) -> Path:
        if path == tracked_app:
            return outside
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)

    with pytest.raises(ValueError, match="вне репозитория"):
        build_component.copy_tracked_app(tmp_path / "staging")


@pytest.mark.parametrize("unsafe_source", ["symlink", "outside"])
def test_build_wheel_rejects_unsafe_pyproject_source(
    tmp_path: Path, monkeypatch, capsys, unsafe_source: str
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    pyproject = repository / "pyproject.toml"
    pyproject.write_text("[build-system]\n", encoding="utf-8")
    outside = tmp_path / "outside-pyproject.toml"
    outside.write_text("[build-system]\n# outside\n", encoding="utf-8")
    monkeypatch.setattr(build_component, "ROOT", repository)
    monkeypatch.setattr(build_component, "source_revision", lambda: "0123456789ab")

    original_is_symlink = Path.is_symlink
    original_resolve = Path.resolve

    def is_symlink(path: Path) -> bool:
        if path == pyproject and unsafe_source == "symlink":
            return True
        return original_is_symlink(path)

    def resolve(path: Path, *args, **kwargs) -> Path:
        if path == pyproject and unsafe_source == "outside":
            return outside
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "is_symlink", is_symlink)
    monkeypatch.setattr(Path, "resolve", resolve)
    work = tmp_path / "work"
    work.mkdir()

    result = build_component.build_wheel(tmp_path / "wheels", work)

    captured = capsys.readouterr()
    assert result == 2
    assert "pyproject.toml" in captured.err
    assert not list((tmp_path / "wheels").glob("tutorflow-*.whl"))


def test_verify_wheel_rejects_non_object_build_metadata(tmp_path: Path) -> None:
    wheel = tmp_path / "invalid-build-info.whl"
    with ZipFile(wheel, "w") as package:
        for name in build_component.REQUIRED_WHEEL_FILES:
            package.writestr(name, b"[]" if name == "app/build-info.json" else b"fixture")
        package.writestr(
            "tutorflow-0.1.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nVersion: 0.1.0\n",
        )

    with pytest.raises(ValueError, match="JSON-объект"):
        build_component.verify_wheel(wheel, "0123456789ab")