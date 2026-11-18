"""Build the optional newspaper viewer without modifying the legacy daily LINE bot.

The newspaper source image bytes are persisted *unchanged*, rather than passing
through the legacy JPEG banner/ImgBB pipeline or a second JPEG re-encode.
A dedicated GitHub Pages publication job preserves each dated gallery.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import sys
import threading
import tempfile
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageFile
from naming import matched_keywords, named_original

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = Path(__file__).resolve().parent / "public"
sys.path.insert(0, str(ROOT))
import ctee_downloader_cloud as legacy  # noqa: E402

ImageFile.LOAD_TRUNCATED_IMAGES = True
NOW = (datetime.strptime(os.environ["CTEE_TARGET_DATE"], "%Y-%m-%d")
       if os.environ.get("CTEE_TARGET_DATE") else datetime.now(ZoneInfo("Asia/Taipei")))
DATE = NOW.strftime("%Y-%m-%d")
DATE_LABEL = NOW.strftime("%Y/%m/%d")
ARCHIVE = PUBLIC / "archive" / DATE
RAW = ARCHIVE / "images"
RAW.mkdir(parents=True, exist_ok=True)
STAGING = Path(tempfile.mkdtemp(prefix="ctee-originals-"))
received_results = []
uploaded = {}
lock = threading.Lock()

def store_exact_source(image_bytes: bytes) -> str | None:
    """Called instead of ImgBB by the legacy crawler; no JPEG recompression."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as original:
            fmt = original.format
            width, height = original.size
            original.verify()
        ext = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif"}.get(fmt)
        if not ext:
            raise ValueError(f"Unsupported source image format: {fmt}")
        if not (0 < width <= 15000 and 0 < height <= 15000):
            raise ValueError("Invalid source dimensions")
        digest = hashlib.sha256(image_bytes).hexdigest()
        filename = f"{digest[:24]}.{ext}"
        uri = "https://viewer.local/source/" + digest
        with lock:
            path = STAGING / filename
            if not path.exists():
                path.write_bytes(image_bytes)
            uploaded[uri] = {"path": path, "width": width, "height": height, "sha256": digest}
        print(f"[viewer] Preserved original bytes: {filename} ({width}x{height})", flush=True)
        return uri
    except Exception as exc:
        print(f"[viewer] Could not preserve image: {exc}", flush=True)
        return None

def capture_results(results):
    received_results.extend(results)

# Patch *only this process*; the legacy schedule retains its original upload,
# banner and LINE delivery behavior without changes to its source files.
legacy.add_banner = lambda image_bytes, _kw: image_bytes
legacy.upload_cdn = store_exact_source
legacy.send_summary_message = capture_results

def build_site():
    if not received_results:
        raise RuntimeError("No matching clippings. Refuse to publish an empty viewer.")
    manifest = []
    # Group on actual source-image checksum. If two matches point to the same
    # image, store the image ONCE while preserving all matched keywords.
    grouped = {}
    for result in sorted(received_results, key=lambda x: str(x.get("aid", ""))):
        file_info = uploaded.get(result.get("cdn_url", ""))
        if not file_info:
            continue
        sha256 = file_info["sha256"]
        if sha256 not in grouped:
            grouped[sha256] = {"file_info": file_info, "keywords": [], "article_url": result.get("article_url", "")}
        entry = grouped[sha256]
        for keyword in matched_keywords(result.get("kw", "")):
            if keyword not in entry["keywords"]:
                entry["keywords"].append(keyword)
    zip_filename = f"工商時報_{DATE.replace('-', '')}.zip"
    archive_zip = ARCHIVE / zip_filename
    with zipfile.ZipFile(archive_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as bundle:
        bundle.writestr("README.txt", f"工商時報剪報 {DATE_LABEL}\n僅供具有合法閱讀權限者使用。\n")
        for sha256, entry in grouped.items():
            file_info = entry["file_info"]
            path = file_info["path"]
            index = len(manifest) + 1
            label = "、".join(entry["keywords"])
            numbered_name = named_original(DATE, index, label, path.suffix)
            target = RAW / numbered_name
            if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != sha256:
                raise ValueError(f"Filename collision with a different image: {numbered_name}")
            shutil.copyfile(path, target)
            if hashlib.sha256(target.read_bytes()).hexdigest() != sha256:
                raise ValueError(f"Original image checksum changed: {numbered_name}")
            bundle.write(target, arcname=numbered_name)
            manifest.append({
                "src": f"archive/{DATE}/images/{numbered_name}",
                "width": file_info["width"],
                "height": file_info["height"],
                "sha256": sha256,
                "keyword": label,
                "article_url": entry["article_url"],
            })
    if not manifest:
        raise RuntimeError("No valid source images were saved; no deployment or LINE push.")
    data = {
        "build_ref": os.getenv("GITHUB_SHA", ""),
        "date_label": DATE_LABEL,
        "date": DATE,
        "total": len(manifest),
        "zip": f"archive/{DATE}/{zip_filename}",
        "images": manifest,
    }
    body = json.dumps(data, ensure_ascii=False, indent=2)
    (ARCHIVE / "data.json").write_text(body, encoding="utf-8")
    (PUBLIC / "data.json").write_text(body, encoding="utf-8")
    shutil.rmtree(STAGING, ignore_errors=True)
    print(f"[viewer] Archived {len(manifest)} UNIQUE, date-and-keyword-named originals for {DATE}; no thumbnails; dated ZIP {archive_zip.stat().st_size} bytes", flush=True)

if __name__ == "__main__":
    missing = [x for x in ("CTEE_USER", "CTEE_PASS") if not os.environ.get(x)]
    if missing:
        raise SystemExit("Missing GitHub Secrets: " + ", ".join(missing))
    asyncio.run(legacy.run_worker())
    build_site()
