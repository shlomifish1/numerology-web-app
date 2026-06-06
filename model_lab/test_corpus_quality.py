"""
Minimal self-contained tests for corpus_quality.
No external deps. No model/API/OCR calls. Run with: py -3.12 test_corpus_quality.py

All file-writing tests use a temporary directory only — never a production
path. Source corpora are tiny throwaway text strings/files.
"""

import os
import shutil
import sys
import tempfile

from corpus_quality import (
    BLANK_LINE_RATIO_WARN_THRESHOLD,
    DUPLICATE_LINE_RATIO_WARN_THRESHOLD,
    LOW_QUALITY_CHARS_THRESHOLD,
    LOW_QUALITY_HEBREW_RATIO,
    NOISE_RATIO_WARN_THRESHOLD,
    analyze_corpus_text,
    analyze_source_corpus_file,
    load_corpus_quality_report,
    save_corpus_quality_report,
)

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
_results: list[bool] = []

HEBREW_SENTENCE = "שלום עולם זה טקסט בדיקה תקין בעברית לצורך ניתוח איכות הקורפוס "


def check(name: str, condition: bool) -> None:
    _results.append(condition)
    print(f"  {'OK' if condition else 'FAIL'} {name}")
    if not condition:
        print("       ^ unexpected result", file=sys.stderr)


def _write_corpus(dir_path: str, name: str, text: str) -> str:
    path = os.path.join(dir_path, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


# ── Test 1: empty corpus fails with corpus_empty ────────────────────────────
print("\n[1] Empty corpus fails with corpus_empty:")
report = analyze_corpus_text("")
check("status is fail", report["status"] == "fail")
check("issues contains corpus_empty", "corpus_empty" in report["issues"])
check("total_chars is 0", report["total_chars"] == 0)
check("ratios are 0.0 (no division by zero)", report["estimated_hebrew_ratio"] == 0.0
      and report["whitespace_ratio"] == 0.0 and report["noise_ratio"] == 0.0)


# ── Test 2: short corpus under threshold fails (conservative rule) ──────────
print("\n[2] Short corpus under LOW_QUALITY_CHARS_THRESHOLD fails (conservative):")
short_text = (HEBREW_SENTENCE * 3)[:LOW_QUALITY_CHARS_THRESHOLD - 1]
check("short text really is below the threshold", len(short_text) < LOW_QUALITY_CHARS_THRESHOLD)
report = analyze_corpus_text(short_text)
check("status is fail", report["status"] == "fail")
check("issues contains corpus_too_short", "corpus_too_short" in report["issues"])


# ── Test 3: valid Hebrew corpus passes ───────────────────────────────────────
print("\n[3] Valid Hebrew corpus (long enough, high Hebrew ratio) passes:")
valid_text = HEBREW_SENTENCE * 30
check("valid text is long enough", len(valid_text) >= LOW_QUALITY_CHARS_THRESHOLD)
report = analyze_corpus_text(valid_text, source_id="abc123", book_id="misparei_bayit")
check("status is pass", report["status"] == "pass")
check("no issues reported", report["issues"] == [])
check("hebrew ratio above threshold", report["estimated_hebrew_ratio"] >= LOW_QUALITY_HEBREW_RATIO)
check("book_id passed through", report["book_id"] == "misparei_bayit")
check("source_id passed through", report["source_id"] == "abc123")


# ── Test 4: low Hebrew ratio fails ───────────────────────────────────────────
print("\n[4] Low Hebrew ratio fails:")
english_text = "the quick brown fox jumps over the lazy dog. " * 30
check("english text is long enough to skip the short-corpus rule", len(english_text) >= LOW_QUALITY_CHARS_THRESHOLD)
report = analyze_corpus_text(english_text)
check("status is fail", report["status"] == "fail")
check("issues contains low_hebrew_ratio", "low_hebrew_ratio" in report["issues"])
check("hebrew ratio below threshold", report["estimated_hebrew_ratio"] < LOW_QUALITY_HEBREW_RATIO)


# ── Test 5: blank-line-heavy corpus warns ───────────────────────────────────
print("\n[5] Blank-line-heavy corpus triggers a warning:")
blank_heavy_lines = []
for i in range(40):
    blank_heavy_lines.append(f"{HEBREW_SENTENCE}{i}")
    blank_heavy_lines.append("")
    blank_heavy_lines.append("")
    blank_heavy_lines.append("")
blank_heavy_text = "\n".join(blank_heavy_lines)
check("blank-heavy text is long enough", len(blank_heavy_text) >= LOW_QUALITY_CHARS_THRESHOLD)
report = analyze_corpus_text(blank_heavy_text)
check("blank_line_ratio is above the warn threshold", report["blank_line_ratio"] >= BLANK_LINE_RATIO_WARN_THRESHOLD)
check("status is warn", report["status"] == "warn")
check("warnings contains high_blank_line_ratio", "high_blank_line_ratio" in report["warnings"])
check("no fail-level issues reported", report["issues"] == [])


# ── Test 6: duplicate-line-heavy corpus warns ───────────────────────────────
print("\n[6] Duplicate-line-heavy corpus triggers a warning:")
dup_lines = []
for i in range(60):
    dup_lines.append(HEBREW_SENTENCE)
    if i % 4 == 0:
        dup_lines.append(f"{HEBREW_SENTENCE}שורה ייחודית מספר {i}")
dup_text = "\n".join(dup_lines)
check("duplicate-heavy text is long enough", len(dup_text) >= LOW_QUALITY_CHARS_THRESHOLD)
report = analyze_corpus_text(dup_text)
check("duplicate_line_ratio is above the warn threshold", report["duplicate_line_ratio"] >= DUPLICATE_LINE_RATIO_WARN_THRESHOLD)
check("status is warn", report["status"] == "warn")
check("warnings contains high_duplicate_line_ratio", "high_duplicate_line_ratio" in report["warnings"])
check("no fail-level issues reported", report["issues"] == [])


# ── Test 7: suspicious/noisy characters trigger warning or failure ──────────
print("\n[7] Suspicious/noisy characters trigger a warning or failure (threshold-based):")
clean_text = HEBREW_SENTENCE * 30
noisy_warn_text = clean_text[:400] + ("\x01\x02\x1f" * 25) + clean_text[400:]
report_warn = analyze_corpus_text(noisy_warn_text)
check("mildly noisy text: noise_ratio above warn threshold", report_warn["noise_ratio"] >= NOISE_RATIO_WARN_THRESHOLD)
check("mildly noisy text: status is warn or fail", report_warn["status"] in ("warn", "fail"))
check("mildly noisy text: noise reflected in warnings or issues", (
    "elevated_noise_ratio" in report_warn["warnings"] or "high_noise_ratio" in report_warn["issues"]
))

very_noisy_text = "\x01\x02\x03\x04\x05\x06\x1f�" * 200 + clean_text
report_fail = analyze_corpus_text(very_noisy_text)
check("very noisy text: status is fail", report_fail["status"] == "fail")
check("very noisy text: issues contains high_noise_ratio", "high_noise_ratio" in report_fail["issues"])


# ── Test 8: analyze_source_corpus_file reads UTF-8 text ─────────────────────
print("\n[8] analyze_source_corpus_file reads an existing UTF-8 corpus file:")
tmp_dir = tempfile.mkdtemp(prefix="corpus_quality_file_test_")
try:
    corpus_path = _write_corpus(tmp_dir, "source_corpus.txt", HEBREW_SENTENCE * 30)
    before_mtime = os.path.getmtime(corpus_path)
    before_content = open(corpus_path, "r", encoding="utf-8").read()

    report = analyze_source_corpus_file(corpus_path, source_id="src-1", book_id="misparei_bayit")
    check("status is pass for the valid corpus file", report["status"] == "pass")
    check("source_id passed through", report["source_id"] == "src-1")
    check("book_id passed through", report["book_id"] == "misparei_bayit")

    after_content = open(corpus_path, "r", encoding="utf-8").read()
    check("source corpus file content unchanged", before_content == after_content)
    check("source corpus file mtime unchanged (read-only)", before_mtime == os.path.getmtime(corpus_path))
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 9: save/load report roundtrip ───────────────────────────────────────
print("\n[9] save_corpus_quality_report / load_corpus_quality_report roundtrip:")
tmp_dir = tempfile.mkdtemp(prefix="corpus_quality_roundtrip_test_")
try:
    report = analyze_corpus_text(HEBREW_SENTENCE * 30, source_id="src-2", book_id="misparei_bayit")
    report_path = os.path.join(tmp_dir, "analysis", "corpus_quality_report.json")

    save_corpus_quality_report(report, report_path)
    check("save_corpus_quality_report wrote the file", os.path.isfile(report_path))
    check("save_corpus_quality_report created the parent dir", os.path.isdir(os.path.dirname(report_path)))

    loaded = load_corpus_quality_report(report_path)
    check("loaded report equals the original report", loaded == report)
    check("loaded report is a plain dict", isinstance(loaded, dict))

    try:
        save_corpus_quality_report(report, "")
        check("save_corpus_quality_report rejects an empty path", False)
    except ValueError:
        check("save_corpus_quality_report rejects an empty path", True)
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 10: no production path is required or hardcoded ────────────────────
print("\n[10] No production path is required or hardcoded:")
import corpus_quality as _cq_module
import inspect as _inspect
_source = _inspect.getsource(_cq_module)
check("module source has no hardcoded book_jobs path literal", not any(
    token in _source for token in ("\\book_jobs\\", "/book_jobs/", '"book_jobs"', "'book_jobs'")
))
check("module source has no 'web_server' reference", "web_server" not in _source)
check("module source has no drive-letter production path literal", not any(
    token in _source for token in ("C:\\\\", "D:\\\\", "/var/", "/srv/")
))
tmp_dir = tempfile.mkdtemp(prefix="corpus_quality_no_prod_path_test_")
try:
    report = analyze_corpus_text(HEBREW_SENTENCE * 30)
    report_path = os.path.join(tmp_dir, "corpus_quality_report.json")
    save_corpus_quality_report(report, report_path)
    check("report written only under the explicit temp path given", os.path.isfile(report_path))
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Summary ──────────────────────────────────────────────────────────────────
total = len(_results)
passed = sum(_results)
failed = total - passed
print(f"\n{'='*50}")
print(f"תוצאות: {passed}/{total} בדיקות עברו" + (f" | {failed} נכשלו" if failed else ""))
sys.exit(0 if failed == 0 else 1)
