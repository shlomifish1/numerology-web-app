import tkinter as tk
from tkinter import ttk, messagebox
from config_manager import ConfigManager

class SettingsUI:
    def __init__(self, parent, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.window = tk.Toplevel(parent)
        self.window.title("נומרולוגיה - הגדרות מערכת")
        self.window.geometry("600x500")
        self.window.resizable(False, False)
        
        # RTL support for UI
        self.style = ttk.Style()
        self.style.configure("RTL.TLabel", anchor="e")
        self.style.configure("RTL.TEntry", justify="right")

        self.create_widgets()

    def create_widgets(self):
        main_frame = ttk.Frame(self.window, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- API Keys Section ---
        keys_frame = ttk.LabelFrame(main_frame, text="API Keys", padding="10")
        keys_frame.pack(fill=tk.X, pady=10)

        # Google AI
        ttk.Label(keys_frame, text="Google Gemini Key:").grid(row=0, column=2, sticky="e", padx=5)
        self.google_key_var = tk.StringVar(value=self.config_manager.get_api_key("google_ai"))
        ttk.Entry(keys_frame, textvariable=self.google_key_var, width=40).grid(row=0, column=0, columnspan=2, sticky="ew")

        # OpenAI
        ttk.Label(keys_frame, text="OpenAI Key:").grid(row=1, column=2, sticky="e", padx=5, pady=5)
        self.openai_key_var = tk.StringVar(value=self.config_manager.get_api_key("openai"))
        ttk.Entry(keys_frame, textvariable=self.openai_key_var, width=40).grid(row=1, column=0, columnspan=2, sticky="ew")

        # Hugging Face
        ttk.Label(keys_frame, text="Hugging Face Key:").grid(row=2, column=2, sticky="e", padx=5)
        self.hf_key_var = tk.StringVar(value=self.config_manager.get_api_key("hugging_face"))
        ttk.Entry(keys_frame, textvariable=self.hf_key_var, width=40).grid(row=2, column=0, columnspan=2, sticky="ew")
        
        # --- Drive Settings ---
        drive_frame = ttk.LabelFrame(main_frame, text="Google Drive", padding="10")
        drive_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(drive_frame, text="Folder ID:").grid(row=0, column=2, sticky="e", padx=5)
        self.drive_folder_var = tk.StringVar(value=self.config_manager.get("drive_folder_id", ""))
        ttk.Entry(drive_frame, textvariable=self.drive_folder_var, width=40).grid(row=0, column=0, columnspan=2, sticky="ew")

        # --- Models Section ---
        models_frame = ttk.LabelFrame(main_frame, text="ניהול מודלים (Model Management)", padding="10")
        models_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Model List Listbox
        list_frame = ttk.Frame(models_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical")
        self.models_listbox = tk.Listbox(list_frame, height=6, yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.models_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.models_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.refresh_models_list()
        
        # Add Model Controls
        controls_frame = ttk.Frame(models_frame)
        controls_frame.pack(fill=tk.X, pady=5)
        
        self.new_model_name = tk.StringVar()
        ttk.Entry(controls_frame, textvariable=self.new_model_name, width=20).pack(side=tk.RIGHT, padx=5)
        ttk.Label(controls_frame, text=":שם מודל").pack(side=tk.RIGHT)
        
        self.new_model_provider = tk.StringVar(value="google")
        ttk.OptionMenu(controls_frame, self.new_model_provider, "google", "google", "openai", "huggingface").pack(side=tk.RIGHT, padx=5)
        
        ttk.Button(controls_frame, text="הוסף מודל", command=self.add_model).pack(side=tk.RIGHT, padx=5)
        ttk.Button(controls_frame, text="מחק נבחר", command=self.remove_model).pack(side=tk.LEFT, padx=5)
        
        # --- Active Model Selector ---
        active_frame = ttk.Frame(main_frame)
        active_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(active_frame, text=":מודל פעיל לשיחה").pack(side=tk.RIGHT, padx=5)
        self.active_model_var = tk.StringVar(value=self.config_manager.get("active_model", "gemini-flash-latest"))
        self.model_selector = ttk.Combobox(active_frame, textvariable=self.active_model_var)
        self.update_selector_values()
        self.model_selector.pack(side=tk.RIGHT)

        # --- Action Buttons ---
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=20)
        
        ttk.Button(btn_frame, text="שמור וסגור", command=self.save_settings).pack(side=tk.LEFT, expand=True)
        ttk.Button(btn_frame, text="ביטול", command=self.window.destroy).pack(side=tk.RIGHT, expand=True)

    def refresh_models_list(self):
        self.models_listbox.delete(0, tk.END)
        models = self.config_manager.get("models", [])
        for m in models:
            self.models_listbox.insert(tk.END, f"{m['name']} ({m['provider']})")

    def update_selector_values(self):
        models = self.config_manager.get("models", [])
        values = [m['name'] for m in models]
        self.model_selector['values'] = values

    def add_model(self):
        name = self.new_model_name.get().strip()
        provider = self.new_model_provider.get()
        if not name:
            return
            
        models = self.config_manager.get("models", [])
        # Check duplicate
        if any(m['name'] == name for m in models):
            messagebox.showwarning("שגיאה", "מודל זה כבר קיים ברשימה.")
            return

        models.append({"name": name, "provider": provider, "display_name": name})
        self.config_manager.set("models", models)
        self.refresh_models_list()
        self.update_selector_values()
        self.new_model_name.set("")

    def remove_model(self):
        sel = self.models_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        models = self.config_manager.get("models", [])
        name_to_remove = models[idx]['name']
        
        # Prevent removing active model
        if name_to_remove == self.active_model_var.get():
            messagebox.showerror("שגיאה", "לא ניתן למחוק את המודל הפעיל.")
            return

        models.pop(idx)
        self.config_manager.set("models", models)
        self.refresh_models_list()
        self.update_selector_values()

    def save_settings(self):
        # Save Keys
        self.config_manager.set_api_key("google_ai", self.google_key_var.get().strip())
        self.config_manager.set_api_key("openai", self.openai_key_var.get().strip())
        self.config_manager.set_api_key("hugging_face", self.hf_key_var.get().strip())
        
        # Save Drive
        self.config_manager.set("drive_folder_id", self.drive_folder_var.get().strip())
        
        # Save Active Model
        self.config_manager.set("active_model", self.active_model_var.get())
        
        messagebox.showinfo("הגדרות", "ההגדרות נשמרו בהצלחה!")
        self.window.destroy()
