"""Build an independent static viewer from the legacy CTEE scanner.

The original daily bot and its LINE/Rentry delivery remain unchanged. This is a
one-shot preview entry point that reuses the scanner and intercepts its results.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageFile

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = Path(__file__).resolve().parent / "public"
sys.path.insert(0, str(ROOT))

import ctee_downloader_cloud as legacy  # noqa: E402

ImageFile.LOAD_TRUNCATED_IMAGES = True
received_results = []
DATE = datetime.now(ZoneInfo("Asia/Taipei"))
DATE_LABEL = DATE.strftime("%Y/%m/%d")


def capture_results(results):
    """Collect only; do not send the old Rentry LINE message during the preview."""
    received_results.extend(results)


legacy.send_summary_message = capture_results


def build_site():
    if not received_results:
        raise RuntimeError("掃描未產生可用結果，停止部署與推播以免傳送空白頁。")

    img_dir = PUBLIC / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    viewer_items = []
    archive = PUBLIC / "latest.zip"
    session = requests.Session()

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=4) as zf:
        zf.writestr("README.txt", "工商時報剪報預覽 " + DATE_LABEL + "\n此 ZIP 僅供具適當閱讀授權者使用，請勿未經授權轉載。\n")
        for result in received_results:
            url = result.get("cdn_url", "")
            if not url or url == "N/A" or not url.startswith("https://"):
                continue
            try:
                resp = session.get(url, timeout=30)
                resp.raise_for_status()
                if len(resp.content) > 25 * 1024 * 1024:
                    raise ValueError("圖片超過 25 MB，避免預覽站點異常膨脹")
                with Image.open(io.BytesIO(resp.content)) as source:
                    image = source.convert("RGB")
                    width, height = image.size
                    if width <= 0 or height <= 0:
                        raise ValueError("無效圖片尺寸")
                    index = len(viewer_items) + 1
                    filename = f"clipping_{index:02d}.jpg"
                    image_path = img_dir / filename
                    # High-quality original for precise zooming and local downloading.
                    image.save(image_path, "JPEG", quality=92, optimize=True)
                    thumb = image.copy()
                    thumb.thumbnail((700, 1200), Image.Resampling.LANCZOS)
                    thumb_path = img_dir / f"thumb_{index:02d}.jpg"
                    thumb.save(thumb_path, "JPEG", quality=77, optimize=True)
                zf.write(image_path, arcname=filename)
                viewer_items.append({
                    "src": "images/" + filename,
                    "thumb": "images/" + thumb_path.name,
                    "width": width,
                    "height": height,
                    "keyword": result.get("kw", ""),
                    "article_url": result.get("article_url", "")
                })
                print(f"[viewer] [{index}] image ready: {width}x{height} {filename}", flush=True)
            except Exception as exc:
                print(f"[viewer] Image skipped ({result.get('aid', 'unknown')}): {exc}", flush=True)

    if not viewer_items:
        raise RuntimeError("所有圖片皆無法讀取，停止部署與推播。")
    data = {
        "date_label": DATE_LABEL,
        "date": DATE.strftime("%Y-%m-%d"),
        "total": len(viewer_items),
        "images": viewer_items,
    }
    (PUBLIC / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[viewer] built {len(viewer_items)} clippings, ZIP {archive.stat().st_size} bytes", flush=True)


if __name__ == "__main__":
    missing = [x for x in ("CTEE_USER", "CTEE_PASS", "IMGBB_API_KEY") if not os.environ.get(x)]
    if missing:
        raise SystemExit("Missing GitHub Secrets: " + ", ".join(missing))
    asyncio.run(legacy.run_worker())
    build_site()
