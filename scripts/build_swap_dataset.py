"""Build data/part_profiles.json: curated profiles + every same-role swap pair (intrinsic 'what changes' records).
Run from the repo root:  python -m scripts.build_swap_dataset      (the run-time store data/swap_store.json is not touched)"""
import itertools, json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
from core import profiles, swap_dataset
from scripts.profile_seed import S

def main():
    profs, problems = {}, []
    for p in S:
        clean, bad = profiles.validate(p["role"], p["attrs"])
        if bad: problems.append((p["id"], bad))
        if not profiles.complete_enough(p["role"], clean): problems.append((p["id"], "missing critical fields"))
        if p["id"] in profs: problems.append((p["id"], "duplicate id"))
        profs[p["id"]] = dict(p, attrs=clean, origin="curated", confidence="typical")
    if problems: raise SystemExit("profile problems:\n" + "\n".join(map(str, problems)))
    pairs = {}
    groups = {}
    for p in profs.values(): groups.setdefault((p["role"], p["kind"] if p["role"] in ("sensor", "driver", "motor") else "all"), []).append(p)
    for (role, _k), items in groups.items():
        for a, b in itertools.permutations(items, 2):
            pairs[swap_dataset.pair_key(role, a["id"], b["id"])] = swap_dataset.build_record(role, a, b)
    out = ROOT / "data" / "part_profiles.json"
    out.write_text(json.dumps(dict(note="Curated TYPICAL values. Rebuild with: python -m scripts.build_swap_dataset", profiles=profs, pairs=pairs), indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(profs)} profiles, {len(pairs)} pair records -> {out.relative_to(ROOT)} ({out.stat().st_size // 1024} kB)")

if __name__ == "__main__": main()
