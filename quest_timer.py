import customtkinter as ctk
import sys, time


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


class QuestTimer(ctk.CTk):
    def __init__(self, duration_ms):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.duration_ms = duration_ms
        self.start_time = time.time()

        self.title("Quest Running")
        self.geometry("340x150")
        self.resizable(False, False)

        self._build_ui()
        self._tick()

    def _build_ui(self):
        self.pct_label = ctk.CTkLabel(
            self, text="0%", font=ctk.CTkFont(size=22, weight="bold"))
        self.pct_label.pack(pady=(20, 2))

        self.time_label = ctk.CTkLabel(
            self, text="", text_color="gray70", font=ctk.CTkFont(size=12))
        self.time_label.pack(pady=(0, 10))

        self.bar = ctk.CTkProgressBar(self, width=280)
        self.bar.set(0)
        self.bar.pack(pady=(0, 16))

    def _tick(self):
        elapsed_ms = (time.time() - self.start_time) * 1000
        pct = min(elapsed_ms / self.duration_ms, 1.0)
        remaining_s = max(self.duration_ms - elapsed_ms, 0) / 1000

        self.bar.set(pct)
        self.pct_label.configure(text=f"{pct * 100:.1f}%")
        self.time_label.configure(text=f"{fmt_time(remaining_s)} remaining")

        if elapsed_ms >= self.duration_ms:
            self.destroy()
            return

        self.after(500, self._tick)


if __name__ == '__main__':
    duration_ms = int(sys.argv[1]) if len(sys.argv) > 1 else 60_000
    app = QuestTimer(duration_ms)
    app.mainloop()
