"""Index every archived issue without deleting previous days."""
from __future__ import annotations

import json
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
archive = root / "archive"
dates = []
for daydir in sorted(archive.iterdir(), reverse=True):
    if not daydir.is_dir():
        continue
    try:
        data = json.loads((daydir / "data.json").read_text(encoding="utf-8"))
        if data.get("date") != daydir.name:
            raise ValueError("Archive directory and date disagree")
        pics = data.get("images", [])
        if not pics:
            raise ValueError("No images")
        for item in pics:
            if not (root / item["src"]).is_file():
                raise FileNotFoundError(item["src"])
        if not (daydir / "latest.zip").exists():
            raise FileNotFoundError("latest.zip")
        dates.append({
            "date": daydir.name,
            "date_label": data.get("date_label", daydir.name),
            "count": len(pics),
            "zip": data.get("zip", f"archive/{daydir.name}/latest.zip"),
        })
    except Exception as exc:
        raise RuntimeError(f"Archived issue {daydir.name} damaged; refusing to remove anything: {exc}") from exc
if not dates:
    raise SystemExit("No archive dates found")
(root / "history.json").write_text(
    json.dumps({"dates": dates, "total_days": len(dates)}, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
total_bytes = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
size_mb = total_bytes / 1024**2
print(f"[history] Preserved {len(dates)} dated issues; site files {size_mb:.1f} MiB", flush=True)
if size_mb > 900:
    raise SystemExit(
        "Archive exceeds safety size near GitHub Pages' 1 GB site limit. "
        "Old images remain intact in viewer-archive branch. "
        "Choose an authorized long-term archival backend before further publication."
    )
