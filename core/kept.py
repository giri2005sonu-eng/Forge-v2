"""Kept optimizer replacements, applied the SAME way everywhere (page bill, component cards, wiring, PDF).

The optimizer stores a swap in state.opt_kept under a key (the part's role, or role_<id> when a role repeats). Before this module the PDF applied
those swaps but the on-page bill of catalog/custom builds did not. One function now builds the active part list, so they cannot disagree.
A kept swap only applies to the build it was made for (identity check), so it can never leak into another project's bill."""
import copy


def keyed_parts(parts_list):
    """[part, ...] -> {key: part}. Same keys the optimizer panel uses: the role, or role_<id> for a repeated role."""
    out = {}
    for index, part in enumerate(parts_list):
        role = part.get("role", "part")
        key = role if role not in out else f"{role}_{part.get('id', index)}"
        out[key] = copy.deepcopy(part)
    return out


def identity(project, parts_map):
    """Which build a set of kept swaps belongs to."""
    return (project, tuple(p.get("id", "") for p in parts_map.values()))


def apply(base, kept):
    """Base build + kept swaps. A replacement that has no quantity inherits the quantity of the line it replaces
    (so replacing 'sensor x3' does not silently become 'sensor x1'). Swaps with a new key are added as extra modules."""
    out = {k: copy.deepcopy(p) for k, p in base.items()}
    for key, part in (kept or {}).items():
        if not isinstance(part, dict):
            continue
        new = copy.deepcopy(part)
        old = out.get(key)
        if old and not new.get("qty") and old.get("qty"):
            new["qty"] = old["qty"]
        out[key] = new
    return out


def active_build(state, project, base):
    """The build the user is actually looking at: base + kept swaps, but only if the swaps were made for THIS build."""
    if state.get("opt_kept") and state.get("opt_base_for") == identity(project, base):
        return apply(base, state.opt_kept)
    return {k: copy.deepcopy(p) for k, p in base.items()}


def by_id(active):
    """{part_id: part} in the shape bill.make / ledger take. If two lines end up with the same part id their quantities are added, never dropped."""
    out = {}
    for part in active.values():
        if part.get("none"):
            continue
        if part["id"] in out:
            out[part["id"]]["qty"] = (out[part["id"]].get("qty") or 1) + (part.get("qty") or 1)
        else:
            out[part["id"]] = part
    return out


def count(state, project, base):
    """How many swaps are applied to this build (0 if none or if they belong to another build)."""
    return len(state.opt_kept) if state.get("opt_kept") and state.get("opt_base_for") == identity(project, base) else 0
