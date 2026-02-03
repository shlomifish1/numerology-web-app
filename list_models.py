import google.generativeai as genai

genai.configure(api_key="AIzaSyDPevIx7UW4cWFZ_Hb0NGLLFrps-va-W2c")

print("Listing models...")
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(m.name)
except Exception as e:
    print(f"Error listing models: {e}")
