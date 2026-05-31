#!/usr/bin/env python3
"""
Convert ISO 11783-11 online database text export to structured JSON.

Usage:
    python convert_isobus_dict.py path/to/isobus_dict.txt -o ISOBUS/isobus_ddi.json
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

FIELD_KEYS = sorted(
    [
        "Typically used by Device Classes",
        "Status Comments",
        "Revision Number",
        "Submit Company",
        "Submit Date",
        "Current Status",
        "Status Date",
        "CANBus Range",
        "Display Range",
        "DD Entity",
        "Definition",
        "Comment",
        "Resolution",
        "SAE SPN",
        "Submit by",
        "Unit",
        "Attachments",
    ],
    key=len,
    reverse=True,
)

DD_ENTITY_RE = re.compile(r"^DD Entity:\s*(\d+)\s+(.*)$", re.IGNORECASE)
RANGE_RE = re.compile(r"^\s*(-?\d+(?:[.,]\d+)?)\s*-\s*(-?\d+(?:[.,]\d+)?)\s*$")


def parse_field_line(line: str) -> Tuple[Optional[str], Optional[str]]:
    for key in FIELD_KEYS:
        prefix = key + ":"
        if line.startswith(prefix):
            return key, line[len(prefix):].strip()
    return None, None


def parse_european_number(text: str) -> Optional[float]:
    text = text.strip()
    if not text or text.lower() in ("not specified", "not assigned", "none"):
        return None
    cleaned = text.replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_range(text: str) -> Tuple[Optional[int], Optional[int]]:
    m = RANGE_RE.match(text.strip())
    if not m:
        return None, None
    lo = parse_european_number(m.group(1))
    hi = parse_european_number(m.group(2))
    if lo is None or hi is None:
        return None, None
    return int(lo), int(hi)


def finalize_field(key: str, lines: List[str]) -> Any:
    if key == "Typically used by Device Classes":
        return [
            ln.strip()
            for ln in lines
            if ln.strip() and ln.strip().lower() not in ("not assigned", "none")
        ]
    return "\n".join(lines).strip()


def parse_entity_block(block: str) -> Optional[Dict[str, Any]]:
    lines = block.splitlines()
    if not lines:
        return None
    m = DD_ENTITY_RE.match(lines[0].strip())
    if not m:
        return None
    ddi = int(m.group(1))
    name = m.group(2).strip()
    raw_fields: Dict[str, Any] = {}
    current_key: Optional[str] = None
    current_lines: List[str] = []
    for line in lines[1:]:
        key, val = parse_field_line(line)
        if key:
            if current_key:
                raw_fields[current_key] = finalize_field(current_key, current_lines)
            current_key = key
            current_lines = [val] if val else []
        elif current_key:
            current_lines.append(line.rstrip())
    if current_key:
        raw_fields[current_key] = finalize_field(current_key, current_lines)
    spn_raw = str(raw_fields.get("SAE SPN", "")).strip()
    sae_spn: Optional[int] = None
    if spn_raw and spn_raw.lower() not in ("not specified", "not assigned", ""):
        val = parse_european_number(spn_raw)
        if val is not None and val == int(val):
            sae_spn = int(val)
    can_min, can_max = parse_range(str(raw_fields.get("CANBus Range", "")))
    device_classes = raw_fields.get("Typically used by Device Classes", [])
    if isinstance(device_classes, str):
        device_classes = [device_classes] if device_classes else []
    return {
        "ddi": ddi,
        "name": name,
        "definition": str(raw_fields.get("Definition", "")).strip(),
        "comment": str(raw_fields.get("Comment", "")).strip(),
        "device_classes": device_classes,
        "unit": str(raw_fields.get("Unit", "")).strip(),
        "resolution": parse_european_number(str(raw_fields.get("Resolution", ""))),
        "sae_spn": sae_spn,
        "canbus_min": can_min,
        "canbus_max": can_max,
        "display_range": str(raw_fields.get("Display Range", "")).strip(),
        "submit_by": str(raw_fields.get("Submit by", "")).strip(),
        "submit_date": str(raw_fields.get("Submit Date", "")).strip(),
        "submit_company": str(raw_fields.get("Submit Company", "")).strip(),
        "revision_number": str(raw_fields.get("Revision Number", "")).strip(),
        "status": str(raw_fields.get("Current Status", "")).strip(),
        "status_date": str(raw_fields.get("Status Date", "")).strip(),
        "status_comments": str(raw_fields.get("Status Comments", "")).strip(),
        "attachments": str(raw_fields.get("Attachments", "")).strip(),
    }


def extract_header_meta(text: str) -> Dict[str, Any]:
    meta: Dict[str, Any] = {"source": "ISO 11783-11 online database export"}
    for line in text.splitlines()[:20]:
        if line.startswith("Version:"):
            meta["version"] = line.split(":", 1)[1].strip()
            break
    return meta


def parse_export(text: str, source_name: str = "") -> Dict[str, Any]:
    meta = extract_header_meta(text)
    if source_name:
        meta["converted_from"] = source_name
    parts = re.split(r"(?=^DD Entity:\s*\d+)", text, flags=re.MULTILINE)
    entries: Dict[str, Dict[str, Any]] = {}
    for part in parts:
        part = part.strip()
        if not part.startswith("DD Entity:"):
            continue
        entity = parse_entity_block(part)
        if entity is None:
            continue
        entries[str(entity["ddi"])] = entity
    meta["entity_count"] = len(entries)
    return {"meta": meta, "entries": entries}


def convert_file(input_path: Path, output_path: Path) -> int:
    text = input_path.read_text(encoding="utf-8", errors="replace")
    data = parse_export(text, source_name=input_path.name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data["meta"]["entity_count"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert ISO 11783-11 DDI text export to JSON."
    )
    parser.add_argument("input", type=Path, help="Path to isobus_dict.txt export")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(__file__).parent / "ISOBUS" / "isobus_ddi.json",
        help="Output JSON path",
    )
    args = parser.parse_args()
    if not args.input.is_file():
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        return 1
    count = convert_file(args.input, args.output)
    print(f"Wrote {count} DDI entries to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
