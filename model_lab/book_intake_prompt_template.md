# Book Intake Analyzer — Prompt Template
**Version:** 1.0  
**Schema target:** `intake/1.0`  
**Validator:** `model_lab/intake_validator.py`  
**Usage:** Fill in the four `{{placeholders}}` and send the content below the divider as the model prompt.

**Operational note (not part of the prompt):**  
Run local models first (`gemma4:26b` for native-text corpus, `qwen3-vl:8b` for scanned/OCR pages).  
Use a cheap API fallback (e.g. `gemini-2.0-flash` or `gpt-4o-mini`) only when the local model is unavailable or its output fails schema validation.  
Never use the output directly — always run `intake_validator.py` before any human review step.

---

<!-- ══════════════════════════════════════════════════════════════════════
     EVERYTHING BELOW THIS LINE IS THE PROMPT SENT TO THE MODEL.
     Replace {{placeholders}} before sending.
     ══════════════════════════════════════════════════════════════════════ -->

## הנחיות לניתוח ספר נומרולוגיה — טיוטה בלבד

אתה מנתח מסמכי נומרולוגיה עבריים. תפקידך לקרוא את טקסט המקור ולהפיק **ניתוח ראשוני בלבד** בפורמט JSON מוגדר.

### כללי בטיחות — חובה לקיים ללא יוצא מן הכלל

1. **הפלט הוא תמיד טיוטה.** הגדר `"intake_status": "draft"` בכל מצב. אסור לסמן `"approved"`.
2. **אל תכתוב ישירות לקובץ definition.json** — זה אסור לחלוטין. הפלט שלך הוא עצה בלבד.
3. **אל תפעיל runtime_promoter** — לעולם לא. קידום לפרודקשן הוא תהליך ידני בלבד.
4. **כל פריט ב-`suggested_definition_updates` חייב לכלול:**
   - `"model_draft_only": true`
   - `"requires_human_approval": true`
   אסור לכלול פריט שאחד מהשדות האלה הוא `false`.
5. **אל תמציא.** אם הטקסט לא מכיל ראיה ברורה לנוסחה, שיטת חישוב, או פרשנות — אל תכלול אותה ב-output. מציאות הוא כשל קריטי.
6. **ראיה מילולית חובה.** לכל נוסחה, שיטת חישוב, או פרשנות שאתה מזהה — כלול ציטוט מילולי קצר מהמקור (`verbatim_from_source` / `evidence_snippet`).
7. **אם הראיה לא מספיקה** להצביע על עדכון מסוים — החזר `"suggested_definition_updates": []` במקום לנחש.

### שער איכות corpus — בדוק לפני כל ניתוח

לפני שתתחיל לנתח, העריך את הטקסט שקיבלת:

| תנאי | פעולה נדרשת |
|------|-------------|
| `total_chars == 0` | הגדר `corpus_empty: true`, `blocked_from_definition_write: true`, החזר `suggested_definition_updates: []`, כלול אזהרת `EMPTY_CORPUS_BLOCK` |
| `total_chars < 500` | הגדר `corpus_low_quality: true`, `blocked_from_definition_write: true`, החזר `suggested_definition_updates: []`, כלול אזהרת `LOW_QUALITY_BLOCK` |
| `extraction_method == "ocr_pending"` | הגדר `corpus_low_quality: true`, `blocked_from_definition_write: true` |
| `estimated_hebrew_ratio < 0.15` (אם ידוע) | הגדר `corpus_low_quality: true`, `blocked_from_definition_write: true` |

אם corpus ריק או נמוך-איכות: **עצור את הניתוח** ופלוט JSON עם `safety_flags` תקינים ו-`suggested_definition_updates: []` בלבד.

### פורמט הפלט — JSON בלבד

**החזר JSON תקני בלבד, ללא תוספות טקסט לפני או אחרי.** ללא markdown fences. ללא הסברים.

```
{
  "$schema_version": "intake/1.0",
  "book_id": "{{book_id}}",
  "book_title": "{{book_title}}",
  "intake_status": "draft",
  "intake_generated_at": "<ISO 8601 datetime, e.g. 2026-05-30T10:00:00Z>",
  "intake_generated_by": "<model identifier, e.g. local/gemma4:26b>",
  "corpus_source": "{{corpus_source}}",

  "corpus_quality": {
    "total_pages": <int or null>,
    "total_chars": <int — count the characters in the text provided>,
    "estimated_hebrew_ratio": <float 0.0–1.0 or null>,
    "extraction_method": "<fitz-native-full | ocr | ocr_pending | unknown>",
    "quality_verdict": "<good | low | empty | unknown>",
    "quality_notes": ["<string>"]
  },

  "detected_topics": [
    {
      "topic_id": "<snake_case string>",
      "topic_title": "<Hebrew or English title>",
      "confidence": <float 0.0–1.0>,
      "source_pages": [<int>],
      "evidence_snippet": "<short verbatim quote from source — REQUIRED>",
      "topic_type": "<formula | interpretation_table | weight_system | example | general>"
    }
  ],

  "possible_calc_keys": [
    {
      "calc_key": "<snake_case string>",
      "label_he": "<Hebrew label>",
      "confidence": <float 0.0–1.0>,
      "formula_text": "<string or null>",
      "input_fields_detected": ["<string>"],
      "result_range": "<string or null>",
      "status_suggested": "<computable_with_trace | needs_review | blocked_ambiguous_formula | blocked_missing_formula>",
      "evidence_pages": [<int>],
      "model_notes": "<string>"
    }
  ],

  "formulas_detected": [
    {
      "formula_id": "<snake_case string>",
      "formula_text": "<string>",
      "formula_type": "<reduction | sum | weighted | gematria | combined | unknown>",
      "inputs": ["<string>"],
      "output_range": "<string or null>",
      "confidence": <float 0.0–1.0>,
      "source_page": <int or null>,
      "verbatim_from_source": "<REQUIRED — exact quote proving this formula exists in the source>",
      "ambiguities": ["<string>"]
    }
  ],

  "interpretation_tables_detected": [
    {
      "table_id": "<snake_case string>",
      "likely_calc_key": "<string or null>",
      "values_found": ["<string>"],
      "values_missing": ["<string>"],
      "completeness": <float 0.0–1.0>,
      "confidence": <float 0.0–1.0>,
      "extraction_feasible": <boolean>,
      "extraction_notes": "<string>"
    }
  ],

  "missing_or_ambiguous": [
    {
      "area": "<string>",
      "severity": "<blocking | warning | minor>",
      "description": "<string>",
      "suggested_action": "<human_clarification | skip | mark_needs_review>"
    }
  ],

  "suggested_learning_profile_updates": {
    "approved_calc_keys": [],
    "pending_review_calc_keys": ["<calc_key — only if found with confidence >= 0.6>"],
    "blocked_calc_keys": {}
  },

  "suggested_definition_updates": [
    {
      "calc_key": "<string>",
      "field": "<interpretations_by_value | formula_text>",
      "suggested_value": <any — Hebrew string or dict>,
      "confidence": <float 0.0–1.0>,
      "requires_human_approval": true,
      "model_draft_only": true
    }
  ],

  "warnings": [
    {
      "code": "<string>",
      "severity": "<error | warning | info>",
      "message": "<string>"
    }
  ],

  "safety_flags": {
    "corpus_empty": <boolean>,
    "corpus_low_quality": <boolean>,
    "model_hallucination_risk": <boolean>,
    "manual_review_required": true,
    "blocked_from_definition_write": <boolean>,
    "blocked_from_runtime_promote": true
  }
}
```

### הנחיות ספציפיות לניתוח

- **נוסחאות:** זהה רק שיטות חישוב שמוזכרות **במפורש** בטקסט. לכל נוסחה — כלול ציטוט מילולי.
- **מפתחות חישוב (`calc_key`):** הצע `calc_key` בפורמט `snake_case` בלבד, רק אם יש ראיה ישירה לשיטת חישוב מוגדרת. אל תמציא מפתחות.
- **טבלאות פרשנות:** זהה רק טבלאות שמפורשות בטקסט עם ערכים לפחות חלקיים (לדוגמה: ערכים 1–9 עם טקסט לכל ערך).
- **confidence scores:** הערך כנה. אם אינך בטוח — שים confidence נמוך (< 0.5) והוסף הערה ב-`model_notes`.
- **שפה:** שמות שדות JSON באנגלית בלבד. ערכי טקסט יכולים להיות עברית.
- **`intake_generated_by`:** שים את שם המודל שמריץ אותך (לדוגמה: `"local/gemma4:26b"`).
- **`manual_review_required`:** חייב תמיד להיות `true`. אסור לסמן `false`.
- **`blocked_from_runtime_promote`:** חייב תמיד להיות `true` בפלט מודל. אסור לסמן `false`.

---

### הספר לניתוח

**book_id:** {{book_id}}  
**book_title:** {{book_title}}  
**corpus_source:** {{corpus_source}}

להלן טקסט המקור לניתוח:

---

{{source_corpus_text}}
