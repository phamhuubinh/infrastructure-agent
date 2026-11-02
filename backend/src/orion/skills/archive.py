"""Bounded uploaded product packages; never extract an archive onto the server filesystem."""

import io
import stat
import zipfile
import zlib

from orion.skills.packages import (
    MAX_PACKAGE_BYTES,
    MAX_PACKAGE_FILES,
    MAX_RESOURCE_BYTES,
    SkillPackageError,
    resource_path,
)

MAX_ARCHIVE_BYTES = 2 * MAX_PACKAGE_BYTES


def archive_resources(data: bytes) -> dict[str, bytes]:
    try:
        if len(data) > MAX_ARCHIVE_BYTES:
            raise ValueError
        resources: dict[str, bytes] = {}
        seen: set[str] = set()
        directories: set[str] = set()
        total = 0
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if len(archive.infolist()) > MAX_PACKAGE_FILES + 64:
                raise ValueError
            for item in archive.infolist():
                original = item.orig_filename
                name = resource_path(original[:-1] if item.is_dir() else original)
                mode = item.external_attr >> 16
                kind = stat.S_IFMT(mode)
                if (
                    original != item.filename
                    or name in seen
                    or item.flag_bits & 1
                    or item.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                    or kind not in {0, stat.S_IFDIR if item.is_dir() else stat.S_IFREG}
                    or len(name.split("/")) > 8
                ):
                    raise ValueError
                seen.add(name)
                parts = name.split("/")
                directories.update("/".join(parts[:i]) for i in range(1, len(parts)))
                if item.is_dir():
                    directories.add(name)
                    if item.file_size:
                        raise ValueError
                else:
                    if item.file_size > MAX_RESOURCE_BYTES or len(resources) >= MAX_PACKAGE_FILES:
                        raise ValueError
                    with archive.open(item) as source:
                        content = source.read(MAX_RESOURCE_BYTES + 1)
                    if len(content) != item.file_size or len(content) > MAX_RESOURCE_BYTES:
                        raise ValueError
                    total += len(content)
                    if total > MAX_PACKAGE_BYTES:
                        raise ValueError
                    resources[name] = content
                if len(directories) > 64:
                    raise ValueError
        if directories & resources.keys():
            raise ValueError
        return resources
    except (OSError, ValueError, RuntimeError, NotImplementedError, zipfile.BadZipFile, zlib.error):
        raise SkillPackageError("invalid_archive") from None
