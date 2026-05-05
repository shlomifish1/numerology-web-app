"""Shared Streamlit UI for internal research mode."""

from __future__ import annotations

import json
import os
from typing import Dict, Optional

import streamlit as st

from book_ingestion.catalog_sync import refresh_all
from research import ComparisonEngine
from research.stale_cleanup import cleanup_stale_research_state


PASSWORD_ENV_KEYS = ("RESEARCH_PASSWORD", "NUMEROLOGY_RESEARCH_PASSWORD")
DEFAULT_PASSWORD = "innerbalance-research"


def _key(prefix: str, suffix: str) -> str:
    return f"{prefix}_{suffix}"


def _get_expected_password() -> str:
    for key in PASSWORD_ENV_KEYS:
        value = os.getenv(key)
        if value:
            return value
    return DEFAULT_PASSWORD


def _parse_hebrew_birthdate(raw_value: str) -> Optional[Dict[str, int]]:
    raw_value = raw_value.strip()
    if not raw_value:
        return None
    parts = [part.strip() for part in raw_value.replace("/", "-").split("-")]
    if len(parts) != 3:
        raise ValueError("פורמט תאריך עברי צריך להיות יום-חודש-שנה")
    day, month, year = (int(part) for part in parts)
    return {"day": day, "month": month, "year": year}


def _gender_label(value: str) -> str:
    return "נקבה" if value == "female" else "זכר"


def _visible_methods(methods):
    return [
        method
        for method in methods
        if method.get("visible_in_research_ui", True) and not method.get("internal_only")
    ]


def _save_approvals(engine: ComparisonEngine, methods, prefix: str) -> None:
    changed = False
    for method in methods:
        state_key = _key(prefix, f"approve__{method['key']}")
        enabled = bool(st.session_state.get(state_key, method["enabled_for_customers"]))
        if enabled != bool(method["enabled_for_customers"]):
            engine.registry.set_customer_enabled(method["key"], enabled)
            engine.approval_store.set_customer_enabled(method["key"], enabled)
            changed = True
    if changed:
        st.success("האישורים נשמרו.")
    else:
        st.info("לא היה שינוי באישורים.")


def _render_method_controls(engine: ComparisonEngine, methods, prefix: str) -> None:
    st.subheader("ניהול אישורים")
    st.caption("הפעל או השבת שיטות עבור הלקוח. כברירת מחדל כל שיטה חדשה נשארת במחקר בלבד.")
    with st.form(_key(prefix, "approval_form")):
        for method in methods:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{method['display_name']}**")
                st.caption(method["result"]["summary"])
            with col2:
                st.checkbox(
                    "מאושר",
                    value=bool(method["enabled_for_customers"]),
                    key=_key(prefix, f"approve__{method['key']}"),
                )
        submitted = st.form_submit_button("שמור אישורים", use_container_width=True)
    if submitted:
        _save_approvals(engine, methods, prefix)
        st.rerun()


def _render_category_summary(items) -> None:
    if not items:
        return
    st.markdown("**קטגוריות מובילות**")
    st.table({
        "קטגוריה": [item.get("label", item.get("key", "-")) for item in items],
        "כמות": [item.get("count", "-") for item in items],
    })


def _render_ocr_queue(items) -> None:
    if not items:
        return
    st.markdown("**תור OCR**")
    st.table({
        "כותרת": [item.get("title", "-") for item in items],
        "סטטוס": [item.get("status", "-") for item in items],
        "ציון": [item.get("score", "-") for item in items],
    })


def _render_ocr_runtime(runtime: Dict[str, object]) -> None:
    if not runtime:
        return
    st.markdown("**מצב OCR**")
    st.caption(runtime.get("recommended_action", "-"))
    caps = runtime.get("capabilities", {})
    cols = st.columns(4)
    cols[0].metric("OCR מלא", "כן" if runtime.get("ready_for_full_ocr") else "לא")
    cols[1].metric("חילוץ טקסט", "כן" if runtime.get("ready_for_text_extraction") else "לא")
    cols[2].metric("Tesseract", "כן" if caps.get("tesseract_available") else "לא")
    cols[3].metric("fitz", "כן" if caps.get("fitz_available") else "לא")


def _render_seed_books(items) -> None:
    if not items:
        return
    st.markdown("**ספרי seed מומלצים**")
    for item in items:
        st.caption(f"- {item}")


def _render_taxonomy(items) -> None:
    if not items:
        return
    st.markdown("**Taxonomy**")
    st.caption(" | ".join(str(item) for item in items))


def _render_method_details(method: Dict[str, object], prefix: str) -> None:
    details = method["result"]["details"]
    overview_tab, raw_tab = st.tabs(["סקירה", "Raw JSON"])
    with overview_tab:
        st.write(method["result"]["summary"])
        _render_category_summary(details.get("category_summary", []))
        _render_ocr_queue(details.get("ocr_queue_top5", []))
        _render_ocr_runtime(details.get("ocr_runtime", {}))
        _render_taxonomy(details.get("taxonomy", []))
        _render_seed_books(details.get("recommended_seed_books", []))
        if details.get("recommendations"):
            st.markdown("**המלצות**")
            for item in details["recommendations"]:
                st.caption(f"- {item}")
    with raw_tab:
        st.json(json.loads(json.dumps(details, ensure_ascii=False)))


def _render_comparison(result: Dict[str, object], prefix: str) -> None:
    methods = result["methods"]
    approved_count = sum(1 for method in methods if method["enabled_for_customers"])
    st.subheader("השוואת שיטות")
    summary_cols = st.columns(4)
    summary_cols[0].metric("שיטות למחקר", len(methods))
    summary_cols[1].metric("שיטות מאושרות", approved_count)
    summary_cols[2].metric("שורות השוואה", len(result["rows"]))
    summary_cols[3].metric("קלט עברי", "כן" if result["inputs"]["hebrew_birthdate"] else "לא")

    comparison_table = {"מדד": [row["label"] for row in result["rows"]]}
    for method in methods:
        comparison_table[method["display_name"]] = [row["values"][method["key"]] for row in result["rows"]]
    st.table(comparison_table)

    st.subheader("פרטי שיטות")
    for method in methods:
        with st.expander(method["display_name"], expanded=False):
            status = "מאושר ללקוח" if method["enabled_for_customers"] else "מחקר בלבד"
            st.write(f"סטטוס: {status}")
            _render_method_details(method, prefix)


def render_research_panel(*, prefix: str = "research", embedded: bool = False, title: Optional[str] = None, caption: Optional[str] = None) -> None:
    auth_key = _key(prefix, "authed")
    result_key = _key(prefix, "last_result")
    input_key = _key(prefix, "last_inputs")
    refresh_key = _key(prefix, "last_refresh_summary")

    if title:
        st.title(title) if not embedded else st.subheader(title)
    if caption:
        st.caption(caption)

    if auth_key not in st.session_state:
        st.session_state[auth_key] = False

    if not st.session_state[auth_key]:
        password = st.text_input("סיסמת מחקר", type="password", key=_key(prefix, "password"))
        if st.button("כניסה", key=_key(prefix, "login")):
            if password == _get_expected_password():
                st.session_state[auth_key] = True
                st.rerun()
            st.error("סיסמה שגויה.")
        st.info("אפשר להגדיר סיסמה דרך משתנה סביבה `RESEARCH_PASSWORD`.")
        return

    cleanup_stale_research_state()
    engine = ComparisonEngine()
    methods_snapshot = _visible_methods(engine.registry.refresh())

    with st.sidebar if not embedded else st.container():
        st.header("קלט למחקר")
        first_name = st.text_input("שם פרטי", value=st.session_state.get(_key(prefix, "input_first_name"), "שרה"), key=_key(prefix, "input_first_name"))
        last_name = st.text_input("שם משפחה", value=st.session_state.get(_key(prefix, "input_last_name"), "כהן"), key=_key(prefix, "input_last_name"))
        day = st.number_input("יום", min_value=1, max_value=31, value=int(st.session_state.get(_key(prefix, "input_day"), 14)), key=_key(prefix, "input_day"))
        month = st.number_input("חודש", min_value=1, max_value=12, value=int(st.session_state.get(_key(prefix, "input_month"), 7)), key=_key(prefix, "input_month"))
        year = st.number_input("שנה", min_value=1900, max_value=2100, value=int(st.session_state.get(_key(prefix, "input_year"), 1991)), key=_key(prefix, "input_year"))
        gender = st.selectbox("מין", options=["female", "male"], index=0 if st.session_state.get(_key(prefix, "input_gender"), "female") == "female" else 1, format_func=_gender_label, key=_key(prefix, "input_gender"))
        hebrew_birthdate_raw = st.text_input("תאריך עברי (אופציונלי)", value=st.session_state.get(_key(prefix, "input_hebrew"), ""), placeholder="כגון 12-4-5751", key=_key(prefix, "input_hebrew"))
        run = st.button("הרץ השוואה", type="primary", use_container_width=True, key=_key(prefix, "run"))
        if st.button("רענן שיטות מזוהות", use_container_width=True, key=_key(prefix, "refresh_methods")):
            engine.registry.refresh()
            st.rerun()
        if st.button("רענן corpora ו-artifacts", use_container_width=True, key=_key(prefix, "refresh_all")):
            with st.spinner("מרענן קטלוגים, maps ו-reports..."):
                st.session_state[refresh_key] = refresh_all()
            st.rerun()
        if refresh_key in st.session_state:
            st.caption(f"refresh אחרון: {st.session_state[refresh_key]}")
        st.markdown("---")
        st.caption(f"שיטות מזוהות כרגע: {len(methods_snapshot)}")
        for method in methods_snapshot:
            status = "לקוח" if engine.approval_store.get_status(method["key"], bool(method.get("enabled_for_customers", False))) else "מחקר"
            st.caption(f"{method['display_name']} | {status} | {method['adapter']}")

    if run:
        try:
            hebrew_birthdate = _parse_hebrew_birthdate(hebrew_birthdate_raw)
        except ValueError as error:
            st.error(str(error))
            return
        result = engine.compare(
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            day=int(day),
            month=int(month),
            year=int(year),
            gender=gender,
            hebrew_birthdate=hebrew_birthdate,
        )
        st.session_state[result_key] = result
        st.session_state[input_key] = {
            "full_name": f"{first_name.strip()} {last_name.strip()}".strip(),
            "birthdate": f"{int(day):02d}/{int(month):02d}/{int(year)}",
            "gender": _gender_label(gender),
            "hebrew_birthdate": hebrew_birthdate,
        }

    if result_key not in st.session_state:
        st.warning("הזן נתונים ולחץ על 'הרץ השוואה' כדי לראות השוואת שיטות.")
        return

    last_inputs = st.session_state[input_key]
    st.info(f"קלט אחרון: {last_inputs['full_name']} | {last_inputs['birthdate']} | {last_inputs['gender']}")
    if last_inputs["hebrew_birthdate"]:
        st.caption(f"תאריך עברי: {last_inputs['hebrew_birthdate']}")

    result = st.session_state[result_key]
    _render_method_controls(engine, result["methods"], prefix)
    _render_comparison(result, prefix)
