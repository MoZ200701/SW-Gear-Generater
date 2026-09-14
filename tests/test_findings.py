"""The constants in findings.py against the committed probe evidence.

``probe/results/latest.json`` is what SolidWorks did; this is what stops the
tool's constants drifting from it.
"""

import json
import math
from pathlib import Path

import pytest

from gear_generator import findings
from gear_generator.probe import decide

LATEST = Path(__file__).resolve().parents[1] / "probe" / "results" / "latest.json"


@pytest.fixture(scope="module")
def evidence():
    assert LATEST.is_file(), f"{LATEST} is the committed probe evidence and must exist"
    data = json.loads(LATEST.read_text(encoding="utf-8"))
    records = {r["name"]: r for r in data["records"]}
    return data, records, decide.decide(records)


def facts(records, name):
    assert records[name]["status"] == "pass", f"{name} did not pass"
    return records[name]["facts"]


def test_the_evidence_is_from_the_version_the_findings_name(evidence):
    data, _, _ = evidence
    assert data["meta"]["version"] == findings.VERIFIED_ON


def test_every_probe_passed_including_the_end_to_end_build(evidence):
    data, records, decided = evidence
    assert [name for name, r in records.items() if r["status"] != "pass"] == []
    assert decided["end_to_end"] is True
    assert {r["tier"] for r in records.values()} >= {0, 1, 2, 3, 4, 5}


def test_decisions(evidence):
    _, _, decided = evidence
    assert decided["flank_recipe"] == findings.DEFAULT_RECIPE
    assert decided["trig_default"] == findings.TRIG_DEFAULT
    assert decided["equation_add_call"] == findings.EQUATION_ADD_CALL
    assert decided["equation_set_route"] == findings.EQUATION_SET_ROUTE
    assert decided["set_units_mmgs_after_new"] is findings.SET_UNITS_MMGS_AFTER_NEW
    assert decided["plane_select_route"] == findings.PLANE_SELECT_ROUTE
    assert decided["equal_constraint"] == findings.RELATIONS["equal"]
    assert decided["circle_dimension"] == findings.CIRCLE_DIMENSION
    assert decided["arc_dimension"] == findings.ARC_DIMENSION
    assert decided["curve_trig"] == findings.CURVE_TRIG
    assert decided["curves_are_fixed"] is findings.CURVES_ARE_FIXED
    assert decided["shared_ends_are_one_point"] is findings.SHARED_ENDS_ARE_ONE_POINT
    assert decided["cut_end_condition"] == findings.CUT_END_CONDITION
    assert decided["pattern_count_dim_index"] == findings.PATTERN_COUNT_DIM_INDEX
    assert decided["save_as_overwrites"] is findings.SAVE_AS_OVERWRITES
    assert decided["first_component_fixed"] is findings.FIRST_COMPONENT_FIXED
    assert decided["manual_steps"] == ["material"]


def test_units(evidence):
    _, records, _ = evidence
    units = facts(records, "document_units")
    assert units["units_2026_folder"] == {"linear": findings.LENGTH_MM, "system": findings.UNIT_SYSTEM_MMGS,
                                          "path": units["units_2026_folder"]["path"]}
    assert units["set_mmgs_default"]["linear_after"] == findings.LENGTH_MM


def test_constrained_status(evidence):
    _, records, _ = evidence
    status = facts(records, "constrained_status")
    assert status["status_free_line"] == findings.UNDER_CONSTRAINED
    assert status["status_defined_line"] == findings.FULLY_CONSTRAINED


def test_pattern_and_extrude_dimensions(evidence):
    _, records, _ = evidence
    pattern = facts(records, "pattern")
    assert pattern["pattern_call"].startswith(findings.PATTERN_CALL.split(".")[-1])
    name, value = pattern["pattern_dimensions"][findings.PATTERN_COUNT_DIM_INDEX]
    assert name == findings.PATTERN_COUNT_DIM_NAME and value == 6.0
    assert any(math.isclose(v, 2 * math.pi) for _, v in pattern["pattern_dimensions"])


def test_mates(evidence):
    _, records, _ = evidence
    mates = facts(records, "assembly_components_and_mates")
    assert [kind for _, kind in mates["mates"]] == ["MateCoincident", "MateCoincident", "MateDistanceDim",
                                                    "MatePlanarAngleDim"]
    assert mates["distance_mate_dimensions"][0][0] == findings.MATE_DISTANCE_DIM_NAME
    link = facts(records, "assembly_distance_link")
    assert link["component_b_translation_mm_after_global_70"][0] == pytest.approx(70.0)


def test_save_as_returns_a_plain_flag(evidence):
    _, records, _ = evidence
    assert facts(records, "save_as")["save_as3_result_is_tuple"] is False
