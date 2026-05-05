import os
import sys
from typing import Any, Dict, Optional

# Ensure ai_agents imports work
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

from ai_manager import ai_engine


def _normalize_payload(
    data_or_name: Any,
    gender: Optional[str] = None,
    destiny: Optional[int] = None,
    personal_year: Optional[int] = None,
    birth_day: Optional[int] = None,
    missing_elements: Optional[list] = None,
    green_context: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    if isinstance(data_or_name, dict):
        payload = dict(data_or_name)
    else:
        payload = {
            'full_name': data_or_name,
            'gender': gender,
            'destiny_number': destiny,
            'personal_year_number': personal_year,
            'birth_day': birth_day,
            'missing_elements': missing_elements or [],
        }
    if green_context and 'green_context' not in payload:
        payload['green_context'] = green_context
    return payload


def _green_context_block(payload: Dict[str, object]) -> str:
    green = payload.get('green_context') or {}
    if not isinstance(green, dict) or not green:
        return ''

    name_analysis = green.get('name_analysis') or {}
    as_vowel = name_analysis.get('as_vowel') or {}
    soul = ((as_vowel.get('soul_expression') or {}).get('final'))
    outer = ((as_vowel.get('outer_behavior') or {}).get('final'))
    destiny_path = ((as_vowel.get('destiny_path') or {}).get('final'))
    missing_info = green.get('missing_info') or {}
    birthdate_analysis = green.get('birthdate_analysis') or {}
    note = name_analysis.get('note') or ''

    lines = [
        '## הקשר נוסף לפי שיטת מיכל גרין (גימטריה מלאה)',
        f'- ביטוי נשמה: {soul if soul is not None else "-"}',
        f'- התנהגות מוחצנת: {outer if outer is not None else "-"}',
        f'- שביל שם מלא: {destiny_path if destiny_path is not None else "-"}',
        f"- מספרים חסרים: {missing_info.get('missing', [])}",
        f"- מספרים מיטיבים: {missing_info.get('beneficial', [])}",
        f"- מספרים עודפים: {missing_info.get('surplus', [])}",
    ]
    if birthdate_analysis:
        lines.extend(
            [
                f"- גורל מתאריך לידה: {birthdate_analysis.get('destiny', '-')}",
                f"- מחזורי חיים: {birthdate_analysis.get('life_cycles', '-')}",
            ]
        )
    if note:
        lines.append(f'- הערה על ו\': {note}')
    return '\n'.join(lines)


def _build_prompt(payload: Dict[str, object]) -> str:
    life_peaks = payload.get('life_peaks') or []
    challenges = payload.get('challenges') or []
    quarters = payload.get('quarters') or []
    green_block = _green_context_block(payload)

    prompt = [
        f"שם מלא: {payload.get('full_name', '-')}",
        f"מין: {payload.get('gender', '-')}",
        f"מסלול חיים (Destiny): {payload.get('destiny_number', '-')}",
        f"שנה אישית (Personal Year): {payload.get('personal_year_number', payload.get('personal_year', '-'))}",
        f"יום לידה מצומצם: {payload.get('birth_day', payload.get('personal_day', '-'))}",
        f"שנה נסתרת: {payload.get('hidden_year', '-')}",
        f"גיל: {payload.get('age', '-')}",
        f"פסגות: {life_peaks}",
        f"אתגרים: {challenges}",
        f"רבעונים: {quarters}",
    ]

    missing = payload.get('missing_elements')
    if missing:
        prompt.append(f"מספרים חסרים: {missing}")
    if green_block:
        prompt.append('')
        prompt.append(green_block)

    prompt.append('')
    prompt.append(
        'הבקשה: כתוב המלצה אישית אחת, מדויקת ומעשית, בעברית בלבד. '
        'שלב בין הנתונים הקלאסיים לבין שכבת Green אם היא קיימת. '
        'אל תכתוב פירוט טכני יבש של כל מספר; תן הכוונה יישומית, רגשית והתפתחותית. '
        'אם יש פער בין החישוב הרגיל לבין Green, הסבר זאת בקצרה כעומק נוסף ולא כסתירה.'
    )
    return '\n'.join(prompt)


def generate_person_report(
    data_or_name: Any,
    gender: Optional[str] = None,
    destiny: Optional[int] = None,
    personal_year: Optional[int] = None,
    birth_day: Optional[int] = None,
    missing_elements: Optional[list] = None,
    *,
    model_name: str = 'gemini_2_flash',
    api_key: Optional[str] = None,
    green_context: Optional[Dict[str, object]] = None,
) -> str:
    """Generate a personalized numerology recommendation via the centralized AI engine."""
    del api_key
    payload = _normalize_payload(
        data_or_name,
        gender=gender,
        destiny=destiny,
        personal_year=personal_year,
        birth_day=birth_day,
        missing_elements=missing_elements,
        green_context=green_context,
    )

    system_instruction = 'אתה חייב לענות רק בעברית, ואתה מומחה בנומרולוגיה התפתחותית וניתוח תכונות אופי.'
    user_prompt = _build_prompt(payload)
    messages = [
        {'role': 'system', 'content': system_instruction},
        {'role': 'user', 'content': user_prompt},
    ]

    previous_model_key = getattr(ai_engine, 'current_model_key', None)
    try:
        if model_name:
            switched, _ = ai_engine.switch_model(model_name)
            if not switched:
                print(f'{model_name} is unavailable, using current model for person report')
        response = ai_engine.chat_completion(messages)
        return (response or '').strip()
    except Exception as e:
        return f'[שגיאה בהפקת דוח AI]: {e}'
    finally:
        if previous_model_key and previous_model_key != getattr(ai_engine, 'current_model_key', None):
            ai_engine.switch_model(previous_model_key)
