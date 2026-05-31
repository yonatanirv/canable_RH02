"""
YonaCan - ISO 11783-11 DDI dictionary loader (JSON or text export).
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from convert_isobus_dict import parse_export


@dataclass
class DdiInfo:
    ddi: int
    name: str
    definition: str = ""
    comment: str = ""
    device_classes: List[str] = field(default_factory=list)
    unit: str = ""
    resolution: Optional[float] = None
    sae_spn: Optional[int] = None
    canbus_min: Optional[int] = None
    canbus_max: Optional[int] = None
    display_range: str = ""


class IsobusDictionary:
    def __init__(self):
        self.meta: Dict[str, Any] = {}
        self.entries: Dict[int, DdiInfo] = {}
        self._by_sae_spn: Dict[int, List[int]] = {}
        self._filepath: str = ""

    @property
    def is_loaded(self) -> bool:
        return len(self.entries) > 0

    @property
    def count(self) -> int:
        return len(self.entries)

    def load(self, filepath: str) -> int:
        path = Path(filepath)
        if not path.is_file():
            raise FileNotFoundError(f"ISOBUS dictionary not found: {filepath}")

        self._filepath = str(path)
        self.entries.clear()
        self._by_sae_spn.clear()

        if path.suffix.lower() == ".json":
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            self.meta = data.get("meta", {})
            for raw in data.get("entries", {}).values():
                info = _raw_to_ddi(raw)
                self.entries[info.ddi] = info
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
            data = parse_export(text, source_name=path.name)
            self.meta = data.get("meta", {})
            for raw in data.get("entries", {}).values():
                info = _raw_to_ddi(raw)
                self.entries[info.ddi] = info

        for ddi, info in self.entries.items():
            if info.sae_spn is not None:
                self._by_sae_spn.setdefault(info.sae_spn, []).append(ddi)

        return len(self.entries)

    def get(self, ddi: int) -> Optional[DdiInfo]:
        return self.entries.get(ddi)

    def by_sae_spn(self, spn: int) -> List[DdiInfo]:
        return [self.entries[d] for d in self._by_sae_spn.get(spn, []) if d in self.entries]

    def search(self, query: str, limit: int = 200) -> List[DdiInfo]:
        q = query.strip().lower()
        if not q:
            return sorted(self.entries.values(), key=lambda e: e.ddi)[:limit]
        results: List[DdiInfo] = []
        for info in self.entries.values():
            if q.isdigit() and str(info.ddi) == q:
                results.append(info)
            elif q in info.name.lower() or q in info.definition.lower():
                results.append(info)
            if len(results) >= limit:
                break
        return results

    def count_sae_spn_matches(self, spn_set: Set[int]) -> int:
        if not spn_set:
            return 0
        return sum(1 for spn in self._by_sae_spn if spn in spn_set)


def _raw_to_ddi(raw: Dict[str, Any]) -> DdiInfo:
    return DdiInfo(
        ddi=int(raw["ddi"]),
        name=str(raw.get("name", "")),
        definition=str(raw.get("definition", "")),
        comment=str(raw.get("comment", "")),
        device_classes=list(raw.get("device_classes") or []),
        unit=str(raw.get("unit", "")),
        resolution=raw.get("resolution"),
        sae_spn=raw.get("sae_spn"),
        canbus_min=raw.get("canbus_min"),
        canbus_max=raw.get("canbus_max"),
        display_range=str(raw.get("display_range", "")),
    )


def default_dictionary_path() -> str:
    return str(Path(__file__).parent / "ISOBUS" / "isobus_ddi.json")
