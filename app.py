import customtkinter as ctk
from tkinter import filedialog
from pathlib import Path
from steam_api import COMMON_FOLDER, get_game_path_by_name
import shutil, os, subprocess, threading, sys, ast, time, webbrowser


def resource_path(relative):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative)
    return os.path.join(os.path.abspath('.'), relative)


def safe_eval_minutes(expr):
    expr = expr.strip()
    if not expr:
        return 15.0
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
        result = float(eval(compile(tree, '<string>', 'eval')))
        if result <= 0:
            raise ValueError("Duration must be greater than 0")
        return result
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Invalid expression: {e}")


def resolve_addr(addr):
    addr = addr.strip()
    p = Path(addr)
    if p.is_absolute():
        return str(p)
    base = Path(COMMON_FOLDER).resolve()
    target = (base / addr).resolve()
    if not str(target).startswith(str(base)):
        raise ValueError("Relative address must stay inside steamapps\\common")
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
        self.geometry("560x560")
        self.resizable(False, False)

        self._active_thread = None
        self._start_time = None
        self._duration_ms = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        # ── Header ────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20, 0))

        ctk.CTkLabel(
            header, text="Discord Quest Completer",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text="Simulate running a game to complete Discord quests — no download needed.",
            text_color="gray55", font=ctk.CTkFont(size=12),
        ).pack(anchor="w", pady=(3, 0))

        # ── Input card ────────────────────────────────────────────────
        card = ctk.CTkFrame(self, corner_radius=12)
        card.pack(fill="x", padx=20, pady=(16, 0))

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=18)
        inner.columnconfigure(0, weight=1)

        # Game Name
        ctk.CTkLabel(inner, text="Game Name",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     anchor="w").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))

        self.name_entry = ctk.CTkEntry(
            inner, placeholder_text="e.g. Valorant",
            height=36, font=ctk.CTkFont(size=13))
        self.name_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 4))

        ctk.CTkLabel(inner, text="Auto-detected via Steam when Address is left blank.",
                     text_color="gray55", font=ctk.CTkFont(size=11),
                     anchor="w").grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 14))

        # Address
        ctk.CTkLabel(inner, text="Address  (optional)",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     anchor="w").grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 4))

        addr_row = ctk.CTkFrame(inner, fg_color="transparent")
        addr_row.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        addr_row.columnconfigure(0, weight=1)

        self.addr_entry = ctk.CTkEntry(
            addr_row,
            placeholder_text=r"Relative (e.g. Valorant\VALORANT.exe) or full path (C:\...)",
            height=36, font=ctk.CTkFont(size=13))
        self.addr_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(addr_row, text="Browse", width=80, height=36,
                      command=self._browse).grid(row=0, column=1)

        ctk.CTkLabel(inner,
                     text="Relative to steamapps\\common, or paste any full absolute path.",
                     text_color="gray55", font=ctk.CTkFont(size=11),
                     anchor="w").grid(row=5, column=0, columnspan=2, sticky="w", pady=(0, 2))

        reddit_link = ctk.CTkLabel(
            inner,
            text="Not sure of the path? Find it on r/DiscordQuests ↗",
            text_color="#4A9EFF", font=ctk.CTkFont(size=11),
            cursor="hand2", anchor="w")
        reddit_link.grid(row=6, column=0, columnspan=2, sticky="w", pady=(0, 14))
        reddit_link.bind("<Button-1>",
                         lambda e: webbrowser.open("https://www.reddit.com/r/DiscordQuests/"))

        # Duration
        ctk.CTkLabel(inner, text="Duration (minutes)",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     anchor="w").grid(row=7, column=0, columnspan=2, sticky="w", pady=(0, 4))

        self.time_entry = ctk.CTkEntry(
            inner, placeholder_text="e.g.  15  or  15*2",
            height=36, font=ctk.CTkFont(size=13))
        self.time_entry.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(0, 4))

        ctk.CTkLabel(inner,
                     text="Default: 15 min. Math expressions like 15*2 are supported.",
                     text_color="gray55", font=ctk.CTkFont(size=11),
                     anchor="w").grid(row=9, column=0, columnspan=2, sticky="w")

        # ── Error label ───────────────────────────────────────────────
        self.error_label = ctk.CTkLabel(
            self, text="", text_color="#FF6B6B",
            font=ctk.CTkFont(size=12), wraplength=500)
        self.error_label.pack(pady=(12, 0))

        # ── Launch button ─────────────────────────────────────────────
        self.launch_btn = ctk.CTkButton(
            self, text="Launch", width=180, height=44,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.launch)
        self.launch_btn.pack(pady=(6, 0))

        # ── Status + progress ─────────────────────────────────────────
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=20, pady=(14, 20))

        self.status_label = ctk.CTkLabel(
            bottom, text="Ready.",
            text_color="gray55", font=ctk.CTkFont(size=12), anchor="w")
        self.status_label.pack(fill="x")

        self.progress_bar = ctk.CTkProgressBar(bottom, height=14, corner_radius=6)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", pady=(6, 0))

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
        except ValueError:
            self.addr_entry.delete(0, "end")
            self.addr_entry.insert(0, path)
        self._set_error("")

    def launch(self):
        name = self.name_entry.get().strip()
        addr = self.addr_entry.get().strip()
        time_expr = self.time_entry.get().strip() or "15"

        if not name and not addr:
            self._set_error("Enter a Game Name or an Address.")
            return

        try:
            duration_min = safe_eval_minutes(time_expr)
        except ValueError as e:
            self._set_error(str(e))
            return

        duration_s = int(duration_min * 60) + 20

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
                    found_addr = resolve_addr(addr)
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
