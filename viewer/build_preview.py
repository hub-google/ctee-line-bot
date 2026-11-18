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
import shutil
import sys
import threading
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageFile

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = Path(__file__).resolve().parent / "public"
sys.path.insert(0, str(ROOT))
import ctee_downloader_cloud as legacy  # noqa: E402

ImageFile.LOAD_TRUNCATED_IMAGES = True
NOW = datetime.now(ZoneInfo("Asia/Taipei"))
DATE = NOW.strftime("%Y-%m-%d")
DATE_LABEL = NOW.strftime("%Y/%m/%d")
ARCHIVE = PUBLIC / "archive" / DATE
RAW = ARCHIVE / "images"
RAW.mkdir(parents=True, exist_ok=True)
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
            path = RAW / filename
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
    archive_zip = ARCHIVE / "latest.zip"
    with zipfile.ZipFile(archive_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as bundle:
        bundle.writestr("README.txt", f"工商時報剪報 {DATE_LABEL}\n僅供具有合法閱讀權限者使用。\n")
        for result in sorted(received_results, key=lambda x: str(x.get("aid", ""))):
            file_info = uploaded.get(result.get("cdn_url", ""))
            if not file_info:
                continue
            path = file_info["path"]
            index = len(manifest) + 1
            thumb = RAW / f"thumb_{index:02d}.jpg"
            try:
                with Image.open(path) as original:
                    resized = original.convert("RGB")
                    resized.thumbnail((700, 1200), Image.Resampling.LANCZOS)
                    resized.save(thumb, "JPEG", quality=85, optimize=True)
                # The ZIP contains the exact bytes from the source, NOT the thumbnail.
                bundle.write(path, arcname=f"{index:02d}_{path.name}")
                prefix = f"archive/{DATE}/images/"
                manifest.append({
                    "src": prefix + path.name,
                    "thumb": prefix + thumb.name,
                    "width": file_info["width"],
                    "height": file_info["height"],
                    "sha256": file_info["sha256"],
                    "keyword": result.get("kw", ""),
                    "article_url": result.get("article_url", ""),
                })
            except Exception as exc:
                print(f"[viewer] Failed to create thumbnail for {path}: {exc}", flush=True)
    if not manifest:
        raise RuntimeError("No valid source images were saved; no deployment or LINE push.")
    data = {
        "build_ref": os.getenv("GITHUB_SHA", ""),
        "date_label": DATE_LABEL,
        "date": DATE,
        "total": len(manifest),
        "zip": f"archive/{DATE}/latest.zip",
        "images": manifest,
    }
    body = json.dumps(data, ensure_ascii=False, indent=2)
    (ARCHIVE / "data.json").write_text(body, encoding="utf-8")
    (PUBLIC / "data.json").write_text(body, encoding="utf-8")
    shutil.copyfile(archive_zip, PUBLIC / "latest.zip")
    print(f"[viewer] Archived {len(manifest)} original-resolution images for {DATE}; ZIP {archive_zip.stat().st_size} bytes", flush=True)

if __name__ == "__main__":
    missing = [x for x in ("CTEE_USER", "CTEE_PASS") if not os.environ.get(x)]
    if missing:
        raise SystemExit("Missing GitHub Secrets: " + ", ".join(missing))
    asyncio.run(legacy.run_worker())
    build_site()
