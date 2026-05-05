import tkinter as tk
from tkinter import ttk
from chat_manager import ChatManager
import threading

class ChatUI(tk.Frame):
    def __init__(self, parent, chat_manager: ChatManager, **kwargs):
        # --- תיקון השגיאה כאן ---
        # אנחנו בודקים אם נשלח צבע רקע (bg) מהקובץ הראשי, ומוחקים אותו
        # כדי שלא יהיה כפל נתונים. אנחנו רוצים שחור בלבד.
        if 'bg' in kwargs:
            kwargs.pop('bg')
            
        # עכשיו אנחנו מגדירים את הרקע לשחור (#000000)
        super().__init__(parent, bg="#000000", **kwargs)
        
        self.chat_manager = chat_manager
        self.create_widgets()

    def create_widgets(self):
        # Title - כותרת שחורה עם טקסט לבן
        lbl_title = tk.Label(self, text="AI Chat Assistant", font=("Arial", 12, "bold"), 
                           bg="#000000", fg="#FFFFFF")
        lbl_title.pack(side=tk.TOP, fill=tk.X, pady=5)

        # Chat History - תיבת הטקסט נשארת כרגע בלבן לקריאות
        self.txt_history = tk.Text(self, state=tk.DISABLED, wrap=tk.WORD, font=("Arial", 10), height=20)
        
        scrollbar = ttk.Scrollbar(self, command=self.txt_history.yview)
        self.txt_history['yscrollcommand'] = scrollbar.set
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_history.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=2)
        
        # Tag configuration
        self.txt_history.tag_config("user", foreground="blue", justify="right")
        self.txt_history.tag_config("ai", foreground="black", justify="right")
        self.txt_history.tag_config("error", foreground="red")

        # Input Area - מסגרת תחתונה בשחור
        input_frame = tk.Frame(self, bg="#000000")
        input_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        
        self.entry_msg = tk.Entry(input_frame, font=("Arial", 11))
        self.entry_msg.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=5, pady=5)
        self.entry_msg.bind("<Return>", self.send_message)
        
        # כפתור מעוצב כהה
        btn_send = tk.Button(input_frame, text="שלח", command=self.send_message, bg="#333333", fg="white")
        btn_send.pack(side=tk.LEFT, padx=5)

    def send_message(self, event=None):
        msg = self.entry_msg.get().strip()
        if not msg:
            return

        self.entry_msg.delete(0, tk.END)
        self.append_text(f"You: {msg}\n", "user")

        threading.Thread(target=self._process_message, args=(msg,), daemon=True).start()

    def _process_message(self, msg):
        try:
            response = self.chat_manager.send_message(msg)
            self.after(0, lambda: self.append_text(f"AI: {response}\n\n", "ai"))
        except Exception as e:
            self.after(0, lambda: self.append_text(f"Error: {str(e)}\n", "error"))

    def append_text(self, text, tag):
        self.txt_history.config(state=tk.NORMAL)
        self.txt_history.insert(tk.END, text, tag)
        self.txt_history.see(tk.END)
        self.txt_history.config(state=tk.DISABLED)