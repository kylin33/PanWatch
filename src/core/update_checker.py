"""应用升级检测模块（基于 Docker Hub tag）。"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from threading import Lock

import requests

_CACHE_LOCK = Lock()
_CACHE: dict[str, object] = {
    "ts": 0.0,
    "latest_version": None,
    "release_url": None,
    "error": None,
}
_CACHE_TTL_SECONDS = 15 * 60


def _normalize(version: str | None) -> str:
    return str(version or "").strip().lstrip("vV")


def _parse_semver(version: str | None) -> tuple[int, int, int] | None:
    v = _normalize(version)
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", v)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _fetch_latest_docker_tag(repo: str) -> tuple[str | None, str | None, str | None]:
    # Docker Hub API:
    # GET /v2/namespaces/{namespace}/repositories/{repository}/tags?page_size=100
    parts = [p for p in repo.strip("/").split("/") if p]
    if len(parts) != 2:
        return None, None, "invalid_repo"
    namespace, repository = parts
    url = f"https://hub.docker.com/v2/namespaces/{namespace}/repositories/{repository}/tags?page_size=100"
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code != 200:
            return None, None, f"http_{resp.status_code}"
        data = resp.json() or {}
        results = data.get("results") or []
        best_sem: tuple[int, int, int] | None = None
        best_tag: str | None = None
        for item in results:
            tag = str(item.get("name") or "").strip()
            sem = _parse_semver(tag)
            if sem is None:
                continue
            if best_sem is None or sem > best_sem:
                best_sem = sem
                best_tag = _normalize(tag)
        tags_url = f"https://hub.docker.com/r/{namespace}/{repository}/tags"
        if best_tag:
            return best_tag, tags_url, None
        return None, tags_url, "no_semver_tag"
    except Exception as e:
        return None, None, str(e)


def check_update(current_version: str) -> dict[str, object]:
    repo = os.getenv("UPDATE_CHECK_DOCKER_REPO", "sunxiao0721/panwatch")
    force_disable = os.getenv("UPDATE_CHECK_DISABLE", "").strip() in {"1", "true", "True"}
    if force_disable:
        return {
            "enabled": False,
            "source": "docker",
            "current_version": _normalize(current_version),
            "latest_version": None,
            "update_available": False,
            "release_url": f"https://hub.docker.com/r/{repo}/tags",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "error": "disabled",
        }

    now = time.monotonic()
    with _CACHE_LOCK:
        age = now - float(_CACHE["ts"] or 0)
        if age <= _CACHE_TTL_SECONDS and _CACHE.get("latest_version") is not None:
            latest = str(_CACHE.get("latest_version") or "")
            release_url = str(_CACHE.get("release_url") or f"https://hub.docker.com/r/{repo}/tags")
            err = _CACHE.get("error")
        else:
            latest, release_url, err = _fetch_latest_docker_tag(repo)
            _CACHE["ts"] = now
            _CACHE["latest_version"] = latest
            _CACHE["release_url"] = release_url
            _CACHE["error"] = err

    current_norm = _normalize(current_version)
    cur_sem = _parse_semver(current_norm)
    latest_sem = _parse_semver(latest)
    update_available = bool(cur_sem and latest_sem and latest_sem > cur_sem)

    return {
        "enabled": True,
        "source": "docker",
        "current_version": current_norm,
        "latest_version": latest,
        "update_available": update_available,
        "release_url": release_url or f"https://hub.docker.com/r/{repo}/tags",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "error": err,
    }
