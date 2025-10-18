#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
download_subs_v3.py
-------------------
v3.2 updates:
- --scan <path-or-glob>: find many url_yt.txt files (e.g., "E:\\phathoc\\*\\url_yt.txt" or a root folder)
  and process each. Subtitles are saved **in the same folder** as its url_yt.txt.
- Keeps previous features: skip-if-exists (default), --force-overwrite, --srt, --also-video, --impersonate, --no-warn.

Examples:
    # 1) Scan with a glob:
    python download_subs_v3.py --scan "E:\\phathoc\\*\\url_yt.txt" -vi

    # 2) Scan a root directory recursively (finds all 'url_yt.txt'):
    python download_subs_v3.py --scan "E:\\phathoc" -vi -en

    # 3) Old single-file / single-URL modes still work:
    python download_subs_v3.py --file "E:\\some\\url_yt.txt" -vi
    python download_subs_v3.py -vi https://www.youtube.com/watch?v=UyqlT52hIO8
"""
from __future__ import annotations

import sys
import argparse
import warnings
import glob as _glob
from pathlib import Path
from typing import List, Dict, Any

try:
    from yt_dlp import YoutubeDL
except Exception:
    print("ERROR: yt-dlp is required. Install with: pip install -U yt-dlp")
    raise


VERSION = "3.2"


def read_urls_from_file(path: Path) -> List[str]:
    """Read non-empty, non-comment lines as URLs from a text file."""
    urls: List[str] = []
    if not path or not path.exists():
        return urls

    tried_encodings = ["utf-8", "utf-8-sig", "cp1258", "cp1252"]
    content = None
    for enc in tried_encodings:
        try:
            content = path.read_text(encoding=enc)
            break
        except Exception:
            continue
    if content is None:
        content = path.read_bytes().decode("utf-8", errors="ignore")

    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        # skip comments
        if line.startswith("#") or line.startswith("//") or line.lower().startswith("rem "):
            continue
        urls.append(line)
    return urls


def find_url_files(spec: str) -> List[Path]:
    """
    Resolve --scan argument:
    - If spec contains wildcard (*?[), treat as glob and return matches (files).
    - If spec is a directory, rglob('url_yt.txt').
    - If spec is an existing file, return [spec].
    """
    matches: List[Path] = []
    has_wildcard = any(ch in spec for ch in "*?[")
    p = Path(spec)

    if has_wildcard:
        for m in _glob.glob(spec, recursive=True):
            mp = Path(m)
            if mp.is_file():
                matches.append(mp)
        return sorted(set(matches))

    if p.is_dir():
        return sorted(p.rglob("url_yt.txt"))
    if p.is_file():
        return [p]
    # If not exist, try parent dir glob fallback
    base = p.parent if p.parent.exists() else Path(".")
    return sorted(base.rglob("url_yt.txt"))


class _QuietWarnLogger:
    """Custom logger that suppresses info/warning but keeps errors."""
    def debug(self, msg):
        pass
    def info(self, msg):
        pass
    def warning(self, msg):
        pass
    def error(self, msg):
        try:
            sys.stderr.write(str(msg) + "\n")
        except Exception:
            pass


def build_ydl_opts(
    outdir: Path,
    langs: List[str],
    force_overwrite: bool,
    restrict: bool,
    as_srt: bool,
    also_video: bool,
    impersonate: str | None,
    max_filesize: str | None,
    no_warn: bool,
) -> Dict[str, Any]:
    """Build yt-dlp options based on CLI arguments."""
    ydl_opts: Dict[str, Any] = {
        "ignoreerrors": True,
        "continuedl": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "skip_download": not also_video,
        "subtitleslangs": langs,
        # Save INTO outdir
        "outtmpl": str(outdir / "%(title).200B [%(id)s] - %(upload_date>%Y-%m-%d)s.%(ext)s"),
        "quiet": False,
        "noprogress": False,
    }

    ydl_opts["subtitlesformat"] = "srt" if as_srt else "vtt"

    if not force_overwrite:
        ydl_opts["nooverwrites"] = True

    if restrict:
        ydl_opts["restrictfilenames"] = True

    if impersonate:
        ydl_opts["impersonate"] = impersonate

    if also_video:
        ydl_opts["format"] = "bv*+ba/best"
        ydl_opts["merge_output_format"] = "mp4"
        ydl_opts["paths"] = {"home": str(outdir)}
        if max_filesize:
            ydl_opts["max_filesize"] = max_filesize

    if no_warn:
        warnings.filterwarnings("ignore")
        ydl_opts["no_warnings"] = True
        ydl_opts["logger"] = _QuietWarnLogger()

    def _hook(d: Dict[str, Any]):
        status = d.get("status")
        if status == "finished":
            info = d.get("info_dict", {})
            fn = d.get("filename") or info.get("filepath") or info.get("requested_downloads", [{}])[0].get("filepath")
            if fn:
                print(f"[OK] Saved: {fn}")
        elif status == "error":
            print("[ERR] Download error")

    ydl_opts["progress_hooks"] = [_hook]
    return ydl_opts


def process_one_urlfile(url_file: Path, langs: List[str], args):
    """Process a single url_yt.txt file and save outputs to its parent folder."""
    urls = read_urls_from_file(url_file)
    outdir = url_file.parent  # save in the same folder
    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"[ERR] Cannot create folder: {outdir} -> {e}")
        return

    # De-duplicate urls
    seen = set()
    unique_urls = [u for u in urls if not (u in seen or seen.add(u))]

    print("\n" + "=" * 80)
    print(f"[SCAN] File : {url_file}")
    print(f"[SCAN] Out  : {outdir}")
    print(f"[SCAN] Lang : {langs} | Save as {'.srt' if args.srt else '.vtt'}")
    print(f"[SCAN] URLs : {len(unique_urls)}")
    print("=" * 80)

    if not unique_urls:
        print("[WARN] No URLs in this file. Skipped.")
        return

    ydl_opts = build_ydl_opts(
        outdir=outdir,
        langs=langs,
        force_overwrite=args.force_overwrite,
        restrict=args.restrict,
        as_srt=args.srt,
        also_video=args.also_video,
        impersonate=args.impersonate,
        max_filesize=args.max_filesize,
        no_warn=args.no_warn,
    )

    with YoutubeDL(ydl_opts) as ydl:
        ydl.download(unique_urls)


def main():
    parser = argparse.ArgumentParser(
        description=f"Download YouTube subtitles (and optionally MP4 video). v{VERSION}"
    )
    parser.add_argument("url", nargs="?", help="A YouTube URL (video/playlist/channel). Optional if using --file/--scan.")
    parser.add_argument("-o", "--outdir", type=Path, default=Path("subs"), help="Output directory for single file/URL mode (default: ./subs)")
    parser.add_argument("--file", type=Path, default=Path("url_yt.txt"), help="A text file with one URL per line (single-file mode).")
    parser.add_argument("--scan", type=str, help="Scan for many url_yt.txt files. Accepts a directory or a glob like \"E:\\\\phathoc\\\\*\\\\url_yt.txt\".")
    parser.add_argument("-vi", action="store_true", help="Download Vietnamese subtitles")
    parser.add_argument("-en", action="store_true", help="Download English subtitles")
    parser.add_argument("--srt", action="store_true", help="Save subtitles as .srt (default .vtt)")
    parser.add_argument("--restrict", action="store_true", help="Use restricted filenames")
    parser.add_argument("--force-overwrite", action="store_true", help="Force overwrite existing files")
    parser.add_argument("--also-video", action="store_true", help="Also download the video and merge to MP4 (needs ffmpeg)")
    parser.add_argument("--impersonate", type=str.lower, choices=["chrome", "edge", "safari", "ios", "android", "msie", "firefox"], help="Browser impersonation (yt-dlp feature)")
    parser.add_argument("--max-filesize", type=str, help='Max video size with --also-video, e.g., "200M" or "1G"')
    parser.add_argument("--no-warn", action="store_true", help="Disable warnings from Python & yt-dlp (keep errors)")

    args = parser.parse_args()

    # Languages
    langs: List[str] = []
    if args.vi:
        langs.append("vi")
    if args.en:
        langs.append("en")
    if not langs:
        langs = ["vi", "en"]

    # SCAN MODE
    if args.scan:
        files = find_url_files(args.scan)
        if not files:
            print(f"[ERR] No url_yt.txt files found for: {args.scan}")
            sys.exit(1)

        print(f"[INFO] Found {len(files)} file(s) to process.")
        for f in files:
            process_one_urlfile(f, langs, args)

        print("\n[ALL DONE] Processed all discovered url_yt.txt files.")
        return

    # SINGLE FILE / URL MODE (original behavior)
    urls: List[str] = []
    if args.url:
        urls.append(args.url)
    file_urls = read_urls_from_file(args.file)
    if file_urls:
        urls.extend(file_urls)

    if not urls:
        print("No URL provided and no valid URL file found.")
        print("Tip: pass a URL, or create url_yt.txt, or use --file <path>, or use --scan to process many.")
        parser.print_help()
        sys.exit(1)

    outdir: Path = args.outdir
    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"ERROR: Cannot create output directory: {outdir}\n{e}")
        sys.exit(2)

    # De-duplicate while preserving order
    seen = set()
    unique_urls: List[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    print(f"Output folder : {outdir}")
    print(f"Subtitle langs: {langs}")
    print(f"Save as       : {'.srt' if args.srt else '.vtt'}")
    print(f"Also video    : {'Yes (MP4)' if args.also_video else 'No (subs only)'}")
    print(f"Overwrite     : {'Force overwrite' if args.force_overwrite else 'Skip if exists'}")
    print(f"Warnings      : {'Disabled' if args.no_warn else 'Normal'}")
    print(f"Total URLs    : {len(unique_urls)}")
    if args.file and args.file.exists():
        print(f"URL file      : {args.file} (found {len(file_urls)} lines)")
    if args.impersonate:
        print(f"Impersonate   : {args.impersonate}")

    ydl_opts = build_ydl_opts(
        outdir=outdir,
        langs=langs,
        force_overwrite=args.force_overwrite,
        restrict=args.restrict,
        as_srt=args.srt,
        also_video=args.also_video,
        impersonate=args.impersonate,
        max_filesize=args.max_filesize,
        no_warn=args.no_warn,
    )

    with YoutubeDL(ydl_opts) as ydl:
        ydl.download(unique_urls)

    print(f"Done. Files saved under: {outdir}")


if __name__ == "__main__":
    main()
