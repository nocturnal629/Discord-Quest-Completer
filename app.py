import customtkinter as ctk
from tkinter import filedialog
from pathlib import Path
from steam_api import COMMON_FOLDER, get_game_path_by_name
import shutil, os, subprocess, threading, sys, ast, time


def resource_path(relative):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative)
    return os.path.join(os.path.abspath('.'), relative)


def safe_eval_seconds(expr):
    expr = expr.strip()
    if not expr:
        return 900
    try:
        tree = ast.parse(expr, mode='eval')
        allowed = (
            ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
            ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod,
            ast.USub, ast.UAdd,
        )
        for node in ast.walk(tree):
            if not isinstance(node, allowed):
                raise ValueError("Only numeric expressions are allowed")
        result = int(eval(compile(tree, '<string>', 'eval')))
        if result <= 0:
            raise ValueError("Duration must be greater than 0")
        return result
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Invalid expression: {e}")


def sanitize_addr(addr):
    base = Path(COMMON_FOLDER).resolve()
    target = (base / addr).resolve()
    if not str(target).startswith(str(base)):
        raise ValueError("Address must be relative to steamapps\\common")
    return str(target)


def mkdir_track(path):
    p = Path(path)
    created = []
    for parent in reversed(p.parents):
        if not parent.exists():
            created.append(parent)
    if not p.exists():
        created.append(p)
    p.mkdir(parents=True, exist_ok=True)
    return created


def fmt_time(seconds):
    seconds = max(0, seconds)
    if seconds >= 3600:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}h {m}m"
    if seconds >= 60:
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}m {s}s"
    return f"{seconds:.0f}s"


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("Discord Quest Completer")
        self.geometry("520x590")
        self.resizable(False, False)

        self._active_thread = None
        self._start_time = None
        self._duration_ms = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        info = ctk.CTkFrame(self, fg_color="transparent")
        info.pack(fill="x", padx=24, pady=(20, 0))

        ctk.CTkLabel(info, text="How it works",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(
            info,
            text=(
                "1. Enter the Game Name to auto-detect via Steam, or fill in\n"
                "   Address manually (relative path inside steamapps\\common).\n"
                "2. Set the Duration in seconds. Math like 15*60 is supported;\n"
                "   leave blank for the default of 900 s (15 min).\n"
                "3. Click Launch — the real game .exe is temporarily swapped for\n"
                "   a harmless fake, then fully restored when the timer ends."
            ),
            justify="left",
            text_color="gray70",
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", pady=(4, 0))

        ctk.CTkFrame(self, height=1, fg_color="gray30").pack(fill="x", padx=24, pady=14)

        fields = ctk.CTkFrame(self, fg_color="transparent")
        fields.pack(fill="x", padx=24)
        fields.columnconfigure(1, weight=1)

        row = 0

        ctk.CTkLabel(fields, text="Game Name",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(0, 2))
        row += 1
        self.name_entry = ctk.CTkEntry(
            fields, placeholder_text="e.g. Valorant", font=ctk.CTkFont(size=13))
        self.name_entry.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(0, 3))
        row += 1
        ctk.CTkLabel(fields, text="Used to find the game automatically when Address is blank.",
                     text_color="gray55", font=ctk.CTkFont(size=11)).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(0, 12))
        row += 1

        ctk.CTkLabel(fields, text="Address  (optional)",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(0, 2))
        row += 1
        self.addr_entry = ctk.CTkEntry(
            fields, placeholder_text=r"e.g. Valorant\VALORANT.exe",
            font=ctk.CTkFont(size=13))
        self.addr_entry.grid(row=row, column=0, columnspan=2, sticky="ew",
                             padx=(0, 8), pady=(0, 3))
        ctk.CTkButton(fields, text="Browse", width=72, height=30,
                      command=self._browse).grid(row=row, column=2, pady=(0, 3))
        row += 1
        ctk.CTkLabel(fields, text="Relative path inside steamapps\\common.",
                     text_color="gray55", font=ctk.CTkFont(size=11)).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(0, 12))
        row += 1

        ctk.CTkLabel(fields, text="Duration (seconds)",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(0, 2))
        row += 1
        self.time_entry = ctk.CTkEntry(
            fields, placeholder_text="e.g. 900  or  15*60",
            font=ctk.CTkFont(size=13))
        self.time_entry.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(0, 3))
        row += 1
        ctk.CTkLabel(fields, text="Default: 900 s (15 min). Math expressions are supported.",
                     text_color="gray55", font=ctk.CTkFont(size=11)).grid(
            row=row, column=0, columnspan=3, sticky="w")

        self.error_label = ctk.CTkLabel(
            self, text="", text_color="#FF6B6B",
            font=ctk.CTkFont(size=12), wraplength=460)
        self.error_label.pack(pady=(10, 0))

        self.launch_btn = ctk.CTkButton(
            self, text="Launch", width=160, height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.launch)
        self.launch_btn.pack(pady=(8, 0))

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=24, pady=(14, 20))

        self.status_label = ctk.CTkLabel(
            bottom, text="Ready.", text_color="gray60", font=ctk.CTkFont(size=12))
        self.status_label.pack()

        self.progress_bar = ctk.CTkProgressBar(bottom, width=460)
        self.progress_bar.set(0)
        self.progress_bar.pack(pady=(6, 0))

    def _browse(self):
        base = Path(COMMON_FOLDER)
        initial = str(base) if base.exists() else str(Path.home())
        path = filedialog.askopenfilename(
            parent=self,
            title="Select game executable",
            initialdir=initial,
            filetypes=[("Executables", "*.exe"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            rel = Path(path).relative_to(Path(COMMON_FOLDER))
            self.addr_entry.delete(0, "end")
            self.addr_entry.insert(0, str(rel))
            self._set_error("")
        except ValueError:
            self._set_error("Selected file is not inside steamapps\\common.")

    def launch(self):
        name = self.name_entry.get().strip()
        addr = self.addr_entry.get().strip()
        time_expr = self.time_entry.get().strip() or "900"

        if not name and not addr:
            self._set_error("Enter a Game Name or an Address.")
            return

        try:
            duration_s = safe_eval_seconds(time_expr)
        except ValueError as e:
            self._set_error(str(e))
            return

        self._set_error("")
        self.launch_btn.configure(state="disabled", text="Running...")
        self.progress_bar.set(0)
        self._set_status("Starting...")

        t = threading.Thread(
            target=self._launch_thread,
            args=(name, addr, duration_s),
            daemon=True,
        )
        t.start()
        self._active_thread = t

    def _launch_thread(self, name, addr, duration_s):
        try:
            if addr:
                try:
                    found_addr = sanitize_addr(addr)
                except ValueError as e:
                    self.after(0, lambda: self._finish_error(str(e)))
                    return
            else:
                self.after(0, lambda: self._set_status("Searching Steam database..."))
                result = get_game_path_by_name(name)
                if not result:
                    self.after(0, lambda: self._finish_error(
                        f'"{name}" was not found in the Steam database.\n'
                        "Try entering the Address manually instead."
                    ))
                    return
                found_addr = result['full_path']
                game_name = result['official_name']
                self.after(0, lambda: self._set_status(f"Found: {game_name}"))

            dir_addr = os.path.dirname(found_addr)
            created_dirs = mkdir_track(dir_addr)
            backup_addr = os.path.join(dir_addr, 'old_game_file.exe')
            is_installed = len(created_dirs) == 0

            if is_installed:
                os.rename(found_addr, backup_addr)

            try:
                shutil.copy(resource_path('quest_timer.exe'), found_addr)
                duration_ms = duration_s * 1000
                self.after(0, lambda: self._start_progress(duration_ms))
                subprocess.run([found_addr, str(duration_ms)])
            finally:
                if is_installed:
                    if os.path.exists(found_addr):
                        os.remove(found_addr)
                    if os.path.exists(backup_addr):
                        os.rename(backup_addr, found_addr)
                elif created_dirs:
                    shutil.rmtree(str(created_dirs[0]))

            self.after(0, self._finish_success)

        except Exception as e:
            self.after(0, lambda: self._finish_error(str(e)))

    def _start_progress(self, duration_ms):
        self._start_time = time.time()
        self._duration_ms = duration_ms
        self._tick_progress()

    def _tick_progress(self):
        if self._start_time is None:
            return
        elapsed_ms = (time.time() - self._start_time) * 1000
        pct = min(elapsed_ms / self._duration_ms, 1.0)
        remaining_s = max(self._duration_ms - elapsed_ms, 0) / 1000
        self.progress_bar.set(pct)
        self._set_status(f"Running... {pct * 100:.0f}%  —  {fmt_time(remaining_s)} left")
        if pct < 1.0:
            self.after(500, self._tick_progress)

    def _finish_success(self):
        self._start_time = None
        self.progress_bar.set(1)
        self._set_status("Done! Quest completed successfully.")
        self.launch_btn.configure(state="normal", text="Launch")

    def _finish_error(self, msg):
        self._start_time = None
        self.progress_bar.set(0)
        self._set_error(msg)
        self._set_status("Ready.")
        self.launch_btn.configure(state="normal", text="Launch")

    def _set_status(self, text):
        self.status_label.configure(text=text)

    def _set_error(self, text):
        self.error_label.configure(text=text)

    def _on_close(self):
        self.destroy()
