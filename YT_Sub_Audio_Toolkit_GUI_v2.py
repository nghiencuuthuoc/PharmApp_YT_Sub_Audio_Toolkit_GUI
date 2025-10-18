# -*- coding: utf-8 -*-
"""
YouTube Sub/Audio Toolkit — Tkinter GUI (v2, per-tab concurrency)

What's new vs v1:
  ✓ Run tasks from different tabs at the same time (e.g., Subtitles + Audio).
  ✓ Separate stop buttons for Subtitles and Audio only stop their own job.
  ✓ Safer per-job stop flags; clearer log prefixes.

Notes:
- Still limits to ONE job PER TAB to avoid overloading network/disk.
- If you insist on 2+ parallel jobs in the same tab, convert _start_worker(key=...)
  logic to accept multiple keys per tab or add a queue/pool.
"""

import os
import sys
import re
import unicodedata
import threading
import queue
from pathlib import Path
from typing import List, Optional, Tuple, Dict

try:
    import yt_dlp
except Exception:
    yt_dlp = None

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

APP_TITLE = "YouTube Sub/Audio Toolkit — GUI v2"
DEFAULT_GEOMETRY = "1596x1008"
URL_TXT = "url_yt.txt"
MEDIA_EXTS = {".mp3", ".m4a", ".mp4", ".webm", ".opus", ".flac", ".wav"}

# ---------------- Utils (same as v1) ----------------

def ensure_yt_dlp():
    if yt_dlp is None:
        messagebox.showerror(
            "Missing dependency",
            "yt-dlp is not installed.\n\nInstall with:\n  python -m pip install -U yt-dlp"
        )
        return False
    return True

def ensure_folder(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)

def read_lines_maybe_file(target: str) -> List[str]:
    p = Path(target)
    if p.exists() and p.is_file():
        with p.open("r", encoding="utf-8", errors="ignore") as f:
            return [ln.strip() for ln in f if ln.strip()]
    return [target.strip()]

def remove_diacritics(s: str) -> str:
    nkfd = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in nkfd if unicodedata.category(ch) != "Mn")

def make_slug(title: str) -> str:
    t = unicodedata.normalize("NFKC", title or "")
    t = remove_diacritics(t).lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t or "unknown"

def make_friendly_stem(title: str) -> str:
    s = unicodedata.normalize("NFKC", title or "").strip().strip(".")
    s = re.sub(r'[<>:"/\\|?*]+', " ", s)
    s = re.sub(r"\s+", " ", s)
    return s or "unknown"

def find_existing_by_slug(out_dir: str, slug: str) -> Optional[str]:
    try:
        for fname in os.listdir(out_dir or "."):
            base, ext = os.path.splitext(fname)
            if ext.lower() not in MEDIA_EXTS:
                continue
            if make_slug(base) == slug:
                return fname
    except FileNotFoundError:
        pass
    return None

def probe_title(url: str) -> Optional[str]:
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "simulate": True, "skip_download": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("title") or "unknown"
    except Exception:
        return None

def fetch_playlist_urls(playlist_url: str) -> List[str]:
    ydl_opts = {
        "quiet": True,
        "extract_flat": True,
        "skip_download": True,
        "dump_single_json": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(playlist_url, download=False)
        entries = info.get("entries", []) or []
        urls = []
        for e in entries:
            if e and e.get("id"):
                urls.append(f"https://www.youtube.com/watch?v={e['id']}")
        return urls

def fetch_channel_urls(channel_url: str) -> List[str]:
    ydl_opts = {
        "quiet": True,
        "extract_flat": True,
        "skip_download": True,
    }
    urls = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
        if "entries" in info:
            for entry in info["entries"]:
                if entry and entry.get("id"):
                    video_url = f"https://www.youtube.com/watch?v={entry['id']}"
                    urls.append(video_url)
    return urls

def write_url_file(out_dir: str, urls: List[str], prepend_to_existing: bool = False) -> Tuple[str, Optional[str], int, int]:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    output_file = str(Path(out_dir) / URL_TXT)

    existing_lines = []
    backup_path = None
    if Path(output_file).exists():
        with open(output_file, "r", encoding="utf-8", errors="ignore") as f:
            existing_lines = [ln.strip() for ln in f if ln.strip()]
        if prepend_to_existing:
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            root, ext = os.path.splitext(output_file)
            backup_path = f"{root}_{ts}.bak{ext or '.txt'}"
            import shutil
            shutil.copyfile(output_file, backup_path)

    existing_set = set(existing_lines)
    new_urls = [u for u in urls if u and u not in existing_set]

    with open(output_file, "w", encoding="utf-8") as f:
        if prepend_to_existing:
            for u in new_urls:
                f.write(u + "\n")
            for ln in existing_lines:
                f.write(ln + "\n")
        else:
            for u in urls:
                f.write(u + "\n")

    return output_file, backup_path, len(urls), len(new_urls)

def find_url_files(spec: str) -> List[Path]:
    import glob as _glob
    matches = []
    has_wildcard = any(ch in spec for ch in "*?[")
    p = Path(spec)
    if has_wildcard:
        for m in _glob.glob(spec, recursive=True):
            mp = Path(m)
            if mp.is_file():
                matches.append(mp)
        return sorted(set(matches))

    if p.is_dir():
        return sorted(p.rglob(URL_TXT))
    if p.is_file():
        return [p]
    base = p.parent if p.parent.exists() else Path(".")
    return sorted(base.rglob(URL_TXT))

def build_subs_opts(outdir: Path, langs: List[str], force_overwrite: bool, restrict: bool,
                    as_srt: bool, also_video: bool, impersonate: Optional[str],
                    max_filesize: Optional[str], quiet_warns: bool, tag: str) -> dict:
    ydl_opts = {
        "ignoreerrors": True,
        "continuedl": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "skip_download": not also_video,
        "subtitleslangs": langs,
        "outtmpl": str(outdir / "%(title).200B [%(id)s] - %(upload_date>%Y-%m-%d)s.%(ext)s"),
        "quiet": False,
        "noprogress": False,
        "subtitlesformat": "srt" if as_srt else "vtt",
    }
    if not force_overwrite: ydl_opts["nooverwrites"] = True
    if restrict: ydl_opts["restrictfilenames"] = True
    if impersonate: ydl_opts["impersonate"] = impersonate
    if also_video:
        ydl_opts["format"] = "bv*+ba/best"
        ydl_opts["merge_output_format"] = "mp4"
        ydl_opts["paths"] = {"home": str(outdir)}
        if max_filesize: ydl_opts["max_filesize"] = max_filesize
    if quiet_warns:
        class _QuietWarnLogger:
            def debug(self, msg): pass
            def info(self, msg): pass
            def warning(self, msg): pass
            def error(self, msg):
                try: sys.stderr.write(f"[{tag}] " + str(msg) + "\n")
                except Exception: pass
        import warnings
        warnings.filterwarnings("ignore")
        ydl_opts["no_warnings"] = True
        ydl_opts["logger"] = _QuietWarnLogger()

    def _hook(d: dict):
        status = d.get("status")
        if status == "finished":
            info = d.get("info_dict", {})
            fn = d.get("filename") or info.get("filepath") or info.get("requested_downloads", [{}])[0].get("filepath")
            if fn:
                print(f"[{tag}] [OK] Saved: {fn}")
        elif status == "error":
            print(f"[{tag}] [ERR] Download error")
    ydl_opts["progress_hooks"] = [_hook]
    return ydl_opts

def build_audio_base_opts(out_dir: str, codec: str, quality: str, allow_playlist: bool,
                          overwrite: bool, quiet: bool, ffmpeg_path: Optional[str],
                          keepvideo: bool, force_inet4: bool = False, cookies_from_browser: Optional[str] = None,
                          proxy: Optional[str] = None, throttled_rate: Optional[str] = None, username: Optional[str] = None,
                          password: Optional[str] = None, twofactor: Optional[str] = None) -> dict:
    postprocessors = [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": codec,
        "preferredquality": quality,
    }]
    opts = {
        "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
        "noplaylist": not allow_playlist,
        "quiet": quiet,
        "no_warnings": False,
        "postprocessors": postprocessors,
        "prefer_ffmpeg": True,
        "keepvideo": keepvideo,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 5,
        "overwrites": overwrite,
        "ignoreerrors": True,
        "extract_flat": False,
        "extractor_args": {"youtube": {"player_client": ["ios", "android", "web"]}},
    }
    if ffmpeg_path: opts["ffmpeg_location"] = ffmpeg_path
    if force_inet4: opts["force_inet4"] = True
    if cookies_from_browser: opts["cookiesfrombrowser"] = (cookies_from_browser,)
    if proxy: opts["proxy"] = proxy
    if throttled_rate: opts["throttledratelimit"] = throttled_rate
    if username: opts["username"] = username
    if password: opts["password"] = password
    if twofactor: opts["twofactor"] = twofactor
    return opts

def list_formats_for_url(url: str, base_opts: dict, tag: str) -> None:
    local = dict(base_opts)
    local["listformats"] = True
    local.pop("postprocessors", None)
    with yt_dlp.YoutubeDL(local) as ydl:
        print(f"[{tag}] Listing formats for: {url}")
        ydl.download([url])

def download_audio_one(url: str, base_opts: dict, format_candidates: List[str],
                       simulate: bool, overwrite: bool, tag: str) -> Tuple[bool, Optional[str]]:
    out_dir = os.path.dirname(base_opts["outtmpl"]) or "."
    raw_title = probe_title(url) or "unknown"
    slug = make_slug(raw_title)
    friendly_stem = make_friendly_stem(raw_title)

    existing = find_existing_by_slug(out_dir, slug)
    if existing and not overwrite:
        print(f"[{tag}] ⏭️  SKIP  | slug='{slug}'  | existing='{existing}'")
        return True, None

    opts_out = dict(base_opts)
    opts_out["outtmpl"] = os.path.join(out_dir, f"{friendly_stem}.%(ext)s")

    last_err = None
    for idx, fmt in enumerate(format_candidates, start=1):
        opts = dict(opts_out)
        opts["format"] = fmt
        if simulate:
            opts["simulate"] = True
        print(f"[{tag}] → Trying format [{idx}/{len(format_candidates)}]: {fmt}")
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            print(f"[{tag}] ✅ DONE | slug='{slug}' | saved='{friendly_stem}' (format={fmt})")
            return True, None
        except yt_dlp.utils.DownloadError as e:
            last_err = str(e)
            print(f"[{tag}] ⚠️  Failed with format '{fmt}': {last_err}")
        except Exception as e:
            last_err = repr(e)
            print(f"[{tag}] ⚠️  Unexpected error with format '{fmt}': {last_err}")

    return False, last_err

# ---------------- Tkinter App ----------------

class LogRedirector:
    def __init__(self, q: "queue.Queue[str]"):
        self.q = q
    def write(self, s: str):
        if s: self.q.put(s)
    def flush(self): pass

class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.master = master
        self.pack(fill="both", expand=True)

        self._make_styles()
        self._build_ui()

        # logging
        self.log_q: "queue.Queue[str]" = queue.Queue()
        self._install_logging_redirect()

        # per-tab workers & stop flags
        self._workers: Dict[str, threading.Thread] = {}
        self._stops: Dict[str, threading.Event] = {}

        self.after(100, self._drain_log_queue)

    # ----- UI -----
    def _make_styles(self):
        style = ttk.Style()
        try: style.theme_use("clam")
        except Exception: pass
        style.configure("TButton", padding=6)
        style.configure("TLabel", padding=4)
        style.configure("TEntry", padding=3)
        style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"))
        style.configure("Big.TButton", padding=10, font=("Segoe UI", 10, "bold"))
        style.configure("Card.TLabelframe", padding=10)
        style.configure("Card.TLabelframe.Label", font=("Segoe UI", 10, "bold"))

    def _build_ui(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_urls = ttk.Frame(nb)
        self.tab_subs = ttk.Frame(nb)
        self.tab_audio = ttk.Frame(nb)
        nb.add(self.tab_urls, text="🧾 Get URLs")
        nb.add(self.tab_subs, text="📝 Subtitles")
        nb.add(self.tab_audio, text="🎵 Audio")

        self._build_tab_urls(self.tab_urls)
        self._build_tab_subs(self.tab_subs)
        self._build_tab_audio(self.tab_audio)

        log_frame = ttk.LabelFrame(self, text="Logs", style="Card.TLabelframe")
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0,10))
        self.txt_log = ScrolledText(log_frame, height=12, wrap="word")
        self.txt_log.pack(fill="both", expand=True)

    def _build_tab_urls(self, tab):
        mode_frame = ttk.Frame(tab); mode_frame.pack(fill="x", padx=10, pady=(10, 5))
        ttk.Label(mode_frame, text="Mode:", style="Header.TLabel").pack(side="left")
        self.url_mode = tk.StringVar(value="playlist")
        ttk.Radiobutton(mode_frame, text="Playlist", variable=self.url_mode, value="playlist").pack(side="left", padx=10)
        ttk.Radiobutton(mode_frame, text="Channel",  variable=self.url_mode, value="channel").pack(side="left", padx=10)

        inp = ttk.Frame(tab); inp.pack(fill="x", padx=10, pady=5)
        ttk.Label(inp, text="YouTube URL (playlist/channel):").pack(side="left")
        self.entry_url = ttk.Entry(inp); self.entry_url.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(inp, text="Paste", command=lambda: self.entry_url.insert("end", self._get_clipboard())).pack(side="left")

        out = ttk.Frame(tab); out.pack(fill="x", padx=10, pady=5)
        ttk.Label(out, text="Output folder (where url_yt.txt will be saved):").pack(side="left")
        self.entry_out = ttk.Entry(out); self.entry_out.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(out, text="Browse…", command=self._choose_output_folder).pack(side="left")

        opt = ttk.Frame(tab); opt.pack(fill="x", padx=10, pady=5)
        self.var_prepend = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="Prepend new URLs on top (keeps old lines)", variable=self.var_prepend).pack(side="left", padx=4)

        act = ttk.Frame(tab); act.pack(fill="x", padx=10, pady=10)
        ttk.Button(act, text="Fetch URLs → Write url_yt.txt", style="Big.TButton",
                   command=self.on_fetch_urls).pack(side="left")
        ttk.Button(act, text="Stop", command=lambda: self._stop('urls')).pack(side="left", padx=6)
        ttk.Button(act, text="Open Output Folder", command=self._open_output_folder).pack(side="left", padx=6)

    def _build_tab_subs(self, tab):
        mode_frame = ttk.LabelFrame(tab, text="Mode", style="Card.TLabelframe")
        mode_frame.pack(fill="x", padx=10, pady=(10, 5))
        self.sub_mode = tk.StringVar(value="single")
        ttk.Radiobutton(mode_frame, text="Single file/URL", variable=self.sub_mode, value="single").pack(side="left", padx=10)
        ttk.Radiobutton(mode_frame, text="Scan folder or glob for many url_yt.txt", variable=self.sub_mode, value="scan").pack(side="left", padx=10)

        row = ttk.Frame(tab); row.pack(fill="x", padx=10, pady=5)
        ttk.Label(row, text="Path (file, URL, folder or glob):").pack(side="left")
        self.entry_sub_path = ttk.Entry(row); self.entry_sub_path.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row, text="Browse…", command=self._choose_sub_path).pack(side="left")

        opt = ttk.LabelFrame(tab, text="Options", style="Card.TLabelframe")
        opt.pack(fill="x", padx=10, pady=5)
        self.var_vi = tk.BooleanVar(value=True)
        self.var_en = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="vi", variable=self.var_vi).pack(side="left")
        ttk.Checkbutton(opt, text="en", variable=self.var_en).pack(side="left")
        self.var_srt = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="Save as .srt (default .vtt)", variable=self.var_srt).pack(side="left", padx=10)
        self.var_restrict = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="Restrict filenames", variable=self.var_restrict).pack(side="left")
        self.var_overwrite = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="Force overwrite", variable=self.var_overwrite).pack(side="left")
        self.var_also_video = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="Also download video (MP4)", variable=self.var_also_video).pack(side="left", padx=10)
        ttk.Label(opt, text="Max size (e.g. 200M):").pack(side="left")
        self.entry_maxsize = ttk.Entry(opt, width=12); self.entry_maxsize.pack(side="left", padx=4)
        ttk.Label(opt, text="Impersonate:").pack(side="left", padx=(12,0))
        self.combo_imp = ttk.Combobox(opt, width=10, values=["", "chrome", "edge", "safari", "ios", "android", "msie", "firefox"])
        self.combo_imp.current(0); self.combo_imp.pack(side="left", padx=4)
        self.var_nowarn = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="No warnings", variable=self.var_nowarn).pack(side="left", padx=10)

        act = ttk.Frame(tab); act.pack(fill="x", padx=10, pady=10)
        ttk.Button(act, text="Start Download Subtitles", style="Big.TButton",
                   command=self.on_download_subs).pack(side="left")
        ttk.Button(act, text="Stop", command=lambda: self._stop('subs')).pack(side="left", padx=6)

    def _build_tab_audio(self, tab):
        inp = ttk.LabelFrame(tab, text="Input", style="Card.TLabelframe")
        inp.pack(fill="x", padx=10, pady=(10, 5))
        ttk.Label(inp, text="URL or file of URLs:").pack(side="left")
        self.entry_audio_target = ttk.Entry(inp); self.entry_audio_target.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(inp, text="Browse…", command=self._choose_audio_target).pack(side="left")

        out = ttk.LabelFrame(tab, text="Output", style="Card.TLabelframe")
        out.pack(fill="x", padx=10, pady=5)
        ttk.Label(out, text="Output folder:").pack(side="left")
        self.entry_audio_out = ttk.Entry(out); self.entry_audio_out.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(out, text="Browse…", command=self._choose_audio_out).pack(side="left")

        opt = ttk.LabelFrame(tab, text="Options", style="Card.TLabelframe")
        opt.pack(fill="x", padx=10, pady=5)
        ttk.Label(opt, text="Codec:").pack(side="left")
        self.combo_codec = ttk.Combobox(opt, width=8, values=["mp3", "m4a", "opus", "wav", "flac"])
        self.combo_codec.set("mp3"); self.combo_codec.pack(side="left", padx=4)
        ttk.Label(opt, text="Quality:").pack(side="left")
        self.combo_q = ttk.Combobox(opt, width=6, values=["128", "160", "192", "320"])
        self.combo_q.set("192"); self.combo_q.pack(side="left", padx=4)
        self.var_allow_pl = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="Allow playlist", variable=self.var_allow_pl).pack(side="left", padx=10)
        self.var_overwrite_a = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="Overwrite", variable=self.var_overwrite_a).pack(side="left")
        self.var_quiet = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="Quiet", variable=self.var_quiet).pack(side="left", padx=10)
        self.var_keepvideo = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="Keep source video", variable=self.var_keepvideo).pack(side="left")

        net = ttk.LabelFrame(tab, text="Network/Auth (optional)", style="Card.TLabelframe")
        net.pack(fill="x", padx=10, pady=5)
        self.var_inet4 = tk.BooleanVar(value=False)
        ttk.Checkbutton(net, text="Force IPv4", variable=self.var_inet4).pack(side="left", padx=4)
        ttk.Label(net, text="Cookies from browser:").pack(side="left")
        self.combo_cookies = ttk.Combobox(net, width=10, values=["", "chrome", "chromium", "firefox", "edge"])
        self.combo_cookies.current(0); self.combo_cookies.pack(side="left", padx=4)
        ttk.Label(net, text="Proxy:").pack(side="left"); self.entry_proxy = ttk.Entry(net, width=18); self.entry_proxy.pack(side="left", padx=4)
        ttk.Label(net, text="Throttled rate:").pack(side="left"); self.entry_throttle = ttk.Entry(net, width=10); self.entry_throttle.pack(side="left", padx=4)
        ttk.Label(net, text="Username:").pack(side="left"); self.entry_user = ttk.Entry(net, width=14); self.entry_user.pack(side="left", padx=4)
        ttk.Label(net, text="Password:").pack(side="left"); self.entry_pass = ttk.Entry(net, show="*", width=14); self.entry_pass.pack(side="left", padx=4)
        ttk.Label(net, text="2FA:").pack(side="left"); self.entry_2fa = ttk.Entry(net, width=10); self.entry_2fa.pack(side="left", padx=4)

        act = ttk.Frame(tab); act.pack(fill="x", padx=10, pady=10)
        ttk.Button(act, text="List Formats (first URL)",
                   command=self.on_list_formats).pack(side="left")
        ttk.Button(act, text="Start Download Audio", style="Big.TButton",
                   command=self.on_download_audio).pack(side="left", padx=6)
        ttk.Button(act, text="Stop", command=lambda: self._stop('audio')).pack(side="left", padx=6)

    # ----- helpers -----
    def _get_clipboard(self) -> str:
        try: return self.master.clipboard_get()
        except Exception: return ""

    def _choose_output_folder(self):
        d = filedialog.askdirectory(title="Choose output folder")
        if d:
            self.entry_out.delete(0, "end"); self.entry_out.insert(0, d)

    def _open_output_folder(self):
        p = self.entry_out.get().strip()
        if not p: return
        if os.name == "nt": os.startfile(p)
        elif sys.platform == "darwin": os.system(f'open "{p}"')
        else: os.system(f'xdg-open "{p}"')

    def _choose_sub_path(self):
        if getattr(self, 'sub_mode', tk.StringVar(value='single')).get() == "single":
            path = filedialog.askopenfilename(title="Choose url_yt.txt or any .txt",
                                              filetypes=[("Text", "*.txt"), ("All", "*.*")])
        else:
            path = filedialog.askdirectory(title="Choose a folder to scan recursively for url_yt.txt")
        if path:
            self.entry_sub_path.delete(0, "end")
            self.entry_sub_path.insert(0, path)

    def _choose_audio_target(self):
        path = filedialog.askopenfilename(title="Choose file of URLs (optional)",
                                          filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if path:
            self.entry_audio_target.delete(0, "end")
            self.entry_audio_target.insert(0, path)

    def _choose_audio_out(self):
        d = filedialog.askdirectory(title="Choose output folder")
        if d:
            self.entry_audio_out.delete(0, "end")
            self.entry_audio_out.insert(0, d)

    def _install_logging_redirect(self):
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        sys.stdout = LogRedirector(self.log_q)
        sys.stderr = LogRedirector(self.log_q)

    def _restore_logging(self):
        sys.stdout = self._orig_stdout
        sys.stderr = self._orig_stderr

    def _drain_log_queue(self):
        try:
            while True:
                s = self.log_q.get_nowait()
                self.txt_log.insert("end", s)
                self.txt_log.see("end")
        except queue.Empty:
            pass
        self.after(100, self._drain_log_queue)

    # ----- concurrency helpers -----
    def _start_worker(self, key: str, target, *args, **kwargs):
        # one worker per key, but keys can run concurrently
        if key in self._workers and self._workers[key].is_alive():
            messagebox.showwarning("Busy", f"A task for '{key}' is already running.")
            return
        stop_event = threading.Event()
        self._stops[key] = stop_event
        def wrapper():
            try:
                target(stop_event, *args, **kwargs)
            except Exception as e:
                print(f"\n[{key}] [ERROR] {e}\n")
            finally:
                print(f"\n[{key}] [Task finished]\n")
        th = threading.Thread(target=wrapper, daemon=True)
        self._workers[key] = th
        th.start()

    def _stop(self, key: str):
        ev = self._stops.get(key)
        if ev:
            ev.set()
            print(f"[{key}] Stop requested (will stop between items).")
        else:
            print(f"[{key}] No running task.")

    # ----- actions -----
    def on_fetch_urls(self):
        if not ensure_yt_dlp(): return
        mode = self.url_mode.get()
        url = self.entry_url.get().strip()
        out_dir = self.entry_out.get().strip()
        if not url or not out_dir:
            messagebox.showwarning("Missing info", "Please provide URL and output folder.")
            return

        def job(stop_event: threading.Event):
            tag = "urls"
            print(f"\n[{tag}] === Fetch URLs ({mode}) ===")
            if mode == "playlist": urls = fetch_playlist_urls(url)
            else: urls = fetch_channel_urls(url)
            print(f"[{tag}] Fetched: {len(urls)} URLs")
            output_file, backup_path, total, new_cnt = write_url_file(out_dir, urls, prepend_to_existing=self.var_prepend.get())
            print(f"[{tag}] Output file : {output_file}")
            if backup_path: print(f"[{tag}] Backup file : {backup_path}")
            print(f"[{tag}] New URLs added: {new_cnt}/{total}")
            print(f"[{tag}] Done.")

        self._start_worker("urls", job)

    def on_download_subs(self):
        if not ensure_yt_dlp(): return
        mode = self.sub_mode.get()
        path = self.entry_sub_path.get().strip()
        if not path:
            messagebox.showwarning("Missing path", "Please choose a path (file/URL or folder/glob).")
            return

        langs = []
        if self.var_vi.get(): langs.append("vi")
        if self.var_en.get(): langs.append("en")
        if not langs: langs = ["vi", "en"]

        as_srt = self.var_srt.get()
        restrict = self.var_restrict.get()
        overwrite = self.var_overwrite.get()
        also_video = self.var_also_video.get()
        maxsize = self.entry_maxsize.get().strip() or None
        impersonate = self.combo_imp.get().strip() or None
        quiet_warns = self.var_nowarn.get()

        def job_single(stop_event: threading.Event):
            tag = "subs"
            if re.match(r"^https?://", path, re.I):
                outdir = filedialog.askdirectory(title="Choose output folder for this URL")
                if not outdir:
                    print(f"[{tag}] [Abort] No output folder chosen."); return
                ydl_opts = build_subs_opts(Path(outdir), langs, overwrite, restrict, as_srt, also_video, impersonate, maxsize, quiet_warns, tag)
                print(f"[{tag}] Output folder : {outdir}")
                print(f"[{tag}] Subtitle langs: {langs}")
                print(f"[{tag}] Save as       : {'.srt' if as_srt else '.vtt'}")
                print(f"[{tag}] Also video    : {'Yes' if also_video else 'No (subs only)'}")
                print(f"[{tag}] Overwrite     : {'Force overwrite' if overwrite else 'Skip if exists'}")
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([path])
                return

            p = Path(path)
            if not p.exists():
                print(f"[{tag}] [ERR] Path not found: {path}"); return
            with p.open("r", encoding="utf-8", errors="ignore") as f:
                raw_urls = [ln.strip() for ln in f if ln.strip()]
            outdir = p.parent
            ydl_opts = build_subs_opts(outdir, langs, overwrite, restrict, as_srt, also_video, impersonate, maxsize, quiet_warns, tag)
            print(f"[{tag}] Output folder : {outdir}")
            print(f"[{tag}] Subtitle langs: {langs}")
            print(f"[{tag}] Total URLs    : {len(raw_urls)}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download(raw_urls)

        def job_scan(stop_event: threading.Event):
            tag = "subs"
            files = find_url_files(path)
            if not files:
                print(f"[{tag}] [ERR] No url_yt.txt found for: {path}")
                return
            print(f"[{tag}] [INFO] Found {len(files)} file(s) to process.")
            for i, url_file in enumerate(files, 1):
                if stop_event.is_set():
                    print(f"[{tag}] Stop requested; exiting loop."); break
                try:
                    with url_file.open("r", encoding="utf-8", errors="ignore") as f:
                        raw_urls = [ln.strip() for ln in f if ln.strip()]
                    outdir = url_file.parent
                    ydl_opts = build_subs_opts(outdir, langs, overwrite, restrict, as_srt, also_video, impersonate, maxsize, quiet_warns, tag)
                    print("\n" + "="*80)
                    print(f"[{tag}] [{i}/{len(files)}] File : {url_file}")
                    print(f"[{tag}] Out : {outdir}")
                    print(f"[{tag}] Lang: {langs} | Save as {'.srt' if as_srt else '.vtt'}")
                    print(f"[{tag}] URLs: {len(raw_urls)}")
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download(raw_urls)
                except Exception as e:
                    print(f"[{tag}] [ERR] {e}")
            print(f"\n[{tag}] [ALL DONE] Processed files.")

        if mode == "single":
            self._start_worker("subs", job_single)
        else:
            self._start_worker("subs", job_scan)

    def on_list_formats(self):
        if not ensure_yt_dlp(): return
        target = self.entry_audio_target.get().strip()
        if not target:
            messagebox.showwarning("Missing target", "Please provide a URL or a text file of URLs.")
            return
        urls = read_lines_maybe_file(target)
        if not urls:
            messagebox.showwarning("No URLs", "No URLs were found.")
            return
        out_dir = self.entry_audio_out.get().strip() or "."
        base_opts = build_audio_base_opts(
            out_dir=out_dir,
            codec=self.combo_codec.get(),
            quality=self.combo_q.get(),
            allow_playlist=self.var_allow_pl.get(),
            overwrite=self.var_overwrite_a.get(),
            quiet=self.var_quiet.get(),
            ffmpeg_path=None,
            keepvideo=self.var_keepvideo.get(),
            force_inet4=self.var_inet4.get(),
            cookies_from_browser=(self.combo_cookies.get() or None),
            proxy=(self.entry_proxy.get().strip() or None),
            throttled_rate=(self.entry_throttle.get().strip() or None),
            username=(self.entry_user.get().strip() or None),
            password=(self.entry_pass.get().strip() or None),
            twofactor=(self.entry_2fa.get().strip() or None),
        )
        def job(stop_event: threading.Event):
            try:
                list_formats_for_url(urls[0], base_opts, tag="audio")
            except Exception as e:
                print("[audio] Failed to list formats:", e)
                print("[audio] Tip: Update yt-dlp nightly: python -m pip install -U --pre yt-dlp")
        self._start_worker("audio_list", job)

    def on_download_audio(self):
        if not ensure_yt_dlp(): return
        target = self.entry_audio_target.get().strip()
        out_dir = self.entry_audio_out.get().strip() or "."
        if not target or not out_dir:
            messagebox.showwarning("Missing info", "Please provide target and output folder.")
            return

        urls = read_lines_maybe_file(target)
        ensure_folder(out_dir)

        base_opts = build_audio_base_opts(
            out_dir=out_dir,
            codec=self.combo_codec.get(),
            quality=self.combo_q.get(),
            allow_playlist=self.var_allow_pl.get(),
            overwrite=self.var_overwrite_a.get(),
            quiet=self.var_quiet.get(),
            ffmpeg_path=None,
            keepvideo=self.var_keepvideo.get(),
            force_inet4=self.var_inet4.get(),
            cookies_from_browser=(self.combo_cookies.get() or None),
            proxy=(self.entry_proxy.get().strip() or None),
            throttled_rate=(self.entry_throttle.get().strip() or None),
            username=(self.entry_user.get().strip() or None),
            password=(self.entry_pass.get().strip() or None),
            twofactor=(self.entry_2fa.get().strip() or None),
        )

        format_candidates = [
            "bestaudio[ext=m4a]/bestaudio[acodec^=opus]/bestaudio/best",
            "bestaudio*",
            "bestvideo+bestaudio/best",
            "best",
        ]

        def job(stop_event: threading.Event):
            tag = "audio"
            failures = []
            total = len(urls)
            for i, url in enumerate(urls, 1):
                if stop_event.is_set():
                    print(f"[{tag}] Stop requested; exiting loop."); break
                print(f"\n[{tag}] ==================== [{i}/{total}] ====================")
                print(f"[{tag}] URL: {url}")
                ok, err = download_audio_one(url, base_opts, format_candidates,
                                             simulate=False, overwrite=self.var_overwrite_a.get(), tag=tag)
                if not ok:
                    print(f"[{tag}] ❌ Error for: {url}")
                    failures.append((url, err))

            if failures:
                print(f"\n[{tag}] ============ SUMMARY: FAILURES ============")
                for url, err in failures:
                    print(f"[{tag}] - {url}\n  {err}\n")
                print(f"[{tag}] Some downloads failed.")
            else:
                print(f"\n[{tag}] ✅ All done.")

        self._start_worker("audio", job)

def main():
    root = tk.Tk()
    root.title(APP_TITLE)
    try:
        root.iconbitmap(default="")
    except Exception:
        pass
    root.geometry(DEFAULT_GEOMETRY)
    App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
