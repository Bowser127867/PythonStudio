import json
import math
import time
import tkinter as tk
import importlib.util
import copy
import keyword
import re
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

APP_NAME = "PythonStudio"
ROOT_DIR = Path(__file__).resolve().parents[1]
PROJECTS_DIR = ROOT_DIR / "projects"
DEFAULT_PROJECT_DIR = PROJECTS_DIR / "MyFirstGame"
DEFAULT_SCENE_PATH = DEFAULT_PROJECT_DIR / "scene.json"
CAMERA_DISTANCE = 18
VIEWPORT_SCALE = 35
CAMERA_MOVE_SPEED = 3.0

print("Starting PythonStudio...")

class SceneObject:
    def __init__(self, data: dict):
        self.name = data.get("name", "Object")
        self.type = data.get("type", "cube")
        self.position = data.get("position", [0.0, 0.0, 0.0])
        self.rotation = data.get("rotation", [0.0, 0.0, 0.0])
        self.scale = data.get("scale", [1.0, 1.0, 1.0])
        self.color = data.get("color", [1.0, 1.0, 1.0])
        self.script = data.get("script", "")

    def to_dict(self) -> dict:
        data = {
            "name": self.name,
            "type": self.type,
            "position": self.position,
            "rotation": self.rotation,
            "scale": self.scale,
            "color": self.color,
        }
        if self.script:
            data["script"] = self.script
        return data


class PythonStudioEditor(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title(f"{APP_NAME} v0.1")
        self.geometry("1100x700")
        self.minsize(900, 560)

        self.scene_path = DEFAULT_SCENE_PATH
        self.objects: list[SceneObject] = []
        self.selected_index: int | None = None
        self.camera_yaw = 35.0
        self.camera_pitch = 20.0
        self.camera_distance = 25.0
        initial_yaw = math.radians(self.camera_yaw)
        initial_pitch = math.radians(self.camera_pitch)
        self.camera_target_x = -math.sin(initial_yaw) * math.cos(initial_pitch) * self.camera_distance
        self.camera_target_y = math.sin(initial_pitch) * self.camera_distance
        self.camera_target_z = -math.cos(initial_yaw) * math.cos(initial_pitch) * self.camera_distance
        self.last_mouse_x = 0
        self.last_mouse_y = 0
        self.last_frame_time = time.perf_counter()
        self.last_update_time = time.perf_counter()
        self.fps = 0.0
        self.pressed_keys: set[str] = set()
        self.is_playing = False
        self.active_scripts = []
        self.play_state_snapshot = []
        self.current_script_path: Path | None = None
        self.current_script_dirty = False

        self._ensure_default_project()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.close_studio)
        self.bind_all("<KeyPress>", self.on_key_press)
        self.bind_all("<KeyRelease>", self.on_key_release)
        self.load_scene(self.scene_path)
        self.log("PythonStudio started.")
        self.after(16, self.update_viewport)

    def _ensure_default_project(self) -> None:
        DEFAULT_PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        (DEFAULT_PROJECT_DIR / "scripts").mkdir(exist_ok=True)
        (DEFAULT_PROJECT_DIR / "assets").mkdir(exist_ok=True)

        if not DEFAULT_SCENE_PATH.exists():
            scene = {
                "name": "MyFirstGame",
                "objects": [
                    {
                        "name": "Baseplate",
                        "type": "cube",
                        "position": [0, 0, 0],
                        "rotation": [0, 0, 0],
                        "scale": [20, 1, 20],
                        "color": [0.35, 0.35, 0.35]
                    },
                    {
                        "name": "SpawnCube",
                        "type": "cube",
                        "position": [0, 2, 0],
                        "rotation": [0, 0, 0],
                        "scale": [2, 2, 2],
                        "color": [0.1, 0.45, 1.0],
                        "script": "scripts/spin.py"
                    }
                ]
            }
            DEFAULT_SCENE_PATH.write_text(json.dumps(scene, indent=4), encoding="utf-8")

        spin_script = DEFAULT_PROJECT_DIR / "scripts" / "spin.py"
        if not spin_script.exists():
            spin_script.write_text(
                "class SpinScript:\n"
                "    def start(self):\n"
                "        print('SpinScript started')\n\n"
                "    def update(self, dt):\n"
                "        self.object.rotation[1] += 90 * dt\n",
                encoding="utf-8"
            )

    def _get_unique_scene_path(self, scene_name: str) -> Path:
        safe_name = "".join(
            char for char in scene_name
            if char.isalnum() or char in ("_", "-", " ")
        ).strip()
        safe_name = safe_name.replace(" ", "_") or "NewScene"

        candidate = DEFAULT_PROJECT_DIR / f"{safe_name}.json"
        counter = 1

        while candidate.exists():
            candidate = DEFAULT_PROJECT_DIR / f"{safe_name}_{counter}.json"
            counter += 1

        return candidate

    def _build_ui(self) -> None:
        self._build_menu()

        main = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True)

        self.explorer_frame = ttk.Frame(main, width=240)
        self.viewport_frame = ttk.Frame(main)
        self.properties_frame = ttk.Frame(main, width=280)

        main.add(self.explorer_frame, weight=1)
        main.add(self.viewport_frame, weight=4)
        main.add(self.properties_frame, weight=1)

        self._build_explorer()
        self._build_viewport_placeholder()
        self._build_properties()
        self._build_output()

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self)

        file_menu = tk.Menu(menu_bar, tearoff=False)
        file_menu.add_command(label="New Scene", command=self.new_scene)
        file_menu.add_command(label="Open Scene...", command=self.open_scene_dialog)
        file_menu.add_command(label="Save Scene", command=self.save_scene)
        file_menu.add_command(label="Save Scene As...", command=self.save_scene_as_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.close_studio)
        menu_bar.add_cascade(label="File", menu=file_menu)

        object_menu = tk.Menu(menu_bar, tearoff=False)
        object_menu.add_command(label="Add Cube", command=self.add_cube)
        object_menu.add_command(label="Delete Selected", command=self.delete_selected)
        menu_bar.add_cascade(label="Object", menu=object_menu)

        play_menu = tk.Menu(menu_bar, tearoff=False)
        play_menu.add_command(label="Play", command=self.play_scene)
        play_menu.add_command(label="Stop", command=self.stop_scene)
        menu_bar.add_cascade(label="Play", menu=play_menu)

        script_menu = tk.Menu(menu_bar, tearoff=False)
        script_menu.add_command(label="New Script...", command=self.new_script_dialog)
        script_menu.add_command(label="Open Script...", command=self.open_script_dialog)
        script_menu.add_command(label="Open Selected Object Script", command=self.open_selected_object_script)
        script_menu.add_command(label="Save Script", command=self.save_script)
        script_menu.add_command(label="Attach Script to Selected", command=self.attach_script_to_selected)
        menu_bar.add_cascade(label="Script", menu=script_menu)

        edit_menu = tk.Menu(menu_bar, tearoff=False)
        edit_menu.add_command(label="Undo", command=lambda: self.code_editor.event_generate("<<Undo>>"))
        edit_menu.add_command(label="Redo", command=lambda: self.code_editor.event_generate("<<Redo>>"))
        edit_menu.add_separator()
        edit_menu.add_command(label="Cut", command=lambda: self.code_editor.event_generate("<<Cut>>"))
        edit_menu.add_command(label="Copy", command=lambda: self.code_editor.event_generate("<<Copy>>"))
        edit_menu.add_command(label="Paste", command=lambda: self.code_editor.event_generate("<<Paste>>"))
        edit_menu.add_command(label="Select All", command=self.select_all_code)
        edit_menu.add_separator()
        edit_menu.add_command(label="Find", command=self.show_find_bar)
        edit_menu.add_command(label="Replace", command=self.show_replace_bar)
        edit_menu.add_command(label="Go To Line...", command=self.go_to_line_dialog)
        menu_bar.add_cascade(label="Edit", menu=edit_menu)

        self.config(menu=menu_bar)

    def _build_explorer(self) -> None:
        ttk.Label(self.explorer_frame, text="Explorer", font=("Arial", 12, "bold")).pack(anchor="w", padx=8, pady=6)

        self.object_list = tk.Listbox(self.explorer_frame)
        self.object_list.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.object_list.bind("<<ListboxSelect>>", self.on_object_selected)
        self.object_list.bind("<ButtonRelease-1>", self.on_explorer_click)

        buttons = ttk.Frame(self.explorer_frame)
        buttons.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Button(buttons, text="Add Cube", command=self.add_cube).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(buttons, text="Delete", command=self.delete_selected).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(6, 0))

    def _build_viewport_placeholder(self) -> None:
        self.center_tabs = ttk.Notebook(self.viewport_frame)
        self.center_tabs.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.viewport_tab = ttk.Frame(self.center_tabs)
        self.code_tab = ttk.Frame(self.center_tabs)
        self.center_tabs.add(self.viewport_tab, text="Viewport")
        self.center_tabs.add(self.code_tab, text="Code")

        self.viewport = tk.Canvas(self.viewport_tab, bg="#202124", highlightthickness=0, takefocus=True)
        self.viewport.pack(fill=tk.BOTH, expand=True)
        self.viewport.bind("<Configure>", lambda _event: self.draw_viewport())
        self.viewport.bind("<ButtonPress-1>", self.start_camera_drag)
        self.viewport.bind("<B1-Motion>", self.drag_camera)
        self.viewport.bind("<Enter>", lambda _event: self.viewport.focus_set())
        self.viewport.bind("<MouseWheel>", self.zoom_camera)
        self.viewport.bind("<Button-4>", self.zoom_camera)
        self.viewport.bind("<Button-5>", self.zoom_camera)
        self.bind_all("<MouseWheel>", self.zoom_camera)
        self.bind_all("<Button-4>", self.zoom_camera)
        self.bind_all("<Button-5>", self.zoom_camera)

        self._build_code_editor()

    def _build_code_editor(self) -> None:
        code_panes = ttk.PanedWindow(self.code_tab, orient=tk.HORIZONTAL)
        code_panes.pack(fill=tk.BOTH, expand=True)

        script_explorer = ttk.Frame(code_panes, width=180)
        editor_panel = ttk.Frame(code_panes)
        code_panes.add(script_explorer, weight=1)
        code_panes.add(editor_panel, weight=4)

        ttk.Label(script_explorer, text="Scripts", font=("Arial", 10, "bold")).pack(anchor="w", pady=(0, 6))
        self.script_tree = ttk.Treeview(script_explorer, show="tree", selectmode="browse")
        self.script_tree.pack(fill=tk.BOTH, expand=True)
        self.script_tree.bind("<Double-1>", self.open_script_from_tree)

        toolbar = ttk.Frame(editor_panel)
        toolbar.pack(fill=tk.X, pady=(0, 6))

        ttk.Button(toolbar, text="New", command=self.new_script_dialog).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Open", command=self.open_script_dialog).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(toolbar, text="Save", command=self.save_script).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(toolbar, text="Open Selected", command=self.open_selected_object_script).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(toolbar, text="Attach", command=self.attach_script_to_selected).pack(side=tk.LEFT, padx=(6, 0))

        self.script_path_label = ttk.Label(toolbar, text="No script open")
        self.script_path_label.pack(side=tk.LEFT, padx=(12, 0))

        self.find_bar = ttk.Frame(editor_panel)
        self.find_text = tk.StringVar()
        self.replace_text = tk.StringVar()
        ttk.Label(self.find_bar, text="Find").pack(side=tk.LEFT)
        find_entry = ttk.Entry(self.find_bar, textvariable=self.find_text, width=24)
        find_entry.pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(self.find_bar, text="Next", command=self.find_next).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(self.find_bar, text="Replace").pack(side=tk.LEFT, padx=(12, 0))
        ttk.Entry(self.find_bar, textvariable=self.replace_text, width=24).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(self.find_bar, text="One", command=self.replace_current).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(self.find_bar, text="All", command=self.replace_all).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(self.find_bar, text="X", command=self.hide_find_bar).pack(side=tk.LEFT, padx=(6, 0))
        self.find_text.trace_add("write", lambda *_args: self.highlight_find_matches())

        editor_frame = ttk.Frame(editor_panel)
        editor_frame.pack(fill=tk.BOTH, expand=True)

        self.line_numbers = tk.Canvas(editor_frame, width=48, bg="#1e1e1e", highlightthickness=0)
        self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)

        self.code_editor = tk.Text(
            editor_frame,
            bg="#151515",
            fg="#eeeeee",
            insertbackground="#ffffff",
            selectbackground="#264f78",
            undo=True,
            wrap=tk.NONE,
            font=("Menlo", 12),
            padx=8,
            pady=6
        )
        self.code_editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        code_scroll = ttk.Scrollbar(editor_frame, orient=tk.VERTICAL, command=self.on_code_scrollbar)
        code_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        code_x_scroll = ttk.Scrollbar(editor_panel, orient=tk.HORIZONTAL, command=self.code_editor.xview)
        code_x_scroll.pack(fill=tk.X)
        self.code_editor.configure(
            yscrollcommand=lambda first, last: self.on_code_yscroll(code_scroll, first, last),
            xscrollcommand=code_x_scroll.set
        )

        self.code_editor.tag_configure("keyword", foreground="#569cd6")
        self.code_editor.tag_configure("string", foreground="#ce9178")
        self.code_editor.tag_configure("comment", foreground="#6a9955")
        self.code_editor.tag_configure("number", foreground="#b5cea8")
        self.code_editor.tag_configure("classdef", foreground="#4ec9b0")
        self.code_editor.tag_configure("functiondef", foreground="#dcdcaa")
        self.code_editor.tag_configure("find_match", background="#51513a")
        self.code_editor.tag_configure("find_current", background="#7f6a00")

        self.code_editor.bind("<<Modified>>", self.on_code_modified)
        self.code_editor.bind("<KeyRelease>", self.on_code_key_release)
        self.code_editor.bind("<ButtonRelease-1>", lambda _event: self.update_line_numbers())
        self.code_editor.bind("<MouseWheel>", lambda _event: self.after_idle(self.update_line_numbers))
        self.code_editor.bind("<Tab>", self.insert_code_tab)
        self.code_editor.bind("<Return>", self.insert_code_newline)
        self.code_editor.bind("<Control-s>", self.save_script_shortcut)
        self.code_editor.bind("<Control-o>", self.open_script_shortcut)
        self.code_editor.bind("<Control-n>", self.new_script_shortcut)
        self.code_editor.bind("<Control-f>", self.find_shortcut)
        self.code_editor.bind("<Control-h>", self.replace_shortcut)
        self.code_editor.bind("<Control-g>", self.go_to_line_shortcut)
        self.code_editor.bind("<Control-a>", self.select_all_code)
        self.code_editor.bind("<Command-s>", self.save_script_shortcut)
        self.code_editor.bind("<Command-o>", self.open_script_shortcut)
        self.code_editor.bind("<Command-n>", self.new_script_shortcut)
        self.code_editor.bind("<Command-f>", self.find_shortcut)
        self.code_editor.bind("<Command-g>", self.go_to_line_shortcut)
        self.code_editor.bind("<Command-a>", self.select_all_code)
        self.code_highlight_job = None

        self.editor_status = ttk.Label(editor_panel, text="Ln 1, Col 1")
        self.editor_status.pack(anchor="e", pady=(4, 0))
        self.refresh_script_tree()

    def on_code_scrollbar(self, *args) -> None:
        self.code_editor.yview(*args)
        self.update_line_numbers()

    def on_code_yscroll(self, scrollbar, first: str, last: str) -> None:
        scrollbar.set(first, last)
        self.update_line_numbers()

    def refresh_script_tree(self) -> None:
        if not hasattr(self, "script_tree"):
            return

        self.script_tree.delete(*self.script_tree.get_children())
        scripts_dir = self.scene_path.parent / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)

        for path in sorted(scripts_dir.rglob("*.py")):
            relative_path = path.relative_to(scripts_dir)
            parent = ""
            parts = relative_path.parts
            for depth, part in enumerate(parts):
                item_path = scripts_dir.joinpath(*parts[:depth + 1])
                item_id = str(item_path)
                if not self.script_tree.exists(item_id):
                    self.script_tree.insert(parent, tk.END, iid=item_id, text=part, open=True)
                parent = item_id

    def open_script_from_tree(self, _event=None) -> None:
        selection = self.script_tree.selection()
        if not selection:
            return

        path = Path(selection[0])
        if path.is_file():
            if not self.confirm_discard_script_changes():
                return
            self.load_script(path)
            self.center_tabs.select(self.code_tab)

    def on_code_key_release(self, _event=None) -> None:
        self.schedule_code_highlight()
        self.highlight_find_matches()
        self.update_cursor_status()

    def update_cursor_status(self) -> None:
        if not hasattr(self, "editor_status"):
            return

        line, column = self.code_editor.index(tk.INSERT).split(".")
        total_lines = int(self.code_editor.index("end-1c").split(".")[0])
        dirty = "Unsaved" if self.current_script_dirty else "Saved"
        self.editor_status.configure(text=f"Ln {line}, Col {int(column) + 1} | {total_lines} lines | {dirty}")

    def update_line_numbers(self) -> None:
        if not hasattr(self, "line_numbers"):
            return

        self.line_numbers.delete("all")
        first_line = int(self.code_editor.index("@0,0").split(".")[0])
        last_line = int(self.code_editor.index(f"@0,{self.code_editor.winfo_height()}").split(".")[0]) + 1

        for line_number in range(first_line, last_line + 1):
            line_info = self.code_editor.dlineinfo(f"{line_number}.0")
            if line_info is None:
                continue
            _, y, _, height, _ = line_info
            self.line_numbers.create_text(
                40,
                y + height / 2,
                anchor="e",
                fill="#858585",
                font=("Menlo", 12),
                text=str(line_number)
            )

    def on_code_modified(self, _event=None) -> None:
        if not self.code_editor.edit_modified():
            return

        self.current_script_dirty = True
        self.update_script_path_label()
        self.update_cursor_status()
        self.schedule_code_highlight()
        self.update_line_numbers()
        self.code_editor.edit_modified(False)

    def update_script_path_label(self) -> None:
        if self.current_script_path is None:
            label = "Untitled"
        else:
            try:
                label = str(self.current_script_path.relative_to(self.scene_path.parent))
            except ValueError:
                label = str(self.current_script_path)

        if self.current_script_dirty:
            label += " *"

        self.script_path_label.configure(text=label)

    def insert_code_tab(self, _event=None) -> str:
        self.code_editor.insert(tk.INSERT, "    ")
        return "break"

    def insert_code_newline(self, _event=None) -> str:
        line_start = self.code_editor.index("insert linestart")
        line_end = self.code_editor.index("insert lineend")
        current_line = self.code_editor.get(line_start, line_end)
        indentation = re.match(r"\s*", current_line).group(0)
        if current_line.rstrip().endswith(":"):
            indentation += "    "

        self.code_editor.insert(tk.INSERT, "\n" + indentation)
        return "break"

    def save_script_shortcut(self, _event=None) -> str:
        self.save_script()
        return "break"

    def open_script_shortcut(self, _event=None) -> str:
        self.open_script_dialog()
        return "break"

    def new_script_shortcut(self, _event=None) -> str:
        self.new_script_dialog()
        return "break"

    def find_shortcut(self, _event=None) -> str:
        self.show_find_bar()
        return "break"

    def replace_shortcut(self, _event=None) -> str:
        self.show_replace_bar()
        return "break"

    def go_to_line_shortcut(self, _event=None) -> str:
        self.go_to_line_dialog()
        return "break"

    def select_all_code(self, _event=None) -> str:
        self.code_editor.tag_add(tk.SEL, "1.0", tk.END)
        self.code_editor.mark_set(tk.INSERT, "1.0")
        self.code_editor.see(tk.INSERT)
        return "break"

    def show_find_bar(self) -> None:
        if not self.find_bar.winfo_ismapped():
            self.find_bar.pack(fill=tk.X, pady=(0, 6), before=self.code_editor.master)
        self.find_bar.focus_set()

    def show_replace_bar(self) -> None:
        self.show_find_bar()

    def hide_find_bar(self) -> None:
        self.find_bar.pack_forget()
        self.code_editor.tag_remove("find_match", "1.0", tk.END)
        self.code_editor.tag_remove("find_current", "1.0", tk.END)

    def highlight_find_matches(self) -> None:
        if not hasattr(self, "code_editor"):
            return

        self.code_editor.tag_remove("find_match", "1.0", tk.END)
        self.code_editor.tag_remove("find_current", "1.0", tk.END)
        query = self.find_text.get()
        if not query:
            return

        start = "1.0"
        while True:
            match_start = self.code_editor.search(query, start, tk.END, nocase=False)
            if not match_start:
                break
            match_end = f"{match_start}+{len(query)}c"
            self.code_editor.tag_add("find_match", match_start, match_end)
            start = match_end

    def find_next(self) -> None:
        query = self.find_text.get()
        if not query:
            return

        start = self.code_editor.index(f"{tk.INSERT}+1c")
        match_start = self.code_editor.search(query, start, tk.END, nocase=False)
        if not match_start:
            match_start = self.code_editor.search(query, "1.0", tk.END, nocase=False)
        if not match_start:
            return

        match_end = f"{match_start}+{len(query)}c"
        self.highlight_find_matches()
        self.code_editor.tag_add("find_current", match_start, match_end)
        self.code_editor.tag_remove(tk.SEL, "1.0", tk.END)
        self.code_editor.tag_add(tk.SEL, match_start, match_end)
        self.code_editor.mark_set(tk.INSERT, match_end)
        self.code_editor.see(match_start)

    def replace_current(self) -> None:
        query = self.find_text.get()
        if not query:
            return

        current_match = self.code_editor.tag_ranges("find_current")
        selection = current_match or self.code_editor.tag_ranges(tk.SEL)
        if not selection or self.code_editor.get(selection[0], selection[1]) != query:
            self.find_next()
            current_match = self.code_editor.tag_ranges("find_current")
            selection = current_match or self.code_editor.tag_ranges(tk.SEL)

        if selection and self.code_editor.get(selection[0], selection[1]) == query:
            self.code_editor.delete(selection[0], selection[1])
            self.code_editor.insert(selection[0], self.replace_text.get())
            self.highlight_find_matches()

    def replace_all(self) -> None:
        query = self.find_text.get()
        if not query:
            return

        replacement = self.replace_text.get()
        start = "1.0"
        count = 0
        while True:
            match_start = self.code_editor.search(query, start, tk.END, nocase=False)
            if not match_start:
                break
            match_end = f"{match_start}+{len(query)}c"
            self.code_editor.delete(match_start, match_end)
            self.code_editor.insert(match_start, replacement)
            start = f"{match_start}+{len(replacement)}c"
            count += 1

        self.log(f"Replaced {count} occurrence(s).")

    def go_to_line_dialog(self) -> None:
        line_number = simpledialog.askinteger("Go To Line", "Line number:", minvalue=1)
        if line_number is None:
            return

        last_line = int(self.code_editor.index("end-1c").split(".")[0])
        line_number = max(1, min(line_number, last_line))
        self.code_editor.mark_set(tk.INSERT, f"{line_number}.0")
        self.code_editor.see(tk.INSERT)
        self.update_cursor_status()

    def schedule_code_highlight(self) -> None:
        if self.code_highlight_job is not None:
            self.after_cancel(self.code_highlight_job)
        self.code_highlight_job = self.after(120, self.highlight_code)

    def highlight_code(self) -> None:
        self.code_highlight_job = None
        if not hasattr(self, "code_editor"):
            return

        for tag in ("keyword", "string", "comment", "number", "classdef", "functiondef"):
            self.code_editor.tag_remove(tag, "1.0", tk.END)

        content = self.code_editor.get("1.0", "end-1c")
        keyword_pattern = r"\b(" + "|".join(re.escape(word) for word in keyword.kwlist) + r")\b"

        for line_index, line in enumerate(content.splitlines(), start=1):
            for match in re.finditer(r"#.*$", line):
                self.add_code_tag("comment", line_index, match.start(), match.end())

            for match in re.finditer(r"('([^'\\]|\\.)*'|\"([^\"\\]|\\.)*\")", line):
                self.add_code_tag("string", line_index, match.start(), match.end())

            for match in re.finditer(r"\b\d+(\.\d+)?\b", line):
                self.add_code_tag("number", line_index, match.start(), match.end())

            for match in re.finditer(keyword_pattern, line):
                self.add_code_tag("keyword", line_index, match.start(), match.end())

            class_match = re.search(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)", line)
            if class_match:
                self.add_code_tag("classdef", line_index, class_match.start(1), class_match.end(1))

            function_match = re.search(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)", line)
            if function_match:
                self.add_code_tag("functiondef", line_index, function_match.start(1), function_match.end(1))

    def add_code_tag(self, tag: str, line: int, start: int, end: int) -> None:
        self.code_editor.tag_add(tag, f"{line}.{start}", f"{line}.{end}")

    def _build_properties(self) -> None:
        ttk.Label(self.properties_frame, text="Properties", font=("Arial", 12, "bold")).pack(anchor="w", padx=8, pady=6)

        self.property_entries: dict[str, tk.Entry] = {}
        form = ttk.Frame(self.properties_frame)
        form.pack(fill=tk.X, padx=8)

        fields = [
            "name", "type", "pos_x", "pos_y", "pos_z",
            "rot_x", "rot_y", "rot_z", "scale_x", "scale_y", "scale_z", "script"
        ]

        for row, field in enumerate(fields):
            ttk.Label(form, text=field).grid(row=row, column=0, sticky="w", pady=2)
            entry = ttk.Entry(form)
            entry.grid(row=row, column=1, sticky="ew", pady=2)
            self.property_entries[field] = entry

        form.columnconfigure(1, weight=1)
        ttk.Button(self.properties_frame, text="Apply", command=self.apply_properties).pack(fill=tk.X, padx=8, pady=8)

    def _build_output(self) -> None:
        output_frame = ttk.Frame(self)
        output_frame.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Label(output_frame, text="Output", font=("Arial", 10, "bold")).pack(anchor="w", padx=8)
        self.output = tk.Text(output_frame, height=6, bg="#111111", fg="#dddddd")
        self.output.pack(fill=tk.X, padx=8, pady=(0, 8))

    def log(self, message: str) -> None:
        self.output.insert(tk.END, message + "\n")
        self.output.see(tk.END)

    def close_studio(self) -> None:
        if not self.confirm_discard_script_changes():
            return
        print("Closed PythonStudio. Goodbye!")
        self.destroy()

    def load_scene(self, path: Path) -> None:
        self.stop_play_mode(log_message=True)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.objects = [SceneObject(obj) for obj in data.get("objects", [])]
            self.scene_path = path
            self.selected_index = None
            self.refresh_explorer()
            self.refresh_script_tree()
            self.clear_properties()
            self.draw_viewport()
            self.log(f"Loaded scene: {path}")
        except Exception as error:
            messagebox.showerror("Load Scene Error", str(error))

    def build_scene_data(self) -> dict:
        return {
            "name": self.scene_path.stem,
            "objects": [obj.to_dict() for obj in self.objects]
        }

    def save_scene(self) -> bool:
        try:
            self.scene_path.parent.mkdir(parents=True, exist_ok=True)
            self.scene_path.write_text(json.dumps(self.build_scene_data(), indent=4), encoding="utf-8")
            self.log(f"Saved scene: {self.scene_path}")
            return True
        except Exception as error:
            messagebox.showerror("Save Scene Error", str(error))
            self.log(f"Failed to save scene: {error}")
            return False

    def save_scene_as_dialog(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save Scene As",
            initialdir=self.scene_path.parent,
            initialfile=self.scene_path.name,
            defaultextension=".json",
            filetypes=[("Scene JSON", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return

        self.scene_path = Path(path)
        self.save_scene()

    def new_script_dialog(self) -> None:
        if not self.confirm_discard_script_changes():
            return

        script_name = simpledialog.askstring("New Script", "Script name:", initialvalue="NewScript")
        if not script_name:
            return

        safe_name = "".join(char for char in script_name if char.isalnum() or char in ("_", "-")).strip()
        safe_name = safe_name or "NewScript"
        if not safe_name.endswith(".py"):
            safe_name += ".py"

        script_path = self.scene_path.parent / "scripts" / safe_name
        script_path.parent.mkdir(parents=True, exist_ok=True)
        if script_path.exists():
            messagebox.showerror("New Script Error", f"Script already exists: {script_path}")
            return

        class_name = "".join(part.capitalize() for part in script_path.stem.replace("-", "_").split("_")) or "NewScript"
        template = (
            f"class {class_name}:\n"
            "    def start(self):\n"
            "        pass\n\n"
            "    def update(self, dt):\n"
            "        pass\n"
        )
        script_path.write_text(template, encoding="utf-8")
        self.load_script(script_path)
        self.refresh_script_tree()
        self.center_tabs.select(self.code_tab)
        self.log(f"Created script: {script_path}")

    def open_script_dialog(self) -> None:
        if not self.confirm_discard_script_changes():
            return

        path = filedialog.askopenfilename(
            title="Open Script",
            initialdir=self.scene_path.parent / "scripts",
            filetypes=[("Python Script", "*.py"), ("All files", "*.*")]
        )
        if path:
            self.load_script(Path(path))
            self.center_tabs.select(self.code_tab)

    def open_selected_object_script(self) -> None:
        if not self.confirm_discard_script_changes():
            return

        if self.selected_index is None:
            messagebox.showinfo("No Selection", "Select an object first.")
            return

        script = self.objects[self.selected_index].script
        if not script:
            messagebox.showinfo("No Script", "Selected object has no script assigned.")
            return

        script_path = self.resolve_script_path(script)
        if not script_path.exists():
            messagebox.showerror("Open Script Error", f"Script not found: {script_path}")
            return

        self.load_script(script_path)
        self.center_tabs.select(self.code_tab)

    def load_script(self, path: Path) -> None:
        try:
            self.current_script_path = path
            self.code_editor.delete("1.0", tk.END)
            self.code_editor.insert("1.0", path.read_text(encoding="utf-8"))
            self.current_script_dirty = False
            self.code_editor.edit_modified(False)
            self.update_script_path_label()
            self.highlight_code()
            self.update_line_numbers()
            self.update_cursor_status()
            self.log(f"Opened script: {path}")
        except Exception as error:
            messagebox.showerror("Open Script Error", str(error))

    def save_script(self) -> bool:
        if self.current_script_path is None:
            path = filedialog.asksaveasfilename(
                title="Save Script",
                initialdir=self.scene_path.parent / "scripts",
                defaultextension=".py",
                filetypes=[("Python Script", "*.py"), ("All files", "*.*")]
            )
            if not path:
                return False
            self.current_script_path = Path(path)

        try:
            self.current_script_path.parent.mkdir(parents=True, exist_ok=True)
            self.current_script_path.write_text(self.code_editor.get("1.0", "end-1c"), encoding="utf-8")
            self.current_script_dirty = False
            self.code_editor.edit_modified(False)
            self.update_script_path_label()
            self.refresh_script_tree()
            self.update_cursor_status()
            self.log(f"Saved script: {self.current_script_path}")
            return True
        except Exception as error:
            messagebox.showerror("Save Script Error", str(error))
            self.log(f"Failed to save script: {error}")
            return False

    def confirm_discard_script_changes(self) -> bool:
        if not self.current_script_dirty:
            return True

        result = messagebox.askyesnocancel(
            "Unsaved Script",
            "Save changes to the current script before continuing?"
        )
        if result is None:
            return False
        if result:
            return self.save_script()
        return True

    def attach_script_to_selected(self) -> None:
        if self.selected_index is None:
            messagebox.showinfo("No Selection", "Select an object first.")
            return

        if self.current_script_path is None:
            messagebox.showinfo("No Script", "Open or create a script first.")
            return

        if not self.save_script():
            return

        obj = self.objects[self.selected_index]
        try:
            obj.script = str(self.current_script_path.relative_to(self.scene_path.parent))
        except ValueError:
            obj.script = str(self.current_script_path)

        self.show_properties(obj)
        self.save_scene()
        self.log(f"Attached script to {obj.name}: {obj.script}")

    def new_scene(self) -> None:
        scene_name = simpledialog.askstring("New Scene", "Scene name:", initialvalue="NewScene")
        if not scene_name:
            return

        self.stop_play_mode(log_message=True)
        self.scene_path = self._get_unique_scene_path(scene_name)
        self.objects = []
        self.selected_index = None
        self.refresh_explorer()
        self.refresh_script_tree()
        self.clear_properties()
        self.save_scene()
        self.draw_viewport()
        self.log(f"Created new scene without deleting the old one: {self.scene_path}")

    def open_scene_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="Open Scene",
            initialdir=PROJECTS_DIR,
            filetypes=[("Scene JSON", "*.json"), ("All files", "*.*")]
        )
        if path:
            self.load_scene(Path(path))

    def refresh_explorer(self) -> None:
        self.object_list.delete(0, tk.END)
        for obj in self.objects:
            self.object_list.insert(tk.END, obj.name)

    def on_object_selected(self, _event=None) -> None:
        selection = self.object_list.curselection()
        if not selection:
            return
        self.selected_index = int(selection[0])
        self.show_properties(self.objects[self.selected_index])
        self.draw_viewport()

    def on_explorer_click(self, event) -> None:
        clicked_index = self.object_list.nearest(event.y)
        item_bbox = self.object_list.bbox(clicked_index)
        if item_bbox is None or event.y < item_bbox[1] or event.y > item_bbox[1] + item_bbox[3]:
            self.unselect_object()

    def unselect_object(self) -> None:
        self.selected_index = None
        self.object_list.selection_clear(0, tk.END)
        self.clear_properties()
        self.draw_viewport()

    def show_properties(self, obj: SceneObject) -> None:
        values = {
            "name": obj.name,
            "type": obj.type,
            "pos_x": obj.position[0],
            "pos_y": obj.position[1],
            "pos_z": obj.position[2],
            "rot_x": obj.rotation[0],
            "rot_y": obj.rotation[1],
            "rot_z": obj.rotation[2],
            "scale_x": obj.scale[0],
            "scale_y": obj.scale[1],
            "scale_z": obj.scale[2],
            "script": obj.script,
        }
        for field, value in values.items():
            entry = self.property_entries[field]
            entry.delete(0, tk.END)
            entry.insert(0, str(value))

    def clear_properties(self) -> None:
        for entry in self.property_entries.values():
            entry.delete(0, tk.END)

    def apply_properties(self) -> None:
        if self.selected_index is None:
            messagebox.showinfo("No Selection", "Select an object first.")
            return

        obj = self.objects[self.selected_index]
        try:
            obj.name = self.property_entries["name"].get() or "Object"
            obj.type = self.property_entries["type"].get() or "cube"
            obj.position = [
                float(self.property_entries["pos_x"].get()),
                float(self.property_entries["pos_y"].get()),
                float(self.property_entries["pos_z"].get()),
            ]
            obj.rotation = [
                float(self.property_entries["rot_x"].get()),
                float(self.property_entries["rot_y"].get()),
                float(self.property_entries["rot_z"].get()),
            ]
            obj.scale = [
                float(self.property_entries["scale_x"].get()),
                float(self.property_entries["scale_y"].get()),
                float(self.property_entries["scale_z"].get()),
            ]
            obj.script = self.property_entries["script"].get()
        except ValueError:
            messagebox.showerror("Invalid Properties", "Position, rotation, and scale must be numbers.")
            return

        self.refresh_explorer()
        self.object_list.select_set(self.selected_index)
        self.save_scene()
        self.draw_viewport()
        self.log(f"Applied properties to {obj.name}.")

    def add_cube(self) -> None:
        name = simpledialog.askstring("Add Cube", "Cube name:", initialvalue=f"Cube{len(self.objects) + 1}")
        if not name:
            return
        self.objects.append(SceneObject({"name": name, "type": "cube"}))
        self.refresh_explorer()
        self.save_scene()
        self.draw_viewport()
        self.log(f"Added cube: {name}")

    def delete_selected(self) -> None:
        if self.selected_index is None:
            messagebox.showinfo("No Selection", "Select an object first.")
            return
        deleted = self.objects.pop(self.selected_index)
        self.selected_index = None
        self.refresh_explorer()
        self.clear_properties()
        self.save_scene()
        self.draw_viewport()
        self.log(f"Deleted object: {deleted.name}")

    def on_key_press(self, event) -> None:
        focused_widget = self.focus_get()
        if isinstance(focused_widget, tk.Entry | tk.Text):
            return

        key = event.keysym.lower()
        object_delta = 0.5

        if key == "escape":
            self.unselect_object()
            return

        if key in ("a", "d", "w", "s", "q", "e"):
            self.pressed_keys.add(key)
            return

        if self.selected_index is None:
            return

        if key == "left":
            self.move_selected(-object_delta, 0.0, 0.0)
        elif key == "right":
            self.move_selected(object_delta, 0.0, 0.0)
        elif key == "up":
            self.move_selected(0.0, 0.0, -object_delta)
        elif key == "down":
            self.move_selected(0.0, 0.0, object_delta)

    def on_key_release(self, event) -> None:
        self.pressed_keys.discard(event.keysym.lower())

    def move_selected(self, dx: float, dy: float, dz: float) -> None:
        obj = self.objects[self.selected_index]
        obj.position[0] += dx
        obj.position[1] += dy
        obj.position[2] += dz
        self.show_properties(obj)
        self.save_scene()
        self.draw_viewport()
        self.log(f"Moved {obj.name} to {obj.position}")

    def update_camera_movement(self, delta_time: float) -> None:
        move_delta = CAMERA_MOVE_SPEED * delta_time
        yaw = math.radians(self.camera_yaw)
        forward_x = math.sin(yaw) * move_delta
        forward_z = math.cos(yaw) * move_delta
        right_x = math.cos(yaw) * move_delta
        right_z = -math.sin(yaw) * move_delta

        if "w" in self.pressed_keys:
            self.camera_target_x += forward_x
            self.camera_target_z += forward_z
        if "s" in self.pressed_keys:
            self.camera_target_x -= forward_x
            self.camera_target_z -= forward_z
        if "d" in self.pressed_keys:
            self.camera_target_x += right_x
            self.camera_target_z += right_z
        if "a" in self.pressed_keys:
            self.camera_target_x -= right_x
            self.camera_target_z -= right_z
        if "q" in self.pressed_keys:
            self.camera_target_y -= move_delta
        if "e" in self.pressed_keys:
            self.camera_target_y += move_delta

    def draw_viewport(self) -> None:
        now = time.perf_counter()
        delta_time = now - self.last_frame_time
        self.last_frame_time = now
        if delta_time > 0:
            current_fps = 1.0 / delta_time
            self.fps = current_fps if self.fps == 0.0 else self.fps * 0.9 + current_fps * 0.1

        self.viewport.delete("all")
        width = max(1, self.viewport.winfo_width())
        height = max(1, self.viewport.winfo_height())

        self.viewport.create_text(
            20,
            20,
            anchor="nw",
            fill="#8ee36f",
            text=f"FPS: {self.fps:0.0f}"
        )
        self.viewport.create_text(
            20,
            42,
            anchor="nw",
            fill="#ffffff",
            text="3D scene preview\nDrag = rotate camera | Scroll = zoom\nWASD = pan camera | Q/E = up/down | Arrows = move selected"
        )

        center_x = width / 2
        center_y = height / 2

        self.viewport.create_line(0, center_y, width, center_y, fill="#333333")
        self.viewport.create_line(center_x, 0, center_x, height, fill="#333333")
        self._draw_grid()

        for index, obj in enumerate(self.objects):
            if obj.type.lower() == "cube":
                selected = index == self.selected_index
                self._draw_cube_3d(obj, selected)
            else:
                x, y = self._project_point(obj.position[0], obj.position[1], obj.position[2])
                self.viewport.create_oval(x - 5, y - 5, x + 5, y + 5, outline="#ffffff")
                self.viewport.create_text(x, y - 14, fill="#ffffff", text=obj.name)

    def update_viewport(self) -> None:
        now = time.perf_counter()
        delta_time = min(0.1, now - self.last_update_time)
        self.last_update_time = now
        self.update_camera_movement(delta_time)
        self.update_play_mode(delta_time)
        self.draw_viewport()
        self.after(16, self.update_viewport)

    def start_camera_drag(self, event) -> None:
        self.last_mouse_x = event.x
        self.last_mouse_y = event.y

    def drag_camera(self, event) -> None:
        dx = event.x - self.last_mouse_x
        dy = event.y - self.last_mouse_y

        self.camera_yaw += dx * 0.5
        self.camera_pitch += dy * 0.5
        self.camera_pitch = max(-80.0, min(80.0, self.camera_pitch))

        self.last_mouse_x = event.x
        self.last_mouse_y = event.y

        self.draw_viewport()

    def enable_viewport_scroll(self, _event=None) -> None:
        self.bind_all("<MouseWheel>", self.zoom_camera)
        self.bind_all("<Button-4>", self.zoom_camera_linux)
        self.bind_all("<Button-5>", self.zoom_camera_linux)

    def disable_viewport_scroll(self, _event=None) -> None:
        self.unbind_all("<MouseWheel>")
        self.unbind_all("<Button-4>")
        self.unbind_all("<Button-5>")

    def zoom_camera(self, event) -> str | None:
        if not self._is_pointer_over_viewport(event):
            return None

        if getattr(event, "num", None) == 4:
            self.camera_distance -= 2
        elif getattr(event, "num", None) == 5:
            self.camera_distance += 2
        elif getattr(event, "delta", 0) > 0:
            self.camera_distance -= 2
        elif getattr(event, "delta", 0) < 0:
            self.camera_distance += 2
        else:
            return "break"

        self.camera_distance = max(5.0, min(100.0, self.camera_distance))
        self.draw_viewport()
        return "break"

    def zoom_camera_linux(self, event) -> None:
        self.zoom_camera(event)

    def _is_pointer_over_viewport(self, event) -> bool:
        pointer_x = getattr(event, "x_root", None)
        pointer_y = getattr(event, "y_root", None)

        if pointer_x is None or pointer_y is None:
            pointer_x, pointer_y = self.winfo_pointerxy()

        viewport_x = self.viewport.winfo_rootx()
        viewport_y = self.viewport.winfo_rooty()
        viewport_width = self.viewport.winfo_width()
        viewport_height = self.viewport.winfo_height()

        return (
            viewport_x <= pointer_x < viewport_x + viewport_width
            and viewport_y <= pointer_y < viewport_y + viewport_height
        )

    def _draw_grid(self) -> None:
        grid_color = "#2f3338"
        axis_x_color = "#7a4444"
        axis_z_color = "#447a44"
        grid_size = 10

        for i in range(-grid_size, grid_size + 1):
            color = axis_z_color if i == 0 else grid_color
            x1, y1 = self._project_point(-grid_size, 0, i)
            x2, y2 = self._project_point(grid_size, 0, i)
            self.viewport.create_line(x1, y1, x2, y2, fill=color)

            color = axis_x_color if i == 0 else grid_color
            x1, y1 = self._project_point(i, 0, -grid_size)
            x2, y2 = self._project_point(i, 0, grid_size)
            self.viewport.create_line(x1, y1, x2, y2, fill=color)

    def _project_point(self, x: float, y: float, z: float) -> tuple[float, float]:
        width = max(1, self.viewport.winfo_width())
        height = max(1, self.viewport.winfo_height())

        yaw = math.radians(self.camera_yaw)
        pitch = math.radians(self.camera_pitch)

        forward = (
            math.sin(yaw) * math.cos(pitch),
            -math.sin(pitch),
            math.cos(yaw) * math.cos(pitch),
        )
        right = (math.cos(yaw), 0.0, -math.sin(yaw))
        up = (
            forward[1] * right[2] - forward[2] * right[1],
            forward[2] * right[0] - forward[0] * right[2],
            forward[0] * right[1] - forward[1] * right[0],
        )

        relative_x = x - self.camera_target_x
        relative_y = y - self.camera_target_y
        relative_z = z - self.camera_target_z

        camera_space_x = relative_x * right[0] + relative_y * right[1] + relative_z * right[2]
        camera_space_y = relative_x * up[0] + relative_y * up[1] + relative_z * up[2]
        zoom_scale = 25.0 / self.camera_distance
        screen_x = width / 2 + camera_space_x * VIEWPORT_SCALE * zoom_scale
        screen_y = height / 2 - camera_space_y * VIEWPORT_SCALE * zoom_scale
        return screen_x, screen_y

    def _draw_cube_3d(self, obj: SceneObject, selected: bool) -> None:
        px, py, pz = obj.position
        sx, sy, sz = obj.scale
        rx, ry, rz = [math.radians(angle) for angle in obj.rotation]

        hx = sx / 2
        hy = sy / 2
        hz = sz / 2

        local_vertices = [
            (-hx, -hy, -hz),
            (hx, -hy, -hz),
            (hx, hy, -hz),
            (-hx, hy, -hz),
            (-hx, -hy, hz),
            (hx, -hy, hz),
            (hx, hy, hz),
            (-hx, hy, hz),
        ]

        vertices = [
            self._rotate_local_point(x, y, z, rx, ry, rz, px, py, pz)
            for x, y, z in local_vertices
        ]
        projected = [self._project_point(x, y, z) for x, y, z in vertices]
        edges = [
            (0, 1), (1, 2), (2, 3), (3, 0),
            (4, 5), (5, 6), (6, 7), (7, 4),
            (0, 4), (1, 5), (2, 6), (3, 7),
        ]

        color = "#4aa3ff" if selected else "#dddddd"
        line_width = 3 if selected else 2

        for start, end in edges:
            x1, y1 = projected[start]
            x2, y2 = projected[end]
            self.viewport.create_line(x1, y1, x2, y2, fill=color, width=line_width)

        label_x, label_y = self._project_point(px, py + hy + 0.5, pz)
        self.viewport.create_text(label_x, label_y, fill="#ffffff", text=obj.name)

    def _rotate_local_point(
        self,
        x: float,
        y: float,
        z: float,
        rx: float,
        ry: float,
        rz: float,
        px: float,
        py: float,
        pz: float,
    ) -> tuple[float, float, float]:
        cos_x, sin_x = math.cos(rx), math.sin(rx)
        cos_y, sin_y = math.cos(ry), math.sin(ry)
        cos_z, sin_z = math.cos(rz), math.sin(rz)

        y, z = y * cos_x - z * sin_x, y * sin_x + z * cos_x
        x, z = x * cos_y + z * sin_y, -x * sin_y + z * cos_y
        x, y = x * cos_z - y * sin_z, x * sin_z + y * cos_z

        return px + x, py + y, pz + z

    def play_scene(self) -> None:
        if self.is_playing:
            self.log("Play mode is already running.")
            return

        if not self.save_scene():
            return

        self.active_scripts = []
        self.play_state_snapshot = [copy.deepcopy(obj.to_dict()) for obj in self.objects]
        for obj in self.objects:
            if not obj.script:
                continue

            script = self.load_object_script(obj)
            if script is None:
                continue

            script.object = obj
            self.active_scripts.append(script)

            start = getattr(script, "start", None)
            if callable(start):
                try:
                    start()
                except Exception as error:
                    self.log(f"Start error on {obj.name}: {error}")

        self.is_playing = True
        self.log(f"Play mode started with {len(self.active_scripts)} script(s).")

    def stop_scene(self) -> None:
        if not self.is_playing:
            self.log("Play mode is not running.")
            return

        self.stop_play_mode(log_message=True)

    def stop_play_mode(self, log_message: bool = False) -> bool:
        if not self.is_playing:
            return False

        self.is_playing = False
        self.active_scripts = []
        self.restore_play_state()
        self.draw_viewport()
        if log_message:
            self.log("Play mode stopped.")
        return True

    def restore_play_state(self) -> None:
        if self.play_state_snapshot:
            self.objects = [SceneObject(copy.deepcopy(data)) for data in self.play_state_snapshot]

        self.play_state_snapshot = []
        if self.selected_index is not None and self.selected_index >= len(self.objects):
            self.selected_index = None

        self.refresh_explorer()
        if self.selected_index is not None and self.selected_index < len(self.objects):
            self.object_list.select_set(self.selected_index)
            self.show_properties(self.objects[self.selected_index])
        else:
            self.clear_properties()

    def update_play_mode(self, delta_time: float) -> None:
        if not self.is_playing:
            return

        for script in list(self.active_scripts):
            update = getattr(script, "update", None)
            if not callable(update):
                continue

            try:
                update(delta_time)
            except Exception as error:
                self.log(f"Update error in {script.__class__.__name__}: {error}")
                self.active_scripts.remove(script)

        if self.selected_index is not None:
            self.show_properties(self.objects[self.selected_index])

    def load_object_script(self, obj: SceneObject):
        script_path = self.resolve_script_path(obj.script)
        if not script_path.exists():
            self.log(f"Script not found for {obj.name}: {script_path}")
            return None

        try:
            module_name = f"pythonstudio_script_{script_path.stem}_{id(obj)}"
            spec = importlib.util.spec_from_file_location(module_name, script_path)
            if spec is None or spec.loader is None:
                self.log(f"Could not load script for {obj.name}: {script_path}")
                return None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            script_class = self.find_script_class(module)
            if script_class is None:
                self.log(f"No script class found in {script_path}")
                return None

            return script_class()
        except Exception as error:
            self.log(f"Load error for {obj.name} script {script_path}: {error}")
            return None

    def resolve_script_path(self, script: str) -> Path:
        path = Path(script)
        if path.is_absolute():
            return path
        return self.scene_path.parent / path

    def find_script_class(self, module):
        for value in vars(module).values():
            if isinstance(value, type) and value.__module__ == module.__name__:
                return value
        return None


if __name__ == "__main__":
    app = PythonStudioEditor()
    app.mainloop()
