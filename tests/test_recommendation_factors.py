import json

from core import picker, pipeline, resume
from core.data import PROJECTS, PROJECT_FACTORS
from core.recommendation_catalog import PROJECT_CATALOG, PROJECT_FACTOR_CATALOG


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
