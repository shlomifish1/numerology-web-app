from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class BookCalculatorContract(Protocol):
    """Shared execution contract for book-specific calculators."""

    def calculate(self, subject_payload: Mapping[str, Any]) -> dict[str, Any]:
        """Run calculation and return a normalized result payload."""

    def get_interpretation(self, calc_key: str, value: Any, context: Mapping[str, Any] | None = None) -> str:
        """Resolve interpretation text for a calculated key/value pair."""

    def get_supported_calculations(self) -> list[dict[str, Any]]:
        """Return calculation metadata for this calculator implementation."""

    def get_book_id(self) -> str:
        """Return stable calculator/book identifier."""

    def get_version(self) -> str:
        """Return calculator implementation version."""
