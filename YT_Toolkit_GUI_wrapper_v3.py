# -*- coding: utf-8 -*-
"""
YouTube Toolkit GUI — thin wrapper (v3)
Only a small Tkinter GUI that calls your existing scripts:
- 1_get_url_yt_input_pl_v1.py
- 1_get_yt_urls_input_channel.py
- download_subs_v4.py
- 2_down_mp3_url_yt_v3.py

Keep this file in the same folder as those scripts for zero-config.
Requires: Python 3.9+, yt-dlp, ffmpeg
"""

import os, sys, threading, subprocess, queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

# ---------------------- CONFIG ----------------------
HERE = Path(__file__).resolve().parent
SCRIPTS = {
    "playlist": HERE / "1_get_url_yt_input_pl_v1.py",
    "channel":  HERE / "1_get_yt_urls_input_channel.py",
    "subs":     HERE / "download_subs_v4.py",
    "audio":    HERE / "2_down_mp3_url_yt_v3.py",
}
PY = sys.executable  # use current Python
DEFAULT_GEOMETRY = "1200x800"

# ---------------------- Utils ----------------------
def find_or_browse(key: str) -> Path:
    p = Path(SCRIPTS[key])
    if p.exists():
        return p
    messagebox.showwarning("Script not found", f"Không thấy file: {p.name}\nChọn file tương ứng.")
    path = filedialog.askopenfilename(title=f"Chọn script cho {key}", filetypes=[("Python", "*.py"), ("All", "*.*")])
    if not path:
        raise FileNotFoundError(f"Missing script for key={key}")
    SCRIPTS[key] = Path(path)
    return SCRIPTS[key]

def start_proc(cmd, logq: "queue.Queue[str]") -> subprocess.Popen:
    # Start process and pipe stdout+stderr to log queue
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )

# ---------------------- GUI ----------------------
class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master); self.pack(fill="both", expand=True)
        self.procs = {}  # key -> Popen
        self.logq: "queue.Queue[str]" = queue.Queue()
        self._build_ui()
        self.after(80, self._drain)

    def _build_ui(self):
        nb = ttk.Notebook(self); nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.t_pl = ttk.Frame(nb); self.t_ch = ttk.Frame(nb); self.t_sub = ttk.Frame(nb); self.t_aud = ttk.Frame(nb)
        nb.add(self.t_pl, text="🧾 Get URLs · Playlist")
        nb.add(self.t_ch, text="🧾 Get URLs · Channel")
        nb.add(self.t_sub, text="📝 Subtitles")
        nb.add(self.t_aud, text="🎵 Audio")

        # Playlist
        frm = ttk.LabelFrame(self.t_pl, text="Playlist → url_yt.txt"); frm.pack(fill="x", padx=8, pady=8)
        ttk.Label(frm, text="Playlist URL:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.pl_url = ttk.Entry(frm, width=80); self.pl_url.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        ttk.Label(frm, text="Output folder:").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        self.pl_out = ttk.Entry(frm, width=80); self.pl_out.grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        ttk.Button(frm, text="Browse…", command=lambda: self._pick_dir(self.pl_out)).grid(row=1, column=2, padx=4)
        frm.columnconfigure(1, weight=1)
        ttk.Button(frm, text="Run", command=self.run_playlist).grid(row=2, column=1, sticky="e", pady=6)
        ttk.Button(frm, text="Stop", command=lambda: self.stop("playlist")).grid(row=2, column=2)

        # Channel
        frm = ttk.LabelFrame(self.t_ch, text="Channel → url_yt.txt"); frm.pack(fill="x", padx=8, pady=8)
        ttk.Label(frm, text="Channel URL:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.ch_url = ttk.Entry(frm, width=80); self.ch_url.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        ttk.Label(frm, text="Output folder:").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        self.ch_out = ttk.Entry(frm, width=80); self.ch_out.grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        ttk.Button(frm, text="Browse…", command=lambda: self._pick_dir(self.ch_out)).grid(row=1, column=2, padx=4)
        frm.columnconfigure(1, weight=1)
        ttk.Button(frm, text="Run", command=self.run_channel).grid(row=2, column=1, sticky="e", pady=6)
        ttk.Button(frm, text="Stop", command=lambda: self.stop("channel")).grid(row=2, column=2)

        # Subtitles
        frm = ttk.LabelFrame(self.t_sub, text="Download subtitles (download_subs_v4.py)"); frm.pack(fill="x", padx=8, pady=8)
        self.sub_mode = tk.StringVar(value="scan")
        ttk.Radiobutton(frm, text="Scan (folder/glob/url_yt.txt)", variable=self.sub_mode, value="scan").grid(row=0, column=0, padx=4, pady=4, sticky="w")
        ttk.Radiobutton(frm, text="Single URL", variable=self.sub_mode, value="url").grid(row=0, column=1, padx=4, pady=4, sticky="w")
        ttk.Radiobutton(frm, text="Single file url_yt.txt", variable=self.sub_mode, value="file").grid(row=0, column=2, padx=4, pady=4, sticky="w")
        ttk.Label(frm, text="Path / URL:").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        self.sub_path = ttk.Entry(frm, width=80); self.sub_path.grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        ttk.Button(frm, text="Browse…", command=lambda: self._pick_path(self.sub_path)).grid(row=1, column=2, padx=4)

        self.sub_vi = tk.BooleanVar(value=True)
        self.sub_en = tk.BooleanVar(value=False)
        self.sub_srt = tk.BooleanVar(value=False)
        self.sub_force = tk.BooleanVar(value=False)
        self.sub_video = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm, text="vi", variable=self.sub_vi).grid(row=2, column=0, sticky="w", padx=4)
        ttk.Checkbutton(frm, text="en", variable=self.sub_en).grid(row=2, column=0, sticky="e", padx=4)
        ttk.Checkbutton(frm, text="SRT", variable=self.sub_srt).grid(row=2, column=1, sticky="w", padx=4)
        ttk.Checkbutton(frm, text="Force overwrite", variable=self.sub_force).grid(row=2, column=1, sticky="e", padx=4)
        ttk.Checkbutton(frm, text="Also video (MP4)", variable=self.sub_video).grid(row=2, column=2, sticky="w", padx=4)
        ttk.Button(frm, text="Run", command=self.run_subs).grid(row=3, column=1, sticky="e", pady=6)
        ttk.Button(frm, text="Stop", command=lambda: self.stop("subs")).grid(row=3, column=2)
        frm.columnconfigure(1, weight=1)

        # Audio
        frm = ttk.LabelFrame(self.t_aud, text="Download audio (2_down_mp3_url_yt_v3.py)"); frm.pack(fill="x", padx=8, pady=8)
        ttk.Label(frm, text="Target (URL or text file):").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.aud_target = ttk.Entry(frm, width=80); self.aud_target.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        ttk.Button(frm, text="Browse…", command=lambda: self._pick_file(self.aud_target)).grid(row=0, column=2, padx=4)
        ttk.Label(frm, text="Output folder:").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        self.aud_out = ttk.Entry(frm, width=80); self.aud_out.grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        ttk.Button(frm, text="Browse…", command=lambda: self._pick_dir(self.aud_out)).grid(row=1, column=2, padx=4)
        ttk.Label(frm, text="Codec:").grid(row=2, column=0, sticky="e", padx=4); self.aud_codec = ttk.Combobox(frm, values=["mp3","m4a","opus","wav","flac"], width=8); self.aud_codec.set("mp3"); self.aud_codec.grid(row=2, column=1, sticky="w")
        ttk.Label(frm, text="Quality:").grid(row=2, column=1, sticky="e", padx=90); self.aud_q = ttk.Combobox(frm, values=["128","160","192","320"], width=6); self.aud_q.set("192"); self.aud_q.grid(row=2, column=1, sticky="e", padx=4)
        self.aud_over = tk.BooleanVar(value=False); ttk.Checkbutton(frm, text="Overwrite", variable=self.aud_over).grid(row=3, column=0, sticky="w", padx=4)
        self.aud_allow = tk.BooleanVar(value=True); ttk.Checkbutton(frm, text="Allow playlist", variable=self.aud_allow).grid(row=3, column=1, sticky="w", padx=4)
        self.aud_quiet = tk.BooleanVar(value=False); ttk.Checkbutton(frm, text="Quiet", variable=self.aud_quiet).grid(row=3, column=2, sticky="w", padx=4)
        ttk.Button(frm, text="List formats (first URL)", command=self.list_formats).grid(row=4, column=1, sticky="w", pady=6)
        ttk.Button(frm, text="Run", command=self.run_audio).grid(row=4, column=1, sticky="e")
        ttk.Button(frm, text="Stop", command=lambda: self.stop("audio")).grid(row=4, column=2)
        frm.columnconfigure(1, weight=1)

        # Logs
        lf = ttk.LabelFrame(self, text="Logs"); lf.pack(fill="both", expand=True, padx=8, pady=(0,8))
        self.txt = ScrolledText(lf, height=12, wrap="word"); self.txt.pack(fill="both", expand=True)

    # ---- pickers ----
    def _pick_dir(self, entry):
        d = filedialog.askdirectory()
        if d:
            entry.delete(0, "end"); entry.insert(0, d)

    def _pick_file(self, entry):
        f = filedialog.askopenfilename(filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if f:
            entry.delete(0, "end"); entry.insert(0, f)

    def _pick_path(self, entry):
        # file or folder
        f = filedialog.askopenfilename(filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if f:
            entry.delete(0, "end"); entry.insert(0, f)
        else:
            d = filedialog.askdirectory()
            if d:
                entry.delete(0, "end"); entry.insert(0, d)

    # ---- runners ----
    def _run_async(self, key: str, cmd: list):
        try:
            script = find_or_browse(key if key in ("playlist","channel","subs","audio") else "subs")
        except FileNotFoundError:
            return
        # Replace script path in cmd if placeholder was used
        cmd = [PY if a == "{PY}" else a for a in cmd]
        cmd = [str(script) if a == "{SCRIPT}" else a for a in cmd]
        self._append(f"→ Running: {' '.join(map(self._q, cmd))}\n")
        def worker():
            try:
                p = start_proc(cmd, self.logq); self.procs[key] = p
                for line in p.stdout:
                    self.logq.put(line)
                p.wait()
            except Exception as e:
                self._append(f"[{key}] ERROR: {e}\n")
            finally:
                self._append(f"[{key}] Finished (code={p.returncode if 'p' in locals() else '?'})\n")
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

    # ---- specific commands ----
    def run_playlist(self):
        url = self.pl_url.get().strip(); out = self.pl_out.get().strip()
        if not url or not out: return messagebox.showwarning("Missing", "Nhập Playlist URL và Output folder")
        cmd = [PY, str(SCRIPTS["playlist"]), "-p", url, "-i", out]
        self._run_async("playlist", cmd)

    def run_channel(self):
        url = self.ch_url.get().strip(); out = self.ch_out.get().strip()
        if not url or not out: return messagebox.showwarning("Missing", "Nhập Channel URL và Output folder")
        cmd = [PY, str(SCRIPTS["channel"]), "-u", url, "-i", out]
        self._run_async("channel", cmd)

    def run_subs(self):
        path = self.sub_path.get().strip()
        if not path: return messagebox.showwarning("Missing", "Nhập Path/URL")
        cmd = [PY, str(SCRIPTS["subs"])]
        # mode
        mode = self.sub_mode.get()
        if mode == "scan":
            cmd += ["--scan", path]
        elif mode == "url":
            cmd += [path]
        else:
            cmd += ["--file", path]
        # options
        if self.sub_vi.get(): cmd += ["-vi"]
        if self.sub_en.get(): cmd += ["-en"]
        if self.sub_srt.get(): cmd += ["--srt"]
        if self.sub_force.get(): cmd += ["--force-overwrite"]
        if self.sub_video.get(): cmd += ["--also-video"]
        cmd += ["--no-warn"]
        self._run_async("subs", cmd)

    def list_formats(self):
        tgt = self.aud_target.get().strip(); out = self.aud_out.get().strip() or "."
        if not tgt: return messagebox.showwarning("Missing", "Nhập URL hoặc file .txt")
        cmd = [PY, str(SCRIPTS["audio"]), tgt, "-o", out, "--codec", self.aud_codec.get(), "--quality", self.aud_q.get(), "--list-formats"]
        self._run_async("audio", cmd)

    def run_audio(self):
        tgt = self.aud_target.get().strip(); out = self.aud_out.get().strip() or "."
        if not tgt: return messagebox.showwarning("Missing", "Nhập URL hoặc file .txt")
        cmd = [PY, str(SCRIPTS["audio"]), tgt, "-o", out,
               "--codec", self.aud_codec.get(), "--quality", self.aud_q.get()]
        if self.aud_over.get(): cmd += ["--overwrite"]
        if self.aud_allow.get(): cmd += ["--allow-playlist"]
        if self.aud_quiet.get(): cmd += ["--quiet"]
        self._run_async("audio", cmd)

    # ---- logs ----
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
    def _q(s: str) -> str:
        return f'"{s}"' if " " in s or "\\" in s else s

def main():
    root = tk.Tk(); root.title("YouTube Toolkit GUI — wrapper v3"); root.geometry(DEFAULT_GEOMETRY)
    App(root); root.mainloop()

if __name__ == "__main__":
    main()
