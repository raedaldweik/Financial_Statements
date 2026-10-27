"""Document identity.

A filing is recognised by the SHA-256 of the uploaded file and, more loosely, by a fingerprint
of its extracted text (letters and digits only, first 40 pages), which survives a re-download
or a metadata-only change of the same PDF. Both are stored on every bundle so a document that
was processed before is restored from that analysis instead of being processed again.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def text_fingerprint(raw_pages: list[str]) -> str:
    norm = re.sub(r"[^a-z0-9]+", "", "".join(raw_pages[:40]).lower())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()
