# -*- coding: utf-8 -*-
"""
YouTube Sub/Audio Toolkit — Tkinter GUI (v3.2, Compact)

What's new vs v3.0 (compact vertical UI):
- Uses a vertical PanedWindow: Notebook on top, Logs pane at bottom (resizable, collapsible).
- Denser paddings/fonts; toolbar-style rows instead of tall labelframes.
- Collapsible "Advanced" sections to hide rarely used options.
- Status bar + keyboard toggle to show/hide Logs (F12).
- Same features: URLs → url_yt.txt, Subtitles, Audio, MP3↔VTT match, Batch Tag Append.

Requirements:
- Python 3.10+
- yt-dlp, ffmpeg (for audio/video)

© 2025 — For personal/educational use.
"""
import os
import sys
import re
import csv
import json
import time
import queue
import threading
import unicodedata
from pathlib import Path
from typing import List, Optional, Tuple, Dict

# --------------- third-party ---------------
try:
    import yt_dlp
except Exception:
    yt_dlp = None

# --------------- tkinter ---------------
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

APP_TITLE = "YouTube Sub/Audio Toolkit — GUI v3.2 (Compact)"
DEFAULT_GEOMETRY = "960x520"
URL_TXT = "url_yt.txt"
MEDIA_EXTS = {".mp3", ".m4a", ".mp4", ".webm", ".opus", ".flac", ".wav"}

# ============================================================================
# Utilities (shared)
# ============================================================================

# Enable bundled ffmpeg in PyInstaller onefile
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    os.environ["PATH"] = sys._MEIPASS + os.pathsep + os.environ.get("PATH", "")

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
    s = re.sub(r'[<>:"/\\\\|?*]+', " ", s)
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

# ============================================================================
# Core youtube helpers (URLs / Subtitles / Audio)
# ============================================================================

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
    """
    Ghi url_yt.txt với mỗi URL đúng 1 dòng, không sinh dòng trống, không lặp.
    - Nếu prepend_to_existing=True: thêm URL mới lên đầu (và backup file cũ).
    - Tự chuẩn hóa 'urls': tách theo khoảng trắng/dấu phẩy, loại bỏ rỗng & trùng.
    """
    from datetime import datetime
    import shutil

    out_dir_path = Path(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)
    output_file = out_dir_path / URL_TXT

    # Chuẩn hóa & dẹt danh sách URL đầu vào
    flat: List[str] = []
    for u in urls:
        if not u:
            continue
        parts = re.split(r"[,\s]+", u.strip())
        for p in parts:
            if p:
                flat.append(p)

    # Loại trùng nhưng giữ thứ tự
    seen = set()
    norm: List[str] = []
    for u in flat:
        if u not in seen:
            norm.append(u)
            seen.add(u)

    # Đọc sẵn nội dung cũ (nếu có) và backup khi cần
    existing_lines: List[str] = []
    backup_path: Optional[str] = None
    if output_file.exists():
        with output_file.open("r", encoding="utf-8", errors="ignore") as f:
            existing_lines = [ln.strip() for ln in f if ln.strip()]

        if prepend_to_existing:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            root, ext = os.path.splitext(str(output_file))
            backup_path = f"{root}_{ts}.bak{ext or '.txt'}"
            shutil.copyfile(output_file, backup_path)

    # Hợp nhất theo chế độ prepend hay ghi mới
    if prepend_to_existing:
        existing_set = set(existing_lines)
        new_only = [u for u in norm if u not in existing_set]
        final_lines = new_only + existing_lines
    else:
        final_lines = norm

    with output_file.open("w", encoding="utf-8", newline="\n") as f:
        if final_lines:
            f.write("\n".join(final_lines))
            f.write("\n")

    new_count = len(final_lines) - len(existing_lines) if prepend_to_existing else len(final_lines)
    return str(output_file), backup_path, len(norm), new_count

# ============================================================================
# Subtitles opts & Audio opts
# ============================================================================

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

# ============================================================================
# Renamer Tab A: MP3 ↔ VTT Name Matcher (by [YouTubeID])
# (Same logic from v3.0, kept; UI density adjusted)
# ============================================================================
YOUTUBE_ID_RE = re.compile(r"\[([A-Za-z0-9_-]{11})\]")
UNDO_LOG_NAME = "_mp3_rename_undo_last.json"

def _find_youtube_id(text: str) -> Optional[str]:
    m = YOUTUBE_ID_RE.search(text)
    return m.group(1) if m else None

def _vtt_base_without_lang(vtt: Path) -> str:
    name = vtt.name
    lower = name.lower()
    if lower.endswith(".vtt"):
        stem = name[:-4]
        if "." in stem:
            parts = stem.split(".")
            last = parts[-1]
            if 1 < len(last) <= 3:
                stem = ".".join(parts[:-1])
        return stem
    return vtt.stem

def _unique_path(target: Path) -> Path:
    if not target.exists():
        return target
    parent = target.parent
    stem = target.stem
    suffix = target.suffix
    i = 1
    while True:
        cand = parent / f"{stem} ({i}){suffix}"
        if not cand.exists():
            return cand
        i += 1

def _best_vtt_for_id(vtt_by_id: Dict[str, List[Path]], yt_id: str, lang_prefs: List[str]) -> Optional[Path]:
    cands = vtt_by_id.get(yt_id, [])
    if not cands:
        return None
    def rank(p: Path) -> int:
        name = p.name.lower()
        for i, lang in enumerate(lang_prefs):
            if lang == "none":
                if name.endswith(".vtt") and not any(name.endswith(f".{x}.vtt") for x in
                    ["vi","en","fr","de","zh","jp","ja","ko","ru","es","pt","it","hi"]):
                    return i
            else:
                if name.endswith(f".{lang}.vtt"):
                    return i
        return 999
    return sorted(cands, key=rank)[0] if cands else None

def _build_match_plan(folder: Path, recursive: bool, lang_prefs: List[str]) -> List[dict]:
    mp3s = list(folder.rglob("*.mp3") if recursive else folder.glob("*.mp3"))
    vtts = list(folder.rglob("*.vtt") if recursive else folder.glob("*.vtt"))
    vtt_by_id: Dict[str, List[Path]] = {}
    for vtt in vtts:
        vid = _find_youtube_id(vtt.name)
        if vid:
            vtt_by_id.setdefault(vid, []).append(vtt)
    rows: List[dict] = []
    for mp3 in mp3s:
        yt_id = _find_youtube_id(mp3.name)
        if not yt_id:
            rows.append({"mp3": mp3, "yt_id": None, "vtt": None, "new_name": None, "status": "No [YouTubeID] in MP3 name"})
            continue
        match = _best_vtt_for_id(vtt_by_id, yt_id, lang_prefs)
        if not match:
            rows.append({"mp3": mp3, "yt_id": yt_id, "vtt": None, "new_name": None, "status": "No matching VTT"})
            continue
        base = _vtt_base_without_lang(match)
        new_name = mp3.with_name(base + ".mp3")
        rows.append({"mp3": mp3, "yt_id": yt_id, "vtt": match, "new_name": new_name, "status": "Ready"})
    return rows

def _perform_match_renames(rows: List[dict], mode: str) -> List[dict]:
    def _unique(t: Path) -> Path:
        return _unique_path(t)
    ops = []
    for row in rows:
        src: Path = row["mp3"]
        dst: Optional[Path] = row.get("new_name")
        if not dst or str(src) == str(dst):
            ops.append({"src": str(src), "dst": str(dst) if dst else "", "result": "skipped", "error": None})
            continue
        try:
            if dst.exists():
                if mode == "Skip":
                    ops.append({"src": str(src), "dst": str(dst), "result": "skipped", "error": None})
                    continue
                elif mode == "Overwrite":
                    os.replace(src, dst)
                    ops.append({"src": str(src), "dst": str(dst), "result": "overwritten", "error": None})
                elif mode == "Suffix":
                    dst2 = _unique(dst)
                    os.replace(src, dst2)
                    ops.append({"src": str(src), "dst": str(dst2), "result": "ok", "error": None})
                else:
                    raise ValueError(f"Unknown collision mode: {mode}")
            else:
                src.rename(dst)
                ops.append({"src": str(src), "dst": str(dst), "result": "ok", "error": None})
        except Exception as e:
            ops.append({"src": str(src), "dst": str(dst), "result": "error", "error": repr(e)})
    return ops

def _save_match_undo(folder: Path, ops: List[dict]):
    payload = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "ops": ops}
    with open(folder / UNDO_LOG_NAME, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def _undo_match(folder: Path) -> dict:
    log_path = folder / UNDO_LOG_NAME
    if not log_path.exists():
        return {"ok": False, "msg": "No undo log found."}
    with open(log_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    errors = []
    undone = 0
    for op in reversed(payload.get("ops", [])):
        src = Path(op["src"])    # original path
        dst = Path(op["dst"])    # renamed path
        if dst.exists():
            try:
                back = src if not src.exists() else _unique_path(src)
                os.replace(dst, back)
                undone += 1
            except Exception as e:
                errors.append(f"{dst} → {src}: {e}")
    if errors:
        return {"ok": False, "msg": f"Undone {undone}, but {len(errors)} errors:\n" + "\n".join(errors)}
    return {"ok": True, "msg": f"Undone {undone} files."}

class Mp3VttMatcherTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.folder_var = tk.StringVar()
        self.recursive_var = tk.BooleanVar(value=False)
        self.lang_var = tk.StringVar(value="vi,en,none")
        self.collision_var = tk.StringVar(value="Suffix")
        self.rows: List[dict] = []
        self._build_ui()
        self._bind_keys()

    def _build_ui(self):
        g = ttk.Frame(self); g.pack(fill="x", padx=6, pady=4)
        ttk.Label(g, text="Folder:").grid(row=0, column=0, sticky="w")
        e = ttk.Entry(g, textvariable=self.folder_var, width=70)
        e.grid(row=0, column=1, sticky="we", padx=4)
        ttk.Button(g, text="Browse… (Alt+O)", command=self.on_browse).grid(row=0, column=2, padx=4)
        ttk.Checkbutton(g, text="Scan subfolders", variable=self.recursive_var).grid(row=0, column=3, sticky="w")
        ttk.Label(g, text="Langs:").grid(row=1, column=0, sticky="e")
        ttk.Entry(g, textvariable=self.lang_var, width=18).grid(row=1, column=1, sticky="w", padx=4)
        ttk.Label(g, text="Collision:").grid(row=1, column=2, sticky="e")
        ttk.Combobox(g, textvariable=self.collision_var, values=["Skip", "Overwrite", "Suffix"], width=10, state="readonly").grid(row=1, column=3, sticky="w")
        g.columnconfigure(1, weight=1)

        btns = ttk.Frame(self); btns.pack(fill="x", padx=6, pady=(2,4))
        for txt, cmd in [
            ("Scan (Alt+S)", self.on_scan),
            ("Rename Selected (Alt+R)", self.on_rename_selected),
            ("Rename All (Alt+A)", self.on_rename_all),
            ("Undo Last (Alt+U)", self.on_undo),
        ]:
            ttk.Button(btns, text=txt, command=cmd).pack(side="left", padx=2)

        tvf = ttk.Frame(self); tvf.pack(fill="both", expand=True, padx=6, pady=4)
        cols = ("mp3", "vtt", "new", "status")
        self.tv = ttk.Treeview(tvf, columns=cols, show="headings", selectmode="extended")
        for c, txt, w in zip(cols, ["Current MP3", "Matched VTT", "New MP3 Name", "Status"], [320, 320, 320, 100]):
            self.tv.heading(c, text=txt); self.tv.column(c, width=w, anchor="w", stretch=True)
        vsb = ttk.Scrollbar(tvf, orient="vertical", command=self.tv.yview)
        hsb = ttk.Scrollbar(tvf, orient="horizontal", command=self.tv.xview)
        self.tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tv.grid(row=0, column=0, sticky="nsew"); vsb.grid(row=0, column=1, sticky="ns"); hsb.grid(row=1, column=0, sticky="ew")
        tvf.rowconfigure(0, weight=1); tvf.columnconfigure(0, weight=1)

        # Auto-resize columns on window resize
        _ratios = (3, 3, 3, 1)
        def _auto_cols(event=None):
            try:
                w = max(200, self.tv.winfo_width() - 18)
                total = sum(_ratios)
                for c, r in zip(cols, _ratios):
                    self.tv.column(c, width=int(w * r / total))
            except Exception:
                pass
        self.tv.bind("<Configure>", _auto_cols)
        _auto_cols()

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(self, textvariable=self.status_var, anchor="w").pack(fill="x", padx=6, pady=(0,4))

    def _bind_keys(self):
        self.bind_all("<Alt-o>", lambda e: self.on_browse())
        self.bind_all("<Alt-O>", lambda e: self.on_browse())
        self.bind_all("<Alt-s>", lambda e: self.on_scan())
        self.bind_all("<Alt-S>", lambda e: self.on_scan())
        self.bind_all("<Alt-r>", lambda e: self.on_rename_selected())
        self.bind_all("<Alt-R>", lambda e: self.on_rename_selected())
        self.bind_all("<Alt-a>", lambda e: self.on_rename_all())
        self.bind_all("<Alt-A>", lambda e: self.on_rename_all())
        self.bind_all("<Alt-u>", lambda e: self.on_undo())
        self.bind_all("<Alt-U>", lambda e: self.on_undo())

    def on_browse(self):
        d = filedialog.askdirectory(title="Select folder containing MP3 and VTT")
        if d:
            self.folder_var.set(d)

    def on_scan(self):
        folder = Path(self.folder_var.get().strip() or ".").resolve()
        if not folder.exists():
            messagebox.showerror("Error", f"Folder not found:\n{folder}")
            return
        lang_prefs = [x.strip().lower() for x in self.lang_var.get().split(",") if x.strip()] or ["vi","en","none"]
        try:
            self.rows = _build_match_plan(folder, self.recursive_var.get(), lang_prefs)
        except Exception as e:
            messagebox.showerror("Scan failed", str(e))
            self.status_var.set("Scan failed."); return

        for i in self.tv.get_children(): self.tv.delete(i)
        ok, miss = 0, 0
        for row in self.rows:
            mp3 = row["mp3"].name
            vtt = row["vtt"].name if row["vtt"] else ""
            newn = row["new_name"].name if row.get("new_name") else ""
            st = row["status"]
            ok += (st == "Ready")
            miss += (st != "Ready")
            self.tv.insert("", "end", values=(mp3, vtt, newn, st))
        self.status_var.set(f"Scan complete. Ready: {ok}, Missing/NoID: {miss}.")

    def _selected_rows(self) -> List[int]:
        sel = []
        names_to_index = {row["mp3"].name: i for i, row in enumerate(self.rows)}
        for iid in self.tv.selection():
            vals = self.tv.item(iid, "values")
            if vals:
                idx = names_to_index.get(vals[0])
                if idx is not None: sel.append(idx)
        return sel

    def _do_rename(self, indices: Optional[List[int]]):
        if not self.rows:
            messagebox.showinfo("Info", "Nothing to rename. Please Scan first."); return
        target_rows = self.rows if indices is None else [self.rows[i] for i in indices]
        target_rows = [r for r in target_rows if r.get("new_name") and r["status"] == "Ready"]
        if not target_rows:
            messagebox.showinfo("Info", "No 'Ready' rows to rename."); return
        folder = Path(self.folder_var.get().strip() or ".").resolve()
        mode = self.collision_var.get()
        ops = _perform_match_renames(target_rows, mode=mode)
        _save_match_undo(folder, ops)
        res_map = {Path(op["src"]).name: op["result"] for op in ops}
        for iid in self.tv.get_children():
            vals = list(self.tv.item(iid, "values")); mp3_name = vals[0]
            result = res_map.get(mp3_name)
            if result:
                vals[3] = f"Renamed ({result})" if result in ("ok","overwritten") else result
                self.tv.item(iid, values=tuple(vals))
        okc = sum(1 for op in ops if op["result"] in ("ok","overwritten"))
        skc = sum(1 for op in ops if op["result"] == "skipped")
        erc = sum(1 for op in ops if op["result"] == "error")
        self.status_var.set(f"Done. Renamed: {okc}, Skipped: {skc}, Errors: {erc}. Undo log saved.")

    def on_rename_all(self):
        self._do_rename(indices=None)

    def on_rename_selected(self):
        idxs = self._selected_rows()
        if not idxs:
            messagebox.showinfo("Info", "Please select one or more rows in the table."); return
        self._do_rename(indices=idxs)

    def on_undo(self):
        folder = Path(self.folder_var.get().strip() or ".").resolve()
        result = _undo_match(folder)
        if result["ok"]: messagebox.showinfo("Undo", result["msg"])
        else: messagebox.showwarning("Undo", result["msg"])

# ============================================================================
# Renamer Tab B: Batch Tag Append — compact UI
# ============================================================================
TAG_RE = re.compile(r"\[([A-Za-z0-9_-]{6,})\]\s*-\s*(\d{4}-\d{2}-\d{2})")
TRAILING_TAG_RE = re.compile(r"\s*\[[A-Za-z0-9_-]{6,}\]\s*-\s*\d{4}-\d{2}-\d{2}\s*$")
DEFAULT_EXTS = {".mp3",".mp4",".mkv",".wav",".pdf",".docx",".txt",".srt",".vtt",".zip"}
ANCHOR_PREFERENCE = (".vtt",".srt",".mp3",".pdf",".docx",".txt")

def ext_full(p: Path) -> str:
    return "".join(p.suffixes) if p.suffixes else ""

def stem_full(p: Path) -> str:
    ef = ext_full(p)
    return p.name if not ef else p.name[: -len(ef)]

def parse_tag_from_text(text: str) -> Optional[Tuple[str, str]]:
    m = TAG_RE.search(text)
    return (m.group(1), m.group(2)) if m else None

def has_trailing_tag(stem: str) -> bool:
    return bool(TRAILING_TAG_RE.search(stem))

def strip_trailing_tag(stem: str) -> str:
    return TRAILING_TAG_RE.sub("", stem).strip(" _-")

def norm_core_key(s: str) -> str:
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()

def unique_target(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    i = 1
    while True:
        cand = path.with_name(f"{stem} ({i}){suffix}")
        if not cand.exists():
            return cand
        i += 1

def discover_anchors(files: List[Path], consider_exts: set) -> Dict[str, Tuple[str, str]]:
    anchors_by_dir: Dict[Path, Dict[str, Tuple[str, str, int]]] = {}
    for p in files:
        if not p.is_file(): continue
        ef = ext_full(p)
        if not ef or not any(ef.lower().endswith(e) for e in consider_exts): continue
        stem = stem_full(p)
        tag = parse_tag_from_text(stem)
        if not tag: continue
        core = strip_trailing_tag(stem)
        key = norm_core_key(core)
        prio = 999
        for idx, cand in enumerate(ANCHOR_PREFERENCE):
            if ef.lower().endswith(cand): prio = idx; break
        dmap = anchors_by_dir.setdefault(p.parent, {})
        if key not in dmap or prio < dmap[key][2]:
            dmap[key] = (tag[0], tag[1], prio)
    anchors: Dict[str, Tuple[str, str]] = {}
    for d, m in anchors_by_dir.items():
        for key, (yt, dt, _) in m.items():
            anchors[f"{d}\\0{key}"] = (yt, dt)
    return anchors

def plan_renames(files: List[Path], consider_exts: set, collision: str, stop_event: threading.Event, progress=None):
    if progress: progress(len(files), 0, "Scanning anchors…")
    anchors = discover_anchors(files, consider_exts)
    planned = []
    skipped = 0
    done = 0
    for p in files:
        if stop_event.is_set(): break
        done += 1
        if progress and done % 50 == 0:
            progress(len(files), done, f"Planning… {done}/{len(files)}")
        if not p.is_file(): continue
        ef = ext_full(p)
        if not ef or not any(ef.lower().endswith(e) for e in consider_exts): continue
        stem = stem_full(p)
        tag_now = parse_tag_from_text(stem)
        if tag_now and has_trailing_tag(stem):
            skipped += 1; continue
        core = strip_trailing_tag(stem)
        if not core.strip(): skipped += 1; continue
        key = norm_core_key(core)
        anchors_key = f"{p.parent}\\0{key}"
        tag = anchors.get(anchors_key)
        if not tag:
            skipped += 1; continue
        yt_id, date = tag
        new_name = f"{core} [{yt_id}] - {date}{ef}"
        new_name = new_name.rstrip(". ").rstrip()
        target = p.with_name(new_name)
        if target == p:
            skipped += 1; continue
        if target.exists():
            if collision == "skip":
                skipped += 1; continue
            elif collision == "unique":
                target = unique_target(target)
        planned.append((p, target, yt_id, date))
    return planned, skipped, stop_event.is_set()

def write_log(planned: list) -> Path:
    from datetime import datetime
    ts = datetime.now().strftime("rename_log_%Y-%m-%d_%H-%M-%S.csv")
    log_path = Path.cwd() / ts
    with log_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "old_path", "new_path", "applied"])
        now = datetime.now().isoformat(timespec="seconds")
        for old, new, _, _ in planned:
            w.writerow([now, str(old), str(new), "NO"])
    return log_path

def apply_renames(planned: list, log_path: Path, stop_event: threading.Event, progress=None):
    from datetime import datetime
    if progress: progress(len(planned), 0, "Applying renames…")
    applied = 0
    with log_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "old_path", "new_path", "applied"])
        now = datetime.now().isoformat(timespec="seconds")
        for idx, (old, new, _, _) in enumerate(planned, 1):
            if stop_event.is_set(): break
            try:
                new.parent.mkdir(parents=True, exist_ok=True)
                if new.exists(): os.replace(old, new)
                else: old.rename(new)
                w.writerow([now, str(old), str(new), "YES"])
                applied += 1
            except Exception as e:
                w.writerow([now, str(old), str(new), f"ERROR: {e}"])
            if progress and idx % 20 == 0:
                progress(len(planned), idx, f"Applying… {idx}/{len(planned)}")
    return applied, stop_event.is_set()

def revert_from_log(log_csv: Path, stop_event: threading.Event, progress=None):
    if not log_csv.exists():
        raise FileNotFoundError(f"Log not found: {log_csv}")
    rows = []
    with log_csv.open("r", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        for r in rdr: rows.append(r)
    total = len(rows)
    if progress: progress(total, 0, "Reverting…")
    count = 0
    for i, r in enumerate(rows, 1):
        if stop_event.is_set(): break
        old = Path(r["old_path"]); new = Path(r["new_path"])
        try:
            if new.exists():
                if old.exists():
                    back = unique_target(old); os.replace(new, back)
                else:
                    new.rename(old)
                count += 1
        except Exception:
            pass
        if progress and i % 20 == 0:
            progress(total, i, f"Reverting… {i}/{total}")
    return count, stop_event.is_set()

class BatchTagAppendTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.stop_event = threading.Event()
        self.worker: Optional[threading.Thread] = None
        self.ui_queue: "queue.Queue" = queue.Queue()

        self.root_path = tk.StringVar()
        self.exts = tk.StringVar(value=",".join(sorted(DEFAULT_EXTS)))
        self.collision = tk.StringVar(value="unique")
        self.include_sub = tk.BooleanVar(value=True)

        self.status_var = tk.StringVar(value="Ready.")
        self.progress_total = 0
        self.progress_done = 0

        self._build_ui()
        self._bind_shortcuts()
        self._poll_ui_queue()

    def _build_ui(self):
        top = ttk.Frame(self); top.pack(fill="x", padx=6, pady=4)
        ttk.Label(top, text="Root:").grid(row=0, column=0, sticky="w")
        e_root = ttk.Entry(top, textvariable=self.root_path, width=90)
        e_root.grid(row=0, column=1, sticky="we", padx=4)
        ttk.Button(top, text="Browse… [Alt+O]", command=self.on_browse).grid(row=0, column=2, padx=2)
        ttk.Label(top, text="Exts:").grid(row=1, column=0, sticky="e")
        ttk.Entry(top, textvariable=self.exts, width=40).grid(row=1, column=1, sticky="w", padx=4)
        ttk.Label(top, text="Collision:").grid(row=1, column=2, sticky="e")
        ttk.Combobox(top, textvariable=self.collision, values=["skip","overwrite","unique"], width=10, state="readonly").grid(row=1, column=3, sticky="w", padx=2)
        ttk.Checkbutton(top, text="Subfolders", variable=self.include_sub).grid(row=1, column=4, sticky="w", padx=6)
        top.grid_columnconfigure(1, weight=1)

        actions = ttk.Frame(self); actions.pack(fill="x", padx=6, pady=4)
        for txt, cmd in [("Plan (Alt+R)", self.on_plan), ("Apply (Alt+A)", self.on_apply), ("Revert… (Alt+V)", self.on_revert), ("Stop (Alt+S)", self.on_stop)]:
            ttk.Button(actions, text=txt, command=cmd).pack(side="left", padx=2)

        tv_frame = ttk.Frame(self); tv_frame.pack(fill="both", expand=True, padx=6, pady=4)
        cols = ("old_name","new_name","yt_id","date","folder")
        self.tv = ttk.Treeview(tv_frame, columns=cols, show="headings")
        for c, txt, w, anc in [
            ("old_name","Old Name",420,"w"),
            ("new_name","New Name",420,"w"),
            ("yt_id","YouTubeID",110,"center"),
            ("date","Date",100,"center"),
            ("folder","Folder",320,"w"),
        ]:
            self.tv.heading(c, text=txt); self.tv.column(c, width=w, anchor=anc, stretch=True)
        self.tv.pack(side="left", fill="both", expand=True)
        vs = ttk.Scrollbar(tv_frame, orient="vertical", command=self.tv.yview)
        vs.pack(side="right", fill="y")
        self.tv.configure(yscrollcommand=vs.set)

        # Auto-resize columns on resize
        _ratios2 = (3, 3, 1, 1, 2)
        def _auto_cols2(event=None):
            try:
                w = max(300, self.tv.winfo_width() - 18)
                total = sum(_ratios2)
                for c, r in zip(cols, _ratios2):
                    self.tv.column(c, width=int(w * r / total))
            except Exception:
                pass
        self.tv.bind("<Configure>", _auto_cols2)
        _auto_cols2()

        bottom = ttk.Frame(self); bottom.pack(fill="x", padx=6, pady=(0,6))
        self.pbar = ttk.Progressbar(bottom, mode="determinate"); self.pbar.pack(fill="x", side="left", expand=True, padx=(0,6))
        ttk.Label(bottom, textvariable=self.status_var).pack(side="right")

    def _bind_shortcuts(self):
        self.bind_all("<Alt-o>", lambda e: self.on_browse())
        self.bind_all("<Alt-O>", lambda e: self.on_browse())
        self.bind_all("<Alt-r>", lambda e: self.on_plan())
        self.bind_all("<Alt-R>", lambda e: self.on_plan())
        self.bind_all("<Alt-a>", lambda e: self.on_apply())
        self.bind_all("<Alt-A>", lambda e: self.on_apply())
        self.bind_all("<Alt-v>", lambda e: self.on_revert())
        self.bind_all("<Alt-V>", lambda e: self.on_revert())
        self.bind_all("<Alt-s>", lambda e: self.on_stop())
        self.bind_all("<Alt-S>", lambda e: self.on_stop())

    def _poll_ui_queue(self):
        try:
            while True:
                item = self.ui_queue.get_nowait()
                t = item[0]
                if t == "progress":
                    _, total, done, msg = item
                    self._update_progress(total, done, msg)
                elif t == "plan_result":
                    _, planned, skipped, stopped = item
                    self._fill_tv(planned)
                    if stopped: self._set_status(f"Stopped. Planned {len(planned)}, skipped {skipped}.")
                    else: self._set_status(f"Planned {len(planned)}, skipped {skipped}. Re-run Apply to execute.")
                elif t == "plan_preview_only":
                    _, planned = item
                    self._fill_tv(planned)
                elif t == "status":
                    _, msg = item
                    self._set_status(msg)
                elif t == "error":
                    _, msg = item
                    messagebox.showerror("Error", msg)
                    self._set_status(f"Error: {msg}")
        except queue.Empty:
            pass
        finally:
            self.after(100, self._poll_ui_queue)

    def _update_progress(self, total, done, msg):
        self.progress_total = total or 1
        self.progress_done = min(done, self.progress_total)
        self.pbar["maximum"] = self.progress_total
        self.pbar["value"] = self.progress_done
        self.status_var.set(msg)

    def _set_status(self, msg): self.status_var.set(msg)

    def _fill_tv(self, planned):
        for i in self.tv.get_children(): self.tv.delete(i)
        for old, new, yt, dt in planned:
            self.tv.insert("", "end", values=(old.name, new.name, yt, dt, str(old.parent)))

    def _clear_tv(self):
        for i in self.tv.get_children(): self.tv.delete(i)

    def _start_worker(self, target, *args):
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("Busy", "A task is running. Please wait or press Stop.")
            return
        self.stop_event.clear()
        self.progress_total = 0; self.progress_done = 0
        self.pbar["value"] = 0; self.pbar["maximum"] = 100
        self.worker = threading.Thread(target=target, args=args, daemon=True)
        self.worker.start()

    def _progress_cb(self, total, done, msg):
        self.ui_queue.put(("progress", total, done, msg))

    def _collect_files(self, root: Path) -> List[Path]:
        if self.include_sub.get():
            return [p for p in root.rglob("*") if p.is_file()]
        else:
            return [p for p in root.glob("*") if p.is_file()]

    def _parse_exts(self) -> set:
        raw = self.exts.get().strip()
        exts = set()
        for x in (t.strip() for t in raw.split(",") if t.strip()):
            if not x.startswith("."): x = "." + x
            exts.add(x.lower())
        return exts

    def on_browse(self):
        d = filedialog.askdirectory(title="Select root folder")
        if d: self.root_path.set(d)

    def on_plan(self):
        root = self._validate_root()
        if not root: return
        consider_exts = self._parse_exts()
        self._clear_tv()
        self._set_status("Planning (dry-run)…")
        self._start_worker(self._worker_plan, root, consider_exts)

    def on_apply(self):
        root = self._validate_root()
        if not root: return
        consider_exts = self._parse_exts()
        self._clear_tv()
        self._set_status("Planning and applying…")
        self._start_worker(self._worker_apply, root, consider_exts)

    def on_revert(self):
        log_path = filedialog.askopenfilename(title="Choose rename log CSV", filetypes=[("CSV files","*.csv"), ("All files","*.*")])
        if not log_path: return
        self._clear_tv()
        self._set_status("Reverting from log…")
        self._start_worker(self._worker_revert, Path(log_path))

    def on_stop(self):
        self.stop_event.set()
        self._set_status("Stopping…")

    def _worker_plan(self, root: Path, consider_exts: set):
        try:
            files = self._collect_files(root)
            planned, skipped, stopped = plan_renames(files, consider_exts, self.collision.get(), self.stop_event, self._progress_cb)
            self.ui_queue.put(("plan_result", planned, skipped, stopped))
        except Exception as e:
            self.ui_queue.put(("error", str(e)))

    def _worker_apply(self, root: Path, consider_exts: set):
        try:
            files = self._collect_files(root)
            planned, skipped, stopped = plan_renames(files, consider_exts, self.collision.get(), self.stop_event, self._progress_cb)
            if stopped:
                self.ui_queue.put(("status", f"Stopped. Planned {len(planned)}, skipped {skipped}.")); return
            if not planned:
                self.ui_queue.put(("status", f"No files to rename. Skipped {skipped}.")); return
            self.ui_queue.put(("plan_preview_only", planned))
            log_path = write_log(planned)
            applied, stopped2 = apply_renames(planned, log_path, self.stop_event, self._progress_cb)
            suffix = " (stopped)" if stopped2 else ""
            self.ui_queue.put(("status", f"Applied {applied}/{len(planned)}{suffix}. Log: {log_path}"))
        except Exception as e:
            self.ui_queue.put(("error", str(e)))

    def _worker_revert(self, log_csv: Path):
        try:
            count, stopped = revert_from_log(log_csv, self.stop_event, self._progress_cb)
            suffix = " (stopped)" if stopped else ""
            self.ui_queue.put(("status", f"Reverted {count}{suffix} from {log_csv.name}"))
        except Exception as e:
            self.ui_queue.put(("error", str(e)))

    def _validate_root(self) -> Optional[Path]:
        rp = self.root_path.get().strip()
        if not rp:
            messagebox.showwarning("Missing folder", "Please choose the root folder (Browse… [Alt+O]).")
            return None
        root = Path(rp).expanduser()
        if not root.exists():
            messagebox.showerror("Not found", f"Folder not found:\n{root}")
            return None
        return root

# ============================================================================
# Tiny Collapsible section helper (for Advanced options)
# ============================================================================
class Collapsible(ttk.Frame):
    def __init__(self, master, title="Advanced", opened=False):
        super().__init__(master)
        self._open = tk.BooleanVar(value=opened)
        self.btn = ttk.Checkbutton(self, text=title, variable=self._open, command=self._toggle, style="Toolbutton")
        self.btn.pack(anchor="w")
        self.body = ttk.Frame(self)
        if opened:
            self.body.pack(fill="x", expand=False)
    def _toggle(self):
        if self._open.get():
            self.body.pack(fill="x", expand=False)
        else:
            self.body.forget()

# ============================================================================
# Tkinter Main App (compact styles + paned logs)
# ============================================================================
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
        # Global smaller font to cut vertical space
        try:
            # self.master.option_add("*Font", "Segoe UI 9")
            default_font = tkfont.nametofont("TkDefaultFont")
            default_font.configure(family="Segoe UI", size=9)
            self.master.option_add("*Font", default_font)

        except Exception:
            pass

        self._make_styles()
        self._build_ui()

        # logging to the bottom "Logs" panel
        self.log_q: "queue.Queue[str]" = queue.Queue()
        self._install_logging_redirect()

        # per-tab workers & stop flags for YT tabs
        self._workers: Dict[str, threading.Thread] = {}
        self._stops: Dict[str, threading.Event] = {}

        self.after(100, self._drain_log_queue)

    def _make_styles(self):
        style = ttk.Style()
        try: style.theme_use("clam")
        except Exception: pass
        # Compact paddings
        style.configure("TButton", padding=2)
        style.configure("TLabel", padding=1)
        style.configure("TEntry", padding=1)
        style.configure("Header.TLabel", font=("Segoe UI", 10, "bold"))
        style.configure("Big.TButton", padding=6, font=("Segoe UI", 10, "bold"))
        style.configure("Card.TLabelframe", padding=4)
        style.configure("Card.TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        # Extra compact tweaks for notebook and tabs
        style.configure("TNotebook", tabmargins=[2,1,2,0])
        style.configure("TNotebook.Tab", padding=(6,2), font=("Segoe UI", 9))

    def _build_ui(self):
        # Top toolbar: show/hide logs, minimal controls
        toolbar = ttk.Frame(self); toolbar.pack(fill="x", padx=6, pady=(6,2))
        self.btn_logs = ttk.Button(toolbar, text="▼ Logs (F12)", command=self._toggle_logs)
        self.btn_logs.pack(side="right")
        ttk.Label(toolbar, text="Compact layout active", style="Header.TLabel").pack(side="left")

        # PanedWindow: top notebook, bottom logs
        self.paned = ttk.Panedwindow(self, orient="vertical")
        self.paned.pack(fill="both", expand=True)

        # --- notebook
        nb_container = ttk.Frame(self.paned)
        self.paned.add(nb_container, weight=4)
        nb = ttk.Notebook(nb_container)
        nb.pack(fill="both", expand=True, padx=6, pady=6)

        # tabs
        self.tab_urls = ttk.Frame(nb); nb.add(self.tab_urls, text="🧾 Get URLs")
        self.tab_subs = ttk.Frame(nb); nb.add(self.tab_subs, text="📝 Subtitles")
        self.tab_audio = ttk.Frame(nb); nb.add(self.tab_audio, text="🎵 Audio")
        self.tab_match = Mp3VttMatcherTab(nb); nb.add(self.tab_match, text="🔗 MP3↔VTT Match")
        self.tab_tagger = BatchTagAppendTab(nb); nb.add(self.tab_tagger, text="🏷️ Batch Tag Append")

        # build contents
        self._build_tab_urls(self.tab_urls)
        self._build_tab_subs(self.tab_subs)
        self._build_tab_audio(self.tab_audio)

        # --- logs pane
        log_container = ttk.Frame(self.paned)
        self.paned.add(log_container, weight=1)
        lf = ttk.Frame(log_container)
        lf.pack(fill="both", expand=True, padx=6, pady=(0,6))
        ttk.Label(lf, text="Logs (YT tasks)").pack(anchor="w")
        self.txt_log = ScrolledText(lf, height=5, wrap="word")
        self.txt_log.pack(fill="both", expand=True)
        # Start with logs collapsed to save vertical space
        self._logs_visible = True
        self._toggle_logs()

        # Status bar
        status = ttk.Frame(self); status.pack(fill="x", padx=6, pady=(0,6))
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(status, textvariable=self.status_var).pack(side="left")

        # shortcuts
        self.master.bind("<F12>", lambda e: self._toggle_logs())

    # ----- compact tabs: UI -----
    def _build_tab_urls(self, tab):
        row1 = ttk.Frame(tab); row1.pack(fill="x", padx=6, pady=(6,2))
        ttk.Label(row1, text="Mode:").pack(side="left")
        self.url_mode = tk.StringVar(value="playlist")
        ttk.Radiobutton(row1, text="Playlist", variable=self.url_mode, value="playlist").pack(side="left", padx=6)
        ttk.Radiobutton(row1, text="Channel",  variable=self.url_mode, value="channel").pack(side="left")

        row2 = ttk.Frame(tab); row2.pack(fill="x", padx=6, pady=2)
        ttk.Label(row2, text="URL:").pack(side="left")
        self.entry_url = ttk.Entry(row2)
        self.entry_url.pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(row2, text="Paste", command=lambda: self.entry_url.insert("end", self._get_clipboard())).pack(side="left")

        row3 = ttk.Frame(tab); row3.pack(fill="x", padx=6, pady=2)
        ttk.Label(row3, text="Output:").pack(side="left")
        self.entry_out = ttk.Entry(row3)
        self.entry_out.pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(row3, text="Browse…", command=self._choose_output_folder).pack(side="left")
        self.var_prepend = tk.BooleanVar(value=True)
        ttk.Checkbutton(row3, text="Prepend", variable=self.var_prepend).pack(side="left", padx=6)

        act = ttk.Frame(tab); act.pack(fill="x", padx=6, pady=(4,6))
        ttk.Button(act, text="Fetch → url_yt.txt", style="Big.TButton", command=self.on_fetch_urls).pack(side="left")
        ttk.Button(act, text="Stop", command=lambda: self._stop('urls')).pack(side="left", padx=6)
        ttk.Button(act, text="Open Folder", command=self._open_output_folder).pack(side="left")

    def _build_tab_subs(self, tab):
        row0 = ttk.Frame(tab); row0.pack(fill="x", padx=6, pady=(6,2))
        self.sub_mode = tk.StringVar(value="single")
        ttk.Radiobutton(row0, text="Single file/URL", variable=self.sub_mode, value="single").pack(side="left")
        ttk.Radiobutton(row0, text="Scan folder/glob", variable=self.sub_mode, value="scan").pack(side="left", padx=8)

        row1 = ttk.Frame(tab); row1.pack(fill="x", padx=6, pady=2)
        ttk.Label(row1, text="Path:").pack(side="left")
        self.entry_sub_path = ttk.Entry(row1); self.entry_sub_path.pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(row1, text="Browse…", command=self._choose_sub_path).pack(side="left")

        row2 = ttk.Frame(tab); row2.pack(fill="x", padx=6, pady=2)
        self.var_vi = tk.BooleanVar(value=True)
        self.var_en = tk.BooleanVar(value=False)
        ttk.Label(row2, text="Lang:").pack(side="left")
        ttk.Checkbutton(row2, text="vi", variable=self.var_vi).pack(side="left")
        ttk.Checkbutton(row2, text="en", variable=self.var_en).pack(side="left")
        self.var_srt = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text=".srt", variable=self.var_srt).pack(side="left", padx=6)
        self.var_restrict = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="Restrict names", variable=self.var_restrict).pack(side="left")
        self.var_overwrite = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="Overwrite", variable=self.var_overwrite).pack(side="left")
        self.var_also_video = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="+Video", variable=self.var_also_video).pack(side="left")
        ttk.Label(row2, text="Max:").pack(side="left"); self.entry_maxsize = ttk.Entry(row2, width=10); self.entry_maxsize.pack(side="left", padx=2)

        adv = Collapsible(tab, title="Advanced", opened=False)
        adv.pack(fill="x", padx=6, pady=(2,2))
        r3 = ttk.Frame(adv.body); r3.pack(fill="x")
        ttk.Label(r3, text="Impersonate:").pack(side="left")
        self.combo_imp = ttk.Combobox(r3, width=10, values=["", "chrome", "edge", "safari", "ios", "android", "msie", "firefox"])
        self.combo_imp.current(0); self.combo_imp.pack(side="left", padx=4)
        self.var_nowarn = tk.BooleanVar(value=True)
        ttk.Checkbutton(r3, text="No warnings", variable=self.var_nowarn).pack(side="left", padx=6)

        act = ttk.Frame(tab); act.pack(fill="x", padx=6, pady=(2,6))
        ttk.Button(act, text="Start Download Subtitles", style="Big.TButton", command=self.on_download_subs).pack(side="left")
        ttk.Button(act, text="Stop", command=lambda: self._stop('subs')).pack(side="left", padx=6)

    def _build_tab_audio(self, tab):
        row1 = ttk.Frame(tab); row1.pack(fill="x", padx=6, pady=(6,2))
        ttk.Label(row1, text="Target (URL or .txt):").pack(side="left")
        self.entry_audio_target = ttk.Entry(row1); self.entry_audio_target.pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(row1, text="Browse…", command=self._choose_audio_target).pack(side="left")

        row2 = ttk.Frame(tab); row2.pack(fill="x", padx=6, pady=2)
        ttk.Label(row2, text="Output:").pack(side="left")
        self.entry_audio_out = ttk.Entry(row2); self.entry_audio_out.pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(row2, text="Browse…", command=self._choose_audio_out).pack(side="left")

        row3 = ttk.Frame(tab); row3.pack(fill="x", padx=6, pady=2)
        ttk.Label(row3, text="Codec:").pack(side="left")
        self.combo_codec = ttk.Combobox(row3, width=8, values=["mp3", "m4a", "opus", "wav", "flac"])
        self.combo_codec.set("mp3"); self.combo_codec.pack(side="left", padx=2)
        ttk.Label(row3, text="Quality:").pack(side="left")
        self.combo_q = ttk.Combobox(row3, width=6, values=["128", "160", "192", "320"])
        self.combo_q.set("192"); self.combo_q.pack(side="left", padx=2)
        self.var_allow_pl = tk.BooleanVar(value=True)
        ttk.Checkbutton(row3, text="Allow playlist", variable=self.var_allow_pl).pack(side="left", padx=6)
        self.var_overwrite_a = tk.BooleanVar(value=False)
        ttk.Checkbutton(row3, text="Overwrite", variable=self.var_overwrite_a).pack(side="left")
        self.var_quiet = tk.BooleanVar(value=False)
        ttk.Checkbutton(row3, text="Quiet", variable=self.var_quiet).pack(side="left", padx=6)
        self.var_keepvideo = tk.BooleanVar(value=False)
        ttk.Checkbutton(row3, text="Keep video", variable=self.var_keepvideo).pack(side="left")

        adv = Collapsible(tab, title="Advanced Network/Auth", opened=False)
        adv.pack(fill="x", padx=6, pady=(2,2))
        r4 = ttk.Frame(adv.body); r4.pack(fill="x")
        self.var_inet4 = tk.BooleanVar(value=False)
        ttk.Checkbutton(r4, text="Force IPv4", variable=self.var_inet4).pack(side="left", padx=2)
        ttk.Label(r4, text="Cookies:").pack(side="left")
        self.combo_cookies = ttk.Combobox(r4, width=10, values=["", "chrome", "chromium", "firefox", "edge"])
        self.combo_cookies.current(0); self.combo_cookies.pack(side="left", padx=4)
        ttk.Label(r4, text="Proxy:").pack(side="left"); self.entry_proxy = ttk.Entry(r4, width=18); self.entry_proxy.pack(side="left", padx=2)
        ttk.Label(r4, text="Throttle:").pack(side="left"); self.entry_throttle = ttk.Entry(r4, width=10); self.entry_throttle.pack(side="left", padx=2)
        ttk.Label(r4, text="User:").pack(side="left"); self.entry_user = ttk.Entry(r4, width=14); self.entry_user.pack(side="left", padx=2)
        ttk.Label(r4, text="Pass:").pack(side="left"); self.entry_pass = ttk.Entry(r4, show="*", width=14); self.entry_pass.pack(side="left", padx=2)
        ttk.Label(r4, text="2FA:").pack(side="left"); self.entry_2fa = ttk.Entry(r4, width=10); self.entry_2fa.pack(side="left", padx=2)

        act = ttk.Frame(tab); act.pack(fill="x", padx=6, pady=(2,6))
        ttk.Button(act, text="List Formats (first URL)", command=self.on_list_formats).pack(side="left")
        ttk.Button(act, text="Start Download Audio", style="Big.TButton", command=self.on_download_audio).pack(side="left", padx=6)
        ttk.Button(act, text="Stop", command=lambda: self._stop('audio')).pack(side="left")

    # ----- helpers -----
    def _toggle_logs(self):
        if self._logs_visible:
            try:
                # Collapse logs by setting its height very small
                self.paned.paneconfigure(1, height=1)
            except Exception:
                pass
            self._logs_visible = False
            self.btn_logs.configure(text="▲ Show Logs (F12)")
        else:
            try:
                self.paned.paneconfigure(1, height=180)
            except Exception:
                pass
            self._logs_visible = True
            self.btn_logs.configure(text="▼ Logs (F12)")

    def _get_clipboard(self) -> str:
        try: return self.master.clipboard_get()
        except Exception: return ""

    def _choose_output_folder(self):
        d = filedialog.askdirectory(title="Choose output folder")
        if d: self.entry_out.delete(0, "end"); self.entry_out.insert(0, d)

    def _open_output_folder(self):
        p = self.entry_out.get().strip()
        if not p: return
        if os.name == "nt": os.startfile(p)
        elif sys.platform == "darwin": os.system(f'open "{p}"')
        else: os.system(f'xdg-open "{p}"')

    def _choose_sub_path(self):
        if getattr(self, 'sub_mode', tk.StringVar(value='single')).get() == "single":
            path = filedialog.askopenfilename(title="Choose url_yt.txt or any .txt", filetypes=[("Text", "*.txt"), ("All", "*.*")])
        else:
            path = filedialog.askdirectory(title="Choose a folder to scan recursively for url_yt.txt")
        if path: self.entry_sub_path.delete(0, "end"); self.entry_sub_path.insert(0, path)

    def _choose_audio_target(self):
        path = filedialog.askopenfilename(title="Choose file of URLs (optional)", filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if path: self.entry_audio_target.delete(0, "end"); self.entry_audio_target.insert(0, path)

    def _choose_audio_out(self):
        d = filedialog.askdirectory(title="Choose output folder")
        if d: self.entry_audio_out.delete(0, "end"); self.entry_audio_out.insert(0, d)

    def _install_logging_redirect(self):
        self._orig_stdout = sys.stdout; self._orig_stderr = sys.stderr
        sys.stdout = LogRedirector(self.log_q); sys.stderr = LogRedirector(self.log_q)

    def _restore_logging(self):
        sys.stdout = self._orig_stdout; sys.stderr = self._orig_stderr

    def _drain_log_queue(self):
        try:
            while True:
                s = self.log_q.get_nowait()
                self.txt_log.insert("end", s); self.txt_log.see("end")
        except queue.Empty:
            pass
        self.after(100, self._drain_log_queue)

    # ----- per-tab worker helpers for YT tabs -----
    def _start_worker(self, key: str, target, *args, **kwargs):
        if key in self._workers and self._workers[key].is_alive():
            messagebox.showwarning("Busy", f"A task for '{key}' is already running."); return
        stop_event = threading.Event()
        self._stops[key] = stop_event
        def wrapper():
            try: target(stop_event, *args, **kwargs)
            except Exception as e: print(f"\n[{key}] [ERROR] {e}\n")
            finally: print(f"\n[{key}] [Task finished]\n")
        th = threading.Thread(target=wrapper, daemon=True); self._workers[key] = th; th.start()

    def _stop(self, key: str):
        ev = self._stops.get(key)
        if ev: ev.set(); print(f"[{key}] Stop requested (will stop between items).")
        else: print(f"[{key}] No running task.")

    # ----- actions for YT tabs -----
    def on_fetch_urls(self):
        if not ensure_yt_dlp(): return
        mode = self.url_mode.get()
        url = self.entry_url.get().strip()
        out_dir = self.entry_out.get().strip()
        if not url or not out_dir:
            messagebox.showwarning("Missing info", "Please provide URL and output folder."); return
        def job(stop_event: threading.Event):
            tag = "urls"
            print(f"\n[{tag}] === Fetch URLs ({mode}) ===")
            urls = fetch_playlist_urls(url) if mode == "playlist" else fetch_channel_urls(url)
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
            messagebox.showwarning("Missing path", "Please choose a path (file/URL or folder/glob)."); return
        langs = []
        if self.var_vi.get(): langs.append("vi")
        if self.var_en.get(): langs.append("en")
        if not langs: langs = ["vi","en"]
        as_srt = self.var_srt.get(); restrict = self.var_restrict.get(); overwrite = self.var_overwrite.get()
        also_video = self.var_also_video.get(); maxsize = self.entry_maxsize.get().strip() or None
        impersonate = self.combo_imp.get().strip() or None; quiet_warns = self.var_nowarn.get()

        def job_single(stop_event: threading.Event):
            tag = "subs"
            if re.match(r"^https?://", path, re.I):
                outdir = filedialog.askdirectory(title="Choose output folder for this URL")
                if not outdir: print(f"[{tag}] [Abort] No output folder chosen."); return
                ydl_opts = build_subs_opts(Path(outdir), langs, overwrite, restrict, as_srt, also_video, impersonate, maxsize, quiet_warns, tag)
                print(f"[{tag}] Output folder : {outdir}")
                with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([path])
                return
            p = Path(path)
            if not p.exists(): print(f"[{tag}] [ERR] Path not found: {path}"); return
            with p.open("r", encoding="utf-8", errors="ignore") as f: raw_urls = [ln.strip() for ln in f if ln.strip()]
            outdir = p.parent
            ydl_opts = build_subs_opts(outdir, langs, overwrite, restrict, as_srt, also_video, impersonate, maxsize, quiet_warns, tag)
            print(f"[{tag}] Output folder : {outdir}")
            print(f"[{tag}] Total URLs    : {len(raw_urls)}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download(raw_urls)

        def job_scan(stop_event: threading.Event):
            tag = "subs"
            files = find_url_files(path)
            if not files: print(f"[{tag}] [ERR] No url_yt.txt found for: {path}"); return
            print(f"[{tag}] [INFO] Found {len(files)} file(s) to process.")
            for i, url_file in enumerate(files, 1):
                if stop_event.is_set(): print(f"[{tag}] Stop requested; exiting loop."); break
                try:
                    with url_file.open("r", encoding="utf-8", errors="ignore") as f:
                        raw_urls = [ln.strip() for ln in f if ln.strip()]
                    outdir = url_file.parent
                    ydl_opts = build_subs_opts(outdir, langs, overwrite, restrict, as_srt, also_video, impersonate, maxsize, quiet_warns, tag)
                    print("\n" + "="*80)
                    print(f"[{tag}] [{i}/{len(files)}] File : {url_file}")
                    print(f"[{tag}] Out : {outdir}")
                    print(f"[{tag}] URLs: {len(raw_urls)}")
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download(raw_urls)
                except Exception as e:
                    print(f"[{tag}] [ERR] {e}")
            print(f"\n[{tag}] [ALL DONE] Processed files.")

        if mode == "single": self._start_worker("subs", job_single)
        else: self._start_worker("subs", job_scan)

    def on_list_formats(self):
        if not ensure_yt_dlp(): return
        target = self.entry_audio_target.get().strip()
        if not target: messagebox.showwarning("Missing target", "Please provide a URL or a text file of URLs."); return
        urls = read_lines_maybe_file(target)
        if not urls: messagebox.showwarning("No URLs", "No URLs were found."); return
        out_dir = self.entry_audio_out.get().strip() or "."
        base_opts = build_audio_base_opts(
            out_dir=out_dir, codec=self.combo_codec.get(), quality=self.combo_q.get(),
            allow_playlist=self.var_allow_pl.get(), overwrite=self.var_overwrite_a.get(),
            quiet=self.var_quiet.get(), ffmpeg_path=None, keepvideo=self.var_keepvideo.get(),
            force_inet4=self.var_inet4.get(), cookies_from_browser=(self.combo_cookies.get() or None),
            proxy=(self.entry_proxy.get().strip() or None), throttled_rate=(self.entry_throttle.get().strip() or None),
            username=(self.entry_user.get().strip() or None), password=(self.entry_pass.get().strip() or None),
            twofactor=(self.entry_2fa.get().strip() or None),
        )
        def job(stop_event: threading.Event):
            try: list_formats_for_url(urls[0], base_opts, tag="audio")
            except Exception as e:
                print("[audio] Failed to list formats:", e)
                print("[audio] Tip: Update yt-dlp nightly: python -m pip install -U --pre yt-dlp")
        self._start_worker("audio_list", job)

    def on_download_audio(self):
        if not ensure_yt_dlp(): return
        target = self.entry_audio_target.get().strip()
        out_dir = self.entry_audio_out.get().strip() or "."
        if not target or not out_dir:
            messagebox.showwarning("Missing info", "Please provide target and output folder."); return

        urls = read_lines_maybe_file(target); ensure_folder(out_dir)
        base_opts = build_audio_base_opts(
            out_dir=out_dir, codec=self.combo_codec.get(), quality=self.combo_q.get(),
            allow_playlist=self.var_allow_pl.get(), overwrite=self.var_overwrite_a.get(),
            quiet=self.var_quiet.get(), ffmpeg_path=None, keepvideo=self.var_keepvideo.get(),
            force_inet4=self.var_inet4.get(), cookies_from_browser=(self.combo_cookies.get() or None),
            proxy=(self.entry_proxy.get().strip() or None), throttled_rate=(self.entry_throttle.get().strip() or None),
            username=(self.entry_user.get().strip() or None), password=(self.entry_pass.get().strip() or None),
            twofactor=(self.entry_2fa.get().strip() or None),
        )

        # Prefer audio-only if available, then bestaudio, then best
        formats = [
            "bestaudio[ext=m4a]/m4a/bestaudio[ext=mp3]/mp3/bestaudio",
            "bestaudio/best",
        ]
        simulate = False
        overwrite = self.var_overwrite_a.get()

        def job(stop_event: threading.Event):
            tag = "audio"
            for i, url in enumerate(urls, 1):
                if stop_event.is_set():
                    print(f"[{tag}] Stop requested; exiting loop.")
                    break
                print(f"\n[{tag}] ({i}/{len(urls)}) → {url}")
                ok, err = download_audio_one(url, base_opts, formats, simulate, overwrite, tag)
                if not ok and err:
                    print(f"[{tag}] ERROR: {err}")
            print(f"\n[{tag}] [ALL DONE]")
        self._start_worker("audio", job)

# ============================================================================
# Entry point
# ============================================================================
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

def main():
    root = tk.Tk()
    root.title(APP_TITLE)
    # Optional icon if present
    for ico in ("./nct_logo.ico", "./nct_logo.png"):
        try:
            if Path(ico).exists():
                if ico.endswith(".ico"):
                    root.iconbitmap(ico)
                else:
                    # PNG fallback on some platforms
                    try:
                        from PIL import Image, ImageTk  # optional
                        img = Image.open(ico)
                        root.iconphoto(True, ImageTk.PhotoImage(img))
                    except Exception:
                        pass
        except Exception:
            pass
    try:
        root.geometry(DEFAULT_GEOMETRY)
    except Exception:
        pass
    root.resizable(True, True)

    app = App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
