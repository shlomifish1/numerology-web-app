import os
import google.generativeai as genai

def generate_person_report(data: dict, model_name: str = "gemini-flash-latest", api_key: str = None) -> str:
    """
    Generates a single personalized recommendation based on numerology data using Google Gemini.

    Expects data dict to include:
        - full_name (str)
        - birth_date (str, DDMMYYYY)
        - personal_day, personal_month, personal_year (int)
        - destiny_number (int)
        - personal_year_number (int)
        - hidden_year (int) or str
        - age (int)
        - life_peaks (list of int)
        - challenges (list of int)
        - quarters (list of int)
        - gender (str): "זכר" or "נקבה"
    """
    # 1) Build Hebrew data lines
    prompt_lines = [
        f"שם מלא: {data['full_name']}",
        f"תאריך לידה (DDMMYYYY): {data['birth_date']}",
        f"מספר יום אישי: {data['personal_day']}",
        f"מספר חודש אישי: {data['personal_month']}",
        f"מספר שנה אישי: {data['personal_year']}",
        f"מסלול חיים (Destiny): {data['destiny_number']}",
        f"שנה אישית (Personal Year): {data['personal_year_number']}",
        f"שנה נסתרת (Hidden Year): {data['hidden_year']}",
        f"גיל נוכחי: {data['age']}",
        f"שיאי חיים: {data['life_peaks']}",
        f"אתגרים: {data['challenges']}",
        f"מעגלים רבעוניים: {data['quarters']}",
        f"מין: {data.get('gender', 'זכר')}",
    ]

    # 2) Compose the focused user prompt
    user_prompt = (
        "להלן כל הנתונים המתקבלים מתוך הנומרולוגיה והמשתמש:\n"
        + "\n".join(prompt_lines)
        + "\n\n"
        + (
            "הבקשה שלי: קח את כל הנתונים שלמעלה, וכתוב **המלצה אחת** מסודרת במספר שורות — "
            "מה עלי לעשות כדי להגשים את הייעוד שלי, ואיך לפעול נכון עם המספרים שברשותי. "
            "התאם את הלשון לפי המין: אם 'מין: נקבה', השתמש בלשון נקבה; אם 'מין: זכר', השתמש בלשון זכר. "
            "כתוב עברית תקנית, קולחת, ללא שגיאות התאמה בין מין ומשתנה. "
            "אנא תן חשיבה באיכות גבוהה, **לא** פירוט טכני של פירוש כל ספרה. "
            "התוצאה צריכה להיות המלצה כללית אך מותאמת אישית."
        )
    )

    try:
        if api_key:
            genai.configure(api_key=api_key)
        
        # 3) Call the Gemini model
        model = genai.GenerativeModel(model_name)
        
        # Adding system instruction via prompt preamble since system_instruction is supported in newer SDKs
        # or we can just prepend it to the user prompt for simplicity and compatibility.
        system_instruction = "אתה מומחה בנומרולוגיה ובכתיבה בשפה העברית. ענה רק בעברית.\n\n"
        final_prompt = system_instruction + user_prompt

        response = model.generate_content(final_prompt)
        
        return response.text.strip()
    except Exception as e:
        return f"שגיאה ביצירת דוח AI: {str(e)}"
