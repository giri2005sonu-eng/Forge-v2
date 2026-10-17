"""The 168-project component dataset: coverage, references and honesty checks."""
import csv, json, pathlib, re
import pytest
from core import project_store as ps
from core.project_store import DATA

SRC = {"general": DATA / "projects.csv", "competition": DATA / "competition_projects.csv"}
D = ps.dataset()


def ids(path):
    return [r["id"] for r in csv.DictReader(open(path, encoding="utf-8-sig"))]


def test_every_project_in_both_csvs_has_a_component_list():
    for src, path in SRC.items():
        want = {f"{src}:{i}" for i in ids(path)}
        assert want <= set(D["projects"]), f"{src}: missing {want - set(D['projects'])}"
    assert len(D["projects"]) == sum(len(ids(p)) for p in SRC.values()) == 168


def test_no_extra_or_duplicate_projects():
    assert len(set(D["projects"])) == len(D["projects"])
    assert {k.split(":")[0] for k in D["projects"]} == {"general", "competition"}


def test_every_part_resolves_to_the_library_and_is_well_formed():
    lib = D["library"]
    for p in D["projects"].values():
        seen = set()
        for x in p["parts"]:
            assert x["part"] in lib and x["id"] == "d_" + x["part"]
            assert x["part"] not in seen; seen.add(x["part"])
            assert 1 <= x["qty"] <= 20, (p["key"], x)
            assert 2 <= len(x["query"].split()) <= 7 and not re.search(r"\b(buy|price)\b", x["query"].lower()), x["query"]
            assert x["role"] and x["name"]


def test_dataset_contains_no_prices_or_fake_specs():
    text = json.dumps(D).lower()
    assert "seed_price" not in text and "inr" not in json.dumps([x for p in D["projects"].values() for x in p["parts"]]).lower()
    assert all(p["bom_status"] == "draft" and p["reviewed"] is False for p in D["projects"].values())


def test_software_only_projects_are_flagged_not_padded():
    soft = {p["id"] for p in D["projects"].values() if p["software_only"]}
    assert soft == {"ros2_gazebo_sim", "drone_sim_pid", "opencv_color_tracker"} and all(not D["projects"][f"general:{i}"]["parts"] for i in soft)


def test_competition_projects_carry_event_constraints_and_safety():
    comp = [p for p in D["projects"].values() if p["project_source"] == "competition"]
    assert len(comp) == 18 and all(p["competition_event"] and p["constraints"] and p["notes"] for p in comp)
    # constraint-driven parts are present where the constraint names them
    has = lambda pid, part: any(x["part"] == part for x in D["projects"][f"competition:{pid}"]["parts"])
    assert has("fpv_speed_racer_drone", "elrs_rx") and has("fpv_speed_racer_drone", "lipo_hd")
    assert has("omnidirectional_striker_bot", "solenoid_kicker") and has("omnidirectional_striker_bot", "cap_bank") and has("omnidirectional_striker_bot", "omni_set")
    assert has("maze_solving_micro_mouse", "n20_enc") and has("ultra_fast_pid_line_follower", "ir_array_highfreq")
    assert has("complex_track_drag_line_tracer", "coreless_fast")


def test_drone_parts_not_applied_to_ground_robots_and_vice_versa():
    drone_only = {"fc", "esc_4in1", "brushless_2207", "props_5in", "frame_5in"}
    for pid in ("high_speed_time_trial_rover", "aggressive_overtaking_rc_bot", "omnidirectional_striker_bot", "ultra_fast_pid_line_follower"):
        assert not drone_only & {x["part"] for x in D["projects"][f"competition:{pid}"]["parts"]}
    assert not {"chassis2wd", "tb6612"} & {x["part"] for x in D["projects"]["competition:fpv_speed_racer_drone"]["parts"]}


def test_dropdown_lists_all_168_and_is_sorted_stably():
    o = ps.options(); assert len(o) == 168 and len({r["key"] for r in o}) == 168 and o == ps.options()


def test_dataset_copy_of_csvs_matches_source_rows():
    for src, path in SRC.items():
        rows = {r["id"]: r for r in csv.DictReader(open(path, encoding="utf-8-sig"))}
        for i, r in rows.items():
            p = D["projects"][f"{src}:{i}"]
            assert p["label"] == r["name"] and p["catalog_cost_inr"] == int(r["cost_inr"] or 0) and p["constraints"] == r.get("constraints", "")
