# Research Mode

הרצה מקומית:

```powershell
cd C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator
streamlit run research_app.py
```

ברירת מחדל לסיסמה:
- `innerbalance-research`

אפשר לשנות דרך משתנה סביבה:

```powershell
$env:RESEARCH_PASSWORD='choose-a-secret'
streamlit run research_app.py
```

מה קיים כרגע:
- זיהוי אוטומטי של תיקיות תחת `interpretations/`
- מנוע השוואה בין פיתגורס, Green, `spirit` ו-`astrology`
- adapters ייעודיים ל-`green`, `spirit`, `astrology`
- שמירת אישור ללקוח ב-SQLite
- UI נפרד למחקר, בלי שינוי ב-`web_app.py`
- חיבור לשכבת ingestion ולמסד `numerology_books.db`
- תצוגת תמות, OCR queue ו-runtime ל-`spirit`
- תצוגת taxonomy ו-seed books ל-`astrology`
- חלוקה ב-expander לכל שיטה ל-`סקירה` ו-`Raw JSON`

מה עדיין לא קיים:
- חיבור route רשמי מתוך אפליקציית הלקוח
- OCR מלא ל-PDFים סרוקים כל עוד `Tesseract` לא מותקן במערכת
- corpus ממשי ל-`astrology`
