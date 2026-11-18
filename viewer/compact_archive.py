"""One-time safe compaction of published, dated CTEE image archives.

Keep each exact original image and the ONE dated ZIP download. Remove only
generated thumbnails and the redundant root-level copy of the ZIP. Historical
manifests are verified and upgraded before any deletion.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
archive = root / "archive"
if not archive.is_dir():
    raise SystemExit("Missing archive; refusing to alter files")

checked = []
for daydir in sorted(archive.iterdir()):
    if not daydir.is_dir():
        continue
    manifest_file = daydir / "data.json"
    doc = json.loads(manifest_file.read_text(encoding="utf-8"))
    if doc.get("date") != daydir.name:
        raise RuntimeError(f"Unexpected dated manifest: {daydir}")
    old = doc.get("images")
    if not isinstance(old, list) or not old:
        raise RuntimeError(f"No images in {daydir.name}")
    if not (daydir / "latest.zip").is_file():
        raise RuntimeError(f"Missing dated ZIP in {daydir.name}")
    updated = []
    seen = set()
    for item in old:
        source = item["src"]
        file_path = (root / source).resolve()
        if not file_path.is_relative_to(daydir.resolve()) or not file_path.is_file():
            raise RuntimeError(f"Missing or unsafe original source: {source}")
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if digest != item.get("sha256"):
            raise RuntimeError(f"Original clipping checksum mismatch: {source}")
        if digest in seen:
            print(f"[dedup] Repeated manifest source omitted: {source}", flush=True)
            continue
        seen.add(digest)
        row = dict(item)
        row.pop("thumb", None)
        updated.append(row)
    if not updated:
        raise RuntimeError(f"No valid originals: {daydir.name}")
    checked.append((manifest_file, doc, updated))

latest = max(checked, key=lambda v: v[1]["date"]) if checked else None
if not latest:
    raise RuntimeError("No historical dates found; no deletion permitted")

removed_thumbs = 0
for manifest_file, doc, updated in checked:
    doc["images"] = updated
    doc["total"] = len(updated)
    manifest_file.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    # A thumbnail was generated from an already saved source; it is redundant.
    imgdir = manifest_file.parent / "images"
    for thumb in imgdir.glob("thumb_*.jpg"):
        if thumb.is_file():
            thumb.unlink()
            removed_thumbs += 1
    print(f"[dedup] {doc['date']}: {len(updated)} verified, unique original image files", flush=True)

latest_data = json.dumps(latest[1], ensure_ascii=False, indent=2)
(root / "data.json").write_text(latest_data, encoding="utf-8")
root_zip = root / "latest.zip"
removed_root_zip = root_zip.is_file()
if removed_root_zip:
    root_zip.unlink()
print(f"[dedup] Removed {removed_thumbs} generated thumbnail files; redundant top-level ZIP removed: {removed_root_zip}", flush=True)
print("[dedup] Each historical date retains exactly one ZIP for the existing bulk-download feature", flush=True)
