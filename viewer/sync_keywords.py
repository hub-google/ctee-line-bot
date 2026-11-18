"""Mirror approved Supabase tracking keywords into the GitHub backup file.

The database is the authoritative source. Do not overwrite GitHub on an API
failure, empty response, invalid data, or ambiguous revision.
This script is safe to rerun: an unchanged backup is not rewritten.
"""
from __future__ import annotations

import json
import os
import sys
import unicodedata
from pathlib import Path
from urllib.request import Request, urlopen

KEYWORDS_API = os.environ.get(
    "CTEE_KEYWORDS_API_URL",
    "https://unapiwajmgqqtdkixaab.supabase.co/functions/v1/ctee-keywords?action=keywords",
)
BACKUP = Path(__file__).resolve().parent.parent / "keywords.txt"


def fetch_approved_keywords() -> tuple[list[str], int]:
    request = Request(KEYWORDS_API, headers={"Cache-Control": "no-store", "Accept": "application/json"})
    with urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise ValueError(f"Keyword API returned HTTP {response.status}")
        raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError("Keyword API response too large")
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("keywords"), list):
        raise ValueError("Keyword API returned invalid JSON structure")
    revision = data.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise ValueError("Keyword API revision missing or invalid")
    words = data["keywords"]
    if not 1 <= len(words) <= 500:
        raise ValueError("Keyword API returned an empty or oversized list")
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in words:
        if not isinstance(value, str):
            raise ValueError("Non-text keyword from API")
        term = unicodedata.normalize("NFKC", value).strip()
        if not term or len(term) > 40 or any(c in term for c in "\n\r\x00"):
            raise ValueError("Invalid keyword from API")
        if term in seen:
            raise ValueError("Duplicate keyword returned by API")
        seen.add(term)
        cleaned.append(term)
    return cleaned, revision


def main() -> int:
    try:
        words, revision = fetch_approved_keywords()
    except Exception as exc:
        print(f"[ctee keywords] Sync aborted; retaining GitHub backup: {exc}", file=sys.stderr)
        return 1
    desired = "\n".join(words) + "\n"
    current = BACKUP.read_text(encoding="utf-8") if BACKUP.exists() else ""
    if current == desired:
        print(f"[ctee keywords] GitHub backup already matches revision {revision} ({len(words)} terms)")
        return 0
    BACKUP.write_text(desired, encoding="utf-8")
    print(f"[ctee keywords] Updated backup to revision {revision} ({len(words)} terms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
