"""Pure-logic unit tests for the phase D/F/H services (no DB, no network)."""
from app.services import cost_governance as cg
from app.services import sandbox, study, tools


# --- P37 tools --------------------------------------------------------------
def test_calculator_basic():
    assert "14" in tools.run("calculator", {"expression": "2*(3+4)"})


def test_calculator_rejects_code():
    out = tools.run("calculator", {"expression": "__import__('os').system('ls')"})
    assert "Could not evaluate" in out


def test_convert_temperature():
    assert "212" in tools.run("convert", {"value": 100, "from_unit": "c", "to_unit": "f"})


def test_convert_length():
    assert tools.run("convert", {"value": 1, "from_unit": "km", "to_unit": "m"}).endswith("m")


def test_unknown_tool():
    assert "Unknown tool" in tools.run("nope", {})


def test_tool_specs_shape():
    names = {s["function"]["name"] for s in tools.SPECS}
    assert {"calculator", "convert", "current_datetime", "campus_info"} <= names


# --- P36 sandbox ------------------------------------------------------------
def test_sandbox_prints():
    r = sandbox.run_python("print(2+2)")
    assert r["ok"] and r["stdout"].strip() == "4"


def test_sandbox_blocks_network_import():
    r = sandbox.run_python("import socket")
    assert not r["ok"] and "not allowed" in r["stderr"]


def test_sandbox_timeout():
    r = sandbox.run_python("while True:\n  pass", timeout=2)
    assert not r["ok"]


# --- P46 cost governance ----------------------------------------------------
def test_budget_breach():
    b = {"cohort": "CSE-A", "monthly_usd": 10, "alert_pct": 80}
    v = cg.evaluate_cohort(b, 12.0)
    assert v["breached"] and v["should_throttle"] and v["percent"] == 120.0


def test_budget_alerting_not_breached():
    b = {"cohort": "CSE-A", "monthly_usd": 10, "alert_pct": 80}
    v = cg.evaluate_cohort(b, 9.0)
    assert v["alerting"] and not v["breached"]


def test_budget_zero_cap_never_throttles():
    b = {"cohort": "X", "monthly_usd": 0, "alert_pct": 80}
    v = cg.evaluate_cohort(b, 5.0)
    assert not v["breached"] and not v["alerting"]


# --- P38 study-aid JSON extraction ------------------------------------------
def test_study_extract_clean_json():
    assert study._extract_json('{"a": 1}') == {"a": 1}


def test_study_extract_embedded_json():
    assert study._extract_json('Here you go:\n{"x": 2}\nThanks') == {"x": 2}


def test_study_extract_garbage():
    assert study._extract_json("no json here") == {}


# --- Auto long-term memory (P31) --------------------------------------------
from app.services import auto_memory as AM  # noqa: E402


def test_auto_memory_detects_personal():
    assert AM._looks_personal("my favourite food is biryani")
    assert AM._looks_personal("i love sci-fi movies")
    assert not AM._looks_personal("what is the capital of France")


def test_auto_memory_parses_facts():
    out = AM.parse_facts('Sure: {"facts":["Favourite food is biryani","Likes sci-fi"]}')
    assert out == ["Favourite food is biryani", "Likes sci-fi"]
    assert AM.parse_facts("no json here") == []
    # de-dupes case-insensitively
    assert AM.parse_facts('{"facts":["Likes tea","likes tea"]}') == ["Likes tea"]


def test_embed_degrades_gracefully():
    # sentence-transformers may be unavailable; embed must still return a 384-vec.
    from app.services import embeddings
    v = embeddings.embed("hello")
    assert isinstance(v, list) and len(v) == 384
