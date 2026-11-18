"""Import approved/rejected CTEE suggestions, write only the GitHub repository.

The anonymous Cloudflare inbox is a temporary buffer. GitHub's own Actions
GITHUB_TOKEN is the sole writer of keywords.txt; no personal GitHub token is
exposed to a visitor or Cloudflare.
"""
import json
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KEYWORDS = ROOT / "keywords.txt"
LOG = ROOT / "viewer" / "keyword_gateway" / "processed.json"
EXPORT = "https://ctee-keywords-inbox.ber-at.workers.dev/export"
ID = re.compile(r"^[a-f0-9-]{38,45}$")


def fetch_events():
    req = urllib.request.Request(EXPORT, headers={"User-Agent":"CTEE-GitHub-Action/1.0","Accept":"application/json"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        if resp.status != 200:
            raise ValueError("Keyword inbox export HTTP "+str(resp.status))
        content = resp.read(524289)
    if len(content)>524288:
        raise ValueError("Keyword inbox too large; refusing partial import")
    data = json.loads(content)
    if not isinstance(data,dict) or data.get("ok") is not True or not isinstance(data.get("items"),list):
        raise ValueError("Keyword inbox response invalid")
    if len(data["items"]) > 600:
        raise ValueError("Too many items in one sync")
    records = []
    seen = set()
    for obj in data["items"]:
        if not isinstance(obj,dict):
            raise ValueError("Invalid item in inbox")
        key = obj.get("id")
        word = obj.get("keyword")
        operation = obj.get("operation")
        decision = obj.get("status")
        if not isinstance(key,str) or not ID.fullmatch(key) or key in seen:
            raise ValueError("Duplicate or invalid inbox id")
        if not isinstance(word,str):
            raise ValueError("Invalid term type")
        word = unicodedata.normalize("NFKC",word).strip()
        if not word or len(word)>40 or any(char in word for char in "<>\r\n"):
            raise ValueError("Invalid term value")
        if operation not in ("add","remove") or decision not in ("approved","rejected"):
            raise ValueError("Unreviewed item in export")
        seen.add(key)
        records.append({"id":key,"operation":operation,"keyword":word,"decision":decision})
    return sorted(records,key=lambda x:x["id"])


def main():
    events=fetch_events()
    existing = [v.strip() for v in KEYWORDS.read_text(encoding="utf-8").splitlines() if v.strip()]
    ledger=json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else {}
    if not isinstance(ledger,dict):
        raise ValueError("Processed log is not a mapping")
    applied = 0
    for event in events:
        key=event["id"]
        if key in ledger:
            continue
        word=event["keyword"]
        before=word in existing
        if event["decision"] == "approved":
            if event["operation"]=="add" and not before:
                existing.append(word)
            elif event["operation"]=="remove" and before:
                if len(existing)==1:
                    raise ValueError("Cannot approve removal of final keyword")
                existing.remove(word)
        # Persist idempotency decisions and keyword list atomically in one Git commit.
        ledger[key]={"operation":event["operation"],"keyword":word,
                     "decision":event["decision"],"effect":"changed" if (word in existing)!=before else "no-op"}
        applied+=1
    if applied:
        KEYWORDS.write_text("\n".join(existing)+"\n",encoding="utf-8")
        LOG.write_text(json.dumps(ledger,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(f"[ctee] {len(events)} reviewed items available, {applied} new items processed, {len(existing)} tracked terms")


if __name__=="__main__":
    try:
        main()
    except Exception as e:
        print(f"[ctee] Refusing to overwrite GitHub keywords on unsafe or unavailable inbox: {e}",file=sys.stderr)
        raise
