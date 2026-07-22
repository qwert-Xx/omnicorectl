"""Read-only controller file-service resources."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from urllib.parse import quote

from omnicorectl.errors import ConfigurationError, ProtocolError
from omnicorectl.rws.client import RwsClient
from omnicorectl.rws.hal import (
    embedded_resources,
    required_bool,
    required_int,
    required_text,
)


@dataclass(frozen=True, slots=True)
class FileEntry:
    path: str
    name: str
    is_directory: bool
    size: int | None
    read_only: bool
    created: str
    modified: str


@dataclass(frozen=True, slots=True)
class DownloadResult:
    remote_path: str
    local_path: str
    bytes_written: int


@dataclass(frozen=True, slots=True)
class UploadResult:
    local_path: str
    remote_path: str
    bytes_written: int


@dataclass(frozen=True, slots=True)
class DeleteResult:
    remote_path: str


class FileService:
    def __init__(self, client: RwsClient) -> None:
        self._client = client

    def list_directory(self, path: str = "/") -> list[FileEntry]:
        normalized, endpoint = _file_endpoint(path)
        resources = embedded_resources(
            self._client.get_json(endpoint), resource=f"file directory {normalized}"
        )
        entries = []
        for item in resources:
            resource_type = item.get("_type")
            if resource_type not in {"fs-file", "fs-dir"}:
                continue
            name = required_text(item, "_title", resource="file entry")
            is_directory = resource_type == "fs-dir"
            entries.append(
                FileEntry(
                    path=_join_controller_path(normalized, name),
                    name=name,
                    is_directory=is_directory,
                    size=None
                    if is_directory
                    else required_int(item, "fs-size", resource="file entry"),
                    read_only=required_bool(
                        item, "fs-readonly", resource="file entry"
                    ),
                    created=required_text(item, "fs-cdate", resource="file entry"),
                    modified=required_text(item, "fs-mdate", resource="file entry"),
                )
            )
        return entries

    def download_file(
        self, remote_path: str, local_path: Path, *, overwrite: bool = False
    ) -> DownloadResult:
        normalized, endpoint = _file_endpoint(remote_path)
        if normalized == "/":
            raise ConfigurationError("a file path is required for download")
        destination = local_path.expanduser().resolve()
        if not destination.parent.is_dir():
            raise ConfigurationError(
                f"destination directory does not exist: {destination.parent}"
            )
        if destination.exists() and not overwrite:
            raise ConfigurationError(f"destination already exists: {destination}")

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w+b",
                prefix=f".{destination.name}.",
                suffix=".part",
                dir=destination.parent,
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                bytes_written = self._client.download(endpoint, temporary)
                temporary.flush()
                os.fsync(temporary.fileno())

            if overwrite:
                os.replace(temporary_path, destination)
            else:
                try:
                    os.link(temporary_path, destination)
                except FileExistsError as exc:
                    raise ConfigurationError(
                        f"destination already exists: {destination}"
                    ) from exc
                temporary_path.unlink()
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        return DownloadResult(
            remote_path=normalized,
            local_path=str(destination),
            bytes_written=bytes_written,
        )

    def upload_file(
        self, local_path: Path, remote_path: str, *, overwrite: bool = False
    ) -> UploadResult:
        source = local_path.expanduser().resolve()
        if not source.is_file():
            raise ConfigurationError(f"local file does not exist: {source}")
        normalized, endpoint = _file_endpoint(remote_path)
        if normalized == "/":
            raise ConfigurationError("a remote file path is required for upload")
        remote = PurePosixPath(normalized)
        parent = str(remote.parent)
        if not overwrite and any(
            entry.name == remote.name for entry in self.list_directory(parent)
        ):
            raise ConfigurationError(f"remote file already exists: {normalized}")

        size = source.stat().st_size
        with source.open("rb") as stream:
            bytes_written = self._client.upload(endpoint, stream, size=size)
        return UploadResult(
            local_path=str(source),
            remote_path=normalized,
            bytes_written=bytes_written,
        )

    def delete_file(self, remote_path: str) -> DeleteResult:
        normalized, endpoint = _file_endpoint(remote_path)
        if normalized == "/":
            raise ConfigurationError("a remote file path is required for deletion")
        self._client.delete(endpoint)
        return DeleteResult(remote_path=normalized)


def _file_endpoint(path: str) -> tuple[str, str]:
    raw_segments = [segment for segment in path.strip("/").split("/") if segment]
    if any(segment in {".", ".."} for segment in raw_segments):
        raise ConfigurationError("file path cannot contain '.' or '..' segments")
    normalized = "/" + "/".join(raw_segments) if raw_segments else "/"
    encoded = "/".join(quote(segment, safe="") for segment in raw_segments)
    endpoint = "/fileservice" + (f"/{encoded}" if encoded else "")
    return normalized, endpoint


def _join_controller_path(parent: str, name: str) -> str:
    if "/" in name:
        raise ProtocolError("file entry name unexpectedly contains '/'")
    return f"/{name}" if parent == "/" else f"{parent}/{name}"
