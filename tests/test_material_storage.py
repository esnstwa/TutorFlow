"""Isolated storage tests: run with --noconftest; no application/DB imports."""
import asyncio
from pathlib import Path
from io import BytesIO

from PIL import Image
from pypdf import PdfWriter, get_configuration
from pypdf.actions import JavaScript
from pypdf.generic import DecodedStreamObject, NameObject

import pytest
from pydantic import ValidationError

from app import storage
from app.core.config import Settings


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.settings, "file_storage_path", str(tmp_path / "uploads"))


@pytest.mark.parametrize("name", ["../x.txt", "a/b.txt", "a\\b.txt", "C:x.txt", "nul.txt", "COM1.txt", "x\x00.txt", "x\n.txt", "x\u202e.txt", "x\u2066.txt", "x. ", ".hidden.txt", "", "..", " x.txt", "aux.any.txt"])
def test_unsafe_filename_rejected_without_repair(name):
    with pytest.raises(storage.FileStorageError) as caught:
        storage.validate_filename(name)
    assert caught.value.status_code == 422
    assert name not in caught.value.detail or not name


def test_valid_filename_preserved():
    name = "Конспект урока 12.TXT"
    assert storage.validate_filename(name) == name


async def chunks(*parts):
    for part in parts:
        yield part


def test_text_stream_is_private_atomic_and_metadata_correct():
    content = "Русский текст\n".encode()

    async def streaming():
        yield content[:3]  # UTF-8 may be split across chunks.
        root = storage.storage_root()
        staged = list(root.iterdir())
        assert len(staged) == 1
        assert staged[0].name.startswith(".") and staged[0].name.endswith(".uploading")
        yield content[3:]

    result = asyncio.run(storage.store_stream("урок.TXT", streaming()))
    assert result.original_name == "урок.TXT"
    assert result.mime_type == "text/plain" and result.previewable is True
    assert result.size == len(content)
    assert Path(result.storage_path).read_bytes() == content
    assert len(result.stored_name) == 36 and result.stored_name.endswith(".txt")
    assert [path.name for path in storage.storage_root().iterdir()] == [result.stored_name]


@pytest.mark.parametrize("parts,limit,code", [([b""], 10, 422), ([b"123", b"456"], 5, 413), ([b"123456"], 5, 413)])
def test_stream_rejections_cleanup(parts, limit, code):
    with pytest.raises(storage.FileStorageError) as caught:
        asyncio.run(storage.store_stream("x.txt", chunks(*parts), max_size=limit))
    assert caught.value.status_code == code
    assert list(storage.storage_root().iterdir()) == []


def test_configured_limit_is_never_raised_by_caller(monkeypatch):
    monkeypatch.setattr(storage.settings, "file_upload_max_bytes", 4)
    with pytest.raises(storage.FileStorageError) as caught:
        asyncio.run(storage.store_stream("x.txt", chunks(b"12345"), max_size=100))
    assert caught.value.status_code == 413
    assert list(storage.storage_root().iterdir()) == []


@pytest.mark.parametrize("failure", [RuntimeError("stream failed"), asyncio.CancelledError()])
def test_stream_error_and_cancellation_cleanup(failure):
    async def broken():
        yield b"first"
        raise failure
    with pytest.raises(type(failure)):
        asyncio.run(storage.store_stream("x.txt", broken()))
    assert list(storage.storage_root().iterdir()) == []


@pytest.mark.parametrize("operation", ["fsync", "replace"])
def test_filesystem_failure_is_sanitized_and_cleans_up(monkeypatch, operation):
    def broken(*args):
        raise OSError("secret-path-do-not-expose")
    monkeypatch.setattr(storage.os, operation, broken)
    with pytest.raises(storage.FileStorageError) as caught:
        asyncio.run(storage.store_stream("x.txt", chunks(b"hello")))
    assert caught.value.status_code == 500
    assert "secret-path" not in caught.value.detail
    assert list(storage.storage_root().iterdir()) == []


@pytest.mark.parametrize("name,content,mime,code", [
    ("x.exe", b"text", None, 415),
    ("x.txt", b"text", "image/png", 415),
    ("x.txt", b"\x89PNG\r\n\x1a\nspoof", None, 415),
    ("x.txt", b"hello\x00binary", None, 415),
    ("x.txt", b"hello\x1bbinary", None, 415),
    ("x.txt", b"\xff\xfeinvalid", None, 422),
    ("x.txt", b"PK\x03\x04zip", None, 415),
])
def test_text_format_and_mime_rejections_cleanup(name, content, mime, code):
    with pytest.raises(storage.FileStorageError) as caught:
        asyncio.run(storage.store_stream(name, chunks(content), declared_mime=mime))
    assert caught.value.status_code == code
    assert list(storage.storage_root().iterdir()) == []


@pytest.mark.parametrize("mime", [None, "", "application/octet-stream", "text/plain; charset=utf-8"])
def test_declared_generic_or_text_mime_allowed(mime):
    result = asyncio.run(storage.store_stream("x.txt", chunks(b"hello"), declared_mime=mime))
    assert result.mime_type == "text/plain"


def test_inspect_enforces_size_and_empty(tmp_path, monkeypatch):
    path = tmp_path / "existing.txt"
    path.write_bytes(b"")
    with pytest.raises(storage.FileStorageError) as caught:
        storage.inspect_file(path, "x.txt")
    assert caught.value.status_code == 422
    path.write_bytes(b"12345")
    monkeypatch.setattr(storage.settings, "file_upload_max_bytes", 4)
    with pytest.raises(storage.FileStorageError) as caught:
        storage.inspect_file(path, "x.txt")
    assert caught.value.status_code == 413


def image_bytes(fmt="PNG", size=(4, 3)):
    target = BytesIO()
    Image.new("RGB", size, (12, 34, 56)).save(target, format=fmt)
    return target.getvalue()


@pytest.mark.parametrize("fmt,suffix,mime", [("PNG", ".png", "image/png"), ("JPEG", ".jpg", "image/jpeg"), ("JPEG", ".jpeg", "image/jpeg")])
def test_real_image_verify_and_decode(fmt, suffix, mime):
    content = image_bytes(fmt)
    result = asyncio.run(storage.store_stream("photo" + suffix, chunks(content)))
    assert result.mime_type == mime and result.previewable is True
    assert Path(result.storage_path).read_bytes() == content


@pytest.mark.parametrize("fmt,suffix", [("PNG", ".png"), ("JPEG", ".jpg")])
def test_truncated_images_are_not_published(fmt, suffix):
    content = image_bytes(fmt)[:-12]
    with pytest.raises(storage.FileStorageError) as caught:
        asyncio.run(storage.store_stream("photo" + suffix, chunks(content)))
    assert caught.value.status_code == 422
    assert list(storage.storage_root().iterdir()) == []


def test_image_extension_spoof_is_rejected():
    with pytest.raises(storage.FileStorageError) as caught:
        asyncio.run(storage.store_stream("photo.jpg", chunks(image_bytes("PNG"))))
    assert caught.value.status_code == 415


def test_image_pixel_budget_without_global_pillow_mutation(monkeypatch):
    monkeypatch.setattr(storage, "MAX_IMAGE_PIXELS", 100, raising=False)
    original = Image.MAX_IMAGE_PIXELS
    with pytest.raises(storage.FileStorageError) as caught:
        asyncio.run(storage.store_stream("photo.png", chunks(image_bytes(size=(11, 10)))))
    assert caught.value.status_code == 422
    assert Image.MAX_IMAGE_PIXELS == original


def test_animated_png_rejected():
    target = BytesIO()
    Image.new("RGB", (2, 2), "red").save(target, format="PNG", save_all=True, append_images=[Image.new("RGB", (2, 2), "blue")], duration=100, loop=0)
    with pytest.raises(storage.FileStorageError) as caught:
        asyncio.run(storage.store_stream("animated.png", chunks(target.getvalue())))
    assert caught.value.status_code == 422


def pdf_bytes(*, pages=1, encrypted=False, script=False, attachment=False, content=None):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    if encrypted:
        writer.encrypt("test-fixture-only")
    if script:
        writer.add_open_action(JavaScript("app.alert('not allowed')"))
    if attachment:
        writer.add_attachment("unsafe.txt", b"attachment")
    if content is not None:
        stream = DecodedStreamObject()
        stream.set_data(content)
        writer.pages[0][NameObject("/Contents")] = writer._add_object(stream.flate_encode())
    target = BytesIO()
    writer.write(target)
    return target.getvalue()


def test_actual_pdf_structure_accepted_without_inline_preview():
    content = pdf_bytes(content=b"q Q")
    result = asyncio.run(storage.store_stream("lesson.pdf", chunks(content)))
    assert result.mime_type == "application/pdf" and result.previewable is False
    assert Path(result.storage_path).read_bytes() == content


@pytest.mark.parametrize("content,code", [
    (lambda: pdf_bytes(pages=0), 422),
    (lambda: pdf_bytes(encrypted=True), 422),
    (lambda: pdf_bytes(script=True), 422),
    (lambda: pdf_bytes(attachment=True), 422),
    (lambda: pdf_bytes()[:-8], 422),
    (lambda: pdf_bytes() + b"trailing payload", 422),
    (lambda: b"%PDF-1.7\nfake\n%%EOF", 422),
])
def test_pdf_invalid_active_and_encrypted_rejected(content, code):
    with pytest.raises(storage.FileStorageError) as caught:
        asyncio.run(storage.store_stream("lesson.pdf", chunks(content())))
    assert caught.value.status_code == code
    assert list(storage.storage_root().iterdir()) == []


def test_pdf_decompression_budget_is_local(monkeypatch):
    content = pdf_bytes(content=b" " * 100_000)
    assert len(content) < 2000
    original = get_configuration()
    monkeypatch.setattr(storage, "MAX_PDF_STREAM_BYTES", 8192, raising=False)
    with pytest.raises(storage.FileStorageError) as caught:
        asyncio.run(storage.store_stream("bomb.pdf", chunks(content)))
    assert caught.value.status_code == 422
    assert get_configuration() == original
    assert list(storage.storage_root().iterdir()) == []


def test_pdf_page_count_bound(monkeypatch):
    monkeypatch.setattr(storage, "MAX_PDF_PAGES", 2, raising=False)
    with pytest.raises(storage.FileStorageError) as caught:
        asyncio.run(storage.store_stream("lesson.pdf", chunks(pdf_bytes(pages=3))))
    assert caught.value.status_code == 422


def test_safe_storage_preserves_legacy_file_and_deletion_round_trip():
    name, absolute = storage.store_bytes("legacy.bin", b"legacy student data")
    target = Path(absolute)
    assert target.is_absolute() and target.name == name
    assert storage.safe_storage_file(absolute) == target
    staged = storage.stage_deletion(absolute)
    assert staged is not None and not target.exists()
    assert storage.safe_storage_file(str(staged[1])) is None
    storage.restore_staged_file(staged)
    assert target.read_bytes() == b"legacy student data"
    storage.finish_staged_deletion(storage.stage_deletion(absolute))
    assert not target.exists()


@pytest.mark.parametrize("live_exists", [False, True])
def test_stage_deletion_refuses_existing_staged_bytes(live_exists):
    _, absolute = storage.store_bytes("notes.txt", b"keep staged bytes")
    target = Path(absolute)
    staged = storage.stage_deletion(absolute)
    assert staged is not None
    if live_exists:
        target.write_bytes(b"keep live bytes too")
    with pytest.raises(storage.FileStorageError) as caught:
        storage.stage_deletion(absolute)
    assert caught.value.status_code == 503
    assert staged[1].read_bytes() == b"keep staged bytes"
    assert target.exists() is live_exists
    if live_exists:
        assert target.read_bytes() == b"keep live bytes too"


@pytest.mark.parametrize("failure_kind", ["root_configuration", "root_permission", "file_permission"])
def test_stage_deletion_does_not_treat_unavailable_storage_as_missing(monkeypatch, failure_kind):
    _, absolute = storage.store_bytes("notes.txt", b"keep private bytes")
    target = Path(absolute)
    original_lstat = Path.lstat

    def unavailable_root():
        if failure_kind == "root_configuration":
            raise storage.FileStorageError(500, "private configuration")
        raise PermissionError("private root")

    def unavailable_lstat(path, *args, **kwargs):
        if path == target:
            raise PermissionError("private file")
        return original_lstat(path, *args, **kwargs)

    with monkeypatch.context() as patcher:
        if failure_kind == "file_permission":
            patcher.setattr(Path, "lstat", unavailable_lstat)
        else:
            patcher.setattr(storage, "storage_root", unavailable_root)
        if failure_kind != "file_permission":
            assert storage.safe_storage_file(absolute) is None
        with pytest.raises((storage.FileStorageError, PermissionError)):
            storage.stage_deletion(absolute)
    assert target.read_bytes() == b"keep private bytes"
    assert list(target.parent.iterdir()) == [target]


def test_safe_storage_rejects_traversal_root_temporary_and_outside(tmp_path):
    root = storage.storage_root()
    target = root / "safe.txt"
    target.write_text("safe")
    hidden = root / ".secret.uploading"
    hidden.write_text("staged")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside")
    for invalid in (str(root), str(hidden), str(outside), str(root / ".." / root.name / target.name), str(root / "missing.txt")):
        assert storage.safe_storage_file(invalid) is None


def make_symlink_or_skip(link, target, directory=False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error.winerror if hasattr(error, 'winerror') else error.errno}")


def test_safe_storage_rejects_even_internal_symlink(tmp_path):
    root = storage.storage_root()
    target = root / "safe.txt"
    target.write_text("safe")
    link = root / "link.txt"
    make_symlink_or_skip(link, target)
    assert storage.safe_storage_file(str(link)) is None


def test_symlink_storage_root_is_rejected(tmp_path, monkeypatch):
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    make_symlink_or_skip(linked, real, directory=True)
    monkeypatch.setattr(storage.settings, "file_storage_path", str(linked))
    with pytest.raises(storage.FileStorageError) as caught:
        storage.storage_root()
    assert caught.value.status_code == 500
    assert list(real.iterdir()) == []


def test_public_static_storage_is_rejected_without_creating_files(tmp_path, monkeypatch):
    public = tmp_path / "static"
    monkeypatch.setattr(storage, "_PUBLIC_STATIC_ROOT", public, raising=False)
    monkeypatch.setattr(storage.settings, "file_storage_path", str(public / "must-not-be-created"))
    with pytest.raises(storage.FileStorageError) as caught:
        storage.storage_root()
    assert caught.value.status_code == 500
    assert not (public / "must-not-be-created").exists()


def test_exclusive_temporary_collision_does_not_delete_existing_file(monkeypatch):
    class FixedUUID:
        hex = "0" * 32
    monkeypatch.setattr(storage, "uuid4", lambda: FixedUUID())
    existing = storage.storage_root() / ("." + "0" * 32 + ".txt.uploading")
    existing.write_bytes(b"do-not-delete")
    with pytest.raises(storage.FileStorageError):
        asyncio.run(storage.store_stream("x.txt", chunks(b"new content")))
    assert existing.read_bytes() == b"do-not-delete"


def test_published_upload_does_not_perform_fallible_temp_cleanup(monkeypatch):
    def cannot_unlink(*args, **kwargs):
        raise OSError("secret-path")
    monkeypatch.setattr(Path, "unlink", cannot_unlink)
    result = asyncio.run(storage.store_stream("x.txt", chunks(b"complete")))
    assert Path(result.storage_path).read_bytes() == b"complete"


def test_cleanup_filesystem_error_does_not_expose_paths(monkeypatch):
    def cannot_unlink(*args, **kwargs):
        raise OSError("secret-path")
    with monkeypatch.context() as patcher:
        patcher.setattr(Path, "unlink", cannot_unlink)
        with pytest.raises(storage.FileStorageError) as caught:
            asyncio.run(storage.store_stream("x.txt", chunks(b"too big"), max_size=1))
    assert caught.value.status_code == 500
    assert "secret-path" not in caught.value.detail


def test_png_decompression_bomb_header_rejected():
    import struct
    import zlib
    data = bytearray(image_bytes())
    data[16:24] = struct.pack(">II", 100_000, 100_000)
    data[29:33] = struct.pack(">I", zlib.crc32(data[12:29]))
    with pytest.raises(storage.FileStorageError) as caught:
        asyncio.run(storage.store_stream("bomb.png", chunks(bytes(data))))
    assert caught.value.status_code == 422
    assert list(storage.storage_root().iterdir()) == []


def test_boundary_limit_is_inclusive_and_stream_is_not_overconsumed():
    result = asyncio.run(storage.store_stream("limit.txt", chunks(b"12", b"345"), max_size=5))
    assert result.size == 5

    async def over_quota():
        yield b"123456"
        pytest.fail("iterator consumed after size limit exceeded")
    with pytest.raises(storage.FileStorageError) as caught:
        asyncio.run(storage.store_stream("large.txt", over_quota(), max_size=5))
    assert caught.value.status_code == 413
    assert len(list(storage.storage_root().iterdir())) == 1


@pytest.mark.parametrize("constant,value", [("MAX_PDF_OBJECTS", 2), ("MAX_PDF_NODES", 3), ("MAX_PDF_DECODED_BYTES", 2)])
def test_pdf_resource_counters_enforced(monkeypatch, constant, value):
    content = pdf_bytes(content=b"q Q")
    monkeypatch.setattr(storage, constant, value)
    with pytest.raises(storage.FileStorageError) as caught:
        asyncio.run(storage.store_stream("limited.pdf", chunks(content)))
    assert caught.value.status_code == 422
    assert list(storage.storage_root().iterdir()) == []


def test_safe_storage_rejects_colon_stream_names():
    root = storage.storage_root()
    (root / "safe.txt").write_bytes(b"base")
    stream_path = root / "safe.txt:metadata"
    stream_path.write_bytes(b"not a public file")
    assert storage.safe_storage_file(str(stream_path)) is None


def test_actual_task_cancellation_removes_staging_file():
    async def scenario():
        waiting = asyncio.Event()
        async def interrupted():
            yield b"part"
            waiting.set()
            await asyncio.Event().wait()
        task = asyncio.create_task(storage.store_stream("x.txt", interrupted()))
        await asyncio.wait_for(waiting.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert list(storage.storage_root().iterdir()) == []
    asyncio.run(scenario())


def test_large_chunk_is_on_disk_before_stream_finishes():
    content = b"x" * 131072
    async def streaming():
        yield content
        staged = list(storage.storage_root().iterdir())
        assert len(staged) == 1
        assert staged[0].stat().st_size == len(content)
        yield b"end"
    result = asyncio.run(storage.store_stream("stream.txt", streaming()))
    assert result.size == len(content) + 3


def test_upload_setting_positive_and_bounded():
    assert Settings(_env_file=None).file_upload_max_bytes == 20 * 1024 * 1024
    for value in (0, -1, 20 * 1024 * 1024 + 1):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, file_upload_max_bytes=value)
