"""Validate the pinned shared Arcium core revision (not a browser build)."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

PIN_FILE = Path(__file__).resolve().parents[1] / "upstream" / "arcium-core.sha"
UPSTREAM_COMMITS_API = "https://api.github.com/repos/dr-baker/Arcium/commits/"


def parse_revision(value: str) -> str:
    revision = value.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Expected a full, lowercase 40-character Git commit SHA")
    return revision


def read_revision(path: Path = PIN_FILE) -> str:
    return parse_revision(path.read_text(encoding="utf-8"))


def check_remote_revision(revision: str) -> None:
    """Raise on a missing or inaccessible commit, or unexpected API response."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Arcium-Windows-upstream-validation",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(UPSTREAM_COMMITS_API + revision, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub upstream commit check failed (HTTP {exc.code})") from exc
    if result.get("sha") != revision:
        raise RuntimeError("Upstream API returned an unexpected commit SHA")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-remote", action="store_true",
                        help="Verify the pinned commit exists in dr-baker/Arcium")
    args = parser.parse_args()
    revision = read_revision()
    print(f"Pinned Arcium core commit: {revision}")
    if args.check_remote:
        check_remote_revision(revision)
        print("Upstream commit exists.")
    print("Validation completed. This does NOT validate or build a Windows browser.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
