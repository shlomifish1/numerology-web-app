"""
adapter_learned.py — Computes numerology using rules learned from book_rules DB.
Uses the existing NumerologyCalculator for standard calculations,
enriched with book-specific interpretation rules.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Optional

from .adapter_base import MethodAdapter

# Ensure NumerologyReportGenerator root is on path
_NRG_ROOT = str(Path(__file__).parent.parent.parent)
if _NRG_ROOT not in sys.path:
    sys.path.insert(0, _NRG_ROOT)

from book_ingestion.knowledge_store import KnowledgeStore
from numerology_calculator import NumerologyCalculator


def _normalize_corpus_key(value: object) -> str:
    return (
        str(value or "")
        .strip()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("'", "")
        .lower()
    )


class LearnedMethodAdapter(MethodAdapter):
    """
    Adapter for books that went through rule_extractor.
    Uses saved rules from book_rules as metadata,
    runs standard calculations (LifePath, NameTotal etc.) via NumerologyCalculator
    with book-specific interpretation.
    """

    def __init__(self, method_config: Dict[str, object]):
        super().__init__(method_config)
        self._store = KnowledgeStore()
        candidates = []
        seen = set()
        for value in (
            method_config.get("learned_corpus"),
            method_config.get("folder"),
            method_config.get("key"),
        ):
            text = str(value or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            candidates.append(text)
            normalized = _normalize_corpus_key(text)
            if normalized and normalized not in seen:
                seen.add(normalized)
                candidates.append(normalized)
        self._candidate_corpora = candidates
        self._corpus = candidates[0] if candidates else ""
        self._rules: dict[str, dict] | None = None

    def _load_rules(self) -> dict[str, dict]:
        if self._rules is None:
            self._rules = {}
            for candidate in self._candidate_corpora:
                rows = self._store.get_book_rules(candidate)
                if rows:
                    self._corpus = candidate
                    self._rules = {r["concept_key"]: r for r in rows}
                    break
        return self._rules

    def analyze(
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
        del hebrew_birthdate
        rules = self._load_rules()

        # Use the existing calculator
        calc = NumerologyCalculator()
        calc.calculate(
            str(day).zfill(2),
            str(month).zfill(2),
            str(year),
            first_name,
            last_name,
            gender,
        )

        metrics = {
            "destiny": calc.final_number_destiny,
            "name_total": calc.full_name_val,
            "soul": calc.aiv_val,
            "outer": calc.itzurim_val,
            "personal_year": calc.shana_ishit,
            "hidden_year": calc.shana_nisteret,
            "missing": "לא מחושב",
            "beneficial": "לא מחושב",
            "surplus": "לא מחושב",
            "corpus_size": f"{len(rules)} מושגים נלמדו",
            "readiness": "learned" if len(rules) >= 5 else "partial",
        }

        # Enrich with book-specific rule details
        details = {}
        for key in ["life_path", "destiny", "name_total", "soul", "outer", "personal_year",
                     "challenge", "pinnacle", "karmic", "master", "missing", "surplus"]:
            r = rules.get(key)
            if r:
                details[key] = {
                    "calc_method": r["calc_method"],
                    "interpretation": r["interpretation_rules"],
                    "confidence": r["confidence"],
                    "cabinet_used": bool(r.get("cabinet_used")),
                }

        return {
            "summary": f"מבוסס על {len(rules)} מושגים שנלמדו מ'{self._corpus}'",
            "metrics": metrics,
            "details": details,
        }
