from __future__ import annotations

import json
import math
import time
import tkinter as tk
import importlib.util
import copy
import keyword
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageTk
except Exception:
    Image = None
    ImageDraw = None
    ImageEnhance = None
    ImageTk = None

APP_NAME = "PythonStudio"
APP_VERSION = "0.3.0"
ROOT_DIR = Path(__file__).resolve().parents[1]
PROJECTS_DIR = ROOT_DIR / "projects"
DEFAULT_PROJECT_DIR = PROJECTS_DIR / "MyFirstGame"
DEFAULT_SCENE_PATH = DEFAULT_PROJECT_DIR / "scene.json"
CAMERA_DISTANCE = 18
VIEWPORT_SCALE = 35
CAMERA_MOVE_SPEED = 3.0
MAX_OBJ_RENDER_VERTICES = 700
MAX_OBJ_RENDER_EDGES = 900
MAX_OBJ_TEXTURE_FACES = 20
UPDATE_VERSION_URL = "https://raw.githubusercontent.com/Bowser127867/PythonStudio/main/editor/version.json"
UPDATE_EDITOR_URL = "https://raw.githubusercontent.com/Bowser127867/PythonStudio/main/editor/main_editor.py"
UPDATE_CACHE_DIR = ROOT_DIR / "usedDuringUpdate"
UPDATE_EDITOR_PATH = "editor/main_editor.py"
UPDATE_CHECK_ON_STARTUP = True

print("Starting PythonStudio...")

class SceneObject:
    def __init__(self, data: dict):
        self.name = data.get("name", "Object")
        self.type = data.get("type", "cube")
        self.position = data.get("position", [0.0, 0.0, 0.0])
        self.rotation = data.get("rotation", [0.0, 0.0, 0.0])
        self.scale = data.get("scale", [1.0, 1.0, 1.0])
        self.color = data.get("color", [1.0, 1.0, 1.0])
        self.texture = data.get("texture", "")
        self.mesh = data.get("mesh", "")
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
        if self.texture:
            data["texture"] = self.texture
        if self.mesh:
            data["mesh"] = self.mesh
        if self.script:
            data["script"] = self.script
        return data


class PythonStudioEditor(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1100x700")
        self.minsize(900, 560)

        self.scene_path = DEFAULT_SCENE_PATH
        self.objects: list[SceneObject] = []
        self.selected_index: Optional[int] = None
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
        self.current_script_path: Optional[Path] = None
        self.current_script_dirty = False
        self.texture_source_cache = {}
        self.mesh_cache = {}
        self.viewport_image_refs = []
        self.failed_texture_paths = set()
        self.failed_mesh_paths = set()

        self._ensure_default_project()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.close_studio)
        self.bind_all("<KeyPress>", self.on_key_press)
        self.bind_all("<KeyRelease>", self.on_key_release)
        self.load_scene(self.scene_path)
        self.log("PythonStudio started.")
        self.after(16, self.update_viewport)
        if UPDATE_CHECK_ON_STARTUP:
            self.after(800, self.check_for_editor_update)

    def _ensure_default_project(self) -> None:
        DEFAULT_PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        UPDATE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.ensure_project_folders(DEFAULT_PROJECT_DIR)

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

    def ensure_project_folders(self, project_dir: Path) -> None:
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "scripts").mkdir(exist_ok=True)
        (project_dir / "assets").mkdir(exist_ok=True)
        (project_dir / "assets" / "models").mkdir(parents=True, exist_ok=True)
        (project_dir / "customTextures").mkdir(exist_ok=True)

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
        file_menu.add_command(label="Check for Editor Updates", command=self.check_for_editor_update)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.close_studio)
        menu_bar.add_cascade(label="File", menu=file_menu)

        object_menu = tk.Menu(menu_bar, tearoff=False)
        object_menu.add_command(label="Add Cube", command=self.add_cube)
        object_menu.add_command(label="Add Sphere", command=self.add_sphere)
        object_menu.add_command(label="Add Wedge", command=self.add_wedge)
        object_menu.add_command(label="Add Pyramid", command=self.add_pyramid)
        object_menu.add_command(label="Import OBJ...", command=self.import_obj_dialog)
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
        script_menu.add_command(label="Object Script Help", command=self.show_object_script_help)
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
        ttk.Button(toolbar, text="Object Help", command=self.show_object_script_help).pack(side=tk.LEFT, padx=(6, 0))

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

    def show_object_script_help(self) -> None:
        if hasattr(self, "script_help_window") and self.script_help_window.winfo_exists():
            self.script_help_window.lift()
            return

        obj = self.objects[self.selected_index] if self.selected_index is not None else None
        object_name = obj.name if obj else "selected object"
        object_type = obj.type if obj else "object"

        self.script_help_window = tk.Toplevel(self)
        self.script_help_window.title("Object Script Help")
        self.script_help_window.geometry("560x620")

        container = ttk.Frame(self.script_help_window)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        help_canvas = tk.Canvas(container, highlightthickness=0)
        help_scroll = ttk.Scrollbar(container, orient=tk.VERTICAL, command=help_canvas.yview)
        help_body = ttk.Frame(help_canvas)
        help_body.bind(
            "<Configure>",
            lambda _event: help_canvas.configure(scrollregion=help_canvas.bbox("all"))
        )
        help_canvas.create_window((0, 0), window=help_body, anchor="nw")
        help_canvas.configure(yscrollcommand=help_scroll.set)
        help_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        help_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Label(
            help_body,
            text=f"Scripting {object_name} ({object_type})",
            font=("Arial", 14, "bold")
        ).pack(anchor="w", pady=(0, 8))

        ttk.Label(
            help_body,
            text="Scripts get the attached object as self.object. start() runs once. update(dt) runs every frame while Play is active.",
            wraplength=500
        ).pack(anchor="w", pady=(0, 12))

        sections = [
            (
                "Lifecycle",
                [
                    ("start()", "Runs once when Play starts.", "def start(self):\n    print('started')\n"),
                    ("update(dt)", "Runs every frame. dt is seconds since the last frame.", "def update(self, dt):\n    pass\n"),
                ],
            ),
            (
                "Object Fields",
                [
                    ("name", "Read or change the object name.", "self.object.name = 'Cube'\n"),
                    ("type", "Object type, currently usually 'cube'.", "print(self.object.type)\n"),
                    ("position", "Move the object with [x, y, z].", "self.object.position[0] += 1 * dt\n"),
                    ("rotation", "Rotate with degrees [x, y, z].", "self.object.rotation[1] += 90 * dt\n"),
                    ("scale", "Resize with [x, y, z].", "self.object.scale = [2, 2, 2]\n"),
                    ("color", "RGB values from 0.0 to 1.0.", "self.object.color = [1.0, 0.2, 0.2]\n"),
                    ("mesh", "The imported OBJ path for mesh objects.", "print(self.object.mesh)\n"),
                    ("script", "The assigned script path.", "print(self.object.script)\n"),
                ],
            ),
            (
                "Common Cube Snippets",
                [
                    ("Spin cube", "Rotate around Y while play mode is active.", "def update(self, dt):\n    self.object.rotation[1] += 90 * dt\n"),
                    ("Bounce cube", "Move up and down using time.", "import math\n\n"
                     "class BounceScript:\n    def start(self):\n        self.time = 0\n\n"
                     "    def update(self, dt):\n        self.time += dt\n        self.object.position[1] = 1 + math.sin(self.time * 3)\n"),
                    ("Grow cube", "Scale bigger over time.", "def update(self, dt):\n    self.object.scale[0] += 0.5 * dt\n    self.object.scale[1] += 0.5 * dt\n    self.object.scale[2] += 0.5 * dt\n"),
                    ("Move forward", "Move on the Z axis.", "def update(self, dt):\n    self.object.position[2] += 2 * dt\n"),
                    ("Full template", "A complete object script class.", "class CubeScript:\n    def start(self):\n        self.time = 0\n\n    def update(self, dt):\n        self.time += dt\n        self.object.rotation[1] += 90 * dt\n"),
                ],
            ),
        ]

        for title, rows in sections:
            ttk.Label(help_body, text=title, font=("Arial", 11, "bold")).pack(anchor="w", pady=(12, 4))
            for name, description, snippet in rows:
                row = ttk.Frame(help_body)
                row.pack(fill=tk.X, pady=3)
                text = ttk.Frame(row)
                text.pack(side=tk.LEFT, fill=tk.X, expand=True)
                ttk.Label(text, text=name, font=("Arial", 10, "bold")).pack(anchor="w")
                ttk.Label(text, text=description, wraplength=380).pack(anchor="w")
                ttk.Button(row, text="Insert", command=lambda code=snippet: self.insert_code_snippet(code)).pack(side=tk.RIGHT, padx=(8, 0))

    def insert_code_snippet(self, snippet: str) -> None:
        self.center_tabs.select(self.code_tab)
        self.code_editor.focus_set()
        if not self.code_editor.get("1.0", "end-1c").strip():
            self.code_editor.insert("1.0", snippet)
        else:
            self.code_editor.insert(tk.INSERT, "\n" + snippet)
        self.current_script_dirty = True
        self.update_script_path_label()
        self.highlight_code()
        self.update_line_numbers()

    def _build_properties(self) -> None:
        ttk.Label(self.properties_frame, text="Properties", font=("Arial", 12, "bold")).pack(anchor="w", padx=8, pady=6)

        self.property_entries: dict[str, tk.Entry] = {}
        form = ttk.Frame(self.properties_frame)
        form.pack(fill=tk.X, padx=8)

        fields = [
            "name", "type", "pos_x", "pos_y", "pos_z",
            "rot_x", "rot_y", "rot_z", "scale_x", "scale_y", "scale_z", "texture", "mesh", "script"
        ]

        for row, field in enumerate(fields):
            ttk.Label(form, text=field).grid(row=row, column=0, sticky="w", pady=2)
            if field == "texture":
                texture_row = ttk.Frame(form)
                texture_row.grid(row=row, column=1, sticky="ew", pady=2)
                texture_row.columnconfigure(0, weight=1)
                entry = ttk.Entry(texture_row)
                entry.grid(row=0, column=0, sticky="ew")
                ttk.Button(texture_row, text="Browse", command=self.browse_texture).grid(row=0, column=1, padx=(4, 0))
                ttk.Button(texture_row, text="Clear", command=self.clear_texture_field).grid(row=0, column=2, padx=(4, 0))
            elif field == "mesh":
                mesh_row = ttk.Frame(form)
                mesh_row.grid(row=row, column=1, sticky="ew", pady=2)
                mesh_row.columnconfigure(0, weight=1)
                entry = ttk.Entry(mesh_row)
                entry.grid(row=0, column=0, sticky="ew")
                ttk.Button(mesh_row, text="Browse", command=self.browse_mesh).grid(row=0, column=1, padx=(4, 0))
                ttk.Button(mesh_row, text="Clear", command=self.clear_mesh_field).grid(row=0, column=2, padx=(4, 0))
            else:
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

    def check_for_editor_update(self) -> None:
        if not UPDATE_VERSION_URL:
            self.log("Editor update check skipped: UPDATE_VERSION_URL is not set.")
            return

        self.log("Checking for editor updates...")
        try:
            version_path = self.download_remote_version_file()
            update_info = json.loads(version_path.read_text(encoding="utf-8"))
            remote_version = update_info.get("version") or update_info.get("editor_version")
            editor_link = update_info.get("editor_link") or update_info.get("download_url") or UPDATE_EDITOR_URL

            if not remote_version:
                self.clear_update_cache()
                self.log("Editor update skipped: downloaded version.json has no version.")
                return

            if not self.is_newer_version(remote_version, APP_VERSION):
                self.clear_update_cache()
                self.log(f"Editor is up to date: v{APP_VERSION}")
                return

            should_update = messagebox.askyesno(
                "Editor Update Available",
                f"PythonStudio editor v{remote_version} is available.\n\n"
                f"Current version: v{APP_VERSION}\n\n"
                "Download, replace the editor file, and restart now?"
            )
            if should_update:
                remote_source = self.download_editor_source(editor_link, update_info)
                self.install_editor_update(remote_source, remote_version)
            else:
                self.clear_update_cache()
        except Exception as error:
            self.clear_update_cache()
            self.log(f"Editor update check failed: {error}")

    def download_remote_version_file(self) -> Path:
        self.clear_update_cache()
        version_path = UPDATE_CACHE_DIR / "version.json"
        with urllib.request.urlopen(UPDATE_VERSION_URL, timeout=20) as response:
            version_path.write_bytes(response.read())
        return version_path

    def download_editor_source(self, editor_link: str, update_info: dict) -> str:
        UPDATE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        update_path = UPDATE_CACHE_DIR / Path(editor_link.split("?")[0]).name
        if not update_path.name:
            update_path = UPDATE_CACHE_DIR / "main_editor.py"

        with urllib.request.urlopen(editor_link, timeout=30) as response:
            update_path.write_bytes(response.read())

        if zipfile.is_zipfile(update_path):
            return self.extract_updated_editor_source(update_path, update_info.get("editor_path", UPDATE_EDITOR_PATH))

        return update_path.read_text(encoding="utf-8")

    def extract_updated_editor_source(self, zip_path: Path, editor_path: str) -> str:
        with zipfile.ZipFile(zip_path) as archive:
            update_member = None
            expected_suffix = editor_path.replace("\\", "/")
            for member in archive.namelist():
                normalized_member = member.replace("\\", "/")
                if normalized_member.endswith(expected_suffix):
                    update_member = member
                    break

            if update_member is None:
                raise FileNotFoundError(f"{editor_path} was not found in the update ZIP.")

            return archive.read(update_member).decode("utf-8")

    def is_newer_version(self, remote_version: str, local_version: str) -> bool:
        return self.version_parts(remote_version) > self.version_parts(local_version)

    def version_parts(self, version: str) -> tuple[int, ...]:
        parts = [int(part) for part in re.findall(r"\d+", version)]
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3] or [0, 0, 0])

    def clear_update_cache(self) -> None:
        UPDATE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        for path in UPDATE_CACHE_DIR.iterdir():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()

    def install_editor_update(self, remote_source: str, remote_version: str) -> None:
        editor_path = ROOT_DIR / UPDATE_EDITOR_PATH
        backup_path = editor_path.with_suffix(editor_path.suffix + ".bak")
        backup_path.write_text(editor_path.read_text(encoding="utf-8"), encoding="utf-8")
        editor_path.write_text(remote_source, encoding="utf-8")
        self.log(f"Installed editor update v{remote_version}. Restarting...")
        subprocess.Popen([sys.executable, str(editor_path)], cwd=ROOT_DIR)
        self.destroy()

    def load_scene(self, path: Path) -> None:
        self.stop_play_mode(log_message=True)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.objects = [SceneObject(obj) for obj in data.get("objects", [])]
            self.scene_path = path
            self.ensure_project_folders(self.scene_path.parent)
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
            self.ensure_project_folders(self.scene_path.parent)
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
        self.show_object_script_help()
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
        self.show_object_script_help()

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
        self.show_object_script_help()
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
            "texture": obj.texture,
            "mesh": obj.mesh,
            "script": obj.script,
        }
        for field, value in values.items():
            entry = self.property_entries[field]
            entry.delete(0, tk.END)
            entry.insert(0, str(value))

    def clear_properties(self) -> None:
        for entry in self.property_entries.values():
            entry.delete(0, tk.END)

    def browse_texture(self) -> None:
        texture_dir = ROOT_DIR / "editor" / "textures"
        if not texture_dir.exists():
            texture_dir = self.scene_path.parent / "customTextures"
        texture_dir.mkdir(parents=True, exist_ok=True)

        path = filedialog.askopenfilename(
            title="Select Texture",
            initialdir=texture_dir,
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.gif"),
                ("All files", "*.*"),
            ]
        )
        if not path:
            return

        texture_entry = self.property_entries["texture"]
        texture_entry.delete(0, tk.END)
        texture_entry.insert(0, self.texture_reference_for_path(Path(path)))

    def clear_texture_field(self) -> None:
        texture_entry = self.property_entries["texture"]
        texture_entry.delete(0, tk.END)

    def browse_mesh(self) -> None:
        models_dir = self.scene_path.parent / "assets" / "models"
        models_dir.mkdir(parents=True, exist_ok=True)

        path = filedialog.askopenfilename(
            title="Select OBJ Mesh",
            initialdir=models_dir,
            filetypes=[
                ("Wavefront OBJ", "*.obj"),
                ("All files", "*.*"),
            ]
        )
        if not path:
            return

        mesh_entry = self.property_entries["mesh"]
        mesh_entry.delete(0, tk.END)
        mesh_entry.insert(0, self.asset_reference_for_path(Path(path)))

    def clear_mesh_field(self) -> None:
        mesh_entry = self.property_entries["mesh"]
        mesh_entry.delete(0, tk.END)

    def texture_reference_for_path(self, path: Path) -> str:
        return self.asset_reference_for_path(path)

    def asset_reference_for_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.scene_path.parent))
        except ValueError:
            pass

        try:
            return str(path.relative_to(ROOT_DIR))
        except ValueError:
            return str(path)

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
            obj.texture = self.property_entries["texture"].get()
            obj.mesh = self.property_entries["mesh"].get()
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
        self.add_object("cube", "Cube")

    def add_sphere(self) -> None:
        self.add_object("sphere", "Sphere")

    def add_wedge(self) -> None:
        self.add_object("wedge", "Wedge")

    def add_pyramid(self) -> None:
        self.add_object("pyramid", "Pyramid")

    def import_obj_dialog(self) -> None:
        source_path = filedialog.askopenfilename(
            title="Import OBJ",
            initialdir=self.scene_path.parent,
            filetypes=[
                ("Wavefront OBJ", "*.obj"),
                ("All files", "*.*"),
            ]
        )
        if not source_path:
            return

        source_path = Path(source_path)
        imported_path = self.copy_obj_to_project(source_path)
        if imported_path is None:
            return

        mesh_reference = self.asset_reference_for_path(imported_path)
        name = source_path.stem or f"Mesh{len(self.objects) + 1}"
        self.objects.append(SceneObject({
            "name": name,
            "type": "mesh",
            "mesh": mesh_reference,
            "scale": [2.0, 2.0, 2.0],
        }))
        self.selected_index = len(self.objects) - 1
        self.refresh_explorer()
        self.object_list.selection_clear(0, tk.END)
        self.object_list.select_set(self.selected_index)
        self.show_properties(self.objects[self.selected_index])
        self.save_scene()
        self.draw_viewport()
        self.log(f"Imported OBJ: {mesh_reference}")

    def copy_obj_to_project(self, source_path: Path) -> Optional[Path]:
        try:
            models_dir = self.scene_path.parent / "assets" / "models"
            models_dir.mkdir(parents=True, exist_ok=True)
            destination = models_dir / source_path.name
            counter = 1
            while destination.exists() and destination.resolve() != source_path.resolve():
                destination = models_dir / f"{source_path.stem}_{counter}{source_path.suffix}"
                counter += 1

            if destination.resolve() != source_path.resolve():
                shutil.copy2(source_path, destination)
            return destination
        except Exception as error:
            messagebox.showerror("Import OBJ Error", str(error))
            self.log(f"Failed to import OBJ {source_path}: {error}")
            return None

    def add_object(self, object_type: str, default_name: str) -> None:
        name = simpledialog.askstring(f"Add {default_name}", f"{default_name} name:", initialvalue=f"{default_name}{len(self.objects) + 1}")
        if not name:
            return
        self.objects.append(SceneObject({"name": name, "type": object_type}))
        self.refresh_explorer()
        self.save_scene()
        self.draw_viewport()
        self.log(f"Added {object_type}: {name}")

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

        self.viewport_image_refs.clear()
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
            obj_type = obj.type.lower()
            selected = index == self.selected_index
            if obj_type == "cube":
                self._draw_cube_3d(obj, selected)
            elif obj_type == "sphere":
                self._draw_sphere_3d(obj, selected)
            elif obj_type == "wedge":
                self._draw_wedge_3d(obj, selected)
            elif obj_type == "pyramid":
                self._draw_pyramid_3d(obj, selected)
            elif obj_type == "mesh":
                self._draw_mesh_3d(obj, selected)
            else:
                x, y = self._project_point(obj.position[0], obj.position[1], obj.position[2])
                self.viewport.create_oval(x - 5, y - 5, x + 5, y + 5, outline="#ffffff")
                self.viewport.create_text(x, y - 14, fill="#ffffff", text=self.object_label_text(obj))

    def update_viewport(self) -> None:
        now = time.perf_counter()
        delta_time = min(0.1, now - self.last_update_time)
        self.last_update_time = now
        needs_redraw = self.is_playing or bool(self.pressed_keys)
        if self.pressed_keys:
            self.update_camera_movement(delta_time)
        if self.is_playing:
            self.update_play_mode(delta_time)
        if needs_redraw:
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

    def zoom_camera(self, event) -> Optional[str]:
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

    def _camera_forward_vector(self) -> tuple[float, float, float]:
        yaw = math.radians(self.camera_yaw)
        pitch = math.radians(self.camera_pitch)
        return (
            math.sin(yaw) * math.cos(pitch),
            -math.sin(pitch),
            math.cos(yaw) * math.cos(pitch),
        )

    def _face_normal(self, a: tuple[float, float, float], b: tuple[float, float, float], c: tuple[float, float, float]) -> tuple[float, float, float]:
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        return (
            uy * vz - uz * vy,
            uz * vx - ux * vz,
            ux * vy - uy * vx,
        )

    def _dot(self, a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    def _normalize_vector(self, vector: tuple[float, float, float]) -> tuple[float, float, float]:
        length = math.sqrt(self._dot(vector, vector))
        if length == 0:
            return (0.0, 0.0, 0.0)
        return (vector[0] / length, vector[1] / length, vector[2] / length)

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
        self._draw_cube_texture_faces(obj, projected, vertices)

        color = "#4aa3ff" if selected else ("#b8b8b8" if obj.texture else "#dddddd")
        line_width = 3 if selected else (1 if obj.texture else 2)

        for start, end in edges:
            x1, y1 = projected[start]
            x2, y2 = projected[end]
            self.viewport.create_line(x1, y1, x2, y2, fill=color, width=line_width)

        label_x, label_y = self._project_point(px, py + hy + 0.5, pz)
        self.viewport.create_text(label_x, label_y, fill="#ffffff", text=self.object_label_text(obj))

    def _draw_sphere_3d(self, obj: SceneObject, selected: bool) -> None:
        px, py, pz = obj.position
        sx, sy, sz = obj.scale
        rx, ry, rz = [math.radians(angle) for angle in obj.rotation]
        color = "#4aa3ff" if selected else ("#b8b8b8" if obj.texture else "#dddddd")
        line_width = 3 if selected else (1 if obj.texture else 2)
        segments = 24

        rings = []
        rings.append([(math.cos(angle) * sx / 2, math.sin(angle) * sy / 2, 0.0) for angle in [2 * math.pi * i / segments for i in range(segments)]])
        rings.append([(math.cos(angle) * sx / 2, 0.0, math.sin(angle) * sz / 2) for angle in [2 * math.pi * i / segments for i in range(segments)]])
        rings.append([(0.0, math.cos(angle) * sy / 2, math.sin(angle) * sz / 2) for angle in [2 * math.pi * i / segments for i in range(segments)]])

        projected_rings = [
            [
                self._project_point(*self._rotate_local_point(x, y, z, rx, ry, rz, px, py, pz))
                for x, y, z in ring
            ]
            for ring in rings
        ]

        if obj.texture:
            all_points = [point for ring in projected_rings for point in ring]
            min_x = min(point[0] for point in all_points)
            max_x = max(point[0] for point in all_points)
            min_y = min(point[1] for point in all_points)
            max_y = max(point[1] for point in all_points)
            if not self._draw_texture_in_oval(obj, min_x, min_y, max_x, max_y):
                fill_color = self.texture_material_color(obj.texture)
                self.viewport.create_oval(min_x, min_y, max_x, max_y, fill=fill_color, outline="")

        for points in projected_rings:
            for index in range(len(points)):
                x1, y1 = points[index]
                x2, y2 = points[(index + 1) % len(points)]
                self.viewport.create_line(x1, y1, x2, y2, fill=color, width=line_width)

        label_x, label_y = self._project_point(px, py + sy / 2 + 0.5, pz)
        self.viewport.create_text(label_x, label_y, fill="#ffffff", text=self.object_label_text(obj))

    def _draw_wedge_3d(self, obj: SceneObject, selected: bool) -> None:
        px, py, pz = obj.position
        sx, sy, sz = obj.scale
        rx, ry, rz = [math.radians(angle) for angle in obj.rotation]

        hx = sx / 2
        hy = sy / 2
        hz = sz / 2
        local_vertices = [
            (-hx, -hy, -hz),
            (hx, -hy, -hz),
            (-hx, -hy, hz),
            (hx, -hy, hz),
            (-hx, hy, hz),
            (hx, hy, hz),
        ]
        edges = [
            (0, 1), (0, 2), (1, 3), (2, 3),
            (2, 4), (3, 5), (4, 5),
            (0, 4), (1, 5),
        ]
        faces = [
            (0, 1, 3, 2),
            (2, 3, 5, 4),
            (0, 1, 5, 4),
            (0, 2, 4),
            (1, 3, 5),
        ]
        self._draw_poly_wireframe(obj, local_vertices, edges, faces, rx, ry, rz, selected, py + hy + 0.5)

    def _draw_pyramid_3d(self, obj: SceneObject, selected: bool) -> None:
        px, py, pz = obj.position
        sx, sy, sz = obj.scale
        rx, ry, rz = [math.radians(angle) for angle in obj.rotation]

        hx = sx / 2
        hy = sy / 2
        hz = sz / 2
        local_vertices = [
            (-hx, -hy, -hz),
            (hx, -hy, -hz),
            (hx, -hy, hz),
            (-hx, -hy, hz),
            (0.0, hy, 0.0),
        ]
        edges = [
            (0, 1), (1, 2), (2, 3), (3, 0),
            (0, 4), (1, 4), (2, 4), (3, 4),
        ]
        faces = [
            (0, 1, 2, 3),
            (0, 1, 4),
            (1, 2, 4),
            (2, 3, 4),
            (3, 0, 4),
        ]
        self._draw_poly_wireframe(obj, local_vertices, edges, faces, rx, ry, rz, selected, py + hy + 0.5)

    def _draw_mesh_3d(self, obj: SceneObject, selected: bool) -> None:
        mesh = self.get_obj_mesh(obj.mesh)
        if mesh is None:
            x, y = self._project_point(obj.position[0], obj.position[1], obj.position[2])
            self.viewport.create_oval(x - 5, y - 5, x + 5, y + 5, outline="#ff7777")
            self.viewport.create_text(x, y - 14, fill="#ffffff", text=self.object_label_text(obj))
            return

        px, py, pz = obj.position
        sx, sy, sz = obj.scale
        rx, ry, rz = [math.radians(angle) for angle in obj.rotation]
        render_vertices = mesh["render_vertices"]
        local_vertices = [
            (x * sx, y * sy, z * sz)
            for x, y, z in render_vertices
        ]
        vertices = [
            self._rotate_local_point(x, y, z, rx, ry, rz, px, py, pz)
            for x, y, z in local_vertices
        ]
        projected = [self._project_point(x, y, z) for x, y, z in vertices]
        faces = mesh["render_faces"]
        edges = mesh["render_edges"]

        if selected and obj.texture and faces:
            self._draw_mesh_texture_faces(obj, projected, vertices, faces)

        color = "#4aa3ff" if selected else ("#b8b8b8" if obj.texture else "#dddddd")
        line_width = 2 if selected else 1
        for start, end in edges:
            if start >= len(projected) or end >= len(projected):
                continue
            x1, y1 = projected[start]
            x2, y2 = projected[end]
            self.viewport.create_line(x1, y1, x2, y2, fill=color, width=line_width)

        top_y = max((vertex[1] for vertex in vertices), default=py)
        label_x, label_y = self._project_point(px, top_y + 0.5, pz)
        self.viewport.create_text(label_x, label_y, fill="#ffffff", text=self.object_label_text(obj))

    def _draw_poly_wireframe(
        self,
        obj: SceneObject,
        local_vertices: list[tuple[float, float, float]],
        edges: list[tuple[int, int]],
        faces: list[tuple[int, ...]],
        rx: float,
        ry: float,
        rz: float,
        selected: bool,
        label_y: float,
    ) -> None:
        px, py, pz = obj.position
        vertices = [
            self._rotate_local_point(x, y, z, rx, ry, rz, px, py, pz)
            for x, y, z in local_vertices
        ]
        projected = [self._project_point(x, y, z) for x, y, z in vertices]
        self._draw_mesh_texture_faces(obj, projected, vertices, faces)

        color = "#4aa3ff" if selected else ("#b8b8b8" if obj.texture else "#dddddd")
        line_width = 3 if selected else (1 if obj.texture else 2)

        for start, end in edges:
            x1, y1 = projected[start]
            x2, y2 = projected[end]
            self.viewport.create_line(x1, y1, x2, y2, fill=color, width=line_width)

        label_x, projected_label_y = self._project_point(px, label_y, pz)
        self.viewport.create_text(label_x, projected_label_y, fill="#ffffff", text=self.object_label_text(obj))

    def _draw_cube_texture_faces(
        self,
        obj: SceneObject,
        projected: list[tuple[float, float]],
        vertices: list[tuple[float, float, float]],
    ) -> None:
        if not obj.texture:
            return

        faces = [
            (0, 1, 2, 3),
            (4, 5, 6, 7),
            (0, 1, 5, 4),
            (2, 3, 7, 6),
            (1, 2, 6, 5),
            (0, 3, 7, 4),
        ]

        self._draw_mesh_texture_faces(obj, projected, vertices, faces)

    def _draw_mesh_texture_faces(
        self,
        obj: SceneObject,
        projected: list[tuple[float, float]],
        vertices: list[tuple[float, float, float]],
        faces: list[tuple[int, ...]],
    ) -> None:
        if not obj.texture:
            return

        visible_faces: list[tuple[float, float, list[tuple[float, float]], float]] = []
        forward = self._camera_forward_vector()
        light_direction = self._normalize_vector((-0.35, -0.75, 0.55))

        for face in faces:
            if len(face) < 3:
                continue

            face_vertices = [vertices[index] for index in face]
            normal = self._normalize_vector(self._face_normal(face_vertices[0], face_vertices[1], face_vertices[2]))
            face_center = (
                sum(vertex[0] for vertex in face_vertices) / len(face_vertices),
                sum(vertex[1] for vertex in face_vertices) / len(face_vertices),
                sum(vertex[2] for vertex in face_vertices) / len(face_vertices),
            )
            camera_vector = self._normalize_vector((
                self.camera_target_x - face_center[0],
                self.camera_target_y - face_center[1],
                self.camera_target_z - face_center[2],
            ))
            if abs(self._dot(normal, camera_vector)) < 0.08:
                continue

            points = [projected[index] for index in face]
            min_x = min(point[0] for point in points)
            max_x = max(point[0] for point in points)
            min_y = min(point[1] for point in points)
            max_y = max(point[1] for point in points)
            area = max(0.0, (max_x - min_x) * (max_y - min_y))
            if area <= 16:
                continue

            # Compute depth (distance along camera forward) for painter's ordering
            depths = [
                self._dot((v[0] - self.camera_target_x, v[1] - self.camera_target_y, v[2] - self.camera_target_z), forward)
                for v in face_vertices
            ]
            avg_depth = sum(depths) / len(depths)
            lighting = 0.88 + 0.12 * abs(self._dot(normal, light_direction))

            visible_faces.append((avg_depth, area, points, lighting))

        visible_faces.sort(key=lambda item: item[0], reverse=True)

        for _depth, _area, points, lighting in visible_faces:
            ordered_polygon = self.order_screen_polygon(points)
            flat_points = [coordinate for point in ordered_polygon for coordinate in point]
            self.viewport.create_polygon(flat_points, fill="#2c2c2c", outline="")
            self._draw_texture_on_face(obj, ordered_polygon, lighting)

    def order_screen_polygon(self, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        center_x = sum(point[0] for point in points) / len(points)
        center_y = sum(point[1] for point in points) / len(points)
        return sorted(points, key=lambda point: math.atan2(point[1] - center_y, point[0] - center_x))

    def order_texture_quad(self, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        sorted_by_y = sorted(points, key=lambda point: (point[1], point[0]))
        top = sorted(sorted_by_y[:2], key=lambda point: point[0])
        bottom = sorted(sorted_by_y[2:], key=lambda point: point[0])
        ul, ur = top[0], top[1]
        ll, lr = bottom[0], bottom[1]
        return [ul, ur, lr, ll]

    def _draw_texture_on_face(
        self,
        obj: SceneObject,
        points: list[tuple[float, float]],
        lighting: float,
    ) -> None:
        source_image = self.get_texture_source_image(obj.texture)
        if source_image is None or Image is None or ImageDraw is None or ImageEnhance is None or ImageTk is None:
            return

        min_x = math.floor(min(point[0] for point in points))
        max_x = math.ceil(max(point[0] for point in points))
        min_y = math.floor(min(point[1] for point in points))
        max_y = math.ceil(max(point[1] for point in points))
        width = max(1, max_x - min_x)
        height = max(1, max_y - min_y)
        if width < 4 or height < 4:
            return

        relative_polygon = [
            (point[0] - min_x, point[1] - min_y)
            for point in points
        ]

        if len(points) == 4:
            ul, ur, lr, ll = self.order_texture_quad(points)
            relative_quad = [
                (ul[0] - min_x, ul[1] - min_y),
                (ur[0] - min_x, ur[1] - min_y),
                (lr[0] - min_x, lr[1] - min_y),
                (ll[0] - min_x, ll[1] - min_y),
            ]
            source_quad = [
                (0.0, 0.0),
                (float(source_image.width), 0.0),
                (float(source_image.width), float(source_image.height)),
                (0.0, float(source_image.height)),
            ]
            coefficients = self.perspective_coefficients(relative_quad, source_quad)
            face_image = source_image.transform(
                (width, height),
                Image.Transform.PERSPECTIVE,
                coefficients,
                Image.Resampling.BILINEAR,
            )
        else:
            face_image = source_image.resize((width, height), Image.Resampling.BILINEAR)

        if lighting != 1.0:
            face_image = ImageEnhance.Brightness(face_image).enhance(lighting)

        mask = Image.new("L", (width, height), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.polygon(relative_polygon, fill=255)
        face_image.putalpha(mask)

        photo = ImageTk.PhotoImage(face_image)
        self.viewport.create_image(min_x, min_y, image=photo, anchor="nw")
        self.viewport_image_refs.append(photo)

    def _draw_texture_in_oval(
        self,
        obj: SceneObject,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
    ) -> bool:
        source_image = self.get_texture_source_image(obj.texture)
        if source_image is None or Image is None or ImageDraw is None or ImageTk is None:
            return False

        left = math.floor(min_x)
        top = math.floor(min_y)
        width = max(1, math.ceil(max_x) - left)
        height = max(1, math.ceil(max_y) - top)
        if width < 4 or height < 4:
            return False

        sphere_image = source_image.resize((width, height), Image.Resampling.BILINEAR)
        mask = Image.new("L", (width, height), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, width - 1, height - 1), fill=255)
        sphere_image.putalpha(mask)

        photo = ImageTk.PhotoImage(sphere_image)
        self.viewport.create_image(left, top, image=photo, anchor="nw")
        self.viewport_image_refs.append(photo)
        return True

    def texture_material_color(self, texture: str) -> str:
        source_image = self.get_texture_source_image(texture)
        if source_image is None or Image is None:
            return "#d0d0d0"

        try:
            red, green, blue = source_image.resize((1, 1), Image.Resampling.BILINEAR).getpixel((0, 0))
        except Exception:
            return "#d0d0d0"

        red = min(255, int(red * 1.2))
        green = min(255, int(green * 1.2))
        blue = min(255, int(blue * 1.2))
        return f"#{red:02x}{green:02x}{blue:02x}"

    def get_obj_mesh(self, mesh: str) -> Optional[dict]:
        mesh_path = self.resolve_mesh_path(mesh)
        if mesh_path is None:
            return None

        try:
            stat = mesh_path.stat()
        except OSError:
            return None

        cache_key = (str(mesh_path), stat.st_mtime_ns)
        cached_mesh = self.mesh_cache.get(cache_key)
        if cached_mesh is not None:
            return cached_mesh

        try:
            vertices: list[tuple[float, float, float]] = []
            faces: list[tuple[int, ...]] = []

            for line in mesh_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                parts = line.split()
                if parts[0] == "v" and len(parts) >= 4:
                    vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
                elif parts[0] == "f" and len(parts) >= 4:
                    face_indices = []
                    for token in parts[1:]:
                        raw_index = token.split("/")[0]
                        if not raw_index:
                            continue
                        index = int(raw_index)
                        if index < 0:
                            index = len(vertices) + index
                        else:
                            index -= 1
                        if 0 <= index < len(vertices):
                            face_indices.append(index)
                    if len(face_indices) >= 3:
                        faces.append(tuple(face_indices))

            if not vertices or not faces:
                raise ValueError("OBJ must contain vertices and faces.")

            normalized_vertices = self.normalize_mesh_vertices(vertices)
            edges = self.mesh_edges_from_faces(faces)
            render_vertices, render_faces, render_edges = self.build_obj_render_mesh(normalized_vertices, faces, edges)
            mesh_data = {
                "vertices": normalized_vertices,
                "faces": faces,
                "edges": edges,
                "render_vertices": render_vertices,
                "render_faces": render_faces,
                "render_edges": render_edges,
            }
            self.mesh_cache[cache_key] = mesh_data
            if len(vertices) > len(render_vertices) or len(edges) > len(render_edges):
                self.log(
                    f"OBJ preview optimized: showing {len(render_vertices)}/{len(vertices)} vertices "
                    f"and {len(render_edges)}/{len(edges)} edges."
                )
            return mesh_data
        except Exception as error:
            if mesh_path not in self.failed_mesh_paths:
                self.failed_mesh_paths.add(mesh_path)
                self.log(f"Could not load OBJ {mesh_path}: {error}")
            return None

    def build_obj_render_mesh(
        self,
        vertices: list[tuple[float, float, float]],
        faces: list[tuple[int, ...]],
        edges: list[tuple[int, int]],
    ) -> tuple[list[tuple[float, float, float]], list[tuple[int, ...]], list[tuple[int, int]]]:
        if len(vertices) <= MAX_OBJ_RENDER_VERTICES and len(edges) <= MAX_OBJ_RENDER_EDGES:
            return vertices, self.sample_sequence(faces, MAX_OBJ_TEXTURE_FACES), edges

        stride = max(1, math.ceil(len(vertices) / MAX_OBJ_RENDER_VERTICES))
        kept_indices = set(range(0, len(vertices), stride))
        if 0 not in kept_indices:
            kept_indices.add(0)

        index_map = {}
        render_vertices = []
        for old_index in sorted(kept_indices):
            index_map[old_index] = len(render_vertices)
            render_vertices.append(vertices[old_index])

        render_edges = []
        for start, end in edges:
            if start in index_map and end in index_map:
                render_edges.append((index_map[start], index_map[end]))
            if len(render_edges) >= MAX_OBJ_RENDER_EDGES:
                break

        if len(render_edges) < min(MAX_OBJ_RENDER_EDGES, len(render_vertices) - 1):
            for index in range(len(render_vertices) - 1):
                render_edges.append((index, index + 1))
                if len(render_edges) >= MAX_OBJ_RENDER_EDGES:
                    break

        render_faces = []
        for face in self.sample_sequence(faces, MAX_OBJ_TEXTURE_FACES * 4):
            mapped_face = tuple(index_map[index] for index in face if index in index_map)
            if len(mapped_face) >= 3:
                render_faces.append(mapped_face)
            if len(render_faces) >= MAX_OBJ_TEXTURE_FACES:
                break

        return render_vertices, render_faces, render_edges

    def sample_sequence(self, items: list, max_items: int) -> list:
        if len(items) <= max_items:
            return items
        stride = max(1, math.ceil(len(items) / max_items))
        return items[::stride][:max_items]

    def normalize_mesh_vertices(
        self,
        vertices: list[tuple[float, float, float]],
    ) -> list[tuple[float, float, float]]:
        min_x = min(vertex[0] for vertex in vertices)
        max_x = max(vertex[0] for vertex in vertices)
        min_y = min(vertex[1] for vertex in vertices)
        max_y = max(vertex[1] for vertex in vertices)
        min_z = min(vertex[2] for vertex in vertices)
        max_z = max(vertex[2] for vertex in vertices)

        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        center_z = (min_z + max_z) / 2
        largest_dimension = max(max_x - min_x, max_y - min_y, max_z - min_z, 1.0)

        return [
            (
                (x - center_x) / largest_dimension,
                (y - center_y) / largest_dimension,
                (z - center_z) / largest_dimension,
            )
            for x, y, z in vertices
        ]

    def mesh_edges_from_faces(self, faces: list[tuple[int, ...]]) -> list[tuple[int, int]]:
        edges = set()
        for face in faces:
            for index, start in enumerate(face):
                end = face[(index + 1) % len(face)]
                edges.add(tuple(sorted((start, end))))
        return sorted(edges)

    def get_texture_source_image(self, texture: str):
        texture_path = self.resolve_texture_path(texture)
        if texture_path is None:
            return None

        try:
            stat = texture_path.stat()
        except OSError:
            return None

        cache_key = (str(texture_path), stat.st_mtime_ns)
        cached_image = self.texture_source_cache.get(cache_key)
        if cached_image is not None:
            return cached_image

        try:
            if Image is None or ImageTk is None:
                if texture_path not in self.failed_texture_paths:
                    self.failed_texture_paths.add(texture_path)
                    self.log("Pillow is required for texture preview images.")
                return None

            source_image = Image.open(texture_path).convert("RGB")
            max_size = 256
            source_image.thumbnail((max_size, max_size), Image.Resampling.BILINEAR)
            source_image = ImageEnhance.Contrast(source_image).enhance(1.55)
            source_image = ImageEnhance.Sharpness(source_image).enhance(1.8)
            self.texture_source_cache[cache_key] = source_image.copy()
            return self.texture_source_cache[cache_key]
        except Exception as error:
            if texture_path not in self.failed_texture_paths:
                self.failed_texture_paths.add(texture_path)
                self.log(f"Could not load texture {texture_path}: {error}")
            return None

    def perspective_coefficients(
        self,
        destination_points: list[tuple[float, float]],
        source_points: list[tuple[float, float]],
    ) -> tuple[float, float, float, float, float, float, float, float]:
        matrix = []
        vector = []
        for (x, y), (u, v) in zip(destination_points, source_points):
            matrix.append([x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y])
            vector.append(u)
            matrix.append([0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y])
            vector.append(v)
        return tuple(self.solve_linear_system(matrix, vector))

    def solve_linear_system(self, matrix: list[list[float]], vector: list[float]) -> list[float]:
        size = len(vector)
        augmented = [row[:] + [value] for row, value in zip(matrix, vector)]
        for column in range(size):
            pivot_row = max(range(column, size), key=lambda row: abs(augmented[row][column]))
            augmented[column], augmented[pivot_row] = augmented[pivot_row], augmented[column]
            pivot = augmented[column][column]
            if abs(pivot) < 1e-8:
                continue
            for item in range(column, size + 1):
                augmented[column][item] /= pivot
            for row in range(size):
                if row == column:
                    continue
                factor = augmented[row][column]
                for item in range(column, size + 1):
                    augmented[row][item] -= factor * augmented[column][item]
        return [augmented[row][size] for row in range(size)]

    def resolve_texture_path(self, texture: str) -> Optional[Path]:
        path = Path(texture)
        candidates = []
        if path.is_absolute():
            candidates.append(path)
        else:
            candidates.extend([
                self.scene_path.parent / path,
                ROOT_DIR / path,
                ROOT_DIR / "editor" / "textures" / path,
                self.scene_path.parent / "customTextures" / path,
            ])

        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def resolve_mesh_path(self, mesh: str) -> Optional[Path]:
        if not mesh:
            return None

        path = Path(mesh)
        candidates = []
        if path.is_absolute():
            candidates.append(path)
        else:
            candidates.extend([
                self.scene_path.parent / path,
                ROOT_DIR / path,
                self.scene_path.parent / "assets" / "models" / path,
            ])

        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def object_label_text(self, obj: SceneObject) -> str:
        return obj.name

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
