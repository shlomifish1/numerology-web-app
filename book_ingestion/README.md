# Book Ingestion

מטרת התיקייה: לנהל אינדוקס, חילוץ טקסט, OCR, קטלוג ומיפוי פרקים לספרים שמזינים את שכבת המחקר.

הרצה בסיסית:

```powershell
cd C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator
& 'C:\Users\fishman-ai-server\Desktop\ai_agents\.venv\Scripts\python.exe' -c "import sys; sys.path.insert(0, r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator'); from book_ingestion.catalog_sync import refresh_all; print(refresh_all())"
```

רענון ממוקד ל-pending OCR:

```powershell
cd C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator
& 'C:\Users\fishman-ai-server\Desktop\ai_agents\.venv\Scripts\python.exe' -c "import sys; sys.path.insert(0, r'C:\Users\fishman-ai-server\Desktop\ai_agents\NumerologyReportGenerator'); from book_ingestion.ocr_batch import PendingOCRRunner; print(PendingOCRRunner().refresh_pending('spirit', method='spirit', limit=5))"
```

פורמטים נתמכים כרגע:
- TXT / MD / CSV
- HTML / HTM
- DOCX
- EPUB
- PDF עם חילוץ טקסט דרך `PyPDF2` ו-`fitz`
- תמונות דרך OCR כאשר `Tesseract` זמין

מה נשמר:
- `numerology_books.db` עם מטא-דאטה לכל ספר/קובץ
- `book_chunks` רק כאשר יש טקסט שחולץ בפועל
- `book_categories` למיפוי פרקים וקטגוריות מחקר
- קטלוגי Markdown לכל corpus
- `green_category_map.md` למפת הידע של Green
- `spirit_category_map.md` למפת התמות של `spirit`
- `spirit_ocr_queue.md` לתיעדוף OCR
- `spirit_ocr_runtime.md` לסטטוס סביבת OCR והקבצים שעדיין ממתינים
- `astrology_taxonomy.md` ו-`astrology_seed_plan.md` לבניית corpus אסטרולוגי עתידי
- `astrology_category_map.md` למיפוי אוטומטי עתידי ברגע שייכנסו ספרים
- `raw_books_intake.md` להצעת ניתוב אוטומטית לחומרי מקור חדשים

סטטוסים עיקריים:
- `text_extracted`: חולץ טקסט מובנה
- `ocr_extracted`: OCR הצליח
- `ocr_pending`: יש PDF/תמונה שעדיין דורשים OCR מלא
- `metadata_only`: נשמר רק מטא-דאטה

הערות runtime:
- המערכת ממחזרת את התלויות שכבר קיימות תחת `C:\Users\fishman-ai-server\Desktop\ai_agents\ocr`
- `fitz` ו-`PyPDF2` זמינים דרך הסביבה הזו גם בלי התקנה נוספת בתוך הפרויקט
- כרגע חסר `tesseract.exe`, לכן OCR מלא על PDF סרוקים עדיין חסום
