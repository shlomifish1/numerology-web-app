"""
הורדת ספרים למערכת הסוכנים
תיקיית יעד: C:/Users/fishman-ai-server/Desktop/ai_agents/books/
הרץ: python download_books.py
"""

import os
import time
import urllib.request

SAVE_DIR = r"C:\Users\fishman-ai-server\Desktop\ai_agents\books"
os.makedirs(SAVE_DIR, exist_ok=True)

BOOKS = [
    # ===== שיווק וקופירייטינג =====
    {
        "name": "Influence - Cialdini.pdf",
        "url": "https://ia800203.us.archive.org/33/items/ThePsychologyOfPersuasion/The%20Psychology%20of%20Persuasion.pdf",
        "category": "marketing"
    },
    {
        "name": "Breakthrough Advertising - Schwartz.pdf",
        "url": "https://burtrexi.files.wordpress.com/2014/12/breakthrough-advertising.pdf",
        "category": "marketing"
    },
    {
        "name": "The Boron Letters - Gary Halbert.txt",
        "url": "https://www.thegaryhalbertletter.com/Boron/BoronLetterCh1.htm",
        "category": "marketing",
        "note": "25 פרקים — ראה הוראות ידניות למטה"
    },

    # ===== פיתוח אישי =====
    {
        "name": "How to Win Friends - Carnegie.pdf",
        "url": "https://dn720004.ca.archive.org/0/items/english-collections-1/How%20To%20Win%20Friends%20And%20Influence%20People%20-%20Carnegie,%20Dale.pdf",
        "category": "personal_development"
    },
    {
        "name": "The Obstacle is the Way - Ryan Holiday.pdf",
        "url": "https://icrrd.com/public/media/16-05-2021-051456The-Obstacle-Is-the-Way.pdf",
        "category": "personal_development"
    },
    {
        "name": "Magic of Thinking Big - Schwartz.pdf",
        "url": "https://ia803208.us.archive.org/35/items/the-magic-of-thinking-big_202110/The%20Magic%20of%20Thinking%20Big.pdf",
        "category": "personal_development"
    },
    {
        "name": "The Happiness Advantage - Shawn Achor.pdf",
        "url": "https://ia601502.us.archive.org/2/items/happinessadvanta00acho/happinessadvanta00acho.pdf",
        "category": "personal_development"
    },
]

def download_book(book):
    category_dir = os.path.join(SAVE_DIR, book["category"])
    os.makedirs(category_dir, exist_ok=True)

    filepath = os.path.join(category_dir, book["name"])

    if os.path.exists(filepath):
        print(f"⏭️  כבר קיים: {book['name']}")
        return

    if book.get("note"):
        print(f"⚠️  {book['name']} — {book['note']}")
        return

    print(f"⬇️  מוריד: {book['name']} ...")
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        req = urllib.request.Request(book["url"], headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            with open(filepath, "wb") as f:
                f.write(response.read())
        size_kb = os.path.getsize(filepath) // 1024
        print(f"✅ הורד ({size_kb} KB): {book['name']}")
    except Exception as e:
        print(f"❌ שגיאה ב-{book['name']}: {e}")

    time.sleep(1)  # נחכה קצת בין הורדות

if __name__ == "__main__":
    print(f"📚 מוריד ספרים ל: {SAVE_DIR}\n")
    for book in BOOKS:
        download_book(book)

    print("\n" + "="*50)
    print("📋 הוראות ידניות לספרים שלא הורדו אוטומטית:")
    print("""
The Boron Letters (25 פרקים חינמיים):
  → כנס ל: https://www.thegaryhalbertletter.com/Boron/BoronLetterCh1.htm
  → כל פרק נמצא ב-URL נפרד (Ch1 עד TChapter25)
  → OR: קנה PDF ב-Amazon כ-$9.99

Breakthrough Advertising (אם הקישור מת):
  → הירשם חינם ל: https://archive.org
  → ואז: https://archive.org/details/breakthroughadve0000schw

ספרים עבריים (נומרולוגיה / NLP):
  → לא נמצאו PDF חינמיים
  → סרוק עם Adobe Scan מהמדף שלך
  → או חפש ב-Z-Library (z-lib.id)
""")
    print("="*50)
    print("✅ סיום!")
