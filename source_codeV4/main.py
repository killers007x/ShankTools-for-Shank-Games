#!/usr/bin/env python3
"""
ShankTools
TEX/PNG Converter + Lua Decompiler/Compiler + CHUI Editor + CANIM Parser + CANIM-META Editor + Plugins
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import threading
import importlib.util
import sys
import os
import ctypes
import math
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from KTEX_Tool import KTEXConverter
except:
    KTEXConverter = None

try:
    from luaQ import decompile_file, compile_lua_file
except:
    def decompile_file(*args): return False
    def compile_lua_file(*args): return False

try:
    from chui import CHUIConverter
    CHUI_AVAILABLE = True
except ImportError:
    CHUI_AVAILABLE = False

try:
    from canim import (parse_canim, batch_report,
                       export_canim_to_json, rebuild_canim_from_json,
                       batch_export, batch_rebuild, verify_roundtrip)
    CANIM_PARSER_AVAILABLE = True
except ImportError:
    CANIM_PARSER_AVAILABLE = False

try:
    from canim_meta import (CAnimMeta, MHITEntry, MCOLEntry,
                            export_json, import_json,
                            verify_roundtrip as meta_verify_roundtrip,
                            verify_silent,
                            batch_analyze, detailed_view)
    CANIM_META_AVAILABLE = True
except ImportError:
    CANIM_META_AVAILABLE = False

try:
    from PIL import Image, ImageTk, ImageEnhance # pyright: ignore[reportMissingImports] 
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def set_title_bar_color(window, color):
    if sys.platform != "win32":
        return False
    try:
        if isinstance(color, str):
            color = color.lstrip('#')
            r, g, b = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
        else:
            r, g, b = color
        window.update()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        color_ref = ctypes.c_int(r | (g << 8) | (b << 16))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color_ref), ctypes.sizeof(color_ref))
        dark_mode = ctypes.c_int(1 if (0.299*r + 0.587*g + 0.114*b) < 128 else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))
        return True
    except:
        return False


def get_average_color(image):
    try:
        small = image.resize((50, 50))
        pixels = list(small.getdata())
        if len(pixels[0]) >= 3:
            return (
                sum(p[0] for p in pixels) // len(pixels),
                sum(p[1] for p in pixels) // len(pixels),
                sum(p[2] for p in pixels) // len(pixels)
            )
    except:
        pass
    return None


class ThemeManager:
    THEME = {
        "bg": "#1a0a2e", "fg": "#e8d5f2",
        "button_bg": "#5c2a7e", "button_fg": "#ffffff",
        "button_active": "#8b45b5", "frame_bg": "#2d1448",
        "accent": "#bf5af2", "success": "#32d74b",
        "warning": "#ff9f0a", "titlebar": "#1a0a2e",
        "flash_color": "#bf5af2", "progress_bg": "#2d1448",
        "progress_fg": "#bf5af2"
    }
    @classmethod
    def get_theme(cls):
        return cls.THEME


class FlashEffect:
    def __init__(self, app):
        self.app = app
        self.is_flashing = False
        self.flash_step = 0
        self.total_steps = 20
        self.original_bg = None
        self.original_frame_bg = None
        self.flash_type = "success"

    def hex_to_rgb(self, hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def rgb_to_hex(self, rgb):
        return "#{:02x}{:02x}{:02x}".format(
            max(0, min(255, int(rgb[0]))),
            max(0, min(255, int(rgb[1]))),
            max(0, min(255, int(rgb[2]))))

    def blend_colors(self, color1, color2, factor):
        r1, g1, b1 = self.hex_to_rgb(color1)
        r2, g2, b2 = self.hex_to_rgb(color2)
        return self.rgb_to_hex((r1+(r2-r1)*factor, g1+(g2-g1)*factor, b1+(b2-b1)*factor))

    def start_flash(self, flash_type="success"):
        if self.is_flashing:
            return
        self.flash_type = flash_type
        self.is_flashing = True
        self.flash_step = 0
        theme = ThemeManager.get_theme()
        self.original_bg = theme["bg"]
        self.original_frame_bg = theme["frame_bg"]
        self._animate_flash()

    def _animate_flash(self):
        if not self.is_flashing:
            return
        theme = ThemeManager.get_theme()
        flash_colors = {"success": theme.get("flash_color", "#00ff88"), "error": "#ff4444"}
        flash_color = flash_colors.get(self.flash_type, theme.get("warning", "#ffaa00"))
        half = self.total_steps // 2
        if self.flash_step < half:
            intensity = math.sin((self.flash_step / half) * math.pi / 2)
        else:
            intensity = math.cos(((self.flash_step - half) / half) * math.pi / 2)
        current_bg = self.blend_colors(self.original_bg, flash_color, intensity * 0.4)
        current_frame_bg = self.blend_colors(self.original_frame_bg, flash_color, intensity * 0.3)
        self._apply_flash_colors(current_bg, current_frame_bg)
        if self.app.bg_image and PIL_AVAILABLE:
            self._flash_background_image(intensity)
        self.flash_step += 1
        if self.flash_step < self.total_steps:
            self.app.window.after(50, self._animate_flash)
        else:
            self.is_flashing = False
            self.app.apply_theme()
            if self.app.bg_image:
                self.app.update_background()

    def _apply_flash_colors(self, bg_color, frame_bg_color):
        try:
            for widget in [self.app.window, self.app.main_container, self.app.canvas, self.app.content_frame]:
                widget.configure(bg=bg_color)
            if not self.app.bg_image:
                self.app.bg_label.configure(bg=bg_color)
            for widget in [self.app.title_label, self.app.status, self.app.log_label]:
                widget.configure(bg=bg_color)
            for frame in self.app.section_frames:
                frame.configure(bg=frame_bg_color)
            for frame in self.app.inner_frames:
                frame.configure(bg=frame_bg_color)
        except:
            pass

    def _flash_background_image(self, intensity):
        if not PIL_AVAILABLE or self.app.bg_image is None:
            return
        try:
            width = self.app.window.winfo_width()
            height = self.app.window.winfo_height()
            if width > 1 and height > 1:
                resized = self.app.bg_image.resize((width, height), Image.Resampling.LANCZOS)
                enhancer = ImageEnhance.Brightness(resized)
                brightened = enhancer.enhance(1.0 + intensity * 0.5)
                self.app.bg_photo = ImageTk.PhotoImage(brightened)
                self.app.bg_label.configure(image=self.app.bg_photo)
        except:
            pass


class PluginManager:
    def __init__(self, app):
        self.app = app
        self.plugins = []
        self.plugin_frames = []
        self.plugins_folder = Path(__file__).parent / "plugins"
        self.plugins_folder.mkdir(exist_ok=True)
        self._create_example_plugins()

    def _create_example_plugins(self):
        text_processor = self.plugins_folder / "text_processor.py"
        if not text_processor.exists():
            text_processor.write_text('''"""
Text Processor Plugin
"""

PLUGIN_INFO = {
    "name": "Text Processor",
    "description": "Process and convert text files",
    "author": "ShankTools",
    "version": "1.0",
    "icon": "📝"
}

def get_actions():
    return [
        {"row": 1, "buttons": [
            {"text": "Convert to Uppercase", "width": 20, "command": "to_uppercase"},
            {"text": "Convert Folder", "width": 16, "command": "to_uppercase_folder"}
        ]},
        {"row": 2, "buttons": [
            {"text": "Convert to Lowercase", "width": 20, "command": "to_lowercase"},
            {"text": "Convert Folder", "width": 16, "command": "to_lowercase_folder"}
        ]},
        {"row": 3, "buttons": [
            {"text": "Count Lines", "width": 20, "command": "count_lines"},
            {"text": "Count in Folder", "width": 16, "command": "count_lines_folder"}
        ]}
    ]

def to_uppercase(app):
    from tkinter import filedialog, messagebox
    file_path = filedialog.askopenfilename(title="Select Text File", filetypes=[("Text files", "*.txt"), ("All", "*.*")])
    if not file_path: return
    try:
        with open(file_path, 'r', encoding='utf-8') as f: content = f.read()
        output_path = file_path.rsplit('.', 1)[0] + '_UPPER.txt'
        with open(output_path, 'w', encoding='utf-8') as f: f.write(content.upper())
        app.log_message(f"[OK] Converted: {output_path}")
        app.trigger_success_flash()
        messagebox.showinfo("Success", f"Saved to: {output_path}")
    except Exception as e:
        app.log_message(f"[ERROR] {e}")
        app.trigger_error_flash()

def to_uppercase_folder(app):
    from tkinter import filedialog, messagebox
    import os
    folder = filedialog.askdirectory(title="Select Folder")
    if not folder: return
    output_folder = os.path.join(folder, "uppercase_output")
    os.makedirs(output_folder, exist_ok=True)
    files = [f for f in os.listdir(folder) if f.endswith('.txt')]
    success = 0
    for filename in files:
        try:
            with open(os.path.join(folder, filename), 'r', encoding='utf-8') as f: content = f.read()
            with open(os.path.join(output_folder, filename), 'w', encoding='utf-8') as f: f.write(content.upper())
            app.log_message(f"[OK] {filename}")
            success += 1
        except Exception as e: app.log_message(f"[ERROR] {filename}: {e}")
    if success > 0: app.trigger_success_flash()
    messagebox.showinfo("Done", f"Converted {success}/{len(files)} files")

def to_lowercase(app):
    from tkinter import filedialog, messagebox
    file_path = filedialog.askopenfilename(title="Select Text File", filetypes=[("Text files", "*.txt"), ("All", "*.*")])
    if not file_path: return
    try:
        with open(file_path, 'r', encoding='utf-8') as f: content = f.read()
        output_path = file_path.rsplit('.', 1)[0] + '_lower.txt'
        with open(output_path, 'w', encoding='utf-8') as f: f.write(content.lower())
        app.log_message(f"[OK] Converted: {output_path}")
        app.trigger_success_flash()
        messagebox.showinfo("Success", f"Saved to: {output_path}")
    except Exception as e:
        app.log_message(f"[ERROR] {e}")
        app.trigger_error_flash()

def to_lowercase_folder(app):
    from tkinter import filedialog, messagebox
    import os
    folder = filedialog.askdirectory(title="Select Folder")
    if not folder: return
    output_folder = os.path.join(folder, "lowercase_output")
    os.makedirs(output_folder, exist_ok=True)
    files = [f for f in os.listdir(folder) if f.endswith('.txt')]
    success = 0
    for filename in files:
        try:
            with open(os.path.join(folder, filename), 'r', encoding='utf-8') as f: content = f.read()
            with open(os.path.join(output_folder, filename), 'w', encoding='utf-8') as f: f.write(content.lower())
            app.log_message(f"[OK] {filename}")
            success += 1
        except Exception as e: app.log_message(f"[ERROR] {filename}: {e}")
    if success > 0: app.trigger_success_flash()
    messagebox.showinfo("Done", f"Converted {success}/{len(files)} files")

def count_lines(app):
    from tkinter import filedialog, messagebox
    file_path = filedialog.askopenfilename(title="Select Text File", filetypes=[("Text files", "*.txt"), ("All", "*.*")])
    if not file_path: return
    try:
        with open(file_path, 'r', encoding='utf-8') as f: lines = len(f.readlines())
        app.log_message(f"[OK] {file_path}: {lines} lines")
        app.trigger_success_flash()
        messagebox.showinfo("Result", f"Total lines: {lines}")
    except Exception as e:
        app.log_message(f"[ERROR] {e}")
        app.trigger_error_flash()

def count_lines_folder(app):
    from tkinter import filedialog, messagebox
    import os
    folder = filedialog.askdirectory(title="Select Folder")
    if not folder: return
    files = [f for f in os.listdir(folder) if f.endswith('.txt')]
    total_lines = 0
    for filename in files:
        try:
            with open(os.path.join(folder, filename), 'r', encoding='utf-8') as f: lines = len(f.readlines())
            total_lines += lines
            app.log_message(f"[OK] {filename}: {lines} lines")
        except Exception as e: app.log_message(f"[ERROR] {filename}: {e}")
    app.trigger_success_flash()
    messagebox.showinfo("Result", f"Total lines in {len(files)} files: {total_lines}")
''', encoding='utf-8')

        json_tool = self.plugins_folder / "json_tool.py"
        if not json_tool.exists():
            json_tool.write_text('''"""
JSON Tool Plugin
"""

PLUGIN_INFO = {
    "name": "JSON Tool",
    "description": "Format and validate JSON files",
    "author": "ShankTools",
    "version": "1.0",
    "icon": "📋"
}

def get_actions():
    return [
        {"row": 1, "buttons": [
            {"text": "Format JSON", "width": 20, "command": "format_json"},
            {"text": "Format Folder", "width": 16, "command": "format_json_folder"}
        ]},
        {"row": 2, "buttons": [
            {"text": "Minify JSON", "width": 20, "command": "minify_json"},
            {"text": "Minify Folder", "width": 16, "command": "minify_json_folder"}
        ]},
        {"row": 3, "buttons": [
            {"text": "Validate JSON", "width": 20, "command": "validate_json"},
            {"text": "Validate Folder", "width": 16, "command": "validate_json_folder"}
        ]}
    ]

def format_json(app):
    from tkinter import filedialog, messagebox
    import json
    file_path = filedialog.askopenfilename(title="Select JSON File", filetypes=[("JSON files", "*.json"), ("All", "*.*")])
    if not file_path: return
    try:
        with open(file_path, 'r', encoding='utf-8') as f: data = json.load(f)
        output_path = file_path.rsplit('.', 1)[0] + '_formatted.json'
        with open(output_path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)
        app.log_message(f"[OK] Formatted: {output_path}")
        app.trigger_success_flash()
    except Exception as e:
        app.log_message(f"[ERROR] {e}")
        app.trigger_error_flash()

def format_json_folder(app):
    from tkinter import filedialog, messagebox
    import json, os
    folder = filedialog.askdirectory(title="Select Folder")
    if not folder: return
    output_folder = os.path.join(folder, "formatted_output")
    os.makedirs(output_folder, exist_ok=True)
    files = [f for f in os.listdir(folder) if f.endswith('.json')]
    success = 0
    for filename in files:
        try:
            with open(os.path.join(folder, filename), 'r', encoding='utf-8') as f: data = json.load(f)
            with open(os.path.join(output_folder, filename), 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)
            success += 1
        except Exception as e: app.log_message(f"[ERROR] {filename}: {e}")
    if success > 0: app.trigger_success_flash()
    messagebox.showinfo("Done", f"Formatted {success}/{len(files)} files")

def minify_json(app):
    from tkinter import filedialog, messagebox
    import json
    file_path = filedialog.askopenfilename(title="Select JSON File", filetypes=[("JSON files", "*.json"), ("All", "*.*")])
    if not file_path: return
    try:
        with open(file_path, 'r', encoding='utf-8') as f: data = json.load(f)
        output_path = file_path.rsplit('.', 1)[0] + '_minified.json'
        with open(output_path, 'w', encoding='utf-8') as f: json.dump(data, f, separators=(',', ':'), ensure_ascii=False)
        app.log_message(f"[OK] Minified: {output_path}")
        app.trigger_success_flash()
    except Exception as e:
        app.log_message(f"[ERROR] {e}")
        app.trigger_error_flash()

def minify_json_folder(app):
    from tkinter import filedialog, messagebox
    import json, os
    folder = filedialog.askdirectory(title="Select Folder")
    if not folder: return
    output_folder = os.path.join(folder, "minified_output")
    os.makedirs(output_folder, exist_ok=True)
    files = [f for f in os.listdir(folder) if f.endswith('.json')]
    success = 0
    for filename in files:
        try:
            with open(os.path.join(folder, filename), 'r', encoding='utf-8') as f: data = json.load(f)
            with open(os.path.join(output_folder, filename), 'w', encoding='utf-8') as f: json.dump(data, f, separators=(',', ':'), ensure_ascii=False)
            success += 1
        except Exception as e: app.log_message(f"[ERROR] {filename}: {e}")
    if success > 0: app.trigger_success_flash()
    messagebox.showinfo("Done", f"Minified {success}/{len(files)} files")

def validate_json(app):
    from tkinter import filedialog, messagebox
    import json
    file_path = filedialog.askopenfilename(title="Select JSON File", filetypes=[("JSON files", "*.json"), ("All", "*.*")])
    if not file_path: return
    try:
        with open(file_path, 'r', encoding='utf-8') as f: json.load(f)
        app.log_message(f"[OK] Valid JSON: {file_path}")
        app.trigger_success_flash()
        messagebox.showinfo("Valid", "JSON file is valid!")
    except Exception as e:
        app.log_message(f"[ERROR] Invalid: {e}")
        app.trigger_error_flash()
        messagebox.showerror("Invalid", f"JSON Error: {e}")

def validate_json_folder(app):
    from tkinter import filedialog, messagebox
    import json, os
    folder = filedialog.askdirectory(title="Select Folder")
    if not folder: return
    files = [f for f in os.listdir(folder) if f.endswith('.json')]
    valid = invalid = 0
    for filename in files:
        try:
            with open(os.path.join(folder, filename), 'r', encoding='utf-8') as f: json.load(f)
            valid += 1
        except: invalid += 1
    if invalid == 0: app.trigger_success_flash()
    else: app.trigger_error_flash()
    messagebox.showinfo("Result", f"Valid: {valid}\\nInvalid: {invalid}")
''', encoding='utf-8')

        file_renamer = self.plugins_folder / "file_renamer.py"
        if not file_renamer.exists():
            file_renamer.write_text('''"""
File Renamer Plugin
"""

PLUGIN_INFO = {
    "name": "File Renamer",
    "description": "Batch rename files with patterns",
    "author": "ShankTools",
    "version": "1.0",
    "icon": "📁"
}

def get_actions():
    return [
        {"row": 1, "buttons": [
            {"text": "Add Prefix", "width": 18, "command": "add_prefix"},
            {"text": "Add Suffix", "width": 18, "command": "add_suffix"}
        ]},
        {"row": 2, "buttons": [
            {"text": "Replace Text", "width": 18, "command": "replace_text"},
            {"text": "Number Files", "width": 18, "command": "number_files"}
        ]}
    ]

def add_prefix(app):
    from tkinter import filedialog, messagebox, simpledialog
    import os
    folder = filedialog.askdirectory(title="Select Folder")
    if not folder: return
    prefix = simpledialog.askstring("Prefix", "Enter prefix to add:")
    if not prefix: return
    files = os.listdir(folder)
    success = 0
    for filename in files:
        if os.path.isfile(os.path.join(folder, filename)):
            try:
                new_name = prefix + filename
                os.rename(os.path.join(folder, filename), os.path.join(folder, new_name))
                app.log_message(f"[OK] {filename} -> {new_name}")
                success += 1
            except Exception as e: app.log_message(f"[ERROR] {filename}: {e}")
    if success > 0: app.trigger_success_flash()
    messagebox.showinfo("Done", f"Renamed {success} files")

def add_suffix(app):
    from tkinter import filedialog, messagebox, simpledialog
    import os
    folder = filedialog.askdirectory(title="Select Folder")
    if not folder: return
    suffix = simpledialog.askstring("Suffix", "Enter suffix to add (before extension):")
    if not suffix: return
    files = os.listdir(folder)
    success = 0
    for filename in files:
        if os.path.isfile(os.path.join(folder, filename)):
            try:
                name, ext = os.path.splitext(filename)
                new_name = name + suffix + ext
                os.rename(os.path.join(folder, filename), os.path.join(folder, new_name))
                success += 1
            except Exception as e: app.log_message(f"[ERROR] {filename}: {e}")
    if success > 0: app.trigger_success_flash()
    messagebox.showinfo("Done", f"Renamed {success} files")

def replace_text(app):
    from tkinter import filedialog, messagebox, simpledialog
    import os
    folder = filedialog.askdirectory(title="Select Folder")
    if not folder: return
    find_text = simpledialog.askstring("Find", "Text to find:")
    if not find_text: return
    replace_with = simpledialog.askstring("Replace", "Replace with:")
    if replace_with is None: return
    files = os.listdir(folder)
    success = 0
    for filename in files:
        if os.path.isfile(os.path.join(folder, filename)) and find_text in filename:
            try:
                new_name = filename.replace(find_text, replace_with)
                os.rename(os.path.join(folder, filename), os.path.join(folder, new_name))
                success += 1
            except Exception as e: app.log_message(f"[ERROR] {filename}: {e}")
    if success > 0: app.trigger_success_flash()
    messagebox.showinfo("Done", f"Renamed {success} files")

def number_files(app):
    from tkinter import filedialog, messagebox, simpledialog
    import os
    folder = filedialog.askdirectory(title="Select Folder")
    if not folder: return
    base_name = simpledialog.askstring("Base Name", "Enter base name (e.g., 'file_'):")
    if not base_name: return
    files = sorted([f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))])
    success = 0
    for i, filename in enumerate(files, 1):
        try:
            ext = os.path.splitext(filename)[1]
            new_name = f"{base_name}{i:03d}{ext}"
            os.rename(os.path.join(folder, filename), os.path.join(folder, new_name))
            success += 1
        except Exception as e: app.log_message(f"[ERROR] {filename}: {e}")
    if success > 0: app.trigger_success_flash()
    messagebox.showinfo("Done", f"Renamed {success} files")
''', encoding='utf-8')

    def load_plugins(self):
        self.plugins = []
        for py_file in self.plugins_folder.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            try:
                plugin = self._load_plugin(py_file)
                if plugin:
                    self.plugins.append(plugin)
            except Exception as e:
                print(f"Error loading {py_file.name}: {e}")

    def _load_plugin(self, path):
        try:
            spec = importlib.util.spec_from_file_location(path.stem, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, 'PLUGIN_INFO') and hasattr(module, 'get_actions'):
                return {"info": module.PLUGIN_INFO, "module": module, "actions": module.get_actions()}
        except Exception as e:
            print(f"Error loading plugin {path.name}: {e}")
        return None

    def execute_command(self, plugin, command):
        if hasattr(plugin["module"], command):
            try:
                getattr(plugin["module"], command)(self.app)
            except Exception as e:
                self.app.log_message(f"[ERROR] Plugin error: {e}")
                self.app.trigger_error_flash()

    def get_total_count(self):
        return len(self.plugins)


class ShankTools:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("ShankTools")
        self.window.geometry("750x700")
        self.window.resizable(True, True)
        self.window.minsize(144, 144)

        self.bg_image = None
        self.bg_photo = None
        self.custom_titlebar_color = None
        self.custom_progress_color = None
        self.all_buttons = []
        self.inner_frames = []
        self.section_frames = []

        self.tex_converter = KTEXConverter() if KTEXConverter else None
        self.chui_converter = CHUIConverter() if CHUI_AVAILABLE else None

        self.plugin_manager = PluginManager(self)
        self.flash_effect = FlashEffect(self)

        self.setup_ui()
        self.apply_theme()
        self.plugin_manager.load_plugins()
        self.load_plugin_ui()
        self.auto_load_background()

    # ==================== UI HELPERS ====================

    def update_ui(self, callback):
        self.window.after(0, callback)

    def set_progress(self, value):
        self.update_ui(lambda: self.progress.configure(value=value))

    def set_status(self, text):
        self.update_ui(lambda: self.status.configure(text=text))

    def log_message(self, msg):
        def _log():
            self.log.insert(tk.END, msg + "\n")
            self.log.see(tk.END)
        self.update_ui(_log)

    def show_info(self, title, message):
        self.update_ui(lambda: messagebox.showinfo(title, message))

    def show_error(self, title, message):
        self.update_ui(lambda: messagebox.showerror(title, message))

    def trigger_success_flash(self):
        self.update_ui(lambda: self.flash_effect.start_flash("success"))

    def trigger_error_flash(self):
        self.update_ui(lambda: self.flash_effect.start_flash("error"))

    def reset_ui(self):
        self.progress['value'] = 0
        self.status.configure(text="Processing...")

    def clear_log(self):
        self.log.delete(1.0, tk.END)

    # ==================== BACKGROUND ====================

    def auto_load_background(self):
        if not PIL_AVAILABLE:
            return
        images_folder = Path(__file__).parent / "images"
        images_folder.mkdir(exist_ok=True)
        for ext in ["*.png", "*.jpg", "*.jpeg", "*.bmp"]:
            for img in images_folder.glob(ext):
                try:
                    self.set_background(img)
                    self.log_message(f"[OK] Background: {img.name}")
                    return
                except:
                    continue

    def set_background(self, image_path):
        if not PIL_AVAILABLE:
            return
        self.bg_image = Image.open(image_path)
        self.update_background()
        self.auto_adjust_colors()
        self.window.bind("<Configure>", self.on_window_resize)

    def update_background(self):
        if self.bg_image is None:
            return
        width, height = self.window.winfo_width(), self.window.winfo_height()
        if width > 1 and height > 1:
            resized = self.bg_image.resize((width, height), Image.Resampling.LANCZOS)
            self.bg_photo = ImageTk.PhotoImage(resized)
            self.bg_label.configure(image=self.bg_photo)

    def auto_adjust_colors(self):
        if self.bg_image is None:
            return
        avg_color = get_average_color(self.bg_image)
        if not avg_color:
            return
        r, g, b = avg_color
        brightness = (r + g + b) // 3
        self.custom_titlebar_color = f"#{max(0,r-20):02x}{max(0,g-20):02x}{max(0,b-20):02x}"
        set_title_bar_color(self.window, self.custom_titlebar_color)
        if brightness > 128:
            self.custom_progress_color = f"#{max(0,255-r):02x}{min(255,g+50):02x}{max(0,255-b):02x}"
            btn_colors = {"bg": "#2d2d2d", "fg": "#ffffff", "active": "#444444"}
        else:
            self.custom_progress_color = f"#{min(255,r+100):02x}{min(255,g+150):02x}{min(255,b+100):02x}"
            theme = ThemeManager.get_theme()
            btn_colors = {"bg": theme["button_bg"], "fg": theme["button_fg"], "active": theme["button_active"]}
        self.update_progress_bar_color()
        for btn in self.all_buttons:
            try:
                btn.configure(bg=btn_colors["bg"], fg=btn_colors["fg"],
                              activebackground=btn_colors["active"], activeforeground=btn_colors["fg"])
            except:
                pass

    def update_progress_bar_color(self):
        theme = ThemeManager.get_theme()
        fg = self.custom_progress_color if (self.custom_progress_color and self.bg_image) else theme["progress_fg"]
        style = ttk.Style()
        style.theme_use('default')
        style.configure("Custom.Horizontal.TProgressbar",
                        troughcolor=theme["progress_bg"], background=fg,
                        darkcolor=fg, lightcolor=fg, bordercolor=theme["progress_bg"], thickness=20)
        self.progress.configure(style="Custom.Horizontal.TProgressbar")

    def on_window_resize(self, event):
        if event.widget == self.window:
            self.update_background()

    # ==================== SETUP UI ====================

    def setup_ui(self):
        self.main_container = tk.Frame(self.window)
        self.main_container.pack(fill="both", expand=True)

        self.bg_label = tk.Label(self.main_container)
        self.bg_label.place(x=0, y=0, relwidth=1, relheight=1)

        self.canvas = tk.Canvas(self.main_container, highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)

        self.content_frame = tk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.content_frame, anchor="n")

        self.content_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        self.title_label = tk.Label(self.content_frame, text="ShankTools", font=("Arial", 22, "bold"))
        self.title_label.pack(pady=20)

        # TEX Section
        self.tex_frame = tk.LabelFrame(self.content_frame, text="  TEX / PNG Converter  ", font=("Arial", 13, "bold"), padx=15, pady=15)
        self.tex_frame.pack(pady=15, padx=30, fill="x")
        self.section_frames.append(self.tex_frame)

        self.tex_btn_frame1 = tk.Frame(self.tex_frame)
        self.tex_btn_frame1.pack(fill="x", pady=5)
        self._add_button(self.tex_btn_frame1, "Extract TEX -> PNG", 20, self.extract_tex)
        self._add_button(self.tex_btn_frame1, "Extract Folder", 16, self.extract_tex_folder)

        self.tex_btn_frame2 = tk.Frame(self.tex_frame)
        self.tex_btn_frame2.pack(fill="x", pady=5)
        self._add_button(self.tex_btn_frame2, "Rebuild PNG -> TEX", 20, self.rebuild_tex)
        self._add_button(self.tex_btn_frame2, "Rebuild Folder", 16, self.rebuild_tex_folder)

        self.inner_frames.extend([self.tex_btn_frame1, self.tex_btn_frame2])

        # Lua Section
        self.lua_frame = tk.LabelFrame(self.content_frame, text="  Lua Decompiler / Compiler  ", font=("Arial", 13, "bold"), padx=15, pady=15)
        self.lua_frame.pack(pady=15, padx=30, fill="x")
        self.section_frames.append(self.lua_frame)

        self.lua_btn_frame1 = tk.Frame(self.lua_frame)
        self.lua_btn_frame1.pack(fill="x", pady=5)
        self._add_button(self.lua_btn_frame1, "Decompile Lua", 18, self.decompile_lua)
        self._add_button(self.lua_btn_frame1, "Batch Decompile", 16, self.decompile_lua_folder)

        self.lua_btn_frame2 = tk.Frame(self.lua_frame)
        self.lua_btn_frame2.pack(fill="x", pady=5)
        self._add_button(self.lua_btn_frame2, "Compile Lua", 18, self.compile_lua)
        self._add_button(self.lua_btn_frame2, "Batch Compile", 16, self.compile_lua_folder)

        self.inner_frames.extend([self.lua_btn_frame1, self.lua_btn_frame2])

        # CHUI Section
        self.chui_frame = tk.LabelFrame(self.content_frame, text="  CHUI / JSON Editor  ", font=("Arial", 13, "bold"), padx=15, pady=15)
        self.chui_frame.pack(pady=15, padx=30, fill="x")
        self.section_frames.append(self.chui_frame)

        self.chui_btn_frame1 = tk.Frame(self.chui_frame)
        self.chui_btn_frame1.pack(fill="x", pady=5)
        self._add_button(self.chui_btn_frame1, "Extract CHUI -> JSON", 20, self.extract_chui)
        self._add_button(self.chui_btn_frame1, "Extract Folder", 16, self.extract_chui_folder)

        self.chui_btn_frame2 = tk.Frame(self.chui_frame)
        self.chui_btn_frame2.pack(fill="x", pady=5)
        self._add_button(self.chui_btn_frame2, "Rebuild JSON -> CHUI", 20, self.rebuild_chui)
        self._add_button(self.chui_btn_frame2, "Rebuild Folder", 16, self.rebuild_chui_folder)

        self.inner_frames.extend([self.chui_btn_frame1, self.chui_btn_frame2])

        # CANIM Animation Section
        self.canim_parse_frame = tk.LabelFrame(self.content_frame, text="  CANIM Animation Parser / Editor  ", font=("Arial", 13, "bold"), padx=15, pady=15)
        self.canim_parse_frame.pack(pady=15, padx=30, fill="x")
        self.section_frames.append(self.canim_parse_frame)

        self.canim_parse_btn_frame1 = tk.Frame(self.canim_parse_frame)
        self.canim_parse_btn_frame1.pack(fill="x", pady=5)
        self._add_button(self.canim_parse_btn_frame1, "Analyze CANIM", 20, self.analyze_canim)
        self._add_button(self.canim_parse_btn_frame1, "Batch Analyze", 16, self.analyze_canim_folder)

        self.canim_parse_btn_frame2 = tk.Frame(self.canim_parse_frame)
        self.canim_parse_btn_frame2.pack(fill="x", pady=5)
        self._add_button(self.canim_parse_btn_frame2, "Extract CANIM -> JSON", 20, self.extract_canim_json)
        self._add_button(self.canim_parse_btn_frame2, "Extract Folder", 16, self.extract_canim_json_folder)

        self.canim_parse_btn_frame3 = tk.Frame(self.canim_parse_frame)
        self.canim_parse_btn_frame3.pack(fill="x", pady=5)
        self._add_button(self.canim_parse_btn_frame3, "Rebuild JSON -> CANIM", 20, self.rebuild_canim_json)
        self._add_button(self.canim_parse_btn_frame3, "Rebuild Folder", 16, self.rebuild_canim_json_folder)

        self.inner_frames.extend([self.canim_parse_btn_frame1, self.canim_parse_btn_frame2, self.canim_parse_btn_frame3])

        # CANIM-META Section
        self.canim_meta_frame = tk.LabelFrame(self.content_frame, text="  CANIM-META / JSON Editor  ", font=("Arial", 13, "bold"), padx=15, pady=15)
        self.canim_meta_frame.pack(pady=15, padx=30, fill="x")
        self.section_frames.append(self.canim_meta_frame)

        self.canim_meta_btn_frame1 = tk.Frame(self.canim_meta_frame)
        self.canim_meta_btn_frame1.pack(fill="x", pady=5)
        self._add_button(self.canim_meta_btn_frame1, "Extract META -> JSON", 20, self.extract_canim_meta)
        self._add_button(self.canim_meta_btn_frame1, "Extract Folder", 16, self.extract_canim_meta_folder)

        self.canim_meta_btn_frame2 = tk.Frame(self.canim_meta_frame)
        self.canim_meta_btn_frame2.pack(fill="x", pady=5)
        self._add_button(self.canim_meta_btn_frame2, "Rebuild JSON -> META", 20, self.rebuild_canim_meta)
        self._add_button(self.canim_meta_btn_frame2, "Rebuild Folder", 16, self.rebuild_canim_meta_folder)

        self.inner_frames.extend([self.canim_meta_btn_frame1, self.canim_meta_btn_frame2])

        # Plugins Container
        self.plugins_container = tk.Frame(self.content_frame)
        self.plugins_container.pack(fill="x")

        # Plugins Header
        self.plugins_header_frame = tk.LabelFrame(self.content_frame, text="  Plugins Management  ", font=("Arial", 13, "bold"), padx=15, pady=10)
        self.plugins_header_frame.pack(pady=15, padx=30, fill="x")
        self.section_frames.append(self.plugins_header_frame)

        self.plugins_btn_frame = tk.Frame(self.plugins_header_frame)
        self.plugins_btn_frame.pack(fill="x", pady=5)
        self._add_button(self.plugins_btn_frame, "🔄 Reload Plugins", 18, self.reload_plugins)
        self._add_button(self.plugins_btn_frame, "📁 Open Folder", 16, self.open_plugins_folder)

        self.plugins_info_label = tk.Label(self.plugins_btn_frame, text="Loaded: 0", font=("Arial", 10))
        self.plugins_info_label.pack(side="right", padx=10)

        self.inner_frames.append(self.plugins_btn_frame)

        # Progress
        self.progress_frame = tk.Frame(self.content_frame)
        self.progress_frame.pack(pady=10, padx=30, fill="x")
        self.inner_frames.append(self.progress_frame)

        self.progress = ttk.Progressbar(self.progress_frame, length=600, mode='determinate')
        self.progress.pack(fill="x", pady=5)

        self.status = tk.Label(self.content_frame, text="Ready", font=("Arial", 11))
        self.status.pack(pady=5)

        # Log
        self.log_label = tk.Label(self.content_frame, text="Log:", font=("Arial", 11, "bold"))
        self.log_label.pack(pady=(10, 5), anchor="w", padx=30)

        self.log_outer_frame = tk.Frame(self.content_frame)
        self.log_outer_frame.pack(pady=5, padx=30, fill="both", expand=True)
        self.inner_frames.append(self.log_outer_frame)

        self.log = tk.Text(self.log_outer_frame, height=8, width=70, font=("Consolas", 10))
        self.log.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(self.log_outer_frame, command=self.log.yview)
        scrollbar.pack(side="right", fill="y")
        self.log.config(yscrollcommand=scrollbar.set)

        self._add_button(self.content_frame, "Clear Log", 0, self.clear_log, font=("Arial", 10), pack_opts={"pady": 10})

    def _add_button(self, parent, text, width, command, font=("Arial", 11), pack_opts=None):
        opts = {"side": "left", "padx": 10, "pady": 5} if pack_opts is None else pack_opts
        btn = tk.Button(parent, text=text, font=font, command=command)
        if width > 0:
            btn.configure(width=width, height=2)
        btn.pack(**opts)
        self.all_buttons.append(btn)
        return btn

    def load_plugin_ui(self):
        for frame in self.plugin_manager.plugin_frames:
            try:
                frame.destroy()
            except:
                pass
        self.plugin_manager.plugin_frames = []

        for plugin in self.plugin_manager.plugins:
            info = plugin["info"]
            actions = plugin["actions"]
            icon = info.get("icon", "🔧")
            title = f"  {icon} {info['name']}  "

            plugin_frame = tk.LabelFrame(self.plugins_container, text=title, font=("Arial", 13, "bold"), padx=15, pady=15)
            plugin_frame.pack(pady=15, padx=30, fill="x")
            self.plugin_manager.plugin_frames.append(plugin_frame)
            self.section_frames.append(plugin_frame)

            for action_row in actions:
                row_frame = tk.Frame(plugin_frame)
                row_frame.pack(fill="x", pady=5)
                self.inner_frames.append(row_frame)

                for btn_info in action_row.get("buttons", []):
                    btn = tk.Button(
                        row_frame,
                        text=btn_info.get("text", "Action"),
                        font=("Arial", 11),
                        width=btn_info.get("width", 15),
                        height=2,
                        command=lambda p=plugin, c=btn_info.get("command"):
                            self.plugin_manager.execute_command(p, c)
                    )
                    btn.pack(side="left", padx=10, pady=5)
                    self.all_buttons.append(btn)

        self.plugins_info_label.configure(text=f"Loaded: {self.plugin_manager.get_total_count()}")
        self.apply_theme()

    def apply_theme(self):
        theme = ThemeManager.get_theme()
        titlebar = self.custom_titlebar_color if (self.custom_titlebar_color and self.bg_image) else theme["titlebar"]
        set_title_bar_color(self.window, titlebar)

        for widget in [self.window, self.main_container, self.canvas, self.content_frame, self.bg_label, self.plugins_container]:
            widget.configure(bg=theme["bg"])

        self.title_label.configure(bg=theme["bg"], fg=theme["accent"])
        self.status.configure(bg=theme["bg"], fg=theme["success"])
        self.log_label.configure(bg=theme["bg"], fg=theme["fg"])
        self.log.configure(bg="#0f0f1a", fg="#00ff41", insertbackground=theme["fg"])
        self.plugins_info_label.configure(bg=theme["frame_bg"], fg=theme["fg"])

        for frame in self.section_frames:
            try:
                frame.configure(bg=theme["frame_bg"], fg=theme["fg"])
            except:
                pass
        for frame in self.inner_frames:
            try:
                frame.configure(bg=theme["frame_bg"])
            except:
                pass

        self.update_progress_bar_color()

        btn_style = {"bg": theme["button_bg"], "fg": theme["button_fg"],
                     "activebackground": theme["button_active"], "activeforeground": theme["button_fg"]}
        for btn in self.all_buttons:
            try:
                btn.configure(**btn_style)
            except:
                pass

    def reload_plugins(self):
        self.plugin_manager.load_plugins()
        self.load_plugin_ui()
        self.log_message(f"[OK] Reloaded {self.plugin_manager.get_total_count()} plugins")

    def open_plugins_folder(self):
        folder = self.plugin_manager.plugins_folder
        folder.mkdir(exist_ok=True)
        if sys.platform == "win32":
            os.startfile(folder)
        else:
            os.system(f'{"open" if sys.platform == "darwin" else "xdg-open"} "{folder}"')

    # ==================== TEX FUNCTIONS ====================

    def extract_tex(self):
        if not self.tex_converter:
            messagebox.showerror("Error", "TEX converter not available!")
            return
        file_path = filedialog.askopenfilename(title="Select TEX File", filetypes=[("TEX files", "*.tex"), ("All", "*.*")])
        if not file_path:
            return
        self.reset_ui()
        self.progress['value'] = 50
        try:
            result = self.tex_converter.extract(Path(file_path))
            if result.success:
                self.log_message(f"[OK] Extracted: {result.output_path.name}")
                self.trigger_success_flash()
                messagebox.showinfo("Success", "Extraction completed!")
            else:
                self.log_message(f"[ERROR] {result.error}")
                self.trigger_error_flash()
        except Exception as e:
            self.log_message(f"[ERROR] {e}")
            self.trigger_error_flash()
        self.progress['value'] = 100
        self.status.configure(text="Done")

    def extract_tex_folder(self):
        if not self.tex_converter:
            messagebox.showerror("Error", "TEX converter not available!")
            return
        folder = filedialog.askdirectory(title="Select Folder")
        if not folder:
            return
        files = list(Path(folder).glob("*.tex"))
        if not files:
            messagebox.showwarning("Warning", "No TEX files found!")
            return
        self.reset_ui()
        threading.Thread(target=self._process_tex_files, args=(files, "extract"), daemon=True).start()

    def rebuild_tex(self):
        if not self.tex_converter:
            messagebox.showerror("Error", "TEX converter not available!")
            return
        file_path = filedialog.askopenfilename(title="Select PNG File", filetypes=[("PNG files", "*.png"), ("All", "*.*")])
        if not file_path:
            return
        self.reset_ui()
        self.progress['value'] = 50
        try:
            result = self.tex_converter.rebuild(Path(file_path))
            if result.success:
                self.log_message(f"[OK] Rebuilt: {result.output_path.name}")
                self.trigger_success_flash()
                messagebox.showinfo("Success", "Rebuild completed!")
            else:
                self.log_message(f"[ERROR] {result.error}")
                self.trigger_error_flash()
        except Exception as e:
            self.log_message(f"[ERROR] {e}")
            self.trigger_error_flash()
        self.progress['value'] = 100
        self.status.configure(text="Done")

    def rebuild_tex_folder(self):
        if not self.tex_converter:
            messagebox.showerror("Error", "TEX converter not available!")
            return
        folder = filedialog.askdirectory(title="Select Folder")
        if not folder:
            return
        files = list(Path(folder).glob("*.png"))
        if not files:
            messagebox.showwarning("Warning", "No PNG files found!")
            return
        self.reset_ui()
        threading.Thread(target=self._process_tex_files, args=(files, "rebuild"), daemon=True).start()

    def _process_tex_files(self, files, mode):
        total = len(files)
        success = 0
        for i, file in enumerate(files):
            try:
                result = self.tex_converter.extract(file) if mode == "extract" else self.tex_converter.rebuild(file)
                if result.success:
                    self.log_message(f"[OK] {file.name}")
                    success += 1
                else:
                    self.log_message(f"[ERROR] {file.name}")
            except Exception as e:
                self.log_message(f"[ERROR] {file.name}: {e}")
            self.set_progress(((i + 1) / total) * 100)
        self.set_status(f"Done ({success}/{total})")
        if success > 0:
            self.trigger_success_flash()
        self.show_info("Done", f"Processed {success}/{total} files")

    # ==================== LUA FUNCTIONS ====================

    def decompile_lua(self):
        file_path = filedialog.askopenfilename(title="Select Lua File", filetypes=[("Lua files", "*.lua"), ("All", "*.*")])
        if not file_path:
            return
        self.reset_ui()
        self.progress['value'] = 50
        try:
            with open(file_path, 'rb') as f:
                if f.read(4) != b'\x1bLua':
                    messagebox.showerror("Error", "Not a compiled Lua file!")
                    return
            output_path = file_path.rsplit('.', 1)[0] + '_decompiled.lua'
            if decompile_file(file_path, output_path):
                self.log_message(f"[OK] Decompiled: {Path(output_path).name}")
                self.trigger_success_flash()
                messagebox.showinfo("Success", "Decompilation completed!")
            else:
                self.trigger_error_flash()
        except Exception as e:
            self.log_message(f"[ERROR] {e}")
            self.trigger_error_flash()
        self.progress['value'] = 100
        self.status.configure(text="Done")

    def decompile_lua_folder(self):
        folder = filedialog.askdirectory(title="Select Folder")
        if folder:
            self.reset_ui()
            threading.Thread(target=self._batch_lua, args=(folder, "decompile"), daemon=True).start()

    def compile_lua(self):
        file_path = filedialog.askopenfilename(title="Select Lua File", filetypes=[("Lua files", "*.lua"), ("All", "*.*")])
        if not file_path:
            return
        self.reset_ui()
        self.progress['value'] = 50
        try:
            with open(file_path, 'rb') as f:
                if f.read(4) == b'\x1bLua':
                    messagebox.showerror("Error", "File already compiled!")
                    return
            output_path = file_path.replace('_decompiled', '').rsplit('.', 1)[0] + '_compiled.lua'
            if compile_lua_file(file_path, output_path):
                self.log_message(f"[OK] Compiled: {Path(output_path).name}")
                self.trigger_success_flash()
                messagebox.showinfo("Success", "Compilation completed!")
            else:
                self.trigger_error_flash()
        except Exception as e:
            self.log_message(f"[ERROR] {e}")
            self.trigger_error_flash()
        self.progress['value'] = 100
        self.status.configure(text="Done")

    def compile_lua_folder(self):
        folder = filedialog.askdirectory(title="Select Folder")
        if folder:
            self.reset_ui()
            threading.Thread(target=self._batch_lua, args=(folder, "compile"), daemon=True).start()

    def _batch_lua(self, folder_path, mode):
        output_name = "decompiled" if mode == "decompile" else "compiled"
        output_folder = os.path.join(folder_path, output_name)
        os.makedirs(output_folder, exist_ok=True)
        files = [f for f in os.listdir(folder_path) if f.endswith('.lua')]
        success = 0
        for i, filename in enumerate(files):
            filepath = os.path.join(folder_path, filename)
            try:
                with open(filepath, 'rb') as f:
                    header = f.read(4)
                if mode == "decompile" and header == b'\x1bLua':
                    out_path = os.path.join(output_folder, filename.replace('.lua', '_dec.lua'))
                    if decompile_file(filepath, out_path):
                        self.log_message(f"[OK] {filename}")
                        success += 1
                elif mode == "compile" and header != b'\x1bLua':
                    out_path = os.path.join(output_folder, filename.replace('_decompiled', ''))
                    if compile_lua_file(filepath, out_path):
                        self.log_message(f"[OK] {filename}")
                        success += 1
            except Exception as e:
                self.log_message(f"[ERROR] {filename}: {e}")
            self.set_progress(((i + 1) / len(files)) * 100)
        self.set_status(f"Done ({success})")
        if success > 0:
            self.trigger_success_flash()
        action = "Decompiled" if mode == "decompile" else "Compiled"
        self.show_info("Done", f"{action} {success} files")

    # ==================== CHUI FUNCTIONS ====================

    def extract_chui(self):
        if not self.chui_converter:
            messagebox.showerror("Error", "CHUI converter not available!")
            return
        file_path = filedialog.askopenfilename(title="Select CHUI File", filetypes=[("CHUI files", "*.chui"), ("All", "*.*")])
        if not file_path:
            return
        self.reset_ui()
        self.progress['value'] = 50
        try:
            result = self.chui_converter.extract(Path(file_path))
            if result.success:
                self.log_message(f"[OK] Extracted: {result.output_path.name}")
                self.trigger_success_flash()
                messagebox.showinfo("Success", f"CHUI extracted!\nOutput: {result.output_path.name}")
            else:
                self.log_message(f"[ERROR] {result.error}")
                self.trigger_error_flash()
        except Exception as e:
            self.log_message(f"[ERROR] {e}")
            self.trigger_error_flash()
        self.progress['value'] = 100
        self.status.configure(text="Done")

    def extract_chui_folder(self):
        if not self.chui_converter:
            messagebox.showerror("Error", "CHUI converter not available!")
            return
        folder = filedialog.askdirectory(title="Select Folder")
        if not folder:
            return
        files = list(Path(folder).glob("*.chui"))
        if not files:
            messagebox.showwarning("Warning", "No CHUI files found!")
            return
        self.reset_ui()
        threading.Thread(target=self._process_chui_files, args=(files, "extract"), daemon=True).start()

    def rebuild_chui(self):
        if not self.chui_converter:
            messagebox.showerror("Error", "CHUI converter not available!")
            return
        file_path = filedialog.askopenfilename(title="Select JSON File", filetypes=[("JSON files", "*.json"), ("All", "*.*")])
        if not file_path:
            return
        self.reset_ui()
        self.progress['value'] = 50
        try:
            result = self.chui_converter.rebuild(Path(file_path))
            if result.success:
                self.log_message(f"[OK] Rebuilt: {result.output_path.name}")
                self.trigger_success_flash()
                messagebox.showinfo("Success", f"CHUI rebuilt!\nOutput: {result.output_path.name}")
            else:
                self.log_message(f"[ERROR] {result.error}")
                self.trigger_error_flash()
        except Exception as e:
            self.log_message(f"[ERROR] {e}")
            self.trigger_error_flash()
        self.progress['value'] = 100
        self.status.configure(text="Done")

    def rebuild_chui_folder(self):
        if not self.chui_converter:
            messagebox.showerror("Error", "CHUI converter not available!")
            return
        folder = filedialog.askdirectory(title="Select Folder")
        if not folder:
            return
        files = list(Path(folder).glob("*.chui.json"))
        if not files:
            messagebox.showwarning("Warning", "No .chui.json files found!")
            return
        self.reset_ui()
        threading.Thread(target=self._process_chui_files, args=(files, "rebuild"), daemon=True).start()

    def _process_chui_files(self, files, mode):
        total = len(files)
        success = 0
        for i, file in enumerate(files):
            try:
                result = self.chui_converter.extract(file) if mode == "extract" else self.chui_converter.rebuild(file)
                if result.success:
                    self.log_message(f"[OK] {file.name}")
                    success += 1
                else:
                    self.log_message(f"[ERROR] {file.name}: {result.error}")
            except Exception as e:
                self.log_message(f"[ERROR] {file.name}: {e}")
            self.set_progress(((i + 1) / total) * 100)
        action = "Extracted" if mode == "extract" else "Rebuilt"
        self.set_status(f"Done ({success}/{total})")
        if success > 0:
            self.trigger_success_flash()
        self.show_info("Done", f"{action} {success}/{total} CHUI files")

    # ==================== CANIM PARSER FUNCTIONS ====================

    def analyze_canim(self):
        if not CANIM_PARSER_AVAILABLE:
            messagebox.showerror("Error", "CANIM parser not available!")
            return
        file_path = filedialog.askopenfilename(title="Select CANIM File", filetypes=[("CANIM files", "*.canim"), ("All", "*.*")])
        if not file_path:
            return
        self.reset_ui()
        self.progress['value'] = 50
        try:
            result = parse_canim(file_path, verbose=True)
            trail = result.get('_trail', 0)
            nsym = len(result.get('symbols', []))
            nsp = sum(len(s['sprites']) for s in result.get('symbols', []))
            self.log_message(f"[OK] {Path(file_path).name}: {nsym} symbols, {nsp} sprites, trail={trail}")
            if trail == 0:
                self.trigger_success_flash()
            messagebox.showinfo("Done", f"Analyzed: {nsym} symbols, {nsp} sprites")
        except Exception as e:
            self.log_message(f"[ERROR] {e}")
            self.trigger_error_flash()
        self.progress['value'] = 100
        self.status.configure(text="Done")

    def analyze_canim_folder(self):
        if not CANIM_PARSER_AVAILABLE:
            messagebox.showerror("Error", "CANIM parser not available!")
            return
        folder = filedialog.askdirectory(title="Select Folder")
        if not folder:
            return
        files = [f for f in os.listdir(folder) if f.endswith('.canim') and '.canim-meta' not in f]
        if not files:
            messagebox.showwarning("Warning", "No CANIM files found!")
            return
        self.reset_ui()
        threading.Thread(target=self._batch_analyze_canim, args=(folder, files), daemon=True).start()

    def _batch_analyze_canim(self, folder, files):
        total = len(files)
        results = []
        success = 0
        for i, fn in enumerate(files):
            fp = os.path.join(folder, fn)
            try:
                r = parse_canim(fp, verbose=False)
                r['_filename'] = fn
                results.append(r)
                trail = r.get('_trail', 0)
                nsym = len(r.get('symbols', []))
                nsp = sum(len(s['sprites']) for s in r.get('symbols', []))
                st = '✓' if trail == 0 else f'trail={trail}'
                self.log_message(f"[OK] {fn}: sym={nsym} spr={nsp} {st}")
                success += 1
            except Exception as e:
                self.log_message(f"[ERROR] {fn}: {e}")
            self.set_progress(((i + 1) / total) * 100)
        if len(results) > 1:
            batch_report(results)
        self.set_status(f"Done ({success}/{total})")
        if success > 0:
            self.trigger_success_flash()
        self.show_info("Done", f"Analyzed {success}/{total} CANIM files")

    def extract_canim_json(self):
        if not CANIM_PARSER_AVAILABLE:
            messagebox.showerror("Error", "CANIM parser not available!")
            return
        file_path = filedialog.askopenfilename(title="Select CANIM File", filetypes=[("CANIM files", "*.canim"), ("All", "*.*")])
        if not file_path:
            return
        self.reset_ui()
        self.progress['value'] = 50
        try:
            out = export_canim_to_json(file_path)
            self.log_message(f"[OK] Exported: {Path(out).name}")
            self.trigger_success_flash()
            messagebox.showinfo("Success", f"Exported to:\n{Path(out).name}")
        except Exception as e:
            self.log_message(f"[ERROR] {e}")
            self.trigger_error_flash()
        self.progress['value'] = 100
        self.status.configure(text="Done")

    def extract_canim_json_folder(self):
        if not CANIM_PARSER_AVAILABLE:
            messagebox.showerror("Error", "CANIM parser not available!")
            return
        folder = filedialog.askdirectory(title="Select Folder")
        if not folder:
            return
        files = [f for f in os.listdir(folder) if f.endswith('.canim') and '.canim-meta' not in f]
        if not files:
            messagebox.showwarning("Warning", "No CANIM files found!")
            return
        self.reset_ui()
        threading.Thread(target=self._batch_export_canim_json, args=(folder, files), daemon=True).start()

    def _batch_export_canim_json(self, folder, files):
        total = len(files)
        success = 0
        for i, fn in enumerate(files):
            fp = os.path.join(folder, fn)
            try:
                out = export_canim_to_json(fp)
                self.log_message(f"[OK] {fn} -> {Path(out).name}")
                success += 1
            except Exception as e:
                self.log_message(f"[ERROR] {fn}: {e}")
            self.set_progress(((i + 1) / total) * 100)
        self.set_status(f"Done ({success}/{total})")
        if success > 0:
            self.trigger_success_flash()
        self.show_info("Done", f"Exported {success}/{total} CANIM files to JSON")

    def rebuild_canim_json(self):
        if not CANIM_PARSER_AVAILABLE:
            messagebox.showerror("Error", "CANIM parser not available!")
            return
        file_path = filedialog.askopenfilename(title="Select CANIM JSON File", filetypes=[("JSON files", "*.canim.json *.json"), ("All", "*.*")])
        if not file_path:
            return
        self.reset_ui()
        self.progress['value'] = 50
        try:
            out = rebuild_canim_from_json(file_path)
            self.log_message(f"[OK] Rebuilt: {Path(out).name}")
            self.trigger_success_flash()
            messagebox.showinfo("Success", f"Rebuilt to:\n{Path(out).name}")
        except Exception as e:
            self.log_message(f"[ERROR] {e}")
            self.trigger_error_flash()
        self.progress['value'] = 100
        self.status.configure(text="Done")

    def rebuild_canim_json_folder(self):
        if not CANIM_PARSER_AVAILABLE:
            messagebox.showerror("Error", "CANIM parser not available!")
            return
        folder = filedialog.askdirectory(title="Select Folder")
        if not folder:
            return
        files = [f for f in os.listdir(folder) if f.endswith('.canim.json')]
        if not files:
            messagebox.showwarning("Warning", "No .canim.json files found!")
            return
        self.reset_ui()
        threading.Thread(target=self._batch_rebuild_canim_json, args=(folder, files), daemon=True).start()

    def _batch_rebuild_canim_json(self, folder, files):
        total = len(files)
        success = 0
        for i, fn in enumerate(files):
            fp = os.path.join(folder, fn)
            try:
                out = rebuild_canim_from_json(fp)
                self.log_message(f"[OK] {fn} -> {Path(out).name}")
                success += 1
            except Exception as e:
                self.log_message(f"[ERROR] {fn}: {e}")
            self.set_progress(((i + 1) / total) * 100)
        self.set_status(f"Done ({success}/{total})")
        if success > 0:
            self.trigger_success_flash()
        self.show_info("Done", f"Rebuilt {success}/{total} CANIM files from JSON")

    # ==================== CANIM-META FUNCTIONS ====================

    def extract_canim_meta(self):
        if not CANIM_META_AVAILABLE:
            messagebox.showerror("Error", "CANIM-META module not available!")
            return
        file_path = filedialog.askopenfilename(title="Select CANIM-META File", filetypes=[("CANIM-META files", "*.canim-meta"), ("All", "*.*")])
        if not file_path:
            return
        self.reset_ui()
        self.progress['value'] = 50
        try:
            meta = CAnimMeta()
            meta.load(file_path)
            json_path = file_path + '.json'
            export_json(meta, json_path)
            self.log_message(f"[OK] Extracted: {Path(json_path).name}")
            self.trigger_success_flash()
            messagebox.showinfo("Success", f"META extracted!\nOutput: {Path(json_path).name}")
        except Exception as e:
            self.log_message(f"[ERROR] {e}")
            self.trigger_error_flash()
        self.progress['value'] = 100
        self.status.configure(text="Done")

    def extract_canim_meta_folder(self):
        if not CANIM_META_AVAILABLE:
            messagebox.showerror("Error", "CANIM-META module not available!")
            return
        folder = filedialog.askdirectory(title="Select Folder")
        if not folder:
            return
        files = [f for f in os.listdir(folder) if f.endswith('.canim-meta')]
        if not files:
            messagebox.showwarning("Warning", "No .canim-meta files found!")
            return
        self.reset_ui()
        threading.Thread(target=self._batch_canim_meta, args=(folder, files, "extract"), daemon=True).start()

    def rebuild_canim_meta(self):
        if not CANIM_META_AVAILABLE:
            messagebox.showerror("Error", "CANIM-META module not available!")
            return
        file_path = filedialog.askopenfilename(title="Select JSON File", filetypes=[("JSON files", "*.json"), ("All", "*.*")])
        if not file_path:
            return
        self.reset_ui()
        self.progress['value'] = 50
        try:
            meta = CAnimMeta()
            import_json(meta, file_path)
            if file_path.endswith('.canim-meta.json'):
                out_path = file_path[:-5]
            else:
                out_path = file_path.rsplit('.', 1)[0] + '.canim-meta'
            meta.save(out_path)
            self.log_message(f"[OK] Rebuilt: {Path(out_path).name}")
            self.trigger_success_flash()
            messagebox.showinfo("Success", f"META rebuilt!\nOutput: {Path(out_path).name}")
        except Exception as e:
            self.log_message(f"[ERROR] {e}")
            self.trigger_error_flash()
        self.progress['value'] = 100
        self.status.configure(text="Done")

    def rebuild_canim_meta_folder(self):
        if not CANIM_META_AVAILABLE:
            messagebox.showerror("Error", "CANIM-META module not available!")
            return
        folder = filedialog.askdirectory(title="Select Folder")
        if not folder:
            return
        files = [f for f in os.listdir(folder) if f.endswith('.canim-meta.json')]
        if not files:
            messagebox.showwarning("Warning", "No .canim-meta.json files found!")
            return
        self.reset_ui()
        threading.Thread(target=self._batch_canim_meta, args=(folder, files, "rebuild"), daemon=True).start()

    def _batch_canim_meta(self, folder, files, mode):
        total = len(files)
        success = 0
        for i, fn in enumerate(files):
            fp = os.path.join(folder, fn)
            try:
                meta = CAnimMeta()
                if mode == "extract":
                    meta.load(fp)
                    json_path = fp + '.json'
                    export_json(meta, json_path)
                    self.log_message(f"[OK] {fn} -> JSON")
                else:
                    import_json(meta, fp)
                    if fn.endswith('.canim-meta.json'):
                        out_path = os.path.join(folder, fn[:-5])
                    else:
                        out_path = os.path.join(folder, fn.rsplit('.', 1)[0] + '.canim-meta')
                    meta.save(out_path)
                    self.log_message(f"[OK] {fn} -> META")
                success += 1
            except Exception as e:
                self.log_message(f"[ERROR] {fn}: {e}")
            self.set_progress(((i + 1) / total) * 100)
        action = "Extracted" if mode == "extract" else "Rebuilt"
        self.set_status(f"Done ({success}/{total})")
        if success > 0:
            self.trigger_success_flash()
        self.show_info("Done", f"{action} {success}/{total} META files")

    # ==================== RUN ====================

    def run(self):
        self.window.mainloop()


if __name__ == "__main__":
    app = ShankTools()
    app.run()