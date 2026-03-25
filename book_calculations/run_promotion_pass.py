from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
NUMEROLOGY_ROOT = SCRIPT_DIR.parent
if str(NUMEROLOGY_ROOT) not in sys.path:
    sys.path.insert(0, str(NUMEROLOGY_ROOT))

from book_calculations.sefer_hanumerologia_hashalem_builder import OUTPUT_PATH, write_definition

REPORTS_DIR = SCRIPT_DIR / "reports"
REPORT_JSON = REPORTS_DIR / "sefer_hanumerologia_hashalem.promotion_pass.json"
REPORT_MD = REPORTS_DIR / "sefer_hanumerologia_hashalem.promotion_pass.md"


def _index(calcs):
    return {c.get("calc_key"): c for c in calcs}


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    before = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    before_calcs = before.get("calculations", [])
    before_idx = _index(before_calcs)

    write_definition(OUTPUT_PATH)

    after = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    after_calcs = after.get("calculations", [])
    after_idx = _index(after_calcs)

    before_computable = sum(1 for c in before_calcs if c.get("status") == "computable")
    after_computable = sum(1 for c in after_calcs if c.get("status") == "computable")

    promoted = []
    for key, after_calc in after_idx.items():
        before_calc = before_idx.get(key)
        if not before_calc:
            continue
        if before_calc.get("status") != "computable" and after_calc.get("status") == "computable":
            promoted.append(key)

    blocked_after = [c for c in after_calcs if c.get("status") != "computable"]
    blocked_reason_counts = Counter((c.get("blocked_reason") or "unclassified") for c in blocked_after)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "book_id": after.get("book_id"),
        "computable_before": before_computable,
        "computable_after": after_computable,
        "promoted_count": len(promoted),
        "promoted_calculations": sorted(promoted),
        "blocked_counts_by_reason": dict(sorted(blocked_reason_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "top_remaining_blockers": [
            {"reason": reason, "count": count}
            for reason, count in sorted(blocked_reason_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        ],
    }

    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Sefer Promotion Pass",
        "",
        f"Generated: {report['generated_at']}",
        f"- Computable before: {before_computable}",
        f"- Computable after: {after_computable}",
        f"- Promoted count: {len(promoted)}",
        "",
        "## Promoted Calculations",
    ]
    if promoted:
        for key in sorted(promoted):
            lines.append(f"- `{key}`")
    else:
        lines.append("- none")

    lines.extend(["", "## Remaining Blocked By Reason"])
    for reason, count in sorted(blocked_reason_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"- `{reason}`: {count}")

    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
