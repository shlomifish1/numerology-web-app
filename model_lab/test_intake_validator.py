"""
Minimal self-contained tests for intake_validator.validate().
No external deps. Run with: py -3.12 test_intake_validator.py
"""

import sys
from intake_validator import validate

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
_results: list[bool] = []


def check(name: str, condition: bool) -> None:
    _results.append(condition)
    print(f"  {'OK' if condition else 'FAIL'} {name}")
    if not condition:
        print(f"       ^ unexpected result", file=sys.stderr)


def _base_profile(**overrides) -> dict:
    """Minimal valid draft profile."""
    p = {
        "$schema_version": "intake/1.0",
        "book_id": "misparei_bayit",
        "book_title": "מספרי בית",
        "intake_status": "draft",
        "intake_generated_at": "2026-05-30T10:00:00Z",
        "intake_generated_by": "local/gemma4:26b",
        "corpus_source": "interpretations/drive_primary_books/מספרי בית/artifacts/chapters/misparei_bayit/מספרי_בית__source_corpus.txt",
        "corpus_quality": {
            "total_chars": 12000,
            "extraction_method": "fitz-native-full",
            "estimated_hebrew_ratio": 0.82,
            "quality_verdict": "good",
            "quality_notes": [],
        },
        "safety_flags": {
            "corpus_empty": False,
            "corpus_low_quality": False,
            "model_hallucination_risk": False,
            "manual_review_required": True,
            "blocked_from_definition_write": False,
            "blocked_from_runtime_promote": True,
        },
    }
    p.update(overrides)
    return p


# ── Test 1: valid minimal profile ───────────────────────────────────────────
print("\n[1] Profile תקין מינימלי:")
r = validate(_base_profile())
check("ok=True", r.ok)
check("no errors", len(r.errors) == 0)


# ── Test 2: intake_status not draft ─────────────────────────────────────────
print("\n[2] intake_status='approved' (אסור בפלט מודל — S1):")
r = validate(_base_profile(intake_status="approved"))
check("ok=False", not r.ok)
check("error about intake_status", any("intake_status" in e for e in r.errors))


# ── Test 3: manual_review_required=False ────────────────────────────────────
print("\n[3] safety_flags.manual_review_required=False (אסור תמיד — S4):")
flags = {**_base_profile()["safety_flags"], "manual_review_required": False}
r = validate(_base_profile(safety_flags=flags))
check("ok=False", not r.ok)
check("error about manual_review_required", any("manual_review_required" in e for e in r.errors))


# ── Test 4: blocked_from_runtime_promote=False ───────────────────────────────
print("\n[4] safety_flags.blocked_from_runtime_promote=False (אסור בפלט מודל — S5):")
flags = {**_base_profile()["safety_flags"], "blocked_from_runtime_promote": False}
r = validate(_base_profile(safety_flags=flags))
check("ok=False", not r.ok)
check("error about blocked_from_runtime_promote", any("blocked_from_runtime_promote" in e for e in r.errors))


# ── Test 5: empty corpus → corpus_empty flag required ───────────────────────
print("\n[5] total_chars=0 אך corpus_empty=False (S6):")
cq = {**_base_profile()["corpus_quality"], "total_chars": 0}
flags = {**_base_profile()["safety_flags"], "corpus_empty": False}
r = validate(_base_profile(corpus_quality=cq, safety_flags=flags))
check("ok=False", not r.ok)
check("error about corpus_empty", any("corpus_empty" in e for e in r.errors))


# ── Test 6: low char count → corpus_low_quality required ────────────────────
print("\n[6] total_chars=200 אך corpus_low_quality=False (S6):")
cq = {**_base_profile()["corpus_quality"], "total_chars": 200}
flags = {**_base_profile()["safety_flags"], "corpus_low_quality": False}
r = validate(_base_profile(corpus_quality=cq, safety_flags=flags))
check("ok=False", not r.ok)
check("error about corpus_low_quality", any("corpus_low_quality" in e for e in r.errors))


# ── Test 7: ocr_pending → corpus_low_quality required ───────────────────────
print("\n[7] extraction_method='ocr_pending' אך corpus_low_quality=False (S6):")
cq = {**_base_profile()["corpus_quality"], "extraction_method": "ocr_pending"}
flags = {**_base_profile()["safety_flags"], "corpus_low_quality": False}
r = validate(_base_profile(corpus_quality=cq, safety_flags=flags))
check("ok=False", not r.ok)
check("error about corpus_low_quality", any("corpus_low_quality" in e for e in r.errors))


# ── Test 8: low hebrew ratio → corpus_low_quality required ──────────────────
print("\n[8] estimated_hebrew_ratio=0.05 אך corpus_low_quality=False (S6):")
cq = {**_base_profile()["corpus_quality"], "estimated_hebrew_ratio": 0.05}
flags = {**_base_profile()["safety_flags"], "corpus_low_quality": False}
r = validate(_base_profile(corpus_quality=cq, safety_flags=flags))
check("ok=False", not r.ok)
check("error about corpus_low_quality", any("corpus_low_quality" in e for e in r.errors))


# ── Test 9: blocked corpus → blocked_from_definition_write required ──────────
print("\n[9] corpus_low_quality=True אך blocked_from_definition_write=False (S6):")
cq = {**_base_profile()["corpus_quality"], "total_chars": 200}
flags = {
    **_base_profile()["safety_flags"],
    "corpus_low_quality": True,
    "blocked_from_definition_write": False,
}
r = validate(_base_profile(corpus_quality=cq, safety_flags=flags))
check("ok=False", not r.ok)
check("error about blocked_from_definition_write", any("blocked_from_definition_write" in e for e in r.errors))


# ── Test 10: suggested_definition_updates missing safety fields ──────────────
print("\n[10] suggested_definition_updates חסרים model_draft_only / requires_human_approval (S3/S4):")
updates = [{"calc_key": "house_number_basic", "field": "interpretations_by_value",
            "suggested_value": {}, "confidence": 0.8,
            "model_draft_only": False, "requires_human_approval": False}]
r = validate(_base_profile(suggested_definition_updates=updates))
check("ok=False", not r.ok)
check("error about model_draft_only", any("model_draft_only" in e for e in r.errors))
check("error about requires_human_approval", any("requires_human_approval" in e for e in r.errors))


# ── Test 11: valid profile with suggested_definition_updates ─────────────────
print("\n[11] Profile תקין עם suggested_definition_updates נכון:")
updates = [{"calc_key": "house_number_basic", "field": "interpretations_by_value",
            "suggested_value": {"1": "...", "2": "..."}, "confidence": 0.75,
            "model_draft_only": True, "requires_human_approval": True}]
r = validate(_base_profile(suggested_definition_updates=updates))
check("ok=True", r.ok)
check("no errors", len(r.errors) == 0)


# ── Test 12: missing top-level fields ────────────────────────────────────────
print("\n[12] חסרים שדות ברמה העליונה:")
minimal = {"book_id": "test"}
r = validate(minimal)
check("ok=False", not r.ok)
check("multiple top-level errors", len(r.errors) >= 5)


# ── Summary ──────────────────────────────────────────────────────────────────
total = len(_results)
passed = sum(_results)
failed = total - passed
print(f"\n{'='*50}")
print(f"תוצאות: {passed}/{total} בדיקות עברו" + (f" | {failed} נכשלו" if failed else ""))
sys.exit(0 if failed == 0 else 1)
