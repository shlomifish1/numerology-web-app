"""Standalone Streamlit app for the internal research dashboard."""

from __future__ import annotations

import streamlit as st

from research.streamlit_panel import render_research_panel


def main() -> None:
    st.set_page_config(
        page_title="Numerology Research Dashboard",
        page_icon="🧪",
        layout="wide",
    )
    st.markdown(
        """
        <style>
            .stApp { direction: rtl; text-align: right; background: linear-gradient(180deg, #fcf8f1 0%, #f3eadf 100%); }
            .stMarkdown, .stText, .stAlert, .stCaption, .stTextInput, .stDateInput, .stSelectbox { direction: rtl; text-align: right; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    render_research_panel(
        prefix="research",
        embedded=False,
        title="מחקר נומרולוגי פנימי",
        caption="אפליקציה נפרדת למחקר והשוואת שיטות, בלי לגעת בממשק הלקוח הקיים.",
    )


if __name__ == "__main__":
    main()
