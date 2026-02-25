"""
Plugin System - Advanced @tool decorator + Auto UI Builder
Embedded Frame Version
"""
import os
import inspect
import importlib.util
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Callable, Dict, List, Any


# ═══════════════════════════════════════════════════════════════════
#                         @tool DECORATOR
# ═══════════════════════════════════════════════════════════════════

def tool(name: str = None, description: str = "", icon: str = "🔧", category: str = "General"):
    """
    Decorator to register a function as a tool.
    
    Usage:
        @tool(name="My Tool", description="Does something", icon="⚡", category="Utils")
        def my_tool(input_file: str, option: bool = False):
            pass
    """
    def decorator(func: Callable):
        func._tool_info = {
            'name': name or func.__name__.replace('_', ' ').title(),
            'description': description or func.__doc__ or "No description",
            'icon': icon,
            'category': category,
            'function': func,
            'parameters': _extract_parameters(func)
        }
        return func
    return decorator


def _extract_parameters(func: Callable) -> List[Dict]:
    """Extract parameter info from function signature."""
    params = []
    sig = inspect.signature(func)
    type_hints = getattr(func, '__annotations__', {})

    for param_name, param in sig.parameters.items():
        if param_name in ('app', 'self'):
            continue
            
        param_type = type_hints.get(param_name, str)
        default = None if param.default == inspect.Parameter.empty else param.default
        required = param.default == inspect.Parameter.empty

        params.append({
            'name': param_name,
            'type': param_type,
            'default': default,
            'required': required
        })

    return params


# ═══════════════════════════════════════════════════════════════════
#                      ADVANCED PLUGIN LOADER
# ═══════════════════════════════════════════════════════════════════

class AdvancedPluginLoader:
    """Loader for @tool decorated plugins."""

    def __init__(self, plugins_folder: str = "plugins"):
        self.plugins_folder = plugins_folder
        self.loaded_tools = {}

    def discover_and_load(self) -> Dict[str, List[Dict]]:
        """Load all plugins and extract @tool functions."""
        if not os.path.exists(self.plugins_folder):
            os.makedirs(self.plugins_folder)

        self.loaded_tools.clear()

        for filename in os.listdir(self.plugins_folder):
            if filename.endswith('.py') and not filename.startswith('_'):
                plugin_name = filename[:-3]
                tools = self._load_plugin(plugin_name)
                if tools:
                    self.loaded_tools[plugin_name] = tools

        return self.loaded_tools

    def _load_plugin(self, plugin_name: str) -> List[Dict]:
        """Load single plugin and extract tools."""
        try:
            plugin_path = os.path.join(self.plugins_folder, f"{plugin_name}.py")
            spec = importlib.util.spec_from_file_location(plugin_name, plugin_path)
            
            if spec is None or spec.loader is None:
                return []

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            tools = []
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if callable(attr) and hasattr(attr, '_tool_info'):
                    tools.append(attr._tool_info)

            return tools

        except Exception as e:
            print(f"[Plugin Error] '{plugin_name}': {e}")
            return []

    def get_all_tools(self) -> List[Dict]:
        """Get flat list of all tools."""
        all_tools = []
        for tools in self.loaded_tools.values():
            all_tools.extend(tools)
        return all_tools

    def get_tools_by_category(self) -> Dict[str, List[Dict]]:
        """Get tools grouped by category."""
        categories = {}
        for tools in self.loaded_tools.values():
            for tool_info in tools:
                cat = tool_info.get('category', 'General')
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(tool_info)
        return categories


# ═══════════════════════════════════════════════════════════════════
#                    TOOL FRAME (Embedded in Main UI)
# ═══════════════════════════════════════════════════════════════════

class ToolFrame:
    """
    Embedded frame for a tool - integrates directly into main window.
    Similar style to TEX/Lua sections.
    """

    def __init__(self, parent, tool_info: Dict, theme: Dict, 
                 on_success=None, log_callback=None):
        """
        Args:
            parent: Parent widget (content_frame from main.py)
            tool_info: Tool information dict
            theme: Theme dict from ThemeManager
            on_success: Callback for success flash
            log_callback: Callback to log messages
        """
        self.tool_info = tool_info
        self.theme = theme
        self.on_success = on_success
        self.log_callback = log_callback
        self.input_vars = {}
        self.all_buttons = []  # للتوافق مع نظام الثيم
        
        # إنشاء الإطار الرئيسي
        self.frame = tk.LabelFrame(
            parent,
            text=f"  {tool_info['icon']} {tool_info['name']}  ",
            font=("Arial", 13, "bold"),
            bg=theme["frame_bg"],
            fg=theme["fg"],
            padx=15,
            pady=15
        )
        
        self._build_ui()
    
    def pack(self, **kwargs):
        """Pack the frame."""
        self.frame.pack(**kwargs)
    
    def grid(self, **kwargs):
        """Grid the frame."""
        self.frame.grid(**kwargs)
    
    def destroy(self):
        """Destroy the frame."""
        self.frame.destroy()
    
    def get_frame(self):
        """Return the LabelFrame widget."""
        return self.frame
    
    def get_buttons(self):
        """Return list of buttons for theme updates."""
        return self.all_buttons

    def _build_ui(self):
        t = self.theme
        
        # Description (optional - shows if description exists)
        if self.tool_info['description'] and self.tool_info['description'] != "No description":
            desc_label = tk.Label(
                self.frame,
                text=self.tool_info['description'],
                font=("Arial", 9, "italic"),
                bg=t["frame_bg"], 
                fg=t["fg"],
                wraplength=500,
                justify="left"
            )
            desc_label.pack(anchor="w", pady=(0, 10))

        # Parameters Frame
        params_container = tk.Frame(self.frame, bg=t["frame_bg"])
        params_container.pack(fill="x", pady=5)

        # إنشاء صفين للمعاملات (مثل تصميم TEX/Lua)
        self.params_row1 = tk.Frame(params_container, bg=t["frame_bg"])
        self.params_row1.pack(fill="x", pady=5)
        
        self.params_row2 = tk.Frame(params_container, bg=t["frame_bg"])
        self.params_row2.pack(fill="x", pady=5)

        # توزيع المعاملات على الصفوف
        params = self.tool_info['parameters']
        for i, param in enumerate(params):
            target_row = self.params_row1 if i % 2 == 0 else self.params_row2
            self._create_param_widget(target_row, param)

        # Buttons Row
        btn_frame = tk.Frame(self.frame, bg=t["frame_bg"])
        btn_frame.pack(fill="x", pady=(10, 5))

        # Run Button
        self.run_btn = tk.Button(
            btn_frame,
            text=f"▶ Run",
            font=("Arial", 11),
            bg=t["button_bg"],
            fg=t["button_fg"],
            activebackground=t["button_active"],
            activeforeground=t["button_fg"],
            command=self._execute,
            width=16,
            height=2
        )
        self.run_btn.pack(side="left", padx=10, pady=5)
        self.all_buttons.append(self.run_btn)

        # Clear Button
        self.clear_btn = tk.Button(
            btn_frame,
            text="🗑 Clear",
            font=("Arial", 11),
            bg=t["button_bg"],
            fg=t["button_fg"],
            activebackground=t["button_active"],
            activeforeground=t["button_fg"],
            command=self._clear_inputs,
            width=12,
            height=2
        )
        self.clear_btn.pack(side="left", padx=10, pady=5)
        self.all_buttons.append(self.clear_btn)

        # Status Label
        self.status_label = tk.Label(
            btn_frame,
            text="Ready",
            font=("Arial", 10),
            bg=t["frame_bg"],
            fg=t["success"]
        )
        self.status_label.pack(side="right", padx=10)

    def _create_param_widget(self, parent, param: Dict):
        """Create input widget based on parameter type."""
        t = self.theme
        
        # Container for this parameter
        param_frame = tk.Frame(parent, bg=t["frame_bg"])
        param_frame.pack(side="left", padx=10, pady=5)

        # Label
        label_text = param['name'].replace('_', ' ').title()
        if param['required']:
            label_text += " *"

        tk.Label(
            param_frame,
            text=label_text,
            font=("Arial", 10),
            bg=t["frame_bg"], 
            fg=t["fg"]
        ).pack(anchor="w")

        param_type = param['type']
        default = param.get('default')

        # Boolean -> Checkbox
        if param_type == bool:
            var = tk.BooleanVar(value=default if default is not None else False)
            cb = tk.Checkbutton(
                param_frame, 
                variable=var,
                text="Enabled",
                bg=t["frame_bg"], 
                fg=t["fg"],
                selectcolor=t["button_bg"],
                activebackground=t["frame_bg"],
                activeforeground=t["fg"]
            )
            cb.pack(anchor="w")
            self.input_vars[param['name']] = var

        # Int -> Spinbox
        elif param_type == int:
            var = tk.IntVar(value=default if default is not None else 0)
            sb = tk.Spinbox(
                param_frame, 
                from_=-9999, 
                to=9999,
                textvariable=var, 
                width=12,
                bg="#1a1a2e", 
                fg=t["fg"],
                buttonbackground=t["button_bg"]
            )
            sb.pack(anchor="w")
            self.input_vars[param['name']] = var

        # Float -> Spinbox
        elif param_type == float:
            var = tk.DoubleVar(value=default if default is not None else 0.0)
            sb = tk.Spinbox(
                param_frame, 
                from_=-9999, 
                to=9999,
                increment=0.1, 
                textvariable=var, 
                width=12,
                bg="#1a1a2e", 
                fg=t["fg"],
                buttonbackground=t["button_bg"]
            )
            sb.pack(anchor="w")
            self.input_vars[param['name']] = var

        # String (with file browser if name suggests file)
        else:
            var = tk.StringVar(value=default if default is not None else "")
            
            is_file_param = any(x in param['name'].lower() for x in 
                               ['file', 'path', 'input', 'output', 'folder', 'dir'])

            input_frame = tk.Frame(param_frame, bg=t["frame_bg"])
            input_frame.pack(anchor="w")

            if is_file_param:
                entry = tk.Entry(
                    input_frame, 
                    textvariable=var, 
                    width=25, 
                    bg="#1a1a2e", 
                    fg=t["fg"],
                    insertbackground=t["fg"]
                )
                entry.pack(side="left")

                browse_btn = tk.Button(
                    input_frame, 
                    text="📁",
                    font=("Arial", 9),
                    bg=t["button_bg"], 
                    fg=t["button_fg"],
                    activebackground=t["button_active"],
                    command=lambda v=var, n=param['name']: self._browse(v, n),
                    width=3
                )
                browse_btn.pack(side="left", padx=(5, 0))
                self.all_buttons.append(browse_btn)
            else:
                entry = tk.Entry(
                    input_frame, 
                    textvariable=var, 
                    width=30, 
                    bg="#1a1a2e", 
                    fg=t["fg"],
                    insertbackground=t["fg"]
                )
                entry.pack(side="left")

            self.input_vars[param['name']] = var

    def _browse(self, var: tk.StringVar, param_name: str):
        """Open file/folder dialog."""
        if 'folder' in param_name.lower() or 'dir' in param_name.lower():
            path = filedialog.askdirectory()
        elif 'output' in param_name.lower():
            path = filedialog.asksaveasfilename()
        else:
            path = filedialog.askopenfilename()
        
        if path:
            var.set(path)

    def _clear_inputs(self):
        """Clear all input fields."""
        for param in self.tool_info['parameters']:
            var = self.input_vars.get(param['name'])
            if var:
                param_type = param['type']
                default = param.get('default')
                
                if param_type == bool:
                    var.set(default if default is not None else False)
                elif param_type in (int, float):
                    var.set(default if default is not None else 0)
                else:
                    var.set(default if default is not None else "")
        
        self.status_label.configure(text="Cleared", fg=self.theme["warning"])

    def _execute(self):
        """Execute the tool function."""
        self.status_label.configure(text="Running...", fg=self.theme["warning"])
        
        try:
            kwargs = {}
            for param in self.tool_info['parameters']:
                var = self.input_vars.get(param['name'])
                if var:
                    value = var.get()
                    
                    if param['required'] and (value is None or value == ""):
                        self.status_label.configure(
                            text=f"Missing: {param['name']}", 
                            fg="#ff4444"
                        )
                        messagebox.showerror("Error", f"'{param['name']}' is required!")
                        return
                    
                    kwargs[param['name']] = value

            # Execute the function
            result = self.tool_info['function'](**kwargs)

            # Log result
            if self.log_callback:
                self.log_callback(f"[OK] {self.tool_info['name']}: {result}")
            
            self.status_label.configure(text="✅ Success!", fg=self.theme["success"])

            if self.on_success:
                self.on_success()

        except Exception as e:
            self.status_label.configure(text="❌ Error", fg="#ff4444")
            if self.log_callback:
                self.log_callback(f"[ERROR] {self.tool_info['name']}: {str(e)}")
            messagebox.showerror("Error", str(e))

    def apply_theme(self, theme: Dict):
        """Update theme colors."""
        self.theme = theme
        t = theme
        
        self.frame.configure(bg=t["frame_bg"], fg=t["fg"])
        
        # Update all child widgets recursively
        self._update_widget_theme(self.frame, t)
        
        # Update buttons
        for btn in self.all_buttons:
            try:
                btn.configure(
                    bg=t["button_bg"],
                    fg=t["button_fg"],
                    activebackground=t["button_active"],
                    activeforeground=t["button_fg"]
                )
            except:
                pass

    def _update_widget_theme(self, widget, theme):
        """Recursively update widget colors."""
        try:
            widget_type = widget.winfo_class()
            
            if widget_type == "Frame":
                widget.configure(bg=theme["frame_bg"])
            elif widget_type == "Label":
                widget.configure(bg=theme["frame_bg"], fg=theme["fg"])
            elif widget_type == "Checkbutton":
                widget.configure(
                    bg=theme["frame_bg"], 
                    fg=theme["fg"],
                    selectcolor=theme["button_bg"],
                    activebackground=theme["frame_bg"]
                )
        except:
            pass
        
        for child in widget.winfo_children():
            self._update_widget_theme(child, theme)


# ═══════════════════════════════════════════════════════════════════
#                    LEGACY: TOOL WINDOW (Popup)
# ═══════════════════════════════════════════════════════════════════

class ToolWindow:
    """
    Popup window for a tool (Legacy - kept for backward compatibility).
    Use ToolFrame for embedded UI instead.
    """

    def __init__(self, parent, tool_info: Dict, theme: Dict, on_success=None):
        self.tool_info = tool_info
        self.theme = theme
        self.on_success = on_success
        self.input_vars = {}

        self.window = tk.Toplevel(parent)
        self.window.title(f"{tool_info['icon']} {tool_info['name']}")
        self.window.geometry("500x450")
        self.window.configure(bg=theme["bg"])
        self.window.resizable(True, True)
        
        self._build_ui()

    def _build_ui(self):
        t = self.theme
        
        header = tk.Frame(self.window, bg=t["bg"])
        header.pack(fill="x", padx=20, pady=15)

        tk.Label(
            header,
            text=f"{self.tool_info['icon']} {self.tool_info['name']}",
            font=("Arial", 16, "bold"),
            bg=t["bg"], fg=t["accent"]
        ).pack(anchor="w")

        tk.Label(
            header,
            text=self.tool_info['description'],
            font=("Arial", 10),
            bg=t["bg"], fg=t["fg"]
        ).pack(anchor="w", pady=(5, 0))

        ttk.Separator(self.window, orient="horizontal").pack(fill="x", padx=20, pady=10)

        params_frame = tk.LabelFrame(
            self.window,
            text=" Parameters ",
            font=("Arial", 11, "bold"),
            bg=t["frame_bg"], fg=t["fg"],
            padx=15, pady=10
        )
        params_frame.pack(fill="x", padx=20, pady=10)

        for param in self.tool_info['parameters']:
            self._create_param_widget(params_frame, param)

        btn_frame = tk.Frame(self.window, bg=t["bg"])
        btn_frame.pack(fill="x", padx=20, pady=15)

        self.run_btn = tk.Button(
            btn_frame,
            text=f"▶ Run {self.tool_info['name']}",
            font=("Arial", 12, "bold"),
            bg=t["button_bg"], fg=t["button_fg"],
            activebackground=t["button_active"],
            command=self._execute,
            height=2, width=20
        )
        self.run_btn.pack()

        result_frame = tk.LabelFrame(
            self.window,
            text=" Result ",
            font=("Arial", 11, "bold"),
            bg=t["frame_bg"], fg=t["fg"],
            padx=10, pady=10
        )
        result_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        self.result_text = tk.Text(
            result_frame,
            height=6,
            font=("Consolas", 10),
            bg="#0f0f1a", fg="#00ff41",
            wrap="word"
        )
        self.result_text.pack(fill="both", expand=True)

    def _create_param_widget(self, parent, param: Dict):
        t = self.theme
        
        row = tk.Frame(parent, bg=t["frame_bg"])
        row.pack(fill="x", pady=8)

        label_text = param['name'].replace('_', ' ').title()
        if param['required']:
            label_text += " *"

        tk.Label(
            row,
            text=label_text,
            font=("Arial", 10),
            bg=t["frame_bg"], fg=t["fg"],
            width=15, anchor="w"
        ).pack(side="left")

        param_type = param['type']
        default = param.get('default')

        if param_type == bool:
            var = tk.BooleanVar(value=default if default is not None else False)
            cb = tk.Checkbutton(
                row, variable=var,
                bg=t["frame_bg"], fg=t["fg"],
                selectcolor=t["button_bg"],
                activebackground=t["frame_bg"]
            )
            cb.pack(side="left")
            self.input_vars[param['name']] = var

        elif param_type == int:
            var = tk.IntVar(value=default if default is not None else 0)
            sb = tk.Spinbox(
                row, from_=-9999, to=9999,
                textvariable=var, width=15,
                bg="#1a1a2e", fg=t["fg"]
            )
            sb.pack(side="left")
            self.input_vars[param['name']] = var

        elif param_type == float:
            var = tk.DoubleVar(value=default if default is not None else 0.0)
            sb = tk.Spinbox(
                row, from_=-9999, to=9999,
                increment=0.1, textvariable=var, width=15,
                bg="#1a1a2e", fg=t["fg"]
            )
            sb.pack(side="left")
            self.input_vars[param['name']] = var

        else:
            var = tk.StringVar(value=default if default is not None else "")
            
            is_file_param = any(x in param['name'].lower() for x in 
                               ['file', 'path', 'input', 'output', 'folder', 'dir'])

            if is_file_param:
                entry = tk.Entry(row, textvariable=var, width=30, bg="#1a1a2e", fg=t["fg"])
                entry.pack(side="left", padx=(0, 5))

                browse_btn = tk.Button(
                    row, text="📁",
                    bg=t["button_bg"], fg=t["button_fg"],
                    command=lambda v=var, n=param['name']: self._browse(v, n)
                )
                browse_btn.pack(side="left")
            else:
                entry = tk.Entry(row, textvariable=var, width=35, bg="#1a1a2e", fg=t["fg"])
                entry.pack(side="left")

            self.input_vars[param['name']] = var

    def _browse(self, var: tk.StringVar, param_name: str):
        if 'folder' in param_name.lower() or 'dir' in param_name.lower():
            path = filedialog.askdirectory()
        elif 'output' in param_name.lower():
            path = filedialog.asksaveasfilename()
        else:
            path = filedialog.askopenfilename()
        
        if path:
            var.set(path)

    def _execute(self):
        try:
            kwargs = {}
            for param in self.tool_info['parameters']:
                var = self.input_vars.get(param['name'])
                if var:
                    value = var.get()
                    
                    if param['required'] and (value is None or value == ""):
                        messagebox.showerror("Error", f"'{param['name']}' is required!")
                        return
                    
                    kwargs[param['name']] = value

            result = self.tool_info['function'](**kwargs)

            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, f"✅ Success!\n\n{result}")

            if self.on_success:
                self.on_success()

        except Exception as e:
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, f"❌ Error:\n\n{str(e)}")
            messagebox.showerror("Error", str(e))