from __future__ import annotations

import asyncio
import codecs
import os
import stat
import unicodedata
import warnings
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.core.config import settings


class FileStorageError(Exception):
    """A public error with no filesystem paths or parser internals."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def validate_filename(name: str) -> str:
    if (
        not isinstance(name, str)
        or not name
        or len(name.encode("utf-8", errors="surrogatepass")) > 255
        or name != name.strip()
        or name.startswith(".")
        or name.endswith(".")
        or any(char in '/\\\\:<>"|?*' or unicodedata.category(char).startswith("C") for char in name)
        or name.split(".", 1)[0].upper().rstrip(" ") in {
            "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
            *(f"{prefix}{number}" for prefix in ("COM", "LPT") for number in "123456789¹²³"),
        }
    ):
        raise FileStorageError(422, "Недопустимое имя файла")
    return name


_PUBLIC_STATIC_ROOT = Path(__file__).resolve().parent / "web" / "static"


def _is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def storage_root() -> Path:
    try:
        candidate = Path(settings.file_storage_path).absolute()
        if ".." in candidate.parts or any(_is_link(part) for part in (candidate, *candidate.parents)):
            raise FileStorageError(500, "Небезопасная конфигурация хранилища")
        root = candidate.resolve()
        public = _PUBLIC_STATIC_ROOT.resolve()
        if root.is_relative_to(public) or public.is_relative_to(root):
            raise FileStorageError(500, "Небезопасная конфигурация хранилища")
        root.mkdir(parents=True, exist_ok=True)
        return root
    except OSError:
        raise FileStorageError(500, "Хранилище недоступно") from None


@dataclass
class StoredUpload:
    original_name: str
    stored_name: str
    storage_path: str
    mime_type: str
    size: int
    previewable: bool


MAX_IMAGE_PIXELS = 16_000_000
MAX_IMAGE_SIDE = 16_384


def _inspect_image(path: Path, mime_type: str) -> tuple[str, bool]:
    from PIL import Image

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path, formats=("PNG", "JPEG")) as image:
                if image.width * image.height > MAX_IMAGE_PIXELS or max(image.size) > MAX_IMAGE_SIDE:
                    raise ValueError("image budget")
                if getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) != 1:
                    raise ValueError("animation")
                image.verify()
            # verify checks structure; a separate decode catches truncated pixel data.
            with Image.open(path, formats=("PNG", "JPEG")) as image:
                image.load()
    except Exception:
        raise FileStorageError(422, "Повреждённое или слишком сложное изображение") from None
    return mime_type, True


MAX_PDF_PAGES = 500
MAX_PDF_OBJECTS = 10_000
MAX_PDF_NODES = 100_000
MAX_PDF_STREAM_BYTES = 8 * 1024 * 1024
MAX_PDF_DECODED_BYTES = 32 * 1024 * 1024
_PDF_FORBIDDEN_KEYS = frozenset({
    "/AA", "/OpenAction", "/A", "/JS", "/JavaScript", "/Launch", "/EmbeddedFiles",
    "/EmbeddedFile", "/XFA", "/AcroForm", "/RichMedia", "/RichMediaContent",
    "/Collection", "/URI", "/GoToR", "/GoToE", "/SubmitForm", "/ImportData",
})
_PDF_FORBIDDEN_TYPES = frozenset({"/EmbeddedFile", "/Filespec", "/RichMedia", "/Movie", "/Sound", "/3D"})
_PDF_FILTERS = frozenset({"/FlateDecode", "/ASCIIHexDecode", "/ASCII85Decode", "/LZWDecode", "/RunLengthDecode", "/DCTDecode", "/JPXDecode", "/CCITTFaxDecode"})


def _inspect_pdf(path: Path) -> tuple[str, bool]:
    from pypdf import PdfReader, apply_configuration
    from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, StreamObject

    try:
        # apply_configuration is ContextVar-scoped, not a process-global mutation.
        with apply_configuration(
            maximum_declared_stream_length=MAX_PDF_STREAM_BYTES,
            array_based_stream_maximum_output_length=MAX_PDF_STREAM_BYTES,
            zlib_maximum_output_length=MAX_PDF_STREAM_BYTES,
            lzw_maximum_output_length=MAX_PDF_STREAM_BYTES,
            run_length_maximum_output_length=MAX_PDF_STREAM_BYTES,
            brotli_maximum_output_length=MAX_PDF_STREAM_BYTES,
            jbig2_maximum_output_length=MAX_PDF_STREAM_BYTES,
            image_maximum_buffer_size=MAX_PDF_STREAM_BYTES,
            stream_decoding_work_maximum_length=MAX_PDF_DECODED_BYTES,
            stream_parsing_work_maximum_count=MAX_PDF_NODES,
            array_maximum_element_count=MAX_PDF_OBJECTS,
            dictionary_maximum_element_count=MAX_PDF_OBJECTS,
            page_tree_maximum_entries=MAX_PDF_PAGES * 2,
            page_tree_maximum_depth=32,
            stream_filters_maximum_length=4,
            jbig2dec_binary=None,
            disable_legacy_handling=True,
        ), path.open("rb") as source:
            header = source.read(9)
            if not (header.startswith((b"%PDF-1.", b"%PDF-2.")) and header[7:8].isdigit()):
                raise ValueError("header")
            source.seek(max(0, path.stat().st_size - 1024))
            tail = source.read(1024)
            if not tail.rstrip().endswith(b"%%EOF") or b"startxref" not in tail:
                raise ValueError("trailer")
            source.seek(0)
            reader = PdfReader(source, strict=True, root_object_recovery_limit=0)
            if reader.is_encrypted:
                raise ValueError("encryption")
            references = [(number, generation) for generation, entries in reader.xref.items() for number in entries if number]
            references.extend((number, 0) for number in reader.xref_objStm)
            if len(references) > MAX_PDF_OBJECTS or int(reader.trailer.get("/Size", 0)) > MAX_PDF_OBJECTS + 1:
                raise ValueError("object budget")
            if not 1 <= len(reader.pages) <= MAX_PDF_PAGES:
                raise ValueError("page budget")
            stack = [(reader.trailer, 0)]
            stack.extend((IndirectObject(number, generation, reader), 0) for number, generation in references)
            seen_references = set()
            seen_containers = set()
            nodes = decoded_bytes = 0
            while stack:
                obj, depth = stack.pop()
                nodes += 1
                if nodes > MAX_PDF_NODES or depth > 64:
                    raise ValueError("graph budget")
                if isinstance(obj, IndirectObject):
                    key = (obj.idnum, obj.generation)
                    if key in seen_references:
                        continue
                    seen_references.add(key)
                    stack.append((obj.get_object(), depth + 1))
                elif isinstance(obj, (DictionaryObject, ArrayObject)):
                    if id(obj) in seen_containers:
                        continue
                    seen_containers.add(id(obj))
                    if isinstance(obj, DictionaryObject):
                        if _PDF_FORBIDDEN_KEYS.intersection(obj) or str(obj.get("/Type", "")) in _PDF_FORBIDDEN_TYPES:
                            raise ValueError("active content")
                        if str(obj.get("/S", "")) in {"/JavaScript", "/Launch", "/URI", "/GoToR", "/GoToE", "/SubmitForm", "/ImportData", "/Rendition", "/Movie", "/Sound"}:
                            raise ValueError("action")
                        if isinstance(obj, StreamObject):
                            filters = obj.get("/Filter", [])
                            if isinstance(filters, IndirectObject):
                                filters = filters.get_object()
                            if not isinstance(filters, (list, ArrayObject)):
                                filters = [filters]
                            if any(str(filter_name) not in _PDF_FILTERS for filter_name in filters):
                                raise ValueError("unsupported filter")
                            decoded_bytes += len(obj.get_data())
                            if decoded_bytes > MAX_PDF_DECODED_BYTES:
                                raise ValueError("decoded budget")
                        stack.extend((value, depth + 1) for value in obj.values())
                    else:
                        stack.extend((value, depth + 1) for value in obj)
    except Exception:
        raise FileStorageError(422, "Повреждённый или недопустимый PDF") from None
    return "application/pdf", False


_MIME_BY_SUFFIX = {".txt": "text/plain", ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def inspect_file(path: Path, original_name: str, declared_mime: str | None = None) -> tuple[str, bool]:
    validate_filename(original_name)
    expected = _MIME_BY_SUFFIX.get(Path(original_name).suffix.lower())
    declared = (declared_mime or "").split(";", 1)[0].strip().lower()
    if not expected or declared not in ("", "application/octet-stream", expected):
        raise FileStorageError(415, "Неподдерживаемый или несовпадающий формат файла")
    try:
        size = path.stat().st_size
        if not size:
            raise FileStorageError(422, "Пустой файл")
        if size > settings.file_upload_max_bytes:
            raise FileStorageError(413, "Файл превышает допустимый размер")
        with path.open("rb") as source:
            header = source.read(16)
            actual = (
                "image/png" if header.startswith(bytes.fromhex("89504e470d0a1a0a")) else
                "image/jpeg" if header.startswith(b"\xff\xd8\xff") else
                "application/pdf" if header.startswith(b"%PDF-") else "text/plain"
            )
            if actual != expected:
                raise FileStorageError(415, "Неподдерживаемый или несовпадающий формат файла")
            if actual.startswith("image/"):
                return _inspect_image(path, actual)
            if actual == "application/pdf":
                return _inspect_pdf(path)
            source.seek(0)
            decoder = codecs.getincrementaldecoder("utf-8")("strict")
            while chunk := source.read(65536):
                text = decoder.decode(chunk)
                if any(unicodedata.category(char) == "Cc" and ord(char) not in (9, 10, 13) for char in text):
                    raise FileStorageError(415, "Двоичный файл не является текстом")
            decoder.decode(b"", final=True)
    except UnicodeError:
        raise FileStorageError(422, "Текст должен быть корректным UTF-8") from None
    except OSError:
        raise FileStorageError(500, "Не удалось прочитать файл") from None
    return "text/plain", True


async def _inspect_stream_file(path: Path, original_name: str, declared_mime: str | None):
    worker = asyncio.create_task(asyncio.to_thread(inspect_file, path, original_name, declared_mime))
    cancelled = None
    while True:
        try:
            result = await asyncio.shield(worker)
        except asyncio.CancelledError as error:
            if worker.cancelled():
                raise
            # Wait until the reader closes its handle before unlinking staging.
            cancelled = error
        except Exception:
            if cancelled is not None:
                raise cancelled
            raise
        else:
            if cancelled is not None:
                raise cancelled
            return result


async def store_stream(
    original_name: str,
    stream: AsyncIterator[bytes],
    *,
    declared_mime: str | None = None,
    max_size: int | None = None,
) -> StoredUpload:
    validate_filename(original_name)
    limit = settings.file_upload_max_bytes if max_size is None else min(max_size, settings.file_upload_max_bytes)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise FileStorageError(422, "Недопустимый лимит размера")
    root = storage_root()
    stored_name = f"{uuid4().hex}{Path(original_name).suffix.lower()}"
    final_path = root / stored_name
    temporary_path = root / f".{stored_name}.uploading"
    size = 0
    created = False
    try:
        with temporary_path.open("xb") as destination:
            created = True
            async for chunk in stream:
                size += len(chunk)
                if size > limit:
                    raise FileStorageError(413, "Файл превышает допустимый размер")
                destination.write(chunk)
            if not size:
                raise FileStorageError(422, "Пустой файл")
            destination.flush()
            os.fsync(destination.fileno())
        mime_type, previewable = await _inspect_stream_file(temporary_path, original_name, declared_mime)
        os.replace(temporary_path, final_path)
        created = False
        return StoredUpload(original_name, stored_name, str(final_path), mime_type, size, previewable)
    except OSError:
        raise FileStorageError(500, "Не удалось сохранить файл") from None
    finally:
        if created:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                raise FileStorageError(500, "Не удалось очистить временный файл") from None


def store_bytes(original_name: str, content: bytes) -> tuple[str, str]:
    suffix = Path(original_name).suffix[:16]
    stored_name = f"{uuid4().hex}{suffix}"
    root = storage_root()
    final_path = root / stored_name
    temporary_path = root / f".{stored_name}.uploading"
    try:
        temporary_path.write_bytes(content)
        os.replace(temporary_path, final_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise
    return stored_name, str(final_path)


def safe_storage_file(path: str | None, *, strict: bool = False) -> Path | None:
    """Resolve private bytes; mutations must not mistake storage failures for absence."""
    if not path:
        return None
    try:
        root = storage_root()
        target = Path(path)
        if ".." in target.parts:
            return None
        validate_filename(target.name)
        target = target.absolute()
        # Files produced by either storage API are direct children, never subtrees.
        if target.parent != root:
            return None
        try:
            info = target.lstat()
        except FileNotFoundError:
            return None
        # Unlike is_file(), lstat does not suppress permission/I/O errors.
        if not stat.S_ISREG(info.st_mode) or _is_link(target):
            return None
        return target if target.resolve(strict=True).parent == root else None
    except (OSError, FileStorageError):
        if strict:
            raise
        return None
    except ValueError:
        if strict:
            raise FileStorageError(500, "Не удалось разрешить путь файла") from None
        return None


def stage_deletion(path: str | None) -> tuple[Path, Path] | None:
    target = safe_storage_file(path, strict=True)
    candidate = Path(path).absolute() if path else None
    if candidate is not None and ".." not in candidate.parts and candidate.parent == storage_root():
        # A rollback releases the row lock before recovery can reacquire it.
        # Missing live bytes with an existing stage are NOT completed cleanup.
        prefix = f".{candidate.name}."
        if any(entry.name.startswith(prefix) and entry.name.endswith(".deleting")
               for entry in candidate.parent.iterdir()):
            raise FileStorageError(503, "Удаление файла ожидает восстановления хранилища")
    if target is None:
        return None
    staged = target.with_name(f".{target.name}.{uuid4().hex}.deleting")
    os.replace(target, staged)
    return target, staged


def restore_staged_file(staged: tuple[Path, Path] | None) -> None:
    if staged and staged[1].exists():
        os.replace(staged[1], staged[0])


def finish_staged_deletion(staged: tuple[Path, Path] | None) -> None:
    if staged:
        staged[1].unlink(missing_ok=True)
