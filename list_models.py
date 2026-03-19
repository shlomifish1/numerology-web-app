import os

import google.generativeai as genai

from config_manager import ConfigManager


def _get_api_key() -> str:
    config_key = ConfigManager().get_api_key("google_ai")
    return (
        os.getenv("GOOGLE_API_KEY", "").strip()
        or os.getenv("GENAI_API_KEY", "").strip()
        or config_key.strip()
    )


def list_models() -> list[str]:
    api_key = _get_api_key()
    if not api_key:
        return []

    genai.configure(api_key=api_key)
    models: list[str] = []
    try:
        for model in genai.list_models():
            if "generateContent" in model.supported_generation_methods:
                models.append(model.name)
    except Exception as e:
        print(f"Error listing models: {e}")
    return models


if __name__ == "__main__":
    print("Listing models...")
    for name in list_models():
        print(name)
