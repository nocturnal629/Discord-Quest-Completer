import customtkinter as ctk
from tkinter import filedialog
from pathlib import Path
import shutil, os, subprocess, threading, sys, ast, time, webbrowser

from steam_api import search_steam_game

COMMON_FOLDER = r'C:\Program Files (x86)\Steam\steamapps\common'


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

    if addr.startswith(('\\', '/')):
        drive = os.environ.get('SystemDrive', 'C:')
        return str(Path(drive + '\\' + addr.lstrip('/\\')))

    base = Path(COMMON_FOLDER).resolve()
    return str((base / addr).resolve())


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
        ctk.set_default_color_theme("dark-blue")

        self.title("Discord Quest Completer")
        self.geometry("520x580")
        self.resizable(False, False)
        self.configure(fg_color="#0e1015")

        self._active_thread = None
        self._start_time = None
        self._duration_ms = None
        self._is_running = False
        self._is_searching = False

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(0, self._apply_icon)

    def _apply_icon(self):
        icon_path = resource_path("icon.ico")
        try:
            self.iconbitmap(icon_path)
        except Exception:
            pass

    def _build_ui(self):
        main_container = ctk.CTkFrame(self, fg_color="#0e1015", corner_radius=0)
        main_container.pack(fill="both", expand=True, padx=0, pady=0)

        # ── Launch button ─── packed first so it always reserves bottom space
        button_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        button_frame.pack(side="bottom", fill="x", pady=(0, 25))

        self.launch_btn = ctk.CTkButton(
            button_frame,
            text="Start Quest",
            width=460,
            height=52,
            font=ctk.CTkFont(size=17, weight="bold"),
            fg_color="#5865F2",
            hover_color="#4752c4",
            corner_radius=12,
            command=self.launch
        )
        self.launch_btn.pack()

        # ── Header ────────────────────────────────
        header_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        header_frame.pack(fill="x", padx=30, pady=(20, 0))

        ctk.CTkLabel(
            header_frame, text="Discord Quest Completer",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="#ffffff"
        ).pack(anchor="w")

        # ── Main card ─────────────────────────────────────────────────────
        card = ctk.CTkFrame(main_container, fg_color="#1a1d23", corner_radius=16, border_width=1, border_color="#2a2d35")
        card.pack(fill="x", padx=30, pady=(15, 0))

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=24, pady=24)
        inner.columnconfigure(0, weight=1)

        # ── Find Game on Steam Section ─────────────────────────────────────
        search_header = ctk.CTkFrame(inner, fg_color="transparent")
        search_header.grid(row=0, column=0, columnspan=2, sticky="ew")

        ctk.CTkLabel(search_header, text="🔍", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 8), pady=(0, 2))
        ctk.CTkLabel(search_header, text="FIND GAME ON STEAM",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#8b8d94").pack(side="left")

        search_frame = ctk.CTkFrame(inner, fg_color="#0e1015", corner_radius=8, border_width=1, border_color="#2a2d35")
        search_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        search_frame.columnconfigure(0, weight=1)

        self.game_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text="Enter game name (e.g. Where Winds Meet)",
            height=42,
            font=ctk.CTkFont(size=13),
            fg_color="#0e1015",
            border_width=0,
            text_color="#ffffff"
        )
        self.game_entry.grid(row=0, column=0, sticky="ew", padx=(12, 0), pady=1)
        self.game_entry.bind("<Return>", lambda e: self._search_game())

        self.search_btn = ctk.CTkButton(
            search_frame,
            text="Search",
            width=70,
            height=32,
            fg_color="#5865F2",
            hover_color="#4752c4",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._search_game
        )
        self.search_btn.grid(row=0, column=1, padx=(0, 6), pady=5)

        self.search_status = ctk.CTkLabel(
            inner, text="",
            text_color="#4a4d55",
            font=ctk.CTkFont(size=11), anchor="w", wraplength=440
        )
        self.search_status.grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 2))

        # ── Game Path Section ──────────────────────────────────────────────
        path_header = ctk.CTkFrame(inner, fg_color="transparent")
        path_header.grid(row=4, column=0, columnspan=2, sticky="ew")

        ctk.CTkLabel(path_header, text="🎮", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 8), pady=(0, 4))
        ctk.CTkLabel(path_header, text="GAME PATH",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#8b8d94").pack(side="left")

        addr_frame = ctk.CTkFrame(inner, fg_color="#0e1015", corner_radius=8, border_width=1, border_color="#2a2d35")
        addr_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        addr_frame.columnconfigure(0, weight=1)

        self.addr_entry = ctk.CTkEntry(
            addr_frame,
            placeholder_text="Enter game path (e.g. Win64\VALORANT-Win64-Shipping.exe)",
            height=42,
            font=ctk.CTkFont(size=13),
            fg_color="#0e1015",
            border_width=0,
            text_color="#ffffff",
            justify="left"
        )
        self.addr_entry.grid(row=0, column=0, sticky="ew", padx=(12, 12), pady=1)
        self.addr_entry.configure(justify="left")

        self.addr_entry.bind("<KeyRelease>", lambda e: self._update_addr_preview())

        self.addr_preview = ctk.CTkLabel(
            inner, text="", text_color="#4a4d55",
            font=ctk.CTkFont(size=11), anchor="w", justify="left", wraplength=440
        )
        self.addr_preview.grid(row=6, column=0, columnspan=2, sticky="w", pady=(2, 8))

        help_frame = ctk.CTkFrame(inner, fg_color="#1e2127", corner_radius=8, height=32)
        help_frame.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(0, 20))
        help_frame.grid_propagate(False)

        reddit_link = ctk.CTkLabel(
            help_frame,
            text="💡 Find game paths on r/DiscordQuests →",
            text_color="#5865F2",
            font=ctk.CTkFont(size=12),
            cursor="hand2"
        )
        reddit_link.pack(anchor="center", pady=6)
        reddit_link.bind("<Button-1>", lambda e: webbrowser.open("https://www.reddit.com/r/DiscordQuests/"))
        reddit_link.bind("<Enter>", lambda e: reddit_link.configure(text_color="#6d79f3"))
        reddit_link.bind("<Leave>", lambda e: reddit_link.configure(text_color="#5865F2"))

        # ── Duration Section ───────────────────────────────────────────────
        duration_header = ctk.CTkFrame(inner, fg_color="transparent")
        duration_header.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(duration_header, text="⏱️", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 8), pady=(0, 4))
        ctk.CTkLabel(duration_header, text="DURATION (MINS)",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#8b8d94").pack(side="left")

        time_frame = ctk.CTkFrame(inner, fg_color="#0e1015", corner_radius=8, border_width=1, border_color="#2a2d35")
        time_frame.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(0, 6))

        self.time_entry = ctk.CTkEntry(
            time_frame,
            placeholder_text="minutes",
            height=42,
            font=ctk.CTkFont(size=13),
            fg_color="#0e1015",
            border_width=0,
            text_color="#ffffff"
        )
        self.time_entry.pack(fill="x", padx=12, pady=1)
        self.time_entry.insert(0, "15")

        # ── Error label ────────────────────────────────────────────────────
        self.error_label = ctk.CTkLabel(
            main_container, text="", text_color="#ff5555",
            font=ctk.CTkFont(size=12), wraplength=460
        )
        self.error_label.pack(pady=(6, 0))


    def _search_game(self):
        if self._is_searching or self._is_running:
            return
        query = self.game_entry.get().strip()
        if not query:
            self.search_status.configure(text="⚠️ Enter a game name to search", text_color="#faa61a")
            return

        self._is_searching = True
        self.search_btn.configure(state="disabled", text="...")
        self.search_status.configure(text="🔍 Searching Steam...", text_color="#8b8d94")
        self._set_error("")

        threading.Thread(target=self._search_thread, args=(query,), daemon=True).start()

    def _search_thread(self, query):
        try:
            result = search_steam_game(query)
            if result is None:
                self.after(0, lambda: self._on_search_result(None, "❌ Game not found on Steam", "#ff5555"))
            else:
                name = result['official_name']
                self.after(0, lambda: self._on_search_result(result, f"✅ Found: {name}", "#43b581"))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._on_search_result(None, f"⚠️ Search failed: {err}", "#faa61a"))
        finally:
            self.after(0, self._search_reset)

    def _on_search_result(self, result, status_text, status_color):
        self.search_status.configure(text=status_text, text_color=status_color)
        if result:
            self.addr_entry.delete(0, "end")
            self.addr_entry.insert(0, result['relative_path'])
            self._update_addr_preview()

    def _search_reset(self):
        self.search_btn.configure(state="normal", text="Search")
        self._is_searching = False

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
        self._update_addr_preview()

    def _update_addr_preview(self):
        addr = self.addr_entry.get().strip()
        if not addr:
            self.addr_preview.configure(text="")
            return
        try:
            resolved = resolve_addr(addr)
            self.addr_preview.configure(text=f"📁 {resolved}", text_color="#43b581")
        except Exception:
            self.addr_preview.configure(text="⚠️ Invalid path", text_color="#faa61a")

    def launch(self):
        if self._is_running:
            return

        addr = self.addr_entry.get().strip()
        duration_s = int(self.time_entry.get().strip()) * 60

        self._set_error("")
        self._is_running = True
        self.launch_btn.configure(state="disabled", text="Initializing...", fg_color="#3a4070")

        t = threading.Thread(
            target=self._launch_thread,
            args=(addr, duration_s),
            daemon=True,
        )
        t.start()
        self._active_thread = t

    def _launch_thread(self, addr, duration_s):
        try:
            try:
                found_addr = resolve_addr(addr)
            except ValueError as e:
                self.after(0, lambda: self._finish_error(str(e)))
                return

            dir_addr = os.path.dirname(found_addr)
            created_dirs = mkdir_track(dir_addr)
            backup_addr = os.path.join(dir_addr, 'old_game_file.exe')
            is_installed = len(created_dirs) == 0

            if is_installed and os.path.exists(found_addr):
                os.rename(found_addr, backup_addr)

            try:
                quest_timer_path = resource_path('quest_timer.exe')
                if not os.path.exists(quest_timer_path):
                    raise FileNotFoundError(f"quest_timer.exe not found at {quest_timer_path}")

                shutil.copy(quest_timer_path, found_addr)
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
            import traceback
            traceback.format_exc()
            self.after(0, lambda: self._finish_error(str(e)))

    def _start_progress(self, duration_ms):
        self._start_time = time.time()
        self._duration_ms = duration_ms
        self.launch_btn.configure(text="Quest Running", fg_color="#43b581")
        self._tick_progress()

    def _tick_progress(self):
        if self._start_time is None:
            return
        elapsed_ms = (time.time() - self._start_time) * 1000
        pct = min(elapsed_ms / self._duration_ms, 1.0)
        remaining_s = max(self._duration_ms - elapsed_ms, 0) / 1000

        if remaining_s > 0:
            self.launch_btn.configure(text=f"⏸ {fmt_time(remaining_s)}")

        if pct < 1.0:
            self.after(500, self._tick_progress)

    def _finish_success(self):
        self._start_time = None
        self._is_running = False
        self.launch_btn.configure(text="✅ Quest Complete!", fg_color="#43b581")

        self.after(3000, lambda: self.launch_btn.configure(state="normal", text="Start Quest", fg_color="#5865F2"))

    def _finish_error(self, msg):
        self._start_time = None
        self._is_running = False
        self._set_error(f"❌ {msg}")
        self.launch_btn.configure(state="normal", text="Start Quest", fg_color="#5865F2")

    def _set_error(self, text):
        self.error_label.configure(text=text)

    def _on_close(self):
        self.destroy()
