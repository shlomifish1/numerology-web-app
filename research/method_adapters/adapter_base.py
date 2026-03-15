"""Base interface for research method adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Optional


class MethodAdapter(ABC):
    def __init__(self, method_config: Dict[str, object]):
        self.method_config = method_config

    @abstractmethod
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
        raise NotImplementedError
