"""The probe harness's ordering, skipping and hang handling, with fake probes."""

import pytest

from gear_generator.probe import comerr, harness, report
from gear_generator.probe.harness import FAIL, HUNG, NOT_RUN, PASS, SKIP, Probe, Px, Record, Require


def make(name, body=None, needs=(), tier=0, extra=False):
    def default(px):
        px.ok(f"{name} ran")

    return Probe(name, body or default, tuple(needs), (f"I.{name}",), tier, extra)


def run(probes, executor=harness.inline_executor):
    shared = {}
    return harness.run(probes, lambda record: Px(record, shared=shared), executor, timeout=1.0, version="SW test")


# -- order and the skip cascade ---------------------------------------------


def test_probes_run_in_registry_order():
    seen = []
    probes = [make(n, lambda px, n=n: seen.append(n)) for n in ("a", "b", "c")]
    records = run(probes)
    assert seen == ["a", "b", "c"]
    assert [r.status for r in records] == [PASS, PASS, PASS]


def test_a_failed_need_skips_its_dependents_and_says_which():
    def broken(px):
        px.fail("did not work")

    records = run([make("a", broken), make("b", needs=("a",)), make("c", needs=("b",)), make("d")])
    assert [r.status for r in records] == [FAIL, SKIP, SKIP, PASS]
    assert "a (fail)" in records[1].reason
    assert "b (skip)" in records[2].reason


def test_require_ends_a_probe_as_a_failure_without_a_traceback():
    def stops(px):
        px.require(False, "the thing it needs")
        px.ok("never reached")

    record = run([make("a", stops)])[0]
    assert record.status == FAIL
    assert record.error is None
    assert [line.text for line in record.lines] == ["the thing it needs"]


def test_an_exception_is_a_failure_with_the_error_recorded():
    def explodes(px):
        raise RuntimeError("SolidWorks said no")

    record = run([make("a", explodes)])[0]
    assert record.status == FAIL
    assert record.error["type"] == "RuntimeError"
    assert "SolidWorks said no" in record.lines[-1].text


def test_a_hang_stops_the_run_and_nothing_after_it_is_run():
    def executor(body, timeout):
        return False, None

    records = run([make("a"), make("b")], executor)
    assert [r.status for r in records] == [HUNG, NOT_RUN]
    assert "stuck" in records[1].reason


def test_every_record_carries_the_version():
    assert run([make("a")])[0].version == "SW test"


def test_attempt_records_both_outcomes_as_facts():
    def body(px):
        px.attempt("works", lambda: 3)
        px.attempt("raises", lambda: (_ for _ in ()).throw(ValueError("nope")))

    record = run([make("a", body)])[0]
    assert record.status == PASS
    assert record.facts["attempt:works"] == {"ok": True, "value": 3}
    assert record.facts["attempt:raises"]["ok"] is False


def test_shared_state_passes_from_one_probe_to_the_next():
    def first(px):
        px.shared["template"] = "Part.PRTDOT"

    def second(px):
        px.check(px.shared.get("template") == "Part.PRTDOT", "saw it")

    assert [r.status for r in run([make("a", first), make("b", second, needs=("a",))])] == [PASS, PASS]


# -- selection --------------------------------------------------------------


def test_only_pulls_in_what_a_probe_needs_in_registry_order():
    registry = [make("a"), make("b", needs=("a",)), make("c"), make("d", needs=("b",))]
    assert [p.name for p in harness.select(registry, only=["d"])] == ["a", "b", "d"]


def test_tier_and_extras_filter():
    registry = [make("a", tier=0), make("b", tier=1), make("c", tier=2), make("x", tier=1, extra=True)]
    assert [p.name for p in harness.select(registry, tier=1)] == ["a", "b"]
    assert [p.name for p in harness.select(registry, tier=1, extras=True)] == ["a", "b", "x"]


def test_an_unknown_probe_is_named():
    with pytest.raises(KeyError, match="nothing"):
        harness.select([make("a")], only=["nothing"])


def test_the_registry_refuses_a_second_probe_of_the_same_name():
    before = list(harness.REGISTRY)
    try:
        harness.probe("dup-for-test")(lambda px: None)
        with pytest.raises(ValueError, match="already registered"):
            harness.probe("dup-for-test")(lambda px: None)
    finally:
        harness.REGISTRY[:] = before


# -- turning COM errors into data -------------------------------------------


class com_error(Exception):  # noqa: N801 - the look-alike shares pywin32's name
    pass


def test_a_com_error_keeps_hresult_name_text_and_argerror():
    exc = com_error(-2147352567, "Exception occurred.", (0, "SolidWorks", "Bad argument", None, 0, -2147024809), 3)
    info = comerr.describe_error(exc)
    assert info["hresult"] == "0x80020009"
    assert info["name"] == "DISP_E_EXCEPTION"
    assert "Bad argument" in info["text"]
    assert info["argerror"] == 3
    assert info["scode_name"] == "E_INVALIDARG"


def test_member_not_found_is_named():
    info = comerr.describe_error(com_error(-2147352573, "Member not found.", None, None))
    assert info["name"] == "DISP_E_MEMBERNOTFOUND"
    assert comerr.one_line(com_error(-2147352573, "Member not found.", None, None)).startswith("DISP_E_MEMBERNOTFOUND")


def test_an_ordinary_exception_is_described_too():
    info = comerr.describe_error(ValueError("plain"))
    assert info == {"type": "ValueError", "hresult": "", "name": "", "text": "plain", "argerror": None}


# -- the report -------------------------------------------------------------


def test_the_report_is_lowercase_for_ok_and_uppercase_for_trouble():
    def body(px):
        px.ok("fine")
        px.fail("not fine")

    record = run([make("a", body)])[0]
    lines = report.record_lines(record)
    assert lines[0].startswith("FAIL    a")
    assert lines[1] == "  ok     fine"
    assert lines[2] == "  FAIL   not fine"


def test_results_are_written_three_ways(tmp_path):
    records = run([make("a")])
    paths = report.write(str(tmp_path), records, {"stamp": "20260914-000000", "version": "SW test"},
                         {"flank_recipe": "B"}, ["pass    a"])
    loaded = report.load(paths["latest"])
    assert loaded["decisions"] == {"flank_recipe": "B"}
    assert loaded["records"][0]["name"] == "a"
    assert (tmp_path / "probe-results-20260914-000000.txt").read_text().startswith("pass")


def test_the_ledger_marks_what_passed_as_verified():
    def broken(px):
        px.fail("no")

    records = run([make("a"), make("b", broken)])
    rows = report.ledger_rows(records, "SolidWorks 2026")
    assert "| `I.a` | pass | Verified, SolidWorks 2026 |" in rows
    assert any(row.startswith("| `I.b` | fail | Failed in probe") for row in rows)
