from tkinter import *
from PIL import Image, ImageGrab
import os
from tkinter import filedialog

import os

def save_image(canvas, print_full_name):
    # Get the full name from the canvas
    full_name = canvas.itemcget(print_full_name, 'text')  # Assuming 'print_full_name' is the item id for the full name text on the canvas

    # Ask the user to select a file path
    save_path = filedialog.asksaveasfilename(defaultextension=".png", initialfile=full_name)

    # Check if a file path was selected
    if save_path:
        # Get the dimensions of the canvas
        x = canvas.winfo_rootx()
        y = canvas.winfo_rooty()
        w = canvas.winfo_width()
        h = canvas.winfo_height()

        # Take a screenshot of the canvas
        image = ImageGrab.grab(bbox=(x, y, x + w, y + h))

        # Save the image with the selected file path
        image.save(save_path)

        print("Image saved successfully!")
