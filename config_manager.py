import json
import os

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "api_keys": {
        "google_ai": "",
        "openai": "",
        "hugging_face": ""
    },
    "models": [
        {"name": "gemini-flash-latest", "provider": "google", "display_name": "Gemini Flash (Latest)"},
        {"name": "gemini-1.5-pro", "provider": "google", "display_name": "Gemini 1.5 Pro"},
        {"name": "gpt-4o", "provider": "openai", "display_name": "GPT-4o"},
        {"name": "gpt-4o-mini", "provider": "openai", "display_name": "GPT-4o Mini"}
    ],
    "active_model": "gemini-flash-latest",
    "drive_folder_id": "1hwxbvU8lsugqqIGP6yJHhLL5s5M_yKnG" # Pre-populated from user request
}

class ConfigManager:
    def __init__(self):
        self.config = self.load_config()

    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            self.save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}. Using defaults.")
            return DEFAULT_CONFIG

    def save_config(self, config=None):
        if config:
            self.config = config
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save_config()

    def get_api_key(self, provider):
        # Try Streamlit Secrets first (for Cloud Deployment)
        try:
            import streamlit as st
            # Check for secrets only if we are in a Streamlit context
            if hasattr(st, "secrets"):
                # Map internal keys to common secret names if needed, or query directly
                if provider == "google_ai" and "GOOGLE_API_KEY" in st.secrets:
                    return st.secrets["GOOGLE_API_KEY"]
                if provider in st.secrets:
                    return st.secrets[provider]
        except ImportError:
            pass # Streamlit not installed or not active
        except Exception:
            pass # Secrets not available

        # Fallback to local config.json
        return self.config.get("api_keys", {}).get(provider, "")

    def set_api_key(self, provider, key):
        if "api_keys" not in self.config:
            self.config["api_keys"] = {}
        self.config["api_keys"][provider] = key
        self.save_config()
