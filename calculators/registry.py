from __future__ import annotations

from typing import Callable

from calculators.contract import BookCalculatorContract
from calculators.green_legacy import GreenLegacyCalculator
from calculators.misparei_bayit import MispareiBayitCalculator
from calculators.sefer_hanumerologia_hashalem import SeferHanumerologiaHashalemCalculator

DEFAULT_CALCULATOR_ID = "green_legacy"

_FACTORY_BY_ID: dict[str, Callable[[], BookCalculatorContract]] = {
    DEFAULT_CALCULATOR_ID: GreenLegacyCalculator,
    "misparei_bayit": MispareiBayitCalculator,
    "sefer_hanumerologia_hashalem": SeferHanumerologiaHashalemCalculator,
}


def get_calculator(calculator_id: str | None = None) -> BookCalculatorContract:
    selected_id = calculator_id or DEFAULT_CALCULATOR_ID
    factory = _FACTORY_BY_ID.get(selected_id)
    if factory is None:
        raise ValueError(f"Unknown calculator id: {selected_id}")
    return factory()


def list_calculators() -> list[str]:
    return sorted(_FACTORY_BY_ID.keys())
