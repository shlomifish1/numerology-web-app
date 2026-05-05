try:
    from .sefer_hanumerologia_hashalem_builder import (
        BOOK_ID,
        BOOK_TITLE,
        OUTPUT_PATH,
        build_definition,
        write_definition,
    )

    __all__ = [
        "BOOK_ID",
        "BOOK_TITLE",
        "OUTPUT_PATH",
        "build_definition",
        "write_definition",
    ]
except Exception:
    # The legacy builder depends on historical book artifacts that may be
    # intentionally removed from the workspace. Keep package import safe so
    # runtime services can continue loading the active calculators.
    __all__ = []
