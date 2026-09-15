import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageDraw
import pystray
import threading
import platform
import os

root = tk.Tk()
root.withdraw()
is_popup_showing = False

def show_warning_popup(message):
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning("安全與健康警告", message)
        root.destroy()
    except Exception:
        print(f"健康與安全警告 {message}")

def create_icon_image():
    """繪製系統匣的圖示"""
    image = Image.new('RGB', (64, 64), 'white')
    dc = ImageDraw.Draw(image)
    dc.ellipse((10, 10, 54, 54), fill='#800000')
    return image

def setup_system_tray(on_quit_callback):
    """建立並於後台執行Windows系統匣"""
    icon = pystray.Icon(
        "all_in_one_monitor",
        create_icon_image(),
        "AI資安與健康動態防禦中",
        menu=pystray.Menu(pystray.MenuItem("結束程式", lambda icon_obj, item: on_quit_callback(icon_obj)))
    )
    # 在背景執行系統匣避免阻塞主執行緒
    threading.Thread(target=icon.run, daemon=True).start()
    return icon

def start_gui_loop():
    """啟動Tkinter核心迴圈"""
    root.mainloop()

def stop_gui_loop():
    """關閉Tkinter核心迴圈"""
    root.quit()