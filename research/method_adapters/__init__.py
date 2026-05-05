"""Method adapter factory."""

from .adapter_astrology import AstrologyMethodAdapter
from .adapter_generic import GenericMethodAdapter
from .adapter_green import GreenMethodAdapter
from .adapter_learned import LearnedMethodAdapter
from .adapter_pythagorean import PythagoreanMethodAdapter
from .adapter_spirit import SpiritMethodAdapter


def _normalize_corpus_key(value):
    return (
        str(value or "")
        .strip()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("'", "")
        .lower()
    )


def _candidate_corpora(method_config):
    seen = set()
    candidates = []
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
    return candidates


def get_adapter(method_config):
    adapter_name = method_config.get("adapter")

    # If the book has learned rules in DB, auto-upgrade to LearnedAdapter
    if adapter_name in ("generic", "green") and (method_config.get("folder") or method_config.get("key")):
        try:
            from ..book_ingestion.knowledge_store import KnowledgeStore
            store = KnowledgeStore()
            for candidate in _candidate_corpora(method_config):
                if store.get_book_rules(candidate):
                    upgraded = dict(method_config)
                    upgraded["learned_corpus"] = candidate
                    return LearnedMethodAdapter(upgraded)
        except Exception:
            pass

    if adapter_name in {"pythagorean", "legacy_runtime"}:
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
