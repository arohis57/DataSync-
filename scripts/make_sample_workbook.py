"""Build a DataSync workbook from an existing cockpit_data.json (the reverse of excel_to_model).

Usage:  python scripts/make_sample_workbook.py [cockpit_data.json] [out.xlsx]
"""
import json
import sys
from pathlib import Path

from datasync.workbook_writer import write_workbook

ROOT = Path(__file__).resolve().parents[1]

src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "src" / "cockpit" / "cockpit_data.json"
out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "samples" / "Phoenix_R6_DataSync.xlsx"
write_workbook(json.loads(src.read_text(encoding="utf-8")), out)
print(f"wrote {out}")
