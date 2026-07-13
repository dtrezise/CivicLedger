#!/usr/bin/env python3
"""Shared deterministic metrics for CivicLedger's public static corpus."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath


class CorpusMetricsError(RuntimeError):
    """Raised when the public corpus does not match its manifest contract."""


def read_manifest(manifest_path: Path) -> dict:
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise CorpusMetricsError(f"Cannot read public manifest {manifest_path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise CorpusMetricsError("Public manifest must contain a JSON object")
    return manifest


def _safe_relative_path(value: object) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise CorpusMetricsError("Manifest artifact path must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise CorpusMetricsError(f"Unsafe manifest artifact path: {value}")
    return path


def _artifact_record(
    *,
    data_root: Path,
    group: str,
    key: str,
    kind: str,
    record: object,
) -> dict:
    if not isinstance(record, dict):
        raise CorpusMetricsError(f"Manifest artifact {group}/{key} must be an object")
    relative_path = _safe_relative_path(record.get("path"))
    path = data_root.joinpath(*relative_path.parts)
    if not path.is_file():
        raise CorpusMetricsError(f"Manifest artifact is missing: {relative_path.as_posix()}")

    encoded = path.read_bytes()
    actual_bytes = len(encoded)
    expected_bytes = record.get("bytes")
    if not isinstance(expected_bytes, int) or expected_bytes < 0:
        raise CorpusMetricsError(f"Manifest artifact has invalid byte count: {relative_path.as_posix()}")
    if actual_bytes != expected_bytes:
        raise CorpusMetricsError(
            f"Manifest byte mismatch for {relative_path.as_posix()}: "
            f"expected {expected_bytes}, found {actual_bytes}"
        )

    expected_sha256 = record.get("sha256")
    actual_sha256 = hashlib.sha256(encoded).hexdigest()
    if expected_sha256 != actual_sha256:
        raise CorpusMetricsError(f"Manifest hash mismatch for {relative_path.as_posix()}")

    return {
        "bytes": actual_bytes,
        "group": group,
        "key": str(key),
        "kind": kind,
        "path": relative_path.as_posix(),
        "sha256": actual_sha256,
    }


def validated_manifest_artifacts(manifest: dict, manifest_path: Path) -> list[dict]:
    """Return unique, byte-verified public artifacts declared by the manifest."""
    artifacts: list[dict] = []
    data_root = manifest_path.parent

    files = manifest.get("files", {})
    if not isinstance(files, dict):
        raise CorpusMetricsError("Manifest files section must be an object")
    for key, record in sorted(files.items()):
        artifacts.append(
            _artifact_record(
                data_root=data_root,
                group="bootstrap",
                key=str(key),
                kind="bootstrap",
                record=record,
            )
        )

    partitions = manifest.get("partitions", {})
    if not isinstance(partitions, dict):
        raise CorpusMetricsError("Manifest partitions section must be an object")
    for group, records in sorted(partitions.items()):
        if not isinstance(records, dict):
            raise CorpusMetricsError(f"Manifest partition group {group} must be an object")
        for key, record in sorted(records.items()):
            artifacts.append(
                _artifact_record(
                    data_root=data_root,
                    group=str(group),
                    key=str(key),
                    kind="query_partition",
                    record=record,
                )
            )

    seen_paths: set[str] = set()
    for artifact in artifacts:
        path = artifact["path"]
        if path in seen_paths:
            raise CorpusMetricsError(f"Manifest declares the artifact more than once: {path}")
        seen_paths.add(path)
    return artifacts


def static_asset_summary(site: Path) -> dict:
    if not site.is_dir():
        raise CorpusMetricsError(f"Static asset directory does not exist: {site}")
    symlinks = sorted(path for path in site.rglob("*") if path.is_symlink())
    if symlinks:
        relative = symlinks[0].relative_to(site).as_posix()
        raise CorpusMetricsError(f"Static asset directory contains symlink: {relative}")

    assets = sorted(path for path in site.rglob("*") if path.is_file())
    sizes = [(path.relative_to(site).as_posix(), path.stat().st_size) for path in assets]
    largest_path, largest_bytes = max(sizes, key=lambda item: (item[1], item[0]), default=(None, 0))
    return {
        "asset_count": len(sizes),
        "largest_asset": {"bytes": largest_bytes, "path": largest_path},
        "total_bytes": sum(size for _, size in sizes),
    }


def public_artifact_summary(artifacts: list[dict]) -> dict:
    groups: dict[str, dict[str, int]] = {}
    for artifact in artifacts:
        group = artifact["group"]
        summary = groups.setdefault(group, {"artifact_count": 0, "total_bytes": 0})
        summary["artifact_count"] += 1
        summary["total_bytes"] += artifact["bytes"]

    query_partitions = [artifact for artifact in artifacts if artifact["kind"] == "query_partition"]
    largest = max(artifacts, key=lambda item: (item["bytes"], item["path"]), default=None)
    return {
        "declared_artifact_count": len(artifacts),
        "groups": dict(sorted(groups.items())),
        "largest_artifact": {
            "bytes": largest["bytes"],
            "group": largest["group"],
            "path": largest["path"],
        }
        if largest
        else None,
        "query_partition_count": len(query_partitions),
        "query_partition_total_bytes": sum(item["bytes"] for item in query_partitions),
        "total_bytes": sum(item["bytes"] for item in artifacts),
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
