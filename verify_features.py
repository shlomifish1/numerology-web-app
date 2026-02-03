import sys
import os

print("Verifying modules...")

try:
    print("1. Testing ConfigManager...")
    from config_manager import ConfigManager
    cm = ConfigManager()
    print(f"   Config loaded. Active Model: {cm.get('active_model')}")
    print("   PASSED")
except Exception as e:
    print(f"   FAILED: {e}")

try:
    print("2. Testing ChatManager...")
    from chat_manager import ChatManager
    chat = ChatManager(cm)
    # Don't send message to avoid API cost/auth issues in automated test, just init
    print("   ChatManager initialized.")
    print("   PASSED")
except Exception as e:
    print(f"   FAILED: {e}")

try:
    print("3. Testing DriveUploader import...")
    from drive_uploader import DriveUploader
    du = DriveUploader()
    print("   DriveUploader initialized (auth deferred).")
    print("   PASSED")
except Exception as e:
    print(f"   FAILED: {e}")

try:
    print("4. Testing ReportEditor import...")
    # ReportEditor requires a Tk root, so we skip full init but check import
    from report_editor import ReportEditor
    print("   ReportEditor imported.")
    print("   PASSED")
except Exception as e:
    print(f"   FAILED: {e}")

try:
    print("5. Testing SettingsUI import...")
    from settings_ui import SettingsUI
    print("   SettingsUI imported.")
    print("   PASSED")
except Exception as e:
    print(f"   FAILED: {e}")

print("\nVerification Complete.")
