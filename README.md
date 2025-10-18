# PharmApp — YT Sub & Audio Toolkit (GUI)

A lightweight toolkit to **collect YouTube links**, **download subtitles** (multi-language, VTT/SRT), and **extract MP3 audio**, wrapped in a simple **Tkinter GUI**. Ideal for building study libraries (talks, lectures, audiobooks) with clean, consistent filenames.

> Repo: **PharmApp_YT_Sub_Audio_Toolkit_GUI** — License: **CC0-1.0 (Public Domain)**.

## ✨ What’s inside

- **URL collectors**
  - `1_get_url_yt_input_pl_v1.py` — fetch video URLs from a YouTube **playlist**.
  - `1_get_yt_urls_input_channel.py` — fetch video URLs from a YouTube **channel**.

- **Subtitle downloader**
  - `download_subs_v4.py` — batch-download subtitles (`.vtt`/`.srt`), choose languages, skip existing files.

- **Audio extractor**
  - `2_down_mp3_url_yt_v3.py` — download via `yt-dlp` and convert to **MP3** with `ffmpeg`.

- **GUI wrappers**
  - `YT_Sub_Audio_Toolkit_GUI_v1.py`, `YT_Sub_Audio_Toolkit_GUI_v2.py`
  - `YT_Toolkit_GUI_wrapper_v3.py`, `YT_Toolkit_GUI_wrapper_v4.py`  
  Launch a GUI to drive the tasks without memorizing CLI flags.

## 🧱 Requirements

- **Python** 3.10+ (tested on Windows 10/11)
- **ffmpeg** available on `PATH`
- **yt-dlp** (Python package); optional `rich` for pretty logs

Install:
```bash
python -m pip install -U yt-dlp rich
```

> `tkinter` ships with most Windows Python builds. If missing, install the standard Python from python.org.

## 🚀 Quick start

### 1) GUI (recommended)
```bash
python YT_Toolkit_GUI_wrapper_v4.py
```
- Pick a task: **collect URLs** → **download subtitles** → **extract MP3**.
- Follow on‑screen prompts (languages, output folder, overwrite/skip).

### 2) CLI flow

**A. Collect URLs from a playlist**
```bash
python 1_get_url_yt_input_pl_v1.py
# Produces `url_yt.txt` with one URL per line.
```

**B. Download subtitles**
```bash
python download_subs_v4.py
# Choose languages (e.g., en/vi), point to `url_yt.txt`, select output folder and overwrite/skip mode.
```

**C. Extract MP3**
```bash
python 2_down_mp3_url_yt_v3.py
# Use `url_yt.txt` to batch download MP3 files.
```

## 📁 Suggested layout

```
YT_Sub_Audio_Toolkit/
├─ url_yt.txt
├─ subtitles/      # .vtt / .srt
└─ audio/          # .mp3
```

Typical filename pattern:
```
<Title> [<YouTubeID>] - <YYYY-MM-DD>.mp3
<Title> [<YouTubeID>] - <YYYY-MM-DD>.<lang>.vtt
```

## 🧩 Tips & troubleshooting

- **ffmpeg not found**: add to PATH, open a new terminal; verify with `ffmpeg -version`.
- **Windows paths & Unicode**: wrap in quotes or use raw strings:
  - `"E:\My Folder\url_yt.txt"` **or** `r"E:\My Folder\url_yt.txt"`
- **Missing subtitles**: not every video offers every language; try `en`, `vi`, etc.
- **Slow downloads**: allow `yt-dlp` to retry; use VPN only if your region is throttled.

## 🗺️ Roadmap

- Multi-folder watch across nested `url_yt.txt`
- Parallel downloads with sensible rate-limits
- Theming + persistent GUI preferences
- Optional JSON/CSV manifest export

## ⚖️ Legal

Use responsibly. Respect YouTube’s Terms of Service and creators’ rights. Subtitles/audio are for personal/educational use unless you have permission to redistribute.

## 🤝 Contributing

PRs and issues are welcome — especially Windows Unicode path handling and GUI UX polish.

## 📜 License

**CC0-1.0** — Public Domain.
