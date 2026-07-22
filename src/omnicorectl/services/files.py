"""Read-only controller file-service resources."""

from __future__ import annotations

from dataclasses import dataclass
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
