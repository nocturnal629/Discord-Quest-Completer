import customtkinter as ctk
from pathlib import Path
import shutil, os, subprocess, threading, sys, time, webbrowser

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

import logger
from logger import log, log_exception

COMMON_FOLDER = r'C:\Program Files (x86)\Steam\steamapps\common'

# Fixed quest run time (minutes). +30s buffer is added at launch time.
DURATION_MINUTES = 16


def resource_path(relative):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative)
    return os.path.join(os.path.abspath('.'), relative)


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


class Tooltip:
    """Lightweight hover tooltip for any widget."""

    def __init__(self, widget, text, wraplength=280):
        self.widget = widget
        self.text = text
        self.wraplength = wraplength
        self._tip = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event=None):
        if self._tip is not None:
            return
        x = self.widget.winfo_rootx() + 24
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self._tip = ctk.CTkToplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        self._tip.attributes("-topmost", True)
        frame = ctk.CTkFrame(
            self._tip, fg_color="#1e2127", corner_radius=8,
            border_width=1, border_color="#2a2d35"
        )
        frame.pack()
        ctk.CTkLabel(
            frame, text=self.text, justify="left", anchor="w",
            wraplength=self.wraplength, text_color="#d5d7de",
            font=ctk.CTkFont(size=12),
        ).pack(padx=12, pady=8)

    def _hide(self, _event=None):
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


class App(ctk.CTk):
    def __init__(self):
        log("App started")
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('DiscordQuestCompleter')
        except Exception:
            pass
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title("Discord Quest Completer")
        self.geometry("520x430")
        self.resizable(False, False)
        self.configure(fg_color="#0e1015")

        self._active_thread = None
        self._start_time = None
        self._duration_ms = None
        self._is_running = False
        self._icon_img = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._apply_icon)

    def _apply_icon(self):
        icon_path = resource_path("icon_original.png")
        if not os.path.exists(icon_path):
            log(f"Icon not found at: {icon_path}")
            return
        log(f"Applying icon from: {icon_path}")
        try:
            from PIL import Image, ImageTk
            img = Image.open(icon_path).convert("RGBA")
            self._icon_img = ImageTk.PhotoImage(img.resize((256, 256)))
            self.iconphoto(True, self._icon_img)
            log("Icon applied via iconphoto")
        except Exception as e:
            log(f"Icon apply failed: {e}")

    def _build_ui(self):
        main_container = ctk.CTkFrame(self, fg_color="#0e1015", corner_radius=0)
        main_container.pack(fill="both", expand=True, padx=0, pady=0)

        # ── Header ────────────────────────────────
        header_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        header_frame.pack(fill="x", padx=30, pady=(20, 0))

        ctk.CTkLabel(
            header_frame, text="By ",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#ffffff"
        ).pack(side="left", anchor="w")

        self._logs_enabled = True
        self.logs_btn = ctk.CTkButton(
            header_frame,
            text="📋 Logs: ON",
            width=100,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#2a2d35",
            hover_color="#3a3d47",
            text_color="#43b581",
            corner_radius=8,
            command=self._toggle_logs,
        )
        self.logs_btn.pack(side="right", anchor="e")

        # ── Main card ─────────────────────────────────────────────────────
        card = ctk.CTkFrame(main_container, fg_color="#1a1d23", corner_radius=16, border_width=1, border_color="#2a2d35")
        card.pack(fill="x", padx=30, pady=(15, 0))

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=24, pady=24)
        inner.columnconfigure(0, weight=1)

        # ── Game Path Section ──────────────────────────────────────────────
        path_header = ctk.CTkFrame(inner, fg_color="transparent")
        path_header.grid(row=0, column=0, sticky="ew")

        ctk.CTkLabel(path_header, text="🎮", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 8), pady=(0, 4))
        ctk.CTkLabel(path_header, text="GAME PATH",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#8b8d94").pack(side="left")

        tip_icon = ctk.CTkLabel(
            path_header, text="ⓘ",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#5865F2", cursor="hand2"
        )
        tip_icon.pack(side="left", padx=(8, 0), pady=(0, 2))
        Tooltip(
            tip_icon,
            "Enter one game path per line to launch multiple .exe files at once.\n\n"
            "Example:\n"
            "Win64\\VALORANT-Win64-Shipping.exe\n"
            "League of Legends\\LeagueClient.exe\n\n"
            "Each line is treated as a separate game and runs at the same time.",
        )

        addr_frame = ctk.CTkFrame(inner, fg_color="#0e1015", corner_radius=8, border_width=1, border_color="#2a2d35")
        addr_frame.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        addr_frame.columnconfigure(0, weight=1)

        self.addr_box = ctk.CTkTextbox(
            addr_frame,
            height=110,
            font=ctk.CTkFont(size=13),
            fg_color="#0e1015",
            border_width=0,
            text_color="#ffffff",
            wrap="none",
            activate_scrollbars=True,
        )
        self.addr_box.grid(row=0, column=0, sticky="ew", padx=(8, 8), pady=6)
        self._placeholder = (
            "One game path per line, e.g.\n"
            "Win64\\VALORANT-Win64-Shipping.exe\n"
            "League of Legends\\LeagueClient.exe"
        )
        self._show_placeholder()
        self.addr_box.bind("<FocusIn>", self._clear_placeholder)
        self.addr_box.bind("<FocusOut>", self._restore_placeholder)

        # ── Help link ──────────────────────────────────────────────────────
        help_frame = ctk.CTkFrame(inner, fg_color="#1e2127", corner_radius=8, height=32)
        help_frame.grid(row=2, column=0, sticky="ew", pady=(4, 0))
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

        # ── Launch button ──────────────────────────────────────────────────
        self.launch_btn = ctk.CTkButton(
            main_container,
            text="Start Quest",
            width=460,
            height=52,
            font=ctk.CTkFont(size=17, weight="bold"),
            fg_color="#5865F2",
            hover_color="#4752c4",
            text_color="#ffffff",
            text_color_disabled="#ffffff",
            corner_radius=12,
            command=self.launch
        )
        self.launch_btn.pack(pady=(18, 0))

        # ── Error label ── shown only when there is an error, so it never
        #    reserves empty space between the input and the button.
        self.error_label = ctk.CTkLabel(
            main_container, text="", text_color="#ff5555",
            font=ctk.CTkFont(size=12), wraplength=460
        )

    # ── Placeholder handling for the multi-line textbox ────────────────────
    def _show_placeholder(self):
        self._placeholder_active = True
        self.addr_box.delete("1.0", "end")
        self.addr_box.insert("1.0", self._placeholder)
        self.addr_box.configure(text_color="#4a4d55")

    def _clear_placeholder(self, _event=None):
        if getattr(self, "_placeholder_active", False):
            self._placeholder_active = False
            self.addr_box.delete("1.0", "end")
            self.addr_box.configure(text_color="#ffffff")

    def _restore_placeholder(self, _event=None):
        if not self.addr_box.get("1.0", "end").strip():
            self._show_placeholder()

    def _get_addrs(self):
        if getattr(self, "_placeholder_active", False):
            return []
        raw = self.addr_box.get("1.0", "end")
        return [ln.strip() for ln in raw.splitlines() if ln.strip()]

    def _toggle_logs(self):
        self._logs_enabled = not self._logs_enabled
        logger.enabled = self._logs_enabled
        if self._logs_enabled:
            self.logs_btn.configure(text="📋 Logs: ON", text_color="#43b581")
        else:
            self.logs_btn.configure(text="📋 Logs: OFF", text_color="#4a4d55")

    def launch(self):
        if self._is_running:
            return

        addrs = self._get_addrs()
        if not addrs:
            self._set_error("❌ Enter at least one game path")
            return

        duration_s = DURATION_MINUTES * 60 + 30

        self._set_error("")
        self._is_running = True
        self.launch_btn.configure(state="disabled", text="Initializing...", fg_color="#3a4070")

        t = threading.Thread(
            target=self._launch_thread,
            args=(addrs, duration_s),
            daemon=True,
        )
        t.start()
        self._active_thread = t

    def _prepare_job(self, addr):
        """Resolve a single path, back up any existing exe, and drop in quest_timer.exe."""
        found_addr = resolve_addr(addr)
        log(f"Resolved path: {found_addr}")

        exe_name = os.path.basename(found_addr)
        log(f"Target exe name (what Discord will see as the process): '{exe_name}'")
        log("NOTE: Discord matches this process name against its game database. "
            "If the quest doesn't progress, the exe name may not match Discord's records for this game.")

        dir_addr = os.path.dirname(found_addr)
        created_dirs = mkdir_track(dir_addr)
        backup_addr = found_addr + '.dqc_backup'
        is_installed = len(created_dirs) == 0
        log(f"Game directory exists (pre-installed): {is_installed}")
        log(f"Game directory: {dir_addr}")
        if created_dirs:
            log(f"Had to create directories: {[str(d) for d in created_dirs]}")

        if is_installed and os.path.exists(found_addr):
            log(f"Existing exe found at target path — backing up to: {backup_addr}")
            if os.path.exists(backup_addr):
                log(f"Stale backup already exists at '{backup_addr}' — removing it")
                os.remove(backup_addr)
            os.rename(found_addr, backup_addr)
            log("Backup complete")
        elif is_installed and not os.path.exists(found_addr):
            log(f"WARNING: Directory exists but no exe found at '{found_addr}' — game may use a launcher or different path")

        quest_timer_path = resource_path('quest_timer.exe')
        log(f"quest_timer.exe source path: {quest_timer_path} (exists: {os.path.exists(quest_timer_path)})")
        if not os.path.exists(quest_timer_path):
            raise FileNotFoundError(f"quest_timer.exe not found at {quest_timer_path}")

        qt_size = os.path.getsize(quest_timer_path)
        shutil.copy(quest_timer_path, found_addr)
        copied_size = os.path.getsize(found_addr)
        log(f"Copied quest_timer.exe to: {found_addr} (size: {copied_size} bytes)")
        if copied_size != qt_size:
            log(f"WARNING: File size mismatch after copy! source={qt_size} dest={copied_size} — copy may be corrupt")

        return {
            'found_addr': found_addr,
            'backup_addr': backup_addr,
            'is_installed': is_installed,
            'created_dirs': created_dirs,
        }

    def _cleanup_jobs(self, jobs):
        log("--- CLEANUP ---")
        for job in jobs:
            found_addr = job['found_addr']
            backup_addr = job['backup_addr']
            try:
                if job['is_installed']:
                    if os.path.exists(found_addr):
                        os.remove(found_addr)
                        log(f"Removed quest_timer copy: {found_addr}")
                    if os.path.exists(backup_addr):
                        os.rename(backup_addr, found_addr)
                        log(f"Restored original exe: {found_addr}")
                elif job['created_dirs']:
                    top = str(job['created_dirs'][0])
                    if os.path.exists(top):
                        shutil.rmtree(top)
                        log(f"Removed created dirs from: {top}")
            except Exception as e:
                log_exception(f"Cleanup failed for '{found_addr}': {e}")

    def _launch_thread(self, addrs, duration_s):
        log(f"Launch requested: {len(addrs)} path(s) duration={duration_s}s ({duration_s/60:.1f} mins)")
        for a in addrs:
            log(f"  path: {a}")
        log("--- PRE-FLIGHT CHECKS ---")

        # Check Discord is running
        if _PSUTIL:
            discord_procs = [p for p in psutil.process_iter(['name']) if 'discord' in (p.info['name'] or '').lower()]
            if discord_procs:
                log(f"Discord detected: {[p.info['name'] for p in discord_procs]}")
            else:
                log("WARNING: Discord does not appear to be running — quest will NOT progress without Discord open")
        else:
            log("psutil not available — skipping Discord process check")

        duration_ms = duration_s * 1000
        jobs = []
        try:
            for addr in addrs:
                try:
                    jobs.append(self._prepare_job(addr))
                except ValueError as e:
                    err_msg = f"{addr}: {e}"
                    log_exception(f"Path resolution failed: {err_msg}")
                    self.after(0, lambda m=err_msg: self._finish_error(m))
                    return

            self.after(0, lambda: self._start_progress(duration_ms))
            log("--- LAUNCHING SUBPROCESSES ---")
            log(f"Expected run time: {duration_s}s ({duration_s/60:.1f} mins)")

            procs = []
            proc_start = time.time()
            for job in jobs:
                log(f"Command: '{job['found_addr']}' arg: {duration_ms}ms")
                p = subprocess.Popen(
                    [job['found_addr'], str(duration_ms)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                procs.append((job, p))

            for job, p in procs:
                out, err = p.communicate()
                log(f"Subprocess '{job['found_addr']}' finished — return code: {p.returncode}")
                if out and out.strip():
                    log(f"  stdout: {out.strip()}")
                if err and err.strip():
                    log(f"  stderr: {err.strip()}")
                if p.returncode != 0:
                    log(f"  WARNING: Non-zero return code {p.returncode} — quest_timer.exe may have failed")

            proc_elapsed = time.time() - proc_start
            log("--- ALL SUBPROCESSES FINISHED ---")
            log(f"Actual elapsed time: {proc_elapsed:.1f}s (expected ~{duration_s}s)")
            if proc_elapsed < duration_s * 0.9:
                log(f"WARNING: Processes exited {duration_s - proc_elapsed:.1f}s too early — "
                    "Discord may not have registered enough playtime")

            log("Quest run completed — check Discord to confirm quest progress")
            self.after(0, self._finish_success)

        except Exception as e:
            err_msg = str(e)
            log_exception(f"Launch failed: {err_msg}")
            self.after(0, lambda: self._finish_error(err_msg))
        finally:
            self._cleanup_jobs(jobs)

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
        if text:
            self.error_label.pack(fill="x", padx=30, pady=(10, 0))
        else:
            self.error_label.pack_forget()

    def _on_close(self):
        self.destroy()
