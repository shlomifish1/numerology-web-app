from tkinter import *
from PIL import Image, ImageGrab
import os

def save_image(canvas):
    # פתיחת תיקייה עבור שמירת התמונה
    save_path = filedialog.asksaveasfilename(defaultextension=".png")
    if save_path:
        # צילום התמונה מה-Canvas
        x = canvas.winfo_rootx() + canvas.winfo_x()
        y = canvas.winfo_rooty() + canvas.winfo_y()
        x1 = x + canvas.winfo_width()
        y1 = y + canvas.winfo_height()
        image = ImageGrab.grab((x, y, x1, y1))
        # שמירת התמונה
        image.save(save_path)
        print("Image saved successfully!")
