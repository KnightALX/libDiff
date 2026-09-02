"""Discover Liberty (.lib) files under a directory."""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from typing import Iterable, List, Optional, Union

_LIBRARY_NAME_RE = re.compile(
    r"^\s*library\s*\(\s*([^)\s]+)\s*\)",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class DiscoveredLib:
    """One discovered .lib file with cheap fingerprint metadata."""

    path: str
    size: int
    library_name: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _peek_library_name(path: str, max_bytes: int = 8192) -> Optional[str]:
    """Read a small prefix and extract the first ``library (name)`` if present."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read(max_bytes)
    except OSError:
        return None
    text = raw.decode("utf-8", errors="replace")
    # Strip block comments in the prefix so commented library lines are ignored cheaply
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    m = _LIBRARY_NAME_RE.search(text)
    if not m:
        return None
    return m.group(1).strip().strip('"').strip("'")


def discover_libs(
    directory: Union[str, os.PathLike],
    *,
    recursive: bool = False,
    extensions: Iterable[str] = (".lib",),
) -> List[DiscoveredLib]:
    """Scan *directory* for Liberty files.

    Non-recursive by default. Returns entries sorted by absolute path.
    """
    root = os.path.abspath(os.fspath(directory))
    if not os.path.isdir(root):
        raise FileNotFoundError('directory "%s" not found' % root)

    exts = {e.lower() if e.startswith(".") else ".%s" % e.lower() for e in extensions}
    found: List[str] = []

    if recursive:
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                if os.path.splitext(name)[1].lower() in exts:
                    found.append(os.path.join(dirpath, name))
    else:
        for name in os.listdir(root):
            path = os.path.join(root, name)
            if os.path.isfile(path) and os.path.splitext(name)[1].lower() in exts:
                found.append(path)

    found.sort()
    results: List[DiscoveredLib] = []
    for path in found:
        abs_path = os.path.abspath(path)
        try:
            size = os.path.getsize(abs_path)
        except OSError:
            size = -1
        results.append(
            DiscoveredLib(
                path=abs_path,
                size=size,
                library_name=_peek_library_name(abs_path),
            )
        )
    return results


__all__ = ["DiscoveredLib", "discover_libs"]
