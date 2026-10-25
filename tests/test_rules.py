"""The rules engine against the hand-written answer keys, plus one test per rule."""
from datetime import date

import pytest

import make_samples as ms
from app.pipeline.rules import decide, norm_entry_number, valid_entry_number, summarize, is_ieepa

AS_OF = date(2026, 10, 24)


def spec_entry(e: "ms.Entry") -> dict:
    """What a perfect reader would extract for this entry."""
    return {
        "entry_number": e.number,
        "entry_type": e.etype,
        "entry_date": e.entry_date.isoformat(),
        "liquidation_status": "liquidated" if e.liq else "unliquidated",
        "liquidation_date": e.liq.isoformat() if e.liq else None,
        "surety_paid_ieepa": e.surety_paid,
        "open_protest": e.open_protest,
        "protest_ieepa_only": e.protest_ieepa_only,
        "drawback": e.drawback,
        "reconciliation_flag": e.recon,
        "adcvd": e.adcvd,
        "ieepa_duty_statement": e.stated_ieepa if e.stated_ieepa is not None else (None if e.in_7501_bundle else e.ieepa),
        "lines": [] if not e.in_7501_bundle else [
            {"hts": [{"code": c, "entered_value": v, "rate": r, "duty": d} for (c, v, r, d) in ln.rows()]}
            for ln in e.lines
        ],
    }


def spec_importer(imp: "ms.Importer") -> dict:
    return {"cit_plaintiff": imp.cit_plaintiff,
            "cit_ior_submitted_date": imp.cit_ior_submitted.isoformat() if imp.cit_ior_submitted else None}


CASES = [(imp, e) for imp in ms.IMPORTERS for e in imp.entries]


@pytest.mark.parametrize("imp,e", CASES, ids=[f"{imp.slug}-{e.key}" for imp, e in CASES])
def test_engine_matches_answer_key(imp, e):
    d = decide(spec_entry(e), spec_importer(imp), AS_OF)
    assert d.route == e.expected_route, e.note
    for f in e.expected_flags:
        assert f in d.flags
    if d.bucket not in ("not_refundable", "review"):
        assert d.refund_amount == pytest.approx(e.ieepa)


def test_boundaries():
    base = {"entry_number": "ABC-1234567-1", "entry_type": "01", "liquidation_status": "liquidated",
            "lines": [{"hts": [{"code": "9903.01.25", "duty": 100.0}]}]}
    imp = {"cit_plaintiff": False}
    for days, route in [(0, "CAPE_NOW"), (80, "CAPE_NOW"), (81, "PROTEST_BY"), (180, "PROTEST_BY"), (181, "CLASS_PENDING")]:
        e = dict(base, liquidation_date=date.fromordinal(AS_OF.toordinal() - days).isoformat())
        assert decide(e, imp, AS_OF).route == route, days


def test_deadlines_and_urgency():
    e = {"entry_number": "ABC-1234567-1", "entry_type": "01", "liquidation_status": "liquidated",
         "liquidation_date": "2026-08-05", "lines": [{"hts": [{"code": "9903.02.69", "duty": 50.0}]}]}
    d = decide(e, {}, AS_OF)
    assert d.deadline == "2026-10-24" and d.days_left == 0 and d.urgent and d.in_cape_csv
    e["liquidation_date"] = "2026-06-01"
    d = decide(e, {}, AS_OF)
    assert d.route == "PROTEST_BY" and d.deadline == "2026-11-28" and not d.in_cape_csv


def test_phase3_requires_ior_by_july_30():
    e = {"entry_number": "ABC-1234567-1", "entry_type": "01", "liquidation_status": "liquidated",
         "liquidation_date": "2025-12-01", "lines": [{"hts": [{"code": "9903.01.24", "duty": 10.0}]}]}
    assert decide(e, {"cit_plaintiff": True, "cit_ior_submitted_date": "2026-07-30"}, AS_OF).route == "CAPE_PHASE3"
    assert decide(e, {"cit_plaintiff": True, "cit_ior_submitted_date": "2026-07-31"}, AS_OF).route == "PLAINTIFF_PHASE3_LATER"
    assert decide(e, {"cit_plaintiff": False}, AS_OF).route == "CLASS_PENDING"


def test_section_301_and_232_are_not_refunded():
    e = {"entry_number": "ABC-1234567-1", "entry_type": "01", "liquidation_status": "unliquidated",
         "lines": [{"hts": [{"code": "8714.91.5000", "entered_value": 1000, "duty": 0},
                            {"code": "9903.88.03", "duty": 250}, {"code": "9903.81.91", "duty": 500},
                            {"code": "9903.01.24", "duty": 100}]}]}
    d = decide(e, {}, AS_OF)
    assert d.route == "CAPE_NOW" and d.refund_amount == 100
    assert not is_ieepa("9903.88.03") and is_ieepa("99030124") and is_ieepa("9903.02.69")


def test_unverified_facts_are_never_guessed():
    e = {"entry_number": "ABC-1234567-1", "entry_type": "01", "liquidation_status": "liquidated",
         "liquidation_date": "2026-09-01", "unverified_fields": ["liquidation_date"],
         "lines": [{"hts": [{"code": "9903.01.24", "duty": 100}]}]}
    d = decide(e, {}, AS_OF)
    assert d.route == "NEEDS_REVIEW" and d.refund_amount == 0 and not d.in_cape_csv
    e2 = dict(e, unverified_fields=["ieepa_duty"], liquidation_date="2026-09-01")
    assert decide(e2, {}, AS_OF).route == "NEEDS_REVIEW"


def test_future_liquidation_date_is_suspicious():
    e = {"entry_number": "ABC-1234567-1", "entry_type": "01", "liquidation_status": "liquidated",
         "liquidation_date": "2026-12-01", "lines": [{"hts": [{"code": "9903.01.24", "duty": 100}]}]}
    assert decide(e, {}, AS_OF).route == "NEEDS_REVIEW"


def test_entry_number_normalization():
    assert norm_entry_number("hp704122073") == "HP7-0412207-3"
    assert norm_entry_number("HP7-0412207-3") == "HP7-0412207-3"
    assert valid_entry_number("RB255301184")
    assert not valid_entry_number("RB25530118")
    assert not valid_entry_number("RB2-55301A8-4")


def test_summary_buckets():
    imp = ms.LOTUS
    ds = [decide(spec_entry(e), spec_importer(imp), AS_OF) for e in imp.entries]
    s = summarize(ds, AS_OF)
    assert s["entries"] == 13
    assert s["at_risk_this_week"]["entries"] == ["HP7-0414106-2"]
    assert s["buckets"]["not_refundable"]["amount"] == 0


def test_phase2_only_inside_the_80_day_window():
    e = {"entry_number": "ABC-1234567-1", "entry_type": "01", "liquidation_status": "liquidated",
         "reconciliation_flag": True, "liquidation_date": "2026-09-01",
         "lines": [{"hts": [{"code": "9903.01.24", "duty": 100.0}]}]}
    d = decide(e, {}, AS_OF)
    assert d.route == "CAPE_PHASE2_RECON" and d.deadline == "2026-11-20" and d.in_cape_csv
    e["liquidation_date"] = "2025-12-01"            # 327 days: CAPE (incl. Phase 2) is closed
    assert decide(e, {}, AS_OF).route == "CLASS_PENDING"
    e["liquidation_date"] = "2026-06-01"            # 145 days
    assert decide(e, {}, AS_OF).route == "PROTEST_BY"
    e.update(liquidation_date="2026-09-01", open_protest=True)   # open protest beats Phase 2
    assert decide(e, {}, AS_OF).route == "PROTEST_OPEN"


def test_excluded_entry_types():
    base = {"entry_number": "ABC-1234567-1", "liquidation_status": "unliquidated",
            "lines": [{"hts": [{"code": "9903.01.24", "duty": 100.0}]}]}
    for t in ("09", "21", "22", "23"):
        assert decide(dict(base, entry_type=t), {}, AS_OF).route == "ASK_BROKER", t
    assert decide(dict(base, entry_type="08"), {}, AS_OF).route == "EXCLUDED_TYPE08"
    assert decide(dict(base, entry_type="47"), {}, AS_OF).route == "EXCLUDED_DRAWBACK"


def test_plaintiff_entries_past_80_days_go_to_phase3_not_protest():
    e = {"entry_number": "ABC-1234567-1", "entry_type": "01", "liquidation_status": "liquidated",
         "liquidation_date": "2026-06-01", "lines": [{"hts": [{"code": "9903.01.24", "duty": 100.0}]}]}
    assert decide(e, {"cit_plaintiff": True, "cit_ior_submitted_date": "2026-07-22"}, AS_OF).route == "CAPE_PHASE3"
    assert decide(e, {"cit_plaintiff": False}, AS_OF).route == "PROTEST_BY"
    e["liquidation_date"] = "2026-09-01"            # inside 80 days: plain Phase 1 for everyone
    assert decide(e, {"cit_plaintiff": True, "cit_ior_submitted_date": "2026-07-22"}, AS_OF).route == "CAPE_NOW"


def test_value_on_any_chapter99_line_blocks_cape():
    e = {"entry_number": "ABC-1234567-1", "entry_type": "01", "liquidation_status": "unliquidated",
         "lines": [{"hts": [{"code": "8714.91.5000", "entered_value": 1000, "duty": 0},
                            {"code": "9903.88.03", "entered_value": 1000, "duty": 250},
                            {"code": "9903.01.24", "duty": 100}]}]}
    d = decide(e, {}, AS_OF)
    assert d.route == "FIX_THEN_CAPE" and "value_on_ch99_line" in d.flags and not d.in_cape_csv
