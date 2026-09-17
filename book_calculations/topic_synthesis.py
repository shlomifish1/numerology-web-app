# -*- coding: utf-8 -*-
"""topic_synthesis — shared module for the central-interpretation (synthesis) layer
and the map-recommendation engine.

Design contract (PRECISION_MASTER_PLAN + approved plan 2026-07-13):
- The "restaurant model" iron rule stands: source variants in the book catalogs are
  NEVER modified here. Synthesis lives in a separate store file that
  build_research_menu_live.py merges (read-only) into the generated RESEARCH_MENU.
- The store is owned exclusively by the web endpoints (single-writer via _STORE_LOCK);
  the build only READS it and computes staleness into the generated menu.
- Client-facing gate: only entries with status == "approved" (Shlomi's manual click)
  may flow into client maps/exports. "published_auto" is lab-internal, always badged.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import unicodedata
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
NRG_ROOT = SCRIPT_DIR.parent
SYNTHESIS_DIR = NRG_ROOT / "interpretations" / "synthesis"
STORE_PATH = SYNTHESIS_DIR / "synthesis_store.json"

_STORE_LOCK = threading.Lock()

# Recommendation scoring weights — cross-book prevalence is the strongest signal
# per Shlomi's spec ("מופיע בממוצע אצל רוב הספרים").
RECO_WEIGHTS = {
    "prevalence": 45.0,            # n_books / total_books
    "computable_for_client": 20.0,  # this client's subject map computed a matching calc
    "has_verified_formula": 15.0,
    "has_synthesis": 10.0,          # approved/published, non-stale
    "richness": 10.0,               # min(n_interpretations_total, 30) / 30
}


def _lp(p) -> str:
    ap = os.path.abspath(str(p))
    if os.name == "nt" and not ap.startswith("\\\\?\\"):
        return "\\\\?\\" + ap
    return ap


# ---------------------------------------------------------------------------
# Store IO
# ---------------------------------------------------------------------------

def _empty_store() -> dict:
    return {"version": 1, "topics": {}}


def load_store() -> dict:
    """Read the synthesis store (returns an empty skeleton if missing/corrupt)."""
    try:
        with open(_lp(STORE_PATH), encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and isinstance(data.get("topics"), dict):
            return data
    except FileNotFoundError:
        pass
    except Exception:
        # corrupt store must never break the build; endpoints will surface it
        pass
    return _empty_store()


def save_store(store: dict) -> None:
    """Atomic-ish store write with a one-time backup (same conventions as the
    catalog writers: .bak_* once, ensure_ascii=False, indent=1). Callers must
    hold store_lock() around read-modify-write cycles."""
    SYNTHESIS_DIR.mkdir(parents=True, exist_ok=True)
    bak = str(STORE_PATH) + ".bak_synth"
    if os.path.exists(_lp(STORE_PATH)) and not os.path.exists(_lp(bak)):
        import shutil
        shutil.copy2(_lp(STORE_PATH), _lp(bak))
    tmp = str(STORE_PATH) + ".tmp"
    with open(_lp(tmp), "w", encoding="utf-8") as fh:
        json.dump(store, fh, ensure_ascii=False, indent=1)
    os.replace(_lp(tmp), _lp(STORE_PATH))


def store_lock() -> threading.Lock:
    return _STORE_LOCK


# ---------------------------------------------------------------------------
# Source collection + hashing (shared by build merge and synthesis endpoint)
# ---------------------------------------------------------------------------

def _norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def collect_topic_sources(topic_rec: dict) -> dict:
    """From a RESEARCH_MENU topic record, gather per-value source texts.

    Returns {value: [{"book", "calc_key", "text"}]}. Only values backed by at
    least one non-empty text. interpretations_by_value entries may be a dict or
    a list of dicts (menu normalises to lists of {text, ...})."""
    out: dict[str, list[dict]] = {}
    for v in topic_rec.get("variants") or []:
        book = v.get("book") or ""
        calc_key = v.get("calc_key") or ""
        ibv = v.get("interpretations_by_value") or {}
        if not isinstance(ibv, dict):
            continue
        for value, payload in ibv.items():
            entries = payload if isinstance(payload, list) else [payload]
            for e in entries:
                text = ""
                if isinstance(e, dict):
                    text = _norm_ws(e.get("text_he") or e.get("text") or "")
                elif isinstance(e, str):
                    text = _norm_ws(e)
                if text:
                    out.setdefault(str(value), []).append(
                        {"book": book, "calc_key": calc_key, "text": text}
                    )
    return out


def sources_hash(topic_rec: dict) -> str:
    """Stable sha256 over the topic's interpretation source texts (whitespace-
    normalised so formatting-only catalog edits don't flag staleness)."""
    sources = collect_topic_sources(topic_rec)
    canonical = [
        (value, sorted((s["book"], s["calc_key"], s["text"]) for s in items))
        for value, items in sorted(sources.items())
    ]
    blob = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Copyright n-gram check
# ---------------------------------------------------------------------------

def _norm_tokens(text: str) -> list:
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = re.sub("[֑-ׇ]", "", text)          # niqqud + teamim
    text = re.sub("[^\\w֐-׿]+", " ", text)    # punctuation -> space
    return text.split()


def ngram_check(synth_text: str, source_texts: list, n: int = 8) -> dict:
    """Word-level overlap check: fail if any run of >= n consecutive words in the
    synthesized text appears verbatim in any source. Hebrew-safe (niqqud and
    punctuation stripped; prefixes travel with copied words so token-level works).

    Returns {passed, n, violations[:10], longest_shared_run}."""
    src = set()
    for s in source_texts:
        t = _norm_tokens(s)
        src.update(tuple(t[i:i + n]) for i in range(len(t) - n + 1))
    t = _norm_tokens(synth_text)
    violations = [
        " ".join(t[i:i + n])
        for i in range(len(t) - n + 1)
        if tuple(t[i:i + n]) in src
    ]
    longest = n if violations else 0
    if not violations:
        # report the longest shared run below the threshold (for transparency)
        for k in range(n - 1, 3, -1):
            srck = set()
            for s in source_texts:
                ts = _norm_tokens(s)
                srck.update(tuple(ts[i:i + k]) for i in range(len(ts) - k + 1))
            if any(tuple(t[i:i + k]) in srck for i in range(len(t) - k + 1)):
                longest = k
                break
    return {
        "passed": not violations,
        "n": n,
        "violations": violations[:10],
        "longest_shared_run": longest,
    }


# ---------------------------------------------------------------------------
# Synthesis prompting (pure text helpers — the model call itself lives in
# web_server so this module stays importable without the AI stack)
# ---------------------------------------------------------------------------

SYNTH_MARKER_CENTRAL = "פרשנות מרכזית:"
SYNTH_MARKER_DIFFS = "הבדלים בין הספרים:"


def build_synthesis_prompt(topic: str, value: str, sources: list, forbidden_phrases: list | None = None) -> tuple:
    """(system, user) prompts for synthesizing ONE value of ONE topic from the
    per-book source quotes. Copyright rule baked in: never copy a run of more
    than 7 consecutive words (enforced afterwards by ngram_check)."""
    system = (
        "אתה עורך-תוכן נומרולוגי מקצועי. תפקידך: לקרוא את הפרשנויות של כמה ספרי נומרולוגיה לאותו "
        "נושא ולאותו ערך, ולכתוב פרשנות מרכזית אחת בעברית שמסנתזת את הליבה המשותפת — במילים שלך "
        "בלבד. חוקים מחייבים:\n"
        "1. אסור בהחלט להעתיק רצף של יותר מ-7 מילים עוקבות מאף מקור — נסח מחדש הכל.\n"
        "2. אל תמציא תוכן שלא נמצא במקורות; רק סנתז את מה שקיים.\n"
        "3. כתוב בגוף שני (\"אתם\"/\"אתה\") בסגנון חם ומקצועי, כמו במפה נומרולוגית ללקוח.\n"
        "4. אם יש מחלוקת אמיתית בין ספרים — אל תטשטש אותה; תאר אותה בסעיף ההבדלים עם שם הספר.\n"
        "5. פורמט הפלט (בדיוק, בלי תוספות):\n"
        f"{SYNTH_MARKER_CENTRAL}\n<הפרשנות המסונתזת, 2-5 פסקאות קצרות>\n\n"
        f"{SYNTH_MARKER_DIFFS}\n<הבדלים משמעותיים בין הספרים, עם שמות; אם אין — כתוב \"אין הבדלים מהותיים\">"
    )
    if forbidden_phrases:
        system += (
            "\n6. בניסיון קודם הועתקו הצירופים הבאים — אסור להשתמש בהם או בנוסח קרוב להם:\n"
            + "\n".join(f"- \"{p}\"" for p in forbidden_phrases[:8])
        )
    lines = [f"נושא: {topic}", f"ערך: {value}", "", "הפרשנויות מהספרים:"]
    for s in sources:
        lines.append(f"\n--- ספר: {s['book']} ---\n{s['text']}")
    return system, "\n".join(lines)


def parse_synthesis_output(text: str) -> dict:
    """Split the model output by the plain-text markers. Whole-text fallback into
    central_he (avoids JSON-escaping failures with Hebrew output)."""
    text = str(text or "").strip()
    # strip the ai_manager model-signature footer if present ("_🤖 ..._")
    text = re.sub(r"\n*_🤖[^\n]*_\s*$", "", text).strip()
    central, diffs = text, ""
    if SYNTH_MARKER_CENTRAL in text:
        after = text.split(SYNTH_MARKER_CENTRAL, 1)[1]
        if SYNTH_MARKER_DIFFS in after:
            central, diffs = after.split(SYNTH_MARKER_DIFFS, 1)
        else:
            central = after
    return {"central_he": central.strip(), "differences_he": diffs.strip()}


# ---------------------------------------------------------------------------
# Menu merge + recommendation index (called from build_research_menu_live.py)
# ---------------------------------------------------------------------------

CLIENT_ELIGIBLE_STATUSES = ("approved",)          # what may reach client maps
LAB_VISIBLE_STATUSES = ("approved", "published_auto", "draft")


def merge_synthesis_into_menu(menu: list) -> dict:
    """Attach central_interpretation (+stale flag) to topic records in-place.
    Read-only wrt the store. Returns {"orphans": [...]} — store topics whose
    canonical name no longer exists in the menu."""
    store = load_store()
    topics_by_name = {rec.get("topic"): rec for rec in menu}
    orphans = []
    for topic_name, entry in (store.get("topics") or {}).items():
        rec = topics_by_name.get(topic_name)
        if rec is None:
            orphans.append(topic_name)
            continue
        current_hash = sources_hash(rec)
        stale = bool(entry.get("sources_hash")) and entry["sources_hash"] != current_hash
        status = entry.get("status") or "draft"
        rec["central_interpretation"] = {
            "status": status,
            "mode": entry.get("mode"),
            "model_key": entry.get("model_key"),
            "created_at": entry.get("created_at"),
            "approved_at": entry.get("approved_at"),
            "stale": stale,
            "values": entry.get("values") or {},
        }
        rec["has_synthesis"] = (status in ("approved", "published_auto")) and not stale
    return {"orphans": orphans}


def _load_internal_definition_calc_keys() -> set:
    """calc_keys the internal calculator (ספר השלם) can actually run per-client."""
    definition_path = SCRIPT_DIR / "sefer_hanumerologia_hashalem.definition.json"
    try:
        definition = json.loads(definition_path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    return {
        str(c.get("calc_key"))
        for c in definition.get("calculations", [])
        if c.get("calc_key")
    }


INTERNAL_BOOK_NAME = "ספר הנומרולוגיה השלם"


def build_recommendation_index(menu: list, total_books: int) -> dict:
    """Derive the static per-topic recommendation signals from the menu.
    Regenerated on every build — no persistence of its own."""
    internal_keys = _load_internal_definition_calc_keys()
    topics = []
    for rec in menu:
        topic = rec.get("topic") or ""
        if topic.startswith("לא-ממופה"):
            continue
        variants = rec.get("variants") or []
        has_verified_formula = False
        topic_internal_keys = []
        page_images: list = []
        seen_images = set()
        for v in variants:
            verdict = ((v.get("human_formula_triage") or {}).get("verdict")
                       or (v.get("formula_triage") or {}).get("verdict") or "")
            if verdict == "formula" or (v.get("formula_example") and v.get("formula_audit")):
                has_verified_formula = True
            if v.get("book") == INTERNAL_BOOK_NAME and v.get("calc_key") in internal_keys:
                topic_internal_keys.append(v.get("calc_key"))
            if len(page_images) < 4:
                for img in (v.get("page_images") or []):
                    if img and img not in seen_images:
                        seen_images.add(img)
                        page_images.append({"book": v.get("book"), "path": img})
                        if len(page_images) >= 4:
                            break
        central = rec.get("central_interpretation") or {}
        topics.append({
            "topic": topic,
            "n_books": rec.get("n_books") or 0,
            "books": rec.get("books") or [],
            "prevalence": round((rec.get("n_books") or 0) / max(total_books, 1), 4),
            "has_verified_formula": has_verified_formula,
            "internal_calc_keys": sorted(set(topic_internal_keys)),
            "computable_via_internal": bool(topic_internal_keys),
            "has_synthesis": bool(rec.get("has_synthesis")),
            "synthesis_status": central.get("status"),
            "n_interpretations_total": rec.get("n_interpretations_total") or 0,
            "page_images": page_images,
        })
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total_books": total_books,
        "n_topics": len(topics),
        "topics": topics,
    }


# ---------------------------------------------------------------------------
# Recommendation scoring (called from the endpoint)
# ---------------------------------------------------------------------------

def score_topic(index_entry: dict, computable_for_client: bool) -> float:
    w = RECO_WEIGHTS
    richness = min(index_entry.get("n_interpretations_total") or 0, 30) / 30.0
    score = (
        w["prevalence"] * (index_entry.get("prevalence") or 0.0)
        + w["computable_for_client"] * (1.0 if computable_for_client else 0.0)
        + w["has_verified_formula"] * (1.0 if index_entry.get("has_verified_formula") else 0.0)
        + w["has_synthesis"] * (1.0 if index_entry.get("has_synthesis") else 0.0)
        + w["richness"] * richness
    )
    return round(score, 2)


def build_reasons(index_entry: dict, computed: dict | None) -> list:
    """Rule-based Hebrew reasons — always available, never blocks on AI."""
    reasons = []
    n_books = index_entry.get("n_books") or 0
    if n_books > 1:
        reasons.append(f"מופיע ב-{n_books} מתוך {index_entry.get('_total_books', 10)} ספרים")
    if computed and computed.get("value"):
        val = str(computed["value"])
        if len(val) <= 20:
            reasons.append(f"ניתן לחישוב מנתוני הלקוח (ערך: {val})")
        else:
            reasons.append("ניתן לחישוב מנתוני הלקוח (תוצאה מורכבת)")
    elif computed and computed.get("value_complex") is not None:
        # composite values (e.g. missing-numbers dicts) — don't dump the blob into a chip
        reasons.append("ניתן לחישוב מנתוני הלקוח (תוצאה מורכבת)")
    elif index_entry.get("computable_via_internal"):
        reasons.append("ניתן לחישוב אוטומטי (ספר הנומרולוגיה השלם)")
    if index_entry.get("has_verified_formula"):
        reasons.append("נוסחה מאומתת מול הספר")
    if index_entry.get("has_synthesis") and index_entry.get("synthesis_status") == "approved":
        reasons.append("יש פרשנות מרכזית מאושרת")
    n_interp = index_entry.get("n_interpretations_total") or 0
    if n_interp >= 10:
        reasons.append(f"{n_interp} פרשנויות-פר-ערך במחקר")
    return reasons
