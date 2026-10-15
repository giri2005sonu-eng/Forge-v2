"""Parts catalog = curated seed + live overlay (data scraped through TinyFish)."""
from __future__ import annotations

import json
from pathlib import Path

from .config import DATA_DIR
from .schemas import Evidence, Part, Spec

OVERLAY_NAME = "live_overlay.json"


class CatalogError(Exception):
    pass


def normalize_part(part: Part, spec_defs: dict) -> Part:
    """Upper-case string specs so 'n20' == 'N20'; reject unknown spec keys."""
    defs = spec_defs.get(part.category)
    if defs is None:
        raise CatalogError(f"{part.id}: unknown category '{part.category}'")
    for key, spec in list(part.specs.items()):
        if key not in defs:
            raise CatalogError(f"{part.id}: unknown spec key '{key}' for category '{part.category}'")
        if defs[key]["type"] == "string" and isinstance(spec.value, str):
            spec.value = spec.value.strip().upper()
        if defs[key]["type"] == "number" and spec.value is not None:
            spec.value = float(spec.value)
    return part


def load_seed(spec_defs: dict, data_dir: Path = DATA_DIR) -> dict[str, Part]:
    with open(data_dir / "parts_catalog.json", encoding="utf-8") as f:
        raw = json.load(f)
    stamp = raw.get("curated_on", "2026-01-01T00:00:00Z")
    seed_note = "Seed value (typical datasheet/listing figure). Not verified live."
    parts: dict[str, Part] = {}
    for p in raw["parts"]:
        ev = lambda note=seed_note: Evidence(method="curated", retrieved_at=stamp, note=note)
        specs = {}
        defs = spec_defs[p["category"]]
        for k, v in p.get("specs", {}).items():
            if k not in defs:
                raise CatalogError(f"{p['id']}: unknown spec key '{k}'")
            specs[k] = Spec(value=v, unit=defs[k].get("unit"), evidence=ev())
        part = Part(
            id=p["id"], category=p["category"], name=p["name"],
            kind=p.get("kind"), search_query=p.get("search_query"),
            price=Spec(value=float(p["price_inr"]), unit="INR",
                       evidence=ev("Seed price: approximate Indian retail. Refresh live.")),
            specs=specs,
        )
        if part.id in parts:
            raise CatalogError(f"duplicate part id {part.id}")
        parts[part.id] = normalize_part(part, spec_defs)
    return parts


def load_overlay(spec_defs: dict, data_dir: Path = DATA_DIR) -> dict[str, Part]:
    path = data_dir / OVERLAY_NAME
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {pid: normalize_part(Part.model_validate(d), spec_defs) for pid, d in raw.items()}


def load_catalog(spec_defs: dict, data_dir: Path = DATA_DIR) -> dict[str, Part]:
    catalog = load_seed(spec_defs, data_dir)
    catalog.update(load_overlay(spec_defs, data_dir))
    return catalog


def save_overlay(parts: list[Part], data_dir: Path = DATA_DIR) -> None:
    path = data_dir / OVERLAY_NAME
    existing = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            existing = json.load(f)
    for p in parts:
        existing[p.id] = p.model_dump(mode="json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)


def reset_overlay(data_dir: Path = DATA_DIR) -> None:
    path = data_dir / OVERLAY_NAME
    if path.exists():
        path.unlink()
