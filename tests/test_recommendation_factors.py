import json
import csv
from pathlib import Path

from core import picker, pipeline, resume
from core.data import PROJECTS, PROJECT_FACTORS
from core.recommendation_catalog import (
    COMPETITION_EVENT_COUNTS,
    COMPETITION_EVENTS,
    COMPETITION_PROJECT_KEYS,
    DOMAIN_TAGS,
    PROJECT_CATALOG,
    PROJECT_FACTOR_CATALOG,
    RECOMMENDATION_PROJECT_KEYS,
    STAR_PROJECTS,
    STAR_COLLISION_ALLOWLIST,
    STAR_KEYS,
    competition_projects_for_event,
)
from core.skill_vocab import ALLOWED_SKILL_TAGS


def test_nine_questions_and_factor_metadata_cover_supported_projects():
    assert len(picker.QUESTIONS) == 9
    assert set(PROJECTS) == set(PROJECT_FACTORS)
    rating_factors = {key for _, key in picker.AXES}
    for factors in PROJECT_FACTORS.values():
        assert all(1 <= factors[key] <= 5 for key in rating_factors)
        assert factors["build_hours"] > 0
        assert factors["cost_inr"] > 0
        assert 1 <= factors["parts_availability_india"] <= 5
        assert factors["tools_required"] and factors["required_skills"] and factors["prerequisites"]


def test_normalize_survey_labels_and_schedule():
    profile = picker.normalize_survey_answers({
        "career": ["ML / vision"],
        "languages": ["Python", "None yet"],
        "schedule": {"hours_per_week": 8, "deadline_weeks": 4},
        "hours_per_week": 6,
        "deadline_weeks": 2,
        "budget_inr": 4000,
        "dream_job": "Computer vision engineer",
    })
    assert profile["career"] == ["vision"]
    assert profile["languages"] == ["python"]
    assert profile["schedule"] == {"hours_per_week": 8, "deadline_weeks": 4}
    assert profile["budget_inr"] == 4000
    assert profile["dream_job"] == "Computer vision engineer"


def test_hard_limits_remove_over_budget_underequipped_and_late_projects():
    within_budget = picker.rank_factor_projects({"budget_inr": 1000})
    assert within_budget
    assert all(picker.eligibility(key, {"budget_inr": 1000})["estimated_cost_inr"] <= 1000 for key, _ in within_budget)
    laptop_only = picker.rank_factor_projects({"tools": ["laptop_only"]})
    assert all(not picker.PROJECT_FACTOR_CATALOG[key]["tools_required"] - {"laptop"} for key, _ in laptop_only)
    assert picker.rank_factor_projects({"schedule": {"hours_per_week": 1, "deadline_weeks": 1}}) == []


def test_owned_hardware_credit_only_applies_to_relevant_project():
    assert picker.eligibility("line_follower", {"budget_inr": 2200, "hardware": ["arduino"]})["eligible"]
    assert not picker.eligibility("bluetooth_car", {"budget_inr": 2500, "hardware": ["arduino"]})["eligible"]
    assert picker.eligibility("bluetooth_car", {"budget_inr": 2500, "hardware": ["esp32"]})["eligible"]


def test_slightly_ambitious_difficulty_beats_too_hard_and_too_easy_is_less_penalized():
    novice = picker.factor_breakdown("line_follower", {})
    assert novice["difficulty"] > picker.factor_breakdown("obstacle_avoider", {})["difficulty"]
    experienced = {"experience": ["sensor_read", "soldering", "motor_driver", "breadboard", "raspberry_pi", "trained_model"],
                   "languages": ["python", "c_cpp"]}
    obstacle_fit = picker.factor_breakdown("obstacle_avoider", experienced)["difficulty"]
    line_fit = picker.factor_breakdown("line_follower", experienced)["difficulty"]
    assert obstacle_fit > line_fit
    assert line_fit > 50


def test_ranking_is_deterministic_and_diverse_across_available_domains():
    profile = {"career": ["robotics"], "interests": ["robotics", "sensing", "iot"]}
    first = picker.rank_factor_projects(profile)
    assert first == picker.rank_factor_projects(profile)
    domains = [PROJECT_FACTOR_CATALOG[key]["domain"] for key, _ in first]
    assert all(domains.count(domain) <= 2 for domain in set(domains))
    assert len(first) == 5
    assert not set(PROJECTS) & {key for key, _ in first}


def test_imported_and_competition_catalogs_exclude_three_existing_recommendations():
    assert sum(project["catalog_source"] == "projects.csv" for project in PROJECT_CATALOG.values()) == 147
    assert sum(project["catalog_source"] == "competition list" for project in PROJECT_CATALOG.values()) == 18
    assert all(PROJECT_CATALOG[key]["bom_supported"] for key in PROJECTS)
    assert not set(PROJECTS) & {key for key, _ in picker.rank_factor_projects({})}


def test_competition_events_are_ordered_by_project_mentions():
    assert len(COMPETITION_PROJECT_KEYS) == 18
    assert COMPETITION_EVENT_COUNTS["Robo Soccer"] == 4
    assert COMPETITION_EVENTS[0] == "Robo Soccer"
    assert COMPETITION_EVENTS[1] == "Search and Rescue"
    assert len(competition_projects_for_event("Robo Soccer")) == 4
    assert all(PROJECT_FACTOR_CATALOG[key]["competition_event"] == "Robo Soccer"
               for key in competition_projects_for_event("Robo Soccer"))


def test_wireless_skill_tags_are_normalized_to_shared_vocabulary():
    competition_skills = set().union(*(
        PROJECT_FACTOR_CATALOG[key]["required_skills"] for key in COMPETITION_PROJECT_KEYS
    ))
    assert "wireless" not in competition_skills
    assert {"wireless_other", "rf_comms"} <= competition_skills
    assert PROJECT_FACTOR_CATALOG["fpv_speed_racer_drone"]["required_skills"] >= {
        "wireless_other", "rf_comms"
    }


def test_star_catalog_has_aerospace_domain_and_hides_unverified_large_costs():
    by_key = {project["key"]: project for project in STAR_PROJECTS}
    assert by_key["cubesat_flatsat"]["domain"] == "space_aerospace"
    for key in ("qdd_robot_arm", "cubesat_flatsat", "imitation_learning_arm"):
        assert by_key[key]["cost_inr"] is None
        assert by_key[key]["price_status"] == "pending_verification"
    assert by_key["f1tenth_autonomous_racecar"]["price_status"] == "unverified_estimate"
    assert by_key["f1tenth_autonomous_racecar"]["cost_inr"] == 55000


def test_csv_ratings_preserve_raw_zero_to_five_scale():
    assert PROJECT_FACTOR_CATALOG["led_chaser"]["ai_vision"] == 0
    assert PROJECT_FACTOR_CATALOG["led_chaser"]["difficulty"] == 1
    assert PROJECT_FACTOR_CATALOG["quadcopter_fc"]["ai_vision"] == 0


def test_competition_domains_use_main_project_taxonomy():
    main_taxonomy = set(DOMAIN_TAGS) | set(DOMAIN_TAGS.values())
    assert all(
        PROJECT_FACTOR_CATALOG[key]["domain"] in main_taxonomy
        for key in RECOMMENDATION_PROJECT_KEYS
    )


def test_star_ids_merge_once_and_only_expected_rows_collide():
    actual_collisions = {
        key for key in STAR_KEYS
        if PROJECT_CATALOG[key]["catalog_source"] != "star projects"
    }
    assert actual_collisions == STAR_COLLISION_ALLOWLIST
    assert len(STAR_KEYS) == 20
    assert all(PROJECT_CATALOG[key]["is_star"] for key in STAR_KEYS)
    assert STAR_KEYS & RECOMMENDATION_PROJECT_KEYS == STAR_COLLISION_ALLOWLIST


def test_csv_skill_tags_stay_inside_reviewed_vocabulary():
    data_dir = Path(__file__).parents[1] / "core" / "project_data"
    unknown = {}
    for filename in ("projects.csv", "competition_projects.csv", "star_projects.csv"):
        with (data_dir / filename).open(encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                tags = {tag.strip() for tag in row.get("skills", "").split("|") if tag.strip()}
                outside = tags - ALLOWED_SKILL_TAGS
                if outside:
                    unknown[f"{filename}:{row.get('id')}"] = sorted(outside)
    assert not unknown


def test_csv_price_provenance_columns_exist_and_report_unverified_rows():
    data_dir = Path(__file__).parents[1] / "core" / "project_data"
    missing = {}
    for filename in ("projects.csv", "competition_projects.csv", "star_projects.csv"):
        with (data_dir / filename).open(encoding="utf-8-sig", newline="") as source:
            rows = list(csv.DictReader(source))
        assert rows and {"last_verified", "price_source"} <= rows[0].keys()
        missing[filename] = sum(
            not row["last_verified"].strip() or not row["price_source"].strip()
            for row in rows
        )
    print(f"Rows missing price verification metadata: {missing}")


def test_all_catalog_prerequisites_exist_and_graph_is_acyclic():
    graph = {
        key: set(meta.get("prerequisites", set()))
        for key, meta in PROJECT_FACTOR_CATALOG.items()
    }
    assert all(
        prerequisite in graph
        for prerequisites in graph.values()
        for prerequisite in prerequisites
    )
    visiting, visited = set(), set()

    def visit(key):
        if key in visiting:
            raise AssertionError(f"Prerequisite cycle includes {key}")
        if key in visited:
            return
        visiting.add(key)
        for prerequisite in graph[key]:
            visit(prerequisite)
        visiting.remove(key)
        visited.add(key)

    for project_key in graph:
        visit(project_key)


def test_v2_neutral_components_and_missing_cost_are_explicit():
    profile = {}
    context = picker.build_recommender_context(profile)
    result = picker.score_project_v2("qdd_robot_arm", profile, context)
    assert result.interest == 0.5
    assert result.learn == 0.7
    assert result.level > 0
    assert "low_information" in result.flags
    assert "cost_unverified" in result.flags
    assert not result.excluded


def test_v2_level_penalizes_too_hard_more_than_too_easy():
    context = {"level": 2.0, "user_skills": set()}
    easy = picker._level_fit({"difficulty": 1, "required_skills": set()}, context)[0]
    hard = picker._level_fit({"difficulty": 5, "required_skills": set()}, context)[0]
    assert hard < easy


def test_v2_feasibility_excludes_far_over_budget_but_accepts_zero_cost():
    profile = {"budget_inr": 1000}
    context = picker.build_recommender_context(profile)
    expensive = picker.score_project_v2("fpv_speed_racer_drone", profile, context)
    free = picker.score_project_v2("ros2_gazebo_sim", profile, context)
    assert expensive.excluded
    assert not free.excluded


def test_v2_role_impact_uses_skill_relevance():
    from core.role_impact import impact_for

    project = {"portfolio_impact": 5, "required_skills": {"stm32", "embedded", "rtos"}}
    assert impact_for("test-project", project, {"embedded"}) > impact_for("test-project", project, {"robotics"})


def test_prerequisite_graph_orders_chains_and_reports_unlocks():
    from core.prereqs import PrerequisiteGraph

    graph = PrerequisiteGraph({
        "base": {"prerequisites": set(), "required_skills": set()},
        "middle": {"prerequisites": {"base"}, "required_skills": set()},
        "goal": {"prerequisites": {"middle"}, "required_skills": set()},
    })
    assert graph.unmet_chain("goal") == ["middle", "base"]
    assert graph.unlocks("base") == ["middle"]


def test_prerequisite_graph_readiness_uses_partial_skill_coverage():
    from core.prereqs import PrerequisiteGraph

    graph = PrerequisiteGraph({
        "base": {"prerequisites": set(), "required_skills": {"embedded", "stm32"}},
        "goal": {"prerequisites": {"base"}, "required_skills": set()},
    })
    assert graph.readiness("goal", set(), {"embedded"}) == 0.3
    assert graph.readiness("goal", {"base"}, set()) == 1.0


def test_prerequisite_graph_rejects_cycles_and_next_step_skips_unready():
    from core.prereqs import PrerequisiteGraph

    try:
        PrerequisiteGraph({
            "a": {"prerequisites": {"b"}, "required_skills": set()},
            "b": {"prerequisites": {"a"}, "required_skills": set()},
        })
    except ValueError as error:
        assert "cycle" in str(error)
    else:
        raise AssertionError("Cycle was not rejected")

    graph = PrerequisiteGraph({
        "root": {"prerequisites": set(), "required_skills": {"embedded"}},
        "middle": {"prerequisites": {"root"}, "required_skills": {"embedded"}},
        "goal": {"prerequisites": {"middle"}, "required_skills": set()},
    })
    assert graph.next_step("goal", set(), set()) == "root"


def test_portfolio_coverage_rewards_new_embedded_evidence():
    from core.coverage import coverage_gain

    done = {"led_chaser", "traffic_light", "digital_dice"}
    rtos, _ = coverage_gain("tiny_rtos_scheduler", {"embedded"}, done, set())
    basic, _ = coverage_gain("led_chaser", {"embedded"}, done, set())
    assert rtos > basic


def test_v2_selection_caps_results_and_blocks_unready_projects():
    from core.picker import rank_factor_projects_v2
    from core.recommender_config import MAX_PER_DOMAIN, STAR_DO_NOW_LEVEL_MIN, STAR_DO_NOW_READINESS_MIN

    profile = {
        "career": ["embedded"],
        "interests": ["embedded", "robotics"],
        "experience": ["sensor_read", "soldering", "motor_driver"],
        "budget_inr": 25000,
    }
    result = rank_factor_projects_v2(profile)
    picks = result["results"]
    assert len(picks) <= 4
    assert all(item.readiness >= 0.6 for item in picks)
    domains = [PROJECT_FACTOR_CATALOG[item.key]["domain"] for item in picks]
    assert all(domains.count(domain) <= MAX_PER_DOMAIN for domain in set(domains))
    assert result["goal"]["key"] in STAR_KEYS
    assert result["goal"]["key"] not in {item.key for item in picks}
    assert all(
        not item.is_star
        or (item.readiness >= STAR_DO_NOW_READINESS_MIN and item.level >= STAR_DO_NOW_LEVEL_MIN)
        for item in picks
    )


def test_profile_completeness_cold_start_requires_minimum_context():
    from core.picker import profile_completeness, rank_factor_projects_v2

    score, missing = profile_completeness({})
    result = rank_factor_projects_v2({})
    assert score == 0
    assert "career direction or interests" in missing
    assert result["needs_more_info"]
    assert result["results"] == []
    assert result["goal"] is None


def test_profile_completeness_accepts_focus_and_experience():
    from core.picker import profile_completeness

    score, missing = profile_completeness({
        "interests": ["embedded"],
        "experience": ["sensor_read"],
    })
    assert score >= 0.4
    assert "career direction or interests" not in missing
    assert "experience, resume skills, or completed projects" not in missing


def test_resume_factor_quotes_must_be_verbatim_and_ids_allowed():
    source = "Read a sensor in C and soldered a small board."
    result = resume.validate_factors(source, {
        "skills": [
            {"id": "sensor_read", "name": "Sensor coding", "quote": "Read a sensor in C"},
            {"id": "trained_model", "name": "Model training", "quote": "I trained a model"},
            {"id": "imaginary", "name": "Invented", "quote": "soldered a small board"},
        ],
        "languages": [{"id": "c_cpp", "name": "C", "quote": "Read a sensor in C"}],
        "tools": [],
        "projects": [{"name": "Sensor board", "domain": "embedded", "skills": ["C"], "quote": "soldered a small board"}],
    })
    assert [item["id"] for item in result["skills"]] == ["sensor_read"]
    assert [item["id"] for item in result["languages"]] == ["c_cpp"]
    assert result["projects"][0]["quote"] == "soldered a small board"
    assert "source" not in result and "raw_text" not in result


def test_gemini_resume_extraction_only_keeps_quote_verified_factors(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    source = "Built an Arduino sensor reader in C++."
    payload = {"skills": [{"id": "sensor_read", "name": "Sensor coding", "quote": "Arduino sensor reader"}],
               "languages": [{"id": "c_cpp", "name": "C++", "quote": "in C++"}],
               "tools": [], "projects": []}
    class Response:
        text = json.dumps(payload)
    monkeypatch.setattr(pipeline, "_generate", lambda *args: Response())
    result = pipeline.extract_resume_factors(source)
    assert result["skills"][0]["id"] == "sensor_read"
    assert result["languages"][0]["quote"] == "in C++"


def test_idea_matching_does_not_call_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(pipeline, "_generate", lambda *args: (_ for _ in ()).throw(AssertionError("unexpected Gemini call")))
    assert pipeline.map_idea("a car that follows a black path")["project"] == "line_follower"


def test_tinyfish_job_research_fetches_sources_and_returns_domain_signals(monkeypatch):
    hits = [{"title": "Embedded Firmware Engineer", "url": "https://jobs.example/role", "snippet": "Firmware role"}]
    monkeypatch.setattr(pipeline.tf, "search", lambda query, location: hits)
    monkeypatch.setattr(pipeline.tf, "fetch", lambda urls: {urls[0]: "Develop embedded firmware for STM32 and RTOS devices."})
    result = pipeline.research_career_target("Embedded engineer")
    assert "embedded" in result["signals"]
    assert result["sources"][0]["url"] == "https://jobs.example/role"
    assert "STM32" in result["sources"][0]["excerpt"]
