# -*- coding: utf-8 -*-
import os
import sys
import re
import datetime
import personal_y  # Assuming this module contains This_Year class and its methods
import name  # Assuming this module contains NamesData class and its methods
from name_gematria_green import MASTER_MEANINGS as GREEN_MASTER_MEANINGS, NamesDataGreen
from interpretation_layout import runtime_interpretation_file_candidates

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller. """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

MASTER_MEANINGS = GREEN_MASTER_MEANINGS

class NumerologyCalculator:
    def __init__(self):
        self.fulldate_list_for_pyth = None
        self.real_year = None
        self.real_month = None
        self.full_list = None
        self.original_day = None
        self.original_month = None
        self.original_year = None
        self.green_snapshot = None
        self.shana_ishit = None
        self.shana_nisteret = None
        self.bd_month = None
        self.first_pick = None
        self.second_pick = None
        self.third_pick = None
        self.forth_pick = None
        self.first_challenge = None
        self.second_challenge = None
        self.third_challenge = None
        self.forth_challenge = None
        self.peak1_reduced = None
        self.peak2_reduced = None
        self.peak3_reduced = None
        self.peak4_reduced = None
        self.challenge1_reduced = None
        self.challenge2_reduced = None
        self.challenge3_reduced = None
        self.challenge4_reduced = None
        self.first_pick_start = None
        self.second_pick_start = None
        self.third_pick_start = None
        self.forth_pick_start = None
        self.final_number_destiny = None
        self.original_destiny_sum = None
        self.p_year = None
        self.p_month = None
        self.p_day = None
        self.original_day = None
        self.original_month = None
        self.original_year = None
        self.green_snapshot = None
        self.full_date_short = None
        
        self.tzimtzum_age = None
        self.age = None
        self.full_date = None
        self.full_name = None
        self.first_name_str = None
        self.last_name_str = None
        self.first_name_val = None
        self.full_name_val = None
        self.itzurim_val = None
        self.aiv_val = None
        self.first_quarter_reduced = None
        self.second_quarter_reduced = None
        self.third_quarter_reduced = None
        self.forth_quarter_reduced = None
        self.quarter_sequences_2 = []
        self.quarter_sequences_3 = []

        
    def short_number_single(self, args):
        if args is None: return None
        try:
            abs_args = abs(int(args))
            num_str = str(abs_args)
        except ValueError:
            return None
        current_sum = abs_args
        while len(num_str) > 1:
            current_sum = sum(int(digit) for digit in num_str)
            if current_sum <= 9: return current_sum
            num_str = str(current_sum)
        return int(num_str)

    def short_number_master(self, args):
        if args is None: return None
        try:
            abs_args = abs(int(args))
            num_str = str(abs_args)
        except ValueError:
            return None
        current_sum = abs_args
        if len(num_str) == 1: return current_sum
        current_sum = sum(int(digit) for digit in num_str)
        if current_sum in [11, 22, 33]: return current_sum
        num_str = str(current_sum)
        while len(num_str) > 1:
            current_sum = sum(int(digit) for digit in num_str)
            if current_sum <= 9: return current_sum
            num_str = str(current_sum)
        return int(num_str)

    def _resolve_gender_context(self, gender_folder_param):
        normalized = str(gender_folder_param or "").strip().lower()
        if normalized in {"female", "women", "woman", "f", "נקבה"}:
            return {
                "target_gender": "female",
                "target_folder": "women",
                "target_suffix": "_f",
                "alternate_gender": "male",
                "alternate_folder": "men",
                "alternate_suffix": "_m",
            }
        if normalized in {"male", "men", "man", "m", "זכר"}:
            return {
                "target_gender": "male",
                "target_folder": "men",
                "target_suffix": "_m",
                "alternate_gender": "female",
                "alternate_folder": "women",
                "alternate_suffix": "_f",
            }
        return {
            "target_gender": "male",
            "target_folder": "men",
            "target_suffix": "_m",
            "alternate_gender": "female",
            "alternate_folder": "women",
            "alternate_suffix": "_f",
        }

    def _infer_source_gender(self, path_value: str) -> str | None:
        path_text = str(path_value or "").replace("\\", "/").lower()
        file_name = path_text.rsplit("/", 1)[-1]
        if file_name.endswith("_m.txt"):
            return "male"
        if file_name.endswith("_f.txt"):
            return "female"
        if "/men/" in path_text:
            return "male"
        if "/women/" in path_text:
            return "female"
        return None

    def _adapt_gender_text(self, text: str, source_gender: str | None, target_gender: str) -> str:
        if not text or not source_gender or source_gender == target_gender:
            return text

        if source_gender == "male" and target_gender == "female":
            replacements = [
                (r"(^|[^\w])(ו?)הוא(?=$|[^\w])", r"\1\2היא"),
                (r"(^|[^\w])(ו?)שלו(?=$|[^\w])", r"\1\2שלה"),
                (r"(^|[^\w])(ו?)אותו(?=$|[^\w])", r"\1\2אותה"),
                (r"(^|[^\w])(ו?)לו(?=$|[^\w])", r"\1\2לה"),
                (r"(^|[^\w])(ו?)בו(?=$|[^\w])", r"\1\2בה"),
                (r"(^|[^\w])(ו?)עצמו(?=$|[^\w])", r"\1\2עצמה"),
                (r"(^|[^\w])(ו?)שולט(?=$|[^\w])", r"\1\2שולטת"),
                (r"(^|[^\w])(ו?)מרגיש(?=$|[^\w])", r"\1\2מרגישה"),
                (r"(^|[^\w])(ו?)עקשן(?=$|[^\w])", r"\1\2עקשנית"),
                (r"(^|[^\w])(ו?)רכושן(?=$|[^\w])", r"\1\2רכושנית"),
                (r"(^|[^\w])(ו?)קנאי(?=$|[^\w])", r"\1\2קנאית"),
                (r"(^|[^\w])(ו?)ביקורתי(?=$|[^\w])", r"\1\2ביקורתית"),
                (r"(^|[^\w])(ו?)עצמאי(?=$|[^\w])", r"\1\2עצמאית"),
                (r"(^|[^\w])(ו?)אקטיבי(?=$|[^\w])", r"\1\2אקטיבית"),
                (r"(^|[^\w])(ו?)מצטיין(?=$|[^\w])", r"\1\2מצטיינת"),
                (r"\bמומלץ להיות עצמאי\b", "מומלץ להיות עצמאית"),
                (r"\bהרעיונות המקוריים שלו\b", "הרעיונות המקוריים שלה"),
            ]
        elif source_gender == "female" and target_gender == "male":
            replacements = [
                (r"(^|[^\w])(ו?)היא(?=$|[^\w])", r"\1\2הוא"),
                (r"(^|[^\w])(ו?)שלה(?=$|[^\w])", r"\1\2שלו"),
                (r"(^|[^\w])(ו?)אותה(?=$|[^\w])", r"\1\2אותו"),
                (r"(^|[^\w])(ו?)לה(?=$|[^\w])", r"\1\2לו"),
                (r"(^|[^\w])(ו?)בה(?=$|[^\w])", r"\1\2בו"),
                (r"(^|[^\w])(ו?)עצמה(?=$|[^\w])", r"\1\2עצמו"),
                (r"(^|[^\w])(ו?)שולטת(?=$|[^\w])", r"\1\2שולט"),
                (r"(^|[^\w])(ו?)מרגישה(?=$|[^\w])", r"\1\2מרגיש"),
                (r"(^|[^\w])(ו?)עקשנית(?=$|[^\w])", r"\1\2עקשן"),
                (r"(^|[^\w])(ו?)רכושנית(?=$|[^\w])", r"\1\2רכושן"),
                (r"(^|[^\w])(ו?)קנאית(?=$|[^\w])", r"\1\2קנאי"),
                (r"(^|[^\w])(ו?)ביקורתית(?=$|[^\w])", r"\1\2ביקורתי"),
                (r"(^|[^\w])(ו?)עצמאית(?=$|[^\w])", r"\1\2עצמאי"),
                (r"(^|[^\w])(ו?)אקטיבית(?=$|[^\w])", r"\1\2אקטיבי"),
                (r"(^|[^\w])(ו?)מצטיינת(?=$|[^\w])", r"\1\2מצטיין"),
                (r"\bמומלץ להיות עצמאית\b", "מומלץ להיות עצמאי"),
                (r"\bהרעיונות המקוריים שלה\b", "הרעיונות המקוריים שלו"),
            ]
        else:
            return text

        adapted = text
        for pattern, replacement in replacements:
            adapted = re.sub(pattern, replacement, adapted)
        return adapted

    def render_interpretation(self, category, number, gender_folder_param, is_hidden_year=False,
                              is_peak_challenge_comb=False):
        """
        Public wrapper for all export and UI paths.
        Keeps gender resolution and auto-adaptation in one place.
        """
        return self.get_interpretation(
            category,
            number,
            gender_folder_param,
            is_hidden_year=is_hidden_year,
            is_peak_challenge_comb=is_peak_challenge_comb,
        )

    def get_interpretation(self, category, number, gender_folder_param, is_hidden_year=False,
                           is_peak_challenge_comb=False):
        if number is None: return f"[שגיאה: מספר לא חושב עבור קטגוריה '{category}']"

        gender_context = self._resolve_gender_context(gender_folder_param)
        gender_folder_actual = gender_context["target_folder"]
        suffix = gender_context["target_suffix"]
        alternate_folder = gender_context["alternate_folder"]
        alternate_suffix = gender_context["alternate_suffix"]
        target_gender = gender_context["target_gender"]

        original_file_name_part = ""
        alternative_file_name_part = None

        if is_peak_challenge_comb:
            original_file_name_part = str(number)
        elif is_hidden_year and isinstance(number, str) and "_" in number:
            original_file_name_part = number  # Expects number to be "X_Y"
            parts = number.split('_')
            if len(parts) == 2 and parts[0] != parts[1]:
                alternative_file_name_part = f"{parts[1]}_{parts[0]}"
        else:
            original_file_name_part = str(number)

        nested_interpretation_categories = [
            "birthdate_expression_type", "clothing_colors", "first_name_N AI API",
            "first_name_correcting", "first_name_love", "first_name_work",
            "hebrew_month", "human_aspiration",
            "missions_negative", "missions_positive",
            "name_expression_balanced", "name_expression_multiple", "name_expression_types",
            "number_groups", "pythagorean_square", "quarters_formulas", "quarters_interpretation"
        ]

        def try_read_file(folder_name, file_suffix, current_category, current_file_name_part_to_try):
            current_file_name = f"{current_file_name_part_to_try}{file_suffix}.txt"
            candidate_paths = runtime_interpretation_file_candidates(
                folder_name,
                current_category,
                current_file_name,
                nested=current_category in nested_interpretation_categories,
            )
            last_path = str(candidate_paths[0]) if candidate_paths else current_file_name
            for path_to_check in candidate_paths:
                try:
                    with open(path_to_check, 'r', encoding='utf-8') as f:
                        return f.read().strip(), str(path_to_check)
                except FileNotFoundError:
                    last_path = str(path_to_check)
                    continue
                except Exception as e:
                    return f"[interpretation file read error: {path_to_check}: {e}]", str(path_to_check)
            return None, last_path

        candidate_specs = [
            (gender_folder_actual, suffix),
            (gender_folder_actual, alternate_suffix),
            (alternate_folder, suffix),
            (alternate_folder, alternate_suffix),
        ]

        file_name_parts = [original_file_name_part]
        if is_hidden_year and alternative_file_name_part and alternative_file_name_part not in file_name_parts:
            file_name_parts.append(alternative_file_name_part)

        last_error = None
        for file_name_part in file_name_parts:
            for folder_name, file_suffix in candidate_specs:
                content, path_or_error = try_read_file(folder_name, file_suffix, category, file_name_part)
                if content is None:
                    last_error = f"[קובץ פרשנות לא נמצא: {path_or_error}]"
                    continue
                if isinstance(content, str) and content.startswith("[שגיאה בקריאת קובץ פרשנות"):
                    return content
                source_gender = self._infer_source_gender(path_or_error)
                return self._adapt_gender_text(content, source_gender, target_gender)

        return last_error or f"[קובץ פרשנות לא נמצא: {category}/{original_file_name_part}]"
    
    def calc_quarters_michal_green(self):
        # Calculate quarters based on peak/challenge or user logic
        # (Copied from original birthdate.py logic)
        if self.final_number_destiny is None or self.shana_ishit is None:
            return

        destiny = self.final_number_destiny
        personal_year = self.shana_ishit
        
        # Quarter 1: (Destiny + Personal Year) - if > 9 reduce
        q1_raw = destiny + personal_year
        self.first_quarter_reduced = self.short_number_single(q1_raw)
        
        # Quarter 2: (Q1 + Personal Year)
        q2_raw = self.first_quarter_reduced + personal_year
        self.second_quarter_reduced = self.short_number_single(q2_raw)
        
        # Quarter 3: (Q2 + Q1)
        q3_raw = self.second_quarter_reduced + self.first_quarter_reduced
        self.third_quarter_reduced = self.short_number_single(q3_raw)
        
        # Quarter 4: (Personal Year + Q3)
        q4_raw = personal_year + self.third_quarter_reduced
        self.forth_quarter_reduced = self.short_number_single(q4_raw)
        
        # Sequences (User requested sequences of 2 and 3)
        # Sequence of 2: Q1+Q2, Q2+Q3, Q3+Q4
        self.quarter_sequences_2 = []
        self.quarter_sequences_2.append(f"{self.first_quarter_reduced}{self.second_quarter_reduced}")
        self.quarter_sequences_2.append(f"{self.second_quarter_reduced}{self.third_quarter_reduced}")
        self.quarter_sequences_2.append(f"{self.third_quarter_reduced}{self.forth_quarter_reduced}")
        
        # Sequence of 3: Q1+Q2+Q3, Q2+Q3+Q4
        self.quarter_sequences_3 = []
        self.quarter_sequences_3.append(f"{self.first_quarter_reduced}{self.second_quarter_reduced}{self.third_quarter_reduced}")
        self.quarter_sequences_3.append(f"{self.second_quarter_reduced}{self.third_quarter_reduced}{self.forth_quarter_reduced}")

    def calc_green_snapshot(self, hebrew_birthdate=None):
        if not self.first_name_str or not self.last_name_str:
            return None
        green = NamesDataGreen()
        self.green_snapshot = green.analyze_full_name(
            first_name=self.first_name_str,
            last_name=self.last_name_str,
            day=self.original_day,
            month=self.original_month,
            year=self.original_year,
            hebrew_birthdate=hebrew_birthdate,
        )
        return self.green_snapshot
    def calculate(self, day, month, year, first_name, last_name, gender):
        # Reset state
        self.fulldate_list_for_pyth = None
        self.real_year = None
        self.real_month = None
        self.full_list = None
        self.original_day = None
        self.original_month = None
        self.original_year = None
        self.green_snapshot = None
        
        # Basic parsing
        self.real_year = int(year)
        self.real_month = int(month)
        self.original_day = int(day)
        self.original_month = int(month)
        self.original_year = int(year)
        today = datetime.date.today()
        
        # --- Date Calculation ---
        # Logic: Sum distinct digits, NOT the integer values of the parts.
        
        # 1. Day (Sum of digits)
        day_digits_sum = sum(int(d) for d in day)
        self.p_day = self.short_number_master(day_digits_sum)
        
        # 2. Month (Sum of digits)
        month_digits_sum = sum(int(d) for d in month)
        self.p_month = self.short_number_master(month_digits_sum)
        
        # 3. Year (Sum of digits)
        year_digits_sum = sum(int(d) for d in year)
        self.p_year = self.short_number_master(year_digits_sum)
        
        # Destiny (Sum of ALL digits)
        full_date_str = f"{day}{month}{year}"
        total_sum_digits = sum(int(d) for d in full_date_str)
        
        self.original_destiny_sum = total_sum_digits
        self.full_date_short = total_sum_digits
        self.final_number_destiny = self.short_number_master(total_sum_digits)
        
        # --- Names ---
        self.full_name = f"{first_name} {last_name}".strip()
        self.first_name_str = first_name
        self.last_name_str = last_name
        
        # Calculate Name Values (Gematria)
        names_data = name.NamesData()
        
        # 1. First Name
        self.first_name_val = names_data.letter(self.first_name_str)
        
        # 2. Full Name
        full_name_combined = self.first_name_str + self.last_name_str
        self.full_name_val = names_data.letter(full_name_combined)
        
        # 3. Consonants (Itzurim)
        # Filter letters that are defined as consonants in names_data.itzurim
        consonants_list = list(filter(names_data.itzurim, full_name_combined))
        self.itzurim_val = names_data.letter(consonants_list)
        
        # 4. Vowels (Aiv)
        # Filter letters that are defined as vowels in names_data.aiv
        vowels_list = list(filter(names_data.aiv, full_name_combined))
        self.aiv_val = names_data.letter(vowels_list)
        
        # --- Personal Year & Age ---
        py_calc = personal_y.This_Year()
        
        # 1. Personal Year
        # Requires p_day, p_month (reduced) and real month
        if self.p_day is not None and self.p_month is not None and self.real_month is not None:
             self.shana_ishit = py_calc.shana_ishit(day=self.p_day, month=self.p_month, bd_month=self.real_month)
        else:
             self.shana_ishit = None

        # 2. Age & Tzimtzum Age
        if self.real_month is not None and self.real_year is not None:
             self.age = py_calc.calculet_age(year_of_birth=self.real_year, bd_month=self.real_month)
             self.tzimtzum_age = self.short_number_single(self.age) if self.age is not None else None
        else:
             self.age = None
             self.tzimtzum_age = None
             
        # 3. Hidden Year (Shana Nisteret) - Restore original logic for "X_Y" format
        # This logic was originally in birthdate.py and is distinct from personal_y.shana_nisteret
        current_gregorian_year = today.year
        universal_year_sum = sum(int(digit) for digit in str(current_gregorian_year))
        universal_year_reduced = self.short_number_single(universal_year_sum)

        if self.p_day is not None and self.p_month is not None and universal_year_reduced is not None and self.final_number_destiny is not None:
            x_sum = self.p_day + self.p_month + universal_year_reduced
            x_reduced = self.short_number_master(x_sum)
            y_sum = x_reduced + self.final_number_destiny
            y_reduced = self.short_number_master(y_sum)
            self.shana_nisteret = f"{x_reduced}_{y_reduced}"
        else:
            self.shana_nisteret = None
        
        # --- Peaks & Challenges ---
        # Reduced values for calculation
        r_day = self.short_number_single(day)
        r_month = self.short_number_single(month)
        r_year = self.short_number_single(year)
        
        # Challenges
        self.first_challenge = abs(r_day - r_month)
        self.challenge1_reduced = self.short_number_single(self.first_challenge)
        
        self.second_challenge = abs(r_day - r_year)
        self.challenge2_reduced = self.short_number_single(self.second_challenge)
        
        self.third_challenge = abs(self.first_challenge - self.second_challenge)
        self.challenge3_reduced = self.short_number_single(self.third_challenge)
        
        self.forth_challenge = abs(r_month - r_year)
        self.challenge4_reduced = self.short_number_single(self.forth_challenge)
        
        # Peaks
        self.first_pick = r_day + r_month
        self.peak1_reduced = self.short_number_single(self.first_pick)
        
        self.second_pick = r_day + r_year
        self.peak2_reduced = self.short_number_single(self.second_pick)
        
        self.third_pick = self.first_pick + self.second_pick
        self.peak3_reduced = self.short_number_single(self.third_pick)
        
        self.forth_pick = r_month + r_year
        self.peak4_reduced = self.short_number_single(self.forth_pick)
        
        # Ages for peaks (Calculated based on Destiny Number)
        # Peak 1 ends at (36 - Destiny)
        if self.final_number_destiny:
            self.first_pick_start = 36 - self.short_number_single(self.final_number_destiny)
        else:
            self.first_pick_start = 36 # Default fallback?
            
        self.second_pick_start = self.first_pick_start + 1 + 9 # +9 years cycle
        self.third_pick_start = self.second_pick_start + 9
        self.forth_pick_start = self.third_pick_start + 9
        
        # --- Quarters ---
        self.calc_quarters_michal_green()

        # --- Green Snapshot ---
        self.calc_green_snapshot()

        return {
            "p_day": self.p_day,
            "p_month": self.p_month,
            "p_year": self.p_year,
            "final_number_destiny": self.final_number_destiny,
            "full_name": self.full_name,
            "age": self.age,
            "shana_ishit": self.shana_ishit
        }








