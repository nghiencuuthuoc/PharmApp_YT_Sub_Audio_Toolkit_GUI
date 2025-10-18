# -*- coding: utf-8 -*-
"""
YouTube Toolkit GUI — wrapper (v4)
- Thin Tkinter GUI that calls your existing scripts via subprocess (keeps code short)
- Shortcuts
- "Always on top" toggle
- PharmApp theme (light) + System theme
- Runs jobs concurrently across tabs
- Help tab

Place this file in the same folder as:
  1_get_url_yt_input_pl_v1.py
  1_get_yt_urls_input_channel.py
  download_subs_v4.py
  2_down_mp3_url_yt_v3.py
"""

import os, sys, subprocess, threading, queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

HERE = Path(__file__).resolve().parent
SCRIPTS = {
    "playlist": HERE / "1_get_url_yt_input_pl_v1.py",
    "channel":  HERE / "1_get_yt_urls_input_channel.py",
    "subs":     HERE / "download_subs_v4.py",
    "audio":    HERE / "2_down_mp3_url_yt_v3.py",
}
PY = sys.executable
DEFAULT_GEOMETRY = "1220x820"

PHARMAPP_COLORS = {
    "bg": "#fdf5e6",      # background (Eggshell)
    "panel": "#fff6e9",
    "accent": "#f4a261",  # buttons
    "accent2": "#e76f51", # active/hover
    "heading": "#b5838d",
    "text": "#2a2a2a",
    "log_bg": "#fffaf2",
}

def script_or_prompt(key: str) -> Path:
    p = Path(SCRIPTS[key])
    if p.exists():
        return p
    messagebox.showwarning("Script not found", f"Không thấy file: {p.name}\nChọn file tương ứng.")
    path = filedialog.askopenfilename(title=f"Chọn script cho {key}", filetypes=[("Python", "*.py"), ("All", "*.*")])
    if not path:
        raise FileNotFoundError(f"Missing script for key={key}")
    SCRIPTS[key] = Path(path)
    return SCRIPTS[key]

def start_proc(cmd: list) -> subprocess.Popen:
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)

class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master); self.master = master; self.pack(fill="both", expand=True)
        self._style = ttk.Style()
        try: self._style.theme_use("clam")
        except Exception: pass

        self._apply_system_theme()  # default
        self._topmost = tk.BooleanVar(value=False)

        self.procs = {}          # key -> Popen
        self.logq: "queue.Queue[str]" = queue.Queue()

        self._build_menu()
        self._build_ui()
        self._bind_hotkeys()

        self.after(80, self._drain)

    # ---------- Theming ----------
    def _apply_pharmapp_theme(self):
        c = PHARMAPP_COLORS
        self.master.configure(bg=c["bg"])
        for cls in ("TFrame","TLabelframe","TLabel","TNotebook","TNotebook.Tab","TButton","TCheckbutton","TMenubutton","TEntry","TCombobox"):
            self._style.configure(cls, background=c["bg"], foreground=c["text"])
        self._style.configure("Card.TLabelframe", background=c["panel"])
        self._style.configure("Card.TLabelframe.Label", foreground=c["heading"])
        self._style.map("TButton", background=[("active", c["accent2"])], relief=[("pressed","sunken")])
        # Logs text area
        try:
            self.txt.configure(bg=c["log_bg"], fg=c["text"], insertbackground=c["text"])
        except Exception:
            pass

    def _apply_system_theme(self):
        # restore defaults as much as possible
        self.master.configure(bg="SystemButtonFace" if os.name=="nt" else self.master.cget("bg"))
        self._style.configure("TFrame", background=self.master.cget("bg"))
        # logs reset later by widget default
        try:
            self.txt.configure(bg="white", fg="black", insertbackground="black")
        except Exception:
            pass

    # ---------- UI ----------
    def _build_menu(self):
        menubar = tk.Menu(self.master)
        view = tk.Menu(menubar, tearoff=0)
        view.add_checkbutton(label="Always on top (Alt+T)", onvalue=True, offvalue=False,
                             variable=self._topmost, command=self._toggle_topmost, accelerator="Alt+T")
        theme = tk.Menu(menubar, tearoff=0)
        theme.add_command(label="PharmApp Light", command=self._apply_pharmapp_theme)
        theme.add_command(label="System Default", command=self._apply_system_theme)
        menubar.add_cascade(label="View", menu=view)
        menubar.add_cascade(label="Theme", menu=theme)
        self.master.config(menu=menubar)

    def _build_ui(self):
        self.nb = ttk.Notebook(self); self.nb.pack(fill="both", expand=True, padx=8, pady=8)

        # Tabs
        self.t_pl = ttk.Frame(self.nb); self.t_ch = ttk.Frame(self.nb); self.t_sub = ttk.Frame(self.nb); self.t_aud = ttk.Frame(self.nb); self.t_help = ttk.Frame(self.nb)
        self.nb.add(self.t_pl,  text="🧾 Playlist → url_yt.txt")
        self.nb.add(self.t_ch,  text="🧾 Channel → url_yt.txt")
        self.nb.add(self.t_sub, text="📝 Subtitles")
        self.nb.add(self.t_aud, text="🎵 Audio")
        self.nb.add(self.t_help, text="❓ Help")

        # Playlist
        f = ttk.LabelFrame(self.t_pl, text="Playlist"); f.pack(fill="x", padx=8, pady=8)
        ttk.Label(f, text="Playlist URL:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.pl_url = ttk.Entry(f, width=80); self.pl_url.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        ttk.Label(f, text="Output folder:").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        self.pl_out = ttk.Entry(f, width=80); self.pl_out.grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        ttk.Button(f, text="Browse… (Alt+B)", command=lambda: self._pick_dir(self.pl_out)).grid(row=1, column=2, padx=4)
        f.columnconfigure(1, weight=1)
        ttk.Button(f, text="Run (F5)", command=self.run_playlist).grid(row=2, column=1, sticky="e", pady=6)
        ttk.Button(f, text="Stop (Shift+F5)", command=lambda: self.stop("playlist")).grid(row=2, column=2)

        # Channel
        f = ttk.LabelFrame(self.t_ch, text="Channel"); f.pack(fill="x", padx=8, pady=8)
        ttk.Label(f, text="Channel URL:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.ch_url = ttk.Entry(f, width=80); self.ch_url.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        ttk.Label(f, text="Output folder:").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        self.ch_out = ttk.Entry(f, width=80); self.ch_out.grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        ttk.Button(f, text="Browse… (Alt+B)", command=lambda: self._pick_dir(self.ch_out)).grid(row=1, column=2, padx=4)
        f.columnconfigure(1, weight=1)
        ttk.Button(f, text="Run (F5)", command=self.run_channel).grid(row=2, column=1, sticky="e", pady=6)
        ttk.Button(f, text="Stop (Shift+F5)", command=lambda: self.stop("channel")).grid(row=2, column=2)

        # Subtitles
        f = ttk.LabelFrame(self.t_sub, text="download_subs_v4.py"); f.pack(fill="x", padx=8, pady=8)
        self.sub_mode = tk.StringVar(value="scan")
        ttk.Radiobutton(f, text="Scan (folder/glob/url_yt.txt)", variable=self.sub_mode, value="scan").grid(row=0, column=0, padx=4, pady=4, sticky="w")
        ttk.Radiobutton(f, text="Single URL", variable=self.sub_mode, value="url").grid(row=0, column=1, padx=4, pady=4, sticky="w")
        ttk.Radiobutton(f, text="Single file url_yt.txt", variable=self.sub_mode, value="file").grid(row=0, column=2, padx=4, pady=4, sticky="w")
        ttk.Label(f, text="Path / URL:").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        self.sub_path = ttk.Entry(f, width=80); self.sub_path.grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        ttk.Button(f, text="Browse… (Alt+B)", command=lambda: self._pick_path(self.sub_path)).grid(row=1, column=2, padx=4)
        self.sub_vi = tk.BooleanVar(value=True);  ttk.Checkbutton(f, text="vi", variable=self.sub_vi).grid(row=2, column=0, sticky="w", padx=4)
        self.sub_en = tk.BooleanVar(value=False); ttk.Checkbutton(f, text="en", variable=self.sub_en).grid(row=2, column=0, sticky="e", padx=40)
        self.sub_srt = tk.BooleanVar(value=False); ttk.Checkbutton(f, text="SRT", variable=self.sub_srt).grid(row=2, column=1, sticky="w", padx=4)
        self.sub_force = tk.BooleanVar(value=False); ttk.Checkbutton(f, text="Force overwrite", variable=self.sub_force).grid(row=2, column=1, sticky="e", padx=4)
        self.sub_video = tk.BooleanVar(value=False); ttk.Checkbutton(f, text="Also video (MP4)", variable=self.sub_video).grid(row=2, column=2, sticky="w", padx=4)
        ttk.Button(f, text="Run (F5)", command=self.run_subs).grid(row=3, column=1, sticky="e", pady=6)
        ttk.Button(f, text="Stop (Shift+F5)", command=lambda: self.stop("subs")).grid(row=3, column=2)
        f.columnconfigure(1, weight=1)

        # Audio
        f = ttk.LabelFrame(self.t_aud, text="2_down_mp3_url_yt_v3.py"); f.pack(fill="x", padx=8, pady=8)
        ttk.Label(f, text="Target (URL or text file):").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.aud_target = ttk.Entry(f, width=80); self.aud_target.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        ttk.Button(f, text="Browse… (Alt+B)", command=lambda: self._pick_file(self.aud_target)).grid(row=0, column=2, padx=4)
        ttk.Label(f, text="Output folder:").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        self.aud_out = ttk.Entry(f, width=80); self.aud_out.grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        ttk.Button(f, text="Browse… (Alt+B)", command=lambda: self._pick_dir(self.aud_out)).grid(row=1, column=2, padx=4)
        ttk.Label(f, text="Codec:").grid(row=2, column=0, sticky="e", padx=4); self.aud_codec = ttk.Combobox(f, values=["mp3","m4a","opus","wav","flac"], width=8); self.aud_codec.set("mp3"); self.aud_codec.grid(row=2, column=1, sticky="w")
        ttk.Label(f, text="Quality:").grid(row=2, column=1, sticky="e", padx=90); self.aud_q = ttk.Combobox(f, values=["128","160","192","320"], width=6); self.aud_q.set("192"); self.aud_q.grid(row=2, column=1, sticky="e", padx=4)
        self.aud_over = tk.BooleanVar(value=False); ttk.Checkbutton(f, text="Overwrite", variable=self.aud_over).grid(row=3, column=0, sticky="w", padx=4)
        self.aud_allow = tk.BooleanVar(value=True); ttk.Checkbutton(f, text="Allow playlist", variable=self.aud_allow).grid(row=3, column=1, sticky="w", padx=4)
        self.aud_quiet = tk.BooleanVar(value=False); ttk.Checkbutton(f, text="Quiet", variable=self.aud_quiet).grid(row=3, column=2, sticky="w", padx=4)
        ttk.Button(f, text="List formats (Ctrl+L)", command=self.list_formats).grid(row=4, column=1, sticky="w", pady=6)
        ttk.Button(f, text="Run (F5)", command=self.run_audio).grid(row=4, column=1, sticky="e")
        ttk.Button(f, text="Stop (Shift+F5)", command=lambda: self.stop("audio")).grid(row=4, column=2)
        f.columnconfigure(1, weight=1)

        # Help
        hf = ttk.Frame(self.t_help); hf.pack(fill="both", expand=True, padx=12, pady=12)
        txt = tk.Text(hf, wrap="word", height=20)
        txt.pack(fill="both", expand=True)
        txt.insert("end",
            "🧭 Shortcuts:\n"
            "  • Ctrl+1 / Ctrl+2 / Ctrl+3 / Ctrl+4: Switch to Playlist / Channel / Subtitles / Audio\n"
            "  • F5: Run on current tab\n"
            "  • Shift+F5: Stop job on current tab\n"
            "  • Ctrl+L: List formats (Audio tab)\n"
            "  • Alt+B: Open Browse… on current field\n"
            "  • Alt+T: Toggle Always on top\n\n"
            "📝 Notes:\n"
            "  • This GUI only wraps your existing scripts (keeps code short).\n"
            "  • Jobs run concurrently across tabs. Each tab has its own Run/Stop.\n"
            "  • Place this GUI with the scripts for auto-detection; otherwise it will ask once.\n"
        )
        txt.configure(state="disabled")

        # Logs
        lf = ttk.LabelFrame(self, text="Logs", style="Card.TLabelframe"); lf.pack(fill="both", expand=True, padx=8, pady=(0,8))
        self.txt = ScrolledText(lf, height=12, wrap="word"); self.txt.pack(fill="both", expand=True)

        # Apply default theme after widgets exist
        self._apply_pharmapp_theme()

    # ---------- Hotkeys ----------
    def _bind_hotkeys(self):
        # Tabs
        self.master.bind("<Control-Key-1>", lambda e: self.nb.select(self.t_pl))
        self.master.bind("<Control-Key-2>", lambda e: self.nb.select(self.t_ch))
        self.master.bind("<Control-Key-3>", lambda e: self.nb.select(self.t_sub))
        self.master.bind("<Control-Key-4>", lambda e: self.nb.select(self.t_aud))
        # Run/Stop
        self.master.bind("<F5>", self._run_current)
        self.master.bind("<Shift-F5>", self._stop_current)
        # Audio specific
        self.master.bind("<Control-l>", lambda e: self.list_formats())
        self.master.bind("<Alt-t>", lambda e: (self._topmost.set(not self._topmost.get()), self._toggle_topmost()))

    def _toggle_topmost(self):
        self.master.attributes("-topmost", bool(self._topmost.get()))
        if self._topmost.get():
            self.master.lift()

    def _run_current(self, event=None):
        curr = self.nb.select()
        if curr == str(self.t_pl): self.run_playlist()
        elif curr == str(self.t_ch): self.run_channel()
        elif curr == str(self.t_sub): self.run_subs()
        elif curr == str(self.t_aud): self.run_audio()

    def _stop_current(self, event=None):
        curr = self.nb.select()
        if curr == str(self.t_pl): self.stop("playlist")
        elif curr == str(self.t_ch): self.stop("channel")
        elif curr == str(self.t_sub): self.stop("subs")
        elif curr == str(self.t_aud): self.stop("audio")

    # ---------- Pickers ----------
    def _pick_dir(self, entry):
        d = filedialog.askdirectory()
        if d:
            entry.delete(0, "end"); entry.insert(0, d)

    def _pick_file(self, entry):
        f = filedialog.askopenfilename(filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if f:
            entry.delete(0, "end"); entry.insert(0, f)

    def _pick_path(self, entry):
        f = filedialog.askopenfilename(filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if f:
            entry.delete(0, "end"); entry.insert(0, f)
        else:
            d = filedialog.askdirectory()
            if d:
                entry.delete(0, "end"); entry.insert(0, d)

    # ---------- Runners ----------
    def _run_async(self, key: str, cmd: list):
        # allow 1 process per key; keys differ per tab → concurrent across tabs.
        try:
            # Ensure script path (auto-prompt if missing)
            _ = script_or_prompt(key if key in SCRIPTS else "subs")
        except FileNotFoundError:
            return
        self._append(f"→ Running: {' '.join(self._quote(a) for a in cmd)}\n")
        def worker():
            try:
                p = start_proc(cmd); self.procs[key] = p
                for line in p.stdout:
                    self.logq.put(line)
                p.wait()
            except Exception as e:
                self._append(f"[{key}] ERROR: {e}\n")
            finally:
                code = p.returncode if 'p' in locals() else '?'
                self._append(f"[{key}] Finished (code={code})\n")
                self.procs.pop(key, None)
        threading.Thread(target=worker, daemon=True).start()

    def stop(self, key: str):
        p = self.procs.get(key)
        if not p:
            self._append(f"[{key}] No running process.\n"); return
        try:
            p.terminate()
            self._append(f"[{key}] Terminate sent.\n")
        except Exception as e:
            self._append(f"[{key}] Terminate failed: {e}\n")

    # ----- command builders -----
    def run_playlist(self):
        url = getattr(self, "pl_url").get().strip()
        out = getattr(self, "pl_out").get().strip()
        if not url or not out: return messagebox.showwarning("Missing", "Nhập Playlist URL và Output folder")
        cmd = [PY, str(SCRIPTS["playlist"]), "-p", url, "-i", out]
        self._run_async("playlist", cmd)

    def run_channel(self):
        url = getattr(self, "ch_url").get().strip()
        out = getattr(self, "ch_out").get().strip()
        if not url or not out: return messagebox.showwarning("Missing", "Nhập Channel URL và Output folder")
        cmd = [PY, str(SCRIPTS["channel"]), "-u", url, "-i", out]
        self._run_async("channel", cmd)

    def run_subs(self):
        path = getattr(self, "sub_path").get().strip()
        if not path: return messagebox.showwarning("Missing", "Nhập Path/URL")
        cmd = [PY, str(SCRIPTS["subs"])]
        mode = self.sub_mode.get()
        if mode == "scan":   cmd += ["--scan", path]
        elif mode == "url":  cmd += [path]
        else:                cmd += ["--file", path]
        if self.sub_vi.get():   cmd += ["-vi"]
        if self.sub_en.get():   cmd += ["-en"]
        if self.sub_srt.get():  cmd += ["--srt"]
        if self.sub_force.get():cmd += ["--force-overwrite"]
        if self.sub_video.get():cmd += ["--also-video"]
        cmd += ["--no-warn"]
        self._run_async("subs", cmd)

    def list_formats(self):
        tgt = getattr(self, "aud_target").get().strip()
        out = getattr(self, "aud_out").get().strip() or "."
        if not tgt: return messagebox.showwarning("Missing", "Nhập URL hoặc file .txt")
        cmd = [PY, str(SCRIPTS["audio"]), tgt, "-o", out, "--codec", self.aud_codec.get(), "--quality", self.aud_q.get(), "--list-formats"]
        self._run_async("audio", cmd)

    def run_audio(self):
        tgt = getattr(self, "aud_target").get().strip()
        out = getattr(self, "aud_out").get().strip() or "."
        if not tgt: return messagebox.showwarning("Missing", "Nhập URL hoặc file .txt")
        cmd = [PY, str(SCRIPTS["audio"]), tgt, "-o", out, "--codec", self.aud_codec.get(), "--quality", self.aud_q.get()]
        if self.aud_over.get():  cmd += ["--overwrite"]
        if self.aud_allow.get(): cmd += ["--allow-playlist"]
        if self.aud_quiet.get(): cmd += ["--quiet"]
        self._run_async("audio", cmd)

    # ---------- Logging ----------
    def _append(self, s: str):
        self.txt.insert("end", s); self.txt.see("end")

    def _drain(self):
        try:
            while True:
                s = self.logq.get_nowait()
                self._append(s)
        except queue.Empty:
            pass
        self.after(80, self._drain)

    @staticmethod
    def _quote(s: str) -> str:
        return f'"{s}"' if (" " in s or "\\" in s) else s

def main():
    root = tk.Tk()
    root.title("YouTube Toolkit GUI — wrapper v4")
    root.geometry(DEFAULT_GEOMETRY)
    app = App(root)
    root.lift()
    root.attributes("-topmost", False)
    root.mainloop()

if __name__ == "__main__":
    main()
