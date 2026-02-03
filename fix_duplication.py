
import os

FILENAME = "birthdate.py"

def fix_file():
    with open(FILENAME, "r", encoding="utf-8") as f:
        lines = f.readlines()

    start_cut_line = 1037
    end_cut_line = 1293
    
    # Check boundaries
    # Line 1037 index is 1036
    # Line 1293 index is 1292
    
    idx_start = start_cut_line - 1
    idx_end = end_cut_line - 1
    
    print(f"Checking line {start_cut_line}: {lines[idx_start].strip()}")
    if "if self.p_day is None:" not in lines[idx_start]:
        print("Mismatch at start line!")
        return

    print(f"Checking line {end_cut_line + 1}: {lines[idx_end + 1].strip()}")
    # We expect 'def get_date(self):' at line 1294 (index 1293)
    if "def get_date" not in lines[idx_end + 1]:
        print("Mismatch at end line!")
        return

    # Delete inclusive
    new_lines = lines[:idx_start] + lines[idx_end + 1:]
    
    with open(FILENAME, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    
    print("File updated successfully.")

if __name__ == "__main__":
    fix_file()
