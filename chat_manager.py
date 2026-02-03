import google.generativeai as genai
import os
from config_manager import ConfigManager

class ChatManager:
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.history = []
        self.chat = None
        # רשימת התיקיות והקבצים שמהם נתעלם (כדי לא להעמיס זבל ולחסוך טוקנים)
        self.ignore_dirs = {'.git', '__pycache__', 'venv', 'venv1', 'venv2', '.idea', 'build', 'dist', 'save_data', 'interpretations'}
        self.ignore_files = {'credentials.json', 'config.json', '.DS_Store', 'my_program.spec'} 
        self._setup_model()

    def _get_project_context(self):
        """
        פונקציה זו היא ה'מוח'. היא סורקת את כל קבצי הקוד וההסברים בתיקייה
        ויוצרת מסמך אחד גדול שה-AI קורא לפני השיחה.
        """
        context_str = "You are an AI assistant embedded inside a Numerology Software named 'Numerology by Shlomi Fishman'.\n"
        context_str += "Below is the full source code and documentation of the project you are running in.\n"
        context_str += "Use this context to answer user questions about the code, logic, errors, or numerology meanings.\n"
        context_str += "If the user asks to fix code, provide the full corrected code for the specific file.\n\n"
        context_str += "--- START OF PROJECT FILES ---\n"

        root_dir = os.path.dirname(os.path.abspath(__file__))

        for root, dirs, files in os.walk(root_dir):
            # סינון תיקיות לא רלוונטיות
            dirs[:] = [d for d in dirs if d not in self.ignore_dirs]
            
            for file in files:
                if file in self.ignore_files:
                    continue
                
                # אנחנו קוראים רק קבצי קוד, ג'ייסון וקבצי טקסט (פרשנויות)
                if file.endswith('.py') or file.endswith('.txt') or file.endswith('.md') or file.endswith('.json'):
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, root_dir)
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            # הוספת הקובץ לקונטקסט
                            context_str += f"\nFile: {rel_path}\n"
                            context_str += "```\n"
                            context_str += content
                            context_str += "\n```\n"
                            context_str += "-" * 20 + "\n"
                    except Exception as e:
                        print(f"Skipping file {rel_path} due to read error: {e}")

        context_str += "--- END OF PROJECT FILES ---\n"
        context_str += "Answer the user's questions based on the code and logic provided above."
        return context_str

    def _setup_model(self):
        # אתחול המודל עם מפתח ה-API
        api_key = self.config_manager.get_api_key("google_ai")
        model_name = self.config_manager.get("active_model", "gemini-flash-latest")
        
        if api_key:
            genai.configure(api_key=api_key)
            
        try:
            # כאן אנחנו טוענים את כל הפרויקט לזיכרון של ה-AI
            # שים לב: זה קורה רק כשפותחים את הצ'אט, אז זה לא מכביד על העבודה השוטפת
            system_instruction = self._get_project_context()
            
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system_instruction
            )
            self.chat = model.start_chat(history=self.history)
            print("AI Chat initialized with full project context (RAG).")
        except Exception as e:
            print(f"Error initializing chat: {e}")
            self.chat = None

    def send_message(self, message):
        if not self.chat:
            self._setup_model()
            if not self.chat:
                return "Error: Could not initialize AI model. Check API Key in Settings."

        try:
            response = self.chat.send_message(message)
            return response.text
        except Exception as e:
            return f"Error: {str(e)}"

    def clear_history(self):
        self.history = []
        self._setup_model()