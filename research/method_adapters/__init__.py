"""Method adapter factory."""

from .adapter_astrology import AstrologyMethodAdapter
from .adapter_generic import GenericMethodAdapter
from .adapter_green import GreenMethodAdapter
from .adapter_learned import LearnedMethodAdapter
from .adapter_pythagorean import PythagoreanMethodAdapter
from .adapter_spirit import SpiritMethodAdapter


def get_adapter(method_config):
    adapter_name = method_config.get("adapter")

    # If the book has learned rules in DB, auto-upgrade to LearnedAdapter
    if adapter_name in ("generic", "green") and method_config.get("folder"):
        corpus = str(method_config.get("folder") or method_config.get("key") or "")
        try:
            from ..book_ingestion.knowledge_store import KnowledgeStore
            store = KnowledgeStore()
            if store.get_book_rules(corpus):
                return LearnedMethodAdapter(method_config)
        except Exception:
            pass

    if adapter_name == "pythagorean":
        return PythagoreanMethodAdapter(method_config)
    if adapter_name == "green":
        return GreenMethodAdapter(method_config)
    if adapter_name == "spirit":
        return SpiritMethodAdapter(method_config)
    if adapter_name == "astrology":
        return AstrologyMethodAdapter(method_config)
    if adapter_name == "learned":
        return LearnedMethodAdapter(method_config)
    return GenericMethodAdapter(method_config)


__all__ = [
    "AstrologyMethodAdapter",
    "GenericMethodAdapter",
    "GreenMethodAdapter",
    "LearnedMethodAdapter",
    "PythagoreanMethodAdapter",
    "SpiritMethodAdapter",
    "get_adapter",
]
