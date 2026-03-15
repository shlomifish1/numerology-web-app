"""Method adapter factory."""

from .adapter_astrology import AstrologyMethodAdapter
from .adapter_generic import GenericMethodAdapter
from .adapter_green import GreenMethodAdapter
from .adapter_pythagorean import PythagoreanMethodAdapter
from .adapter_spirit import SpiritMethodAdapter


def get_adapter(method_config):
    adapter_name = method_config.get("adapter")
    if adapter_name == "pythagorean":
        return PythagoreanMethodAdapter(method_config)
    if adapter_name == "green":
        return GreenMethodAdapter(method_config)
    if adapter_name == "spirit":
        return SpiritMethodAdapter(method_config)
    if adapter_name == "astrology":
        return AstrologyMethodAdapter(method_config)
    return GenericMethodAdapter(method_config)


__all__ = [
    "AstrologyMethodAdapter",
    "GenericMethodAdapter",
    "GreenMethodAdapter",
    "PythagoreanMethodAdapter",
    "SpiritMethodAdapter",
    "get_adapter",
]
