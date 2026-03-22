"""Comparison engine for research-only numerology methods."""

from __future__ import annotations

from typing import Dict, List, Optional

from .approval_store import ApprovalStore
from .method_adapters import get_adapter
from .method_registry import MethodRegistry


DEFAULT_ROWS = [
    ("destiny", "שביל גורל"),
    ("name_total", "מספר השם"),
    ("soul", "ביטוי פנימי"),
    ("outer", "ביטוי חיצוני"),
    ("personal_year", "שנה אישית / מצב"),
    ("hidden_year", "שכבה נסתרת / נפח"),
    ("missing", "פערים"),
    ("beneficial", "חוזקות"),
    ("surplus", "עודפים / עומס"),
    ("corpus_size", "חומרי מקור"),
    ("top_themes", "תמות מובילות"),
    ("media_mix", "סוגי קבצים"),
    ("readiness", "מוכנות"),
    ("next_step", "השלב הבא"),
]


class ComparisonEngine:
    def __init__(
        self,
        registry: Optional[MethodRegistry] = None,
        approval_store: Optional[ApprovalStore] = None,
    ):
        self.registry = registry or MethodRegistry()
        self.approval_store = approval_store or ApprovalStore()

    def compare(
        self,
        *,
        first_name: str,
        last_name: str,
        day: int,
        month: int,
        year: int,
        gender: str,
        hebrew_birthdate: Optional[Dict[str, int]] = None,
    ) -> Dict[str, object]:
        methods = self.registry.list_methods(research_only=True)
        self.approval_store.merge_methods(methods)

        rendered_methods: List[Dict[str, object]] = []
        for method in methods:
            adapter = get_adapter(method)
            result = adapter.analyze(
                first_name=first_name,
                last_name=last_name,
                day=day,
                month=month,
                year=year,
                gender=gender,
                hebrew_birthdate=hebrew_birthdate,
            )
            method_result = dict(method)
            method_result["enabled_for_customers"] = self.approval_store.get_status(
                str(method["key"]),
                default=bool(method.get("enabled_for_customers", False)),
            )
            method_result["result"] = result
            rendered_methods.append(method_result)

        pythagorean_result = next(
            (
                method.get("result", {})
                for method in rendered_methods
                if method.get("key") == "pythagorean_existing"
            ),
            {},
        )

        comparison_rows = []
        for row_key, row_label in DEFAULT_ROWS:
            comparison_rows.append(
                {
                    "key": row_key,
                    "label": row_label,
                    "values": {
                        method["key"]: method["result"]["metrics"].get(row_key, "-")
                        for method in rendered_methods
                    },
                }
            )

        return {
            "inputs": {
                "first_name": first_name,
                "last_name": last_name,
                "day": day,
                "month": month,
                "year": year,
                "gender": gender,
                "hebrew_birthdate": hebrew_birthdate or {},
            },
            "methods": rendered_methods,
            "rows": comparison_rows,
            "report_sections": list(pythagorean_result.get("report_sections") or []),
            "report_summary": dict(pythagorean_result.get("report_summary") or {}),
        }
