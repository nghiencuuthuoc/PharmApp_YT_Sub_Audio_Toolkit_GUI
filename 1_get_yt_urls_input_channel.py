import yt_dlp
import argparse
import os

def get_video_urls(channel_url):
    ydl_opts = {
        "quiet": True,
        "extract_flat": True,  # Chỉ lấy metadata, không tải video
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Get all YouTube video URLs from a channel")
    parser.add_argument("-u", "--url", required=True, help="YouTube channel URL")
    parser.add_argument("-i", "--output", required=True, help="Output folder")
    args = parser.parse_args()

    output_folder = os.path.abspath(args.output)
    os.makedirs(output_folder, exist_ok=True)

    output_file = os.path.join(output_folder, "url_yt.txt")

    urls = get_video_urls(args.url)

    with open(output_file, "w", encoding="utf-8") as f:
        for url in urls:
            f.write(url + "\n")

    print(f"✅ Saved {len(urls)} URLs to {output_file}")
