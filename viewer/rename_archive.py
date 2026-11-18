"""Safely rename historical originals to YYYYMMDD_01_關鍵字1、關鍵字2.jpg.

Verify original SHA-256 before changing anything. Preserve bytes, use one source
image per clipping and one date-specific ZIP. Git history provides rollback.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from naming import named_original, matched_keywords

root = Path(sys.argv[1]).resolve()
archive = root / "archive"
if not archive.is_dir():
    raise SystemExit("Refusing rename: archive directory missing")

days = sorted(p for p in archive.iterdir() if p.is_dir())
if not days:
    raise SystemExit("Refusing rename: no dated archives")

plans = []
for day in days:
    data_file = day / "data.json"
    data = json.loads(data_file.read_text(encoding="utf-8"))
    if data.get("date") != day.name:
        raise ValueError(f"Date mismatch: {day}")
    imgs = data.get("images")
    if not isinstance(imgs, list) or not imgs:
        raise ValueError(f"Empty clipping collection: {day}")
    if not (day / "latest.zip").is_file():
        raise FileNotFoundError(f"Dated ZIP not found: {day}")
    seen_hashes = set()
    planned = []
    seen_names = set()
    for i, item in enumerate(imgs, 1):
        old = (root / item["src"]).resolve()
        if not old.is_relative_to((day / "images").resolve()):
            raise ValueError(f"Image location outside archive: {old}")
        if not old.is_file():
            raise FileNotFoundError(old)
        raw = old.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != item.get("sha256"):
            raise ValueError(f"Image hash mismatch: {old}")
        if digest in seen_hashes:
            raise ValueError(f"Repeated source hash in manifest: {digest}")
        seen_hashes.add(digest)
        keywords = "、".join(matched_keywords(item.get("keyword", "")))
        filename = named_original(day.name, i, keywords, old.suffix)
        if filename in seen_names:
            raise ValueError(f"Filename collision: {filename}")
        seen_names.add(filename)
        new = day / "images" / filename
        if new.exists() and new != old and hashlib.sha256(new.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Cannot overwrite a different image: {new}")
        rewritten = dict(item)
        rewritten["src"] = f"archive/{day.name}/images/{filename}"
        rewritten["keyword"] = keywords
        rewritten.pop("thumb", None)
        planned.append((old, new, raw, rewritten))
    plans.append((day, data, planned))

n_renamed = 0
for day, data, planned in plans:
    with tempfile.TemporaryDirectory(prefix="ctee-rename-") as stage_dir:
        stage = Path(stage_dir)
        with zipfile.ZipFile(stage / "latest.zip", "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as zf:
            zf.writestr("README.txt", f"工商時報每日剪報 {day.name}\n來源原圖，已按日期、序號、關鍵字命名。\n")
            for old, new, raw, rewritten in planned:
                staged = stage / new.name
                staged.write_bytes(raw)
                if hashlib.sha256(staged.read_bytes()).hexdigest() != rewritten["sha256"]:
                    raise ValueError(f"Staging checksum error: {new}")
                zf.write(staged, arcname=new.name)
        with zipfile.ZipFile(stage / "latest.zip") as zf:
            entries = [i for i in zf.namelist() if i != "README.txt"]
            if len(entries) != len(planned):
                raise ValueError("ZIP does not contain the complete dated collection")
        for old, new, raw, item in planned:
            if new != old:
                shutil.copyfile(stage / new.name, new)
                n_renamed += 1
        for old, new, raw, item in planned:
            if old != new:
                old.unlink()
        expected = {entry[1].name for entry in planned}
        actual = {p.name for p in (day / "images").iterdir() if p.is_file()}
        if actual != expected:
            raise ValueError(f"Unexpected extra/missing files at {day}: {actual ^ expected}")
        data["images"] = [entry[3] for entry in planned]
        data["total"] = len(planned)
        (day / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        shutil.copyfile(stage / "latest.zip", day / "latest.zip")
        print(f"[rename] {day.name}: verified {len(planned)} originals and rebuilt dated ZIP", flush=True)

latest = max(plans, key=lambda x: x[0].name)[1]
(root / "data.json").write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
if (root / "latest.zip").exists():
    raise ValueError("Unexpected duplicate root ZIP exists")
print(f"[rename] Completed: {len(plans)} dates, {n_renamed} renamed originals, no thumbnails or extra copies", flush=True)
