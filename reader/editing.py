"""Editable document state and atomic source writes; independent of the window."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from PySide6.QtCore import QIODevice, QSaveFile

from reader.documents import Document, EXTENSIONS, MAX_FILE_BYTES


class FileChangedError(OSError):
    """The on-disk version no longer matches the version the user opened."""


def fingerprint(path: Path) -> str | None:
    try:
        with path.open("rb") as stream:
            digest = sha256()
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
            return digest.hexdigest()
    except FileNotFoundError:
        return None


def atomic_write(path: Path, data: bytes, expected: str | None) -> str:
    """Check the destination both before writing and before committing."""
    if fingerprint(path) != expected:
        raise FileChangedError("The file changed on disk.")
    output = QSaveFile(str(path))
    output.setDirectWriteFallback(False)
    if not output.open(QIODevice.OpenModeFlag.WriteOnly):
        raise OSError(output.errorString())
    if output.write(data) != len(data):
        output.cancelWriting()
        raise OSError(output.errorString())
    if fingerprint(path) != expected:
        output.cancelWriting()
        raise FileChangedError("The file changed while saving. Please try again.")
    if not output.commit():
        raise OSError(output.errorString())
    return sha256(data).hexdigest()


@dataclass
class EditSession:
    document: Document
    saved_source: str

    @classmethod
    def opened(cls, document: Document) -> EditSession:
        return cls(document, document.source)

    @property
    def dirty(self) -> bool:
        return self.document.source != self.saved_source

    def payload(self) -> dict:
        return {**self.document.to_dict(), "savedSource": self.saved_source, "dirty": self.dirty}

    def save(self, path: Path, expected: str | None) -> None:
        doc = self.document
        path = path.expanduser().resolve()
        if path.suffix.lower() not in EXTENSIONS:
            raise ValueError("Choose a Markdown, HTML, or text filename.")
        target_format = "HTML" if path.suffix.lower() in {".html", ".htm"} else "Markdown"
        if target_format != doc.format:
            raise ValueError(f"Choose a {doc.format} extension. Save As preserves the source format.")
        if "\x00" in doc.source:
            raise ValueError("The source contains a null character and cannot be saved as a text document.")
        data = bytes.fromhex(doc.bom) + doc.source.replace("\n", doc.newline).encode(doc.codec)
        if len(data) > MAX_FILE_BYTES:
            raise ValueError("This document exceeds the 5 MB file limit. Your edits are still open.")
        digest = atomic_write(path, data, expected)
        # Only a successful commit may change the active path or saved baseline.
        doc.path, doc.name = str(path), path.name
        doc.size, doc.fingerprint, doc.sample = len(data), digest, False
        self.saved_source = doc.source
