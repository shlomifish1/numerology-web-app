from gpt_report import generate_person_report

data = {
    "full_name": "ישראל ישראלי",
    "birth_date": "01011980",
    "personal_day": 1,
    "personal_month": 1,
    "personal_year": 1,
    "destiny_number": 1,
    "personal_year_number": 1,
    "hidden_year": "1_2",
    "age": 44,
    "life_peaks": [1, 2, 3, 4],
    "challenges": [1, 2, 3, 4],
    "quarters": [1, 2, 3, 4],
    "gender": "זכר"
}

print("Attempting to generate report with Gemini...")
try:
    report = generate_person_report(data)
    print("\n--- Report Start ---")
    print(report)
    print("--- Report End ---\n")
    if "שגיאה" in report:
        print("Test FAILED: Error returned in report.")
    else:
        print("Test PASSED: Report generated successfully.")
except Exception as e:
    print(f"Test FAILED: Exception occurred: {e}")
