import os
import sys
import subprocess
import webbrowser
import mss
import mss.tools
import pyautogui
from datetime import datetime

# Setup for CachyOS/Linux
def _is_linux():
    return sys.platform.startswith("linux")

def search_web(query):
    """Opens a google search."""
    url = f"https://www.google.com/search?q={query}"
    webbrowser.open(url)
    return f"Searching web for: {query}"

def open_url(url):
    """Opens a specific URL."""
    if not url.startswith("http"):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened: {url}"

def launch_application(app_name):
    """Launches an app using subprocess."""
    try:
        # Linux specific generic launcher
        if _is_linux():
            subprocess.Popen(["gtk-launch", app_name]) 
        else:
            subprocess.Popen(app_name, shell=True)
        return f"Launched {app_name}"
    except Exception as e:
        return f"Failed to launch {app_name}: {e}"

def get_application_list():
    """Crude listing of apps (Linux specific example)."""
    # In reality, parsing .desktop files is complex. 
    # This is a simplified placeholder.
    return "List of apps requires complex parsing of /usr/share/applications"

def take_screenshot():
    """Takes a screenshot using MSS (works better on Linux than pyautogui)."""
    try:
        with mss.mss() as sct:
            filename = f"/tmp/screenshot_{datetime.now().strftime('%H%M%S')}.png"
            sct.shot(mon=-1, output=filename)
            return f"IMAGE_PATH:{filename}"
    except Exception as e:
        return f"Screenshot failed: {e}"

def get_screen_size():
    width, height = pyautogui.size()
    return f"{width}x{height}"

def mouse_click(coords_str):
    """Moves mouse and clicks. Format: 'x,y'"""
    try:
        x, y = map(int, coords_str.replace(",", " ").split())
        pyautogui.click(x, y)
        return f"Clicked at {x}, {y}"
    except Exception as e:
        return f"Click failed: {e}"

def keyboard_type(text):
    pyautogui.write(text)
    return f"Typed: {text}"

def read_file(path):
    if not os.path.exists(path): return "File not found."
    with open(path, 'r') as f:
        return f.read()

def write_file(args):
    """Expects 'path|content'"""
    try:
        if "|" in args:
            path, content = args.split("|", 1)
        else:
            return "Error: Use format 'path|content'"
        
        with open(path, 'w') as f:
            f.write(content)
        return f"Wrote to {path}"
    except Exception as e:
        return f"Write failed: {e}"

# Stubs for audio to prevent crashes if main calls them
def stop_audio(): pass
def speak(text): pass
