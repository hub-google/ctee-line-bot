"""Approve keyword-change GitHub Issues, using GitHub as the only datastore.

A trusted repository collaborator comments /approve or /reject on an Issue
created by the public suggestion form. The workflow must run with contents and
issues write permissions. Untrusted issue bodies are DATA, never executable code.
"""
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPO = os.environ["GITHUB_REPOSITORY"]
TOKEN = os.environ["GITHUB_TOKEN"]
EVENT = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
ROOT = Path(__file__).resolve().parents[1]
KEYWORDS_FILE = ROOT / "keywords.txt"
API = "https://api.github.com/repos/" + REPO
JSON_HEADERS = {"Authorization": "Bearer " + TOKEN, "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "ctee-keyword-review"}


def github(path, method="GET", body=None):
    headers = dict(JSON_HEADERS)
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(path if path.startswith("https://") else API + path,
                      method=method, headers=headers,
                      data=json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None)
    with urlopen(request, timeout=25) as resp:
        payload = resp.read()
        return json.loads(payload) if payload else {}


def parse_request(body):
    if not isinstance(body, str) or len(body) > 10000:
        raise ValueError("Invalid suggestion body")
    sections = {}
    section = None
    for line in body.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            sections[section] = []
        elif section:
            sections[section].append(line.strip())

    def terms(key):
        result = []
        for line in sections.get(key, []):
            if not line or line == "（無）":
                continue
            if not line.startswith("- "):
                raise ValueError("Invalid keyword line in " + key)
            word = unicodedata.normalize("NFKC", line[2:].strip())
            if not word or len(word) > 40 or any(c in word for c in "\r\n<>"):
                raise ValueError("Invalid keyword")
            if word in result:
                raise ValueError("Duplicate keyword")
            result.append(word)
        return result

    name = "".join(sections.get("申請人", [])).strip()
    if not 1 <= len(name) <= 40:
        raise ValueError("Missing requester")
    additions = terms("新增關鍵字")
    removals = terms("移除關鍵字")
    if not (additions or removals) or len(additions) + len(removals) > 20:
        raise ValueError("Must specify 1-20 keyword changes")
    if set(additions) & set(removals):
        raise ValueError("Overlapping additions and removals")
    return additions, removals


def main():
    issue = EVENT.get("issue", {})
    comment = EVENT.get("comment", {})
    number = issue.get("number")
    cmd = str(comment.get("body", "")).strip().lower()
    author = comment.get("user", {}).get("login", "")
    if (not isinstance(number, int) or not str(issue.get("title", "")).startswith("[關鍵字申請] ")
            or issue.get("pull_request") or issue.get("state") != "open"
            or cmd not in ("/approve", "/reject")):
        print("Not a keyword-review command")
        return 0
    # Verify actual GitHub repository permissions, not a short public PIN.
    p = github("/collaborators/" + author + "/permission")
    if p.get("permission") not in ("admin", "write", "maintain"):
        raise PermissionError("Only a repository write collaborator can approve or reject")
    adds, removes = parse_request(issue.get("body"))
    if cmd == "/approve":
        existing = [line.strip() for line in KEYWORDS_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
        current = set(existing)
        if any(word in current for word in adds):
            raise ValueError("Some additions are already tracked; resolve before approval")
        if any(word not in current for word in removes):
            raise ValueError("Some removals no longer exist; resolve before approval")
        final = [word for word in existing if word not in removes] + adds
        if not final:
            raise ValueError("Cannot approve an empty tracking list")
        KEYWORDS_FILE.write_text("\n".join(final) + "\n", encoding="utf-8")
        print(f"Approved: +{adds}, -{removes}")
    else:
        print("Rejected issue", number)
    # Save the final review result for the workflow. Post updates only after commit.
    Path("/tmp/ctee-review-result.json").write_text(
        json.dumps({"number": number, "decision": "approved" if cmd == "/approve" else "rejected",
                    "add": adds, "remove": removes}, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, PermissionError, HTTPError) as exc:
        print("Review failed: " + str(exc), file=sys.stderr)
        sys.exit(1)
