# 1_get_url_yt_input_pl.py
import yt_dlp
import argparse
import os
import shutil
from datetime import datetime

DEFAULT_PL = "https://www.youtube.com/playlist?list=PLTUVTlI0NHrnNI0tvdzAlbYpHC4o5vxOM"
FILENAME = "url_yt.txt"

def read_existing_lines(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        # Giữ nguyên thứ tự cũ, bỏ dòng trống và strip
        lines = [ln.strip() for ln in f.readlines()]
        return [ln for ln in lines if ln]

def backup_file(path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    root, ext = os.path.splitext(path)
    backup_path = f"{root}_{ts}.bak{ext or '.txt'}"
    shutil.copyfile(path, backup_path)
    return backup_path

def fetch_playlist_urls(playlist_url):
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

def main():
    parser = argparse.ArgumentParser(description="Extract YouTube video URLs from a playlist and update url_yt.txt by prepending new URLs.")
    parser.add_argument("-p", "--playlist", help="YouTube playlist URL", default=None)
    parser.add_argument("-i", "--output", required=True, help="Output folder to save url_yt.txt")
    args = parser.parse_args()

    output_folder = os.path.abspath(args.output)
    os.makedirs(output_folder, exist_ok=True)
    output_file = os.path.join(output_folder, FILENAME)

    playlist_url = args.playlist
    if not playlist_url:
        # fallback tương thích phiên bản cũ
        playlist_url = input("Enter YouTube playlist URL (or press Enter for default): ").strip() or DEFAULT_PL

    # Lấy danh sách URL mới từ playlist
    fetched_urls = fetch_playlist_urls(playlist_url)

    # Đọc file hiện có (nếu có), rồi xác định URL mới (chưa có trong file)
    existing_lines = read_existing_lines(output_file)
    existing_set = set(existing_lines)

    # Giữ thứ tự như yt-dlp trả về, chỉ lấy URL chưa có
    new_urls = [u.strip() for u in fetched_urls if u.strip() and u.strip() not in existing_set]

    # Nếu file đã tồn tại → backup trước khi ghi
    backup_path = None
    if os.path.exists(output_file):
        backup_path = backup_file(output_file)

    # Ghi: URL mới ở trên cùng, sau đó là các dòng cũ
    with open(output_file, "w", encoding="utf-8") as f:
        for u in new_urls:
            f.write(u + "\n")
        for ln in existing_lines:
            f.write(ln + "\n")

    print(f"✅ Fetched: {len(fetched_urls)} URLs from playlist")
    print(f"🆕 New URLs prepended: {len(new_urls)}")
    print(f"📝 Output file: {output_file}")
    if backup_path:
        print(f"🗂️ Backup created: {backup_path}")

if __name__ == "__main__":
    main()
