# PharmApp — Bộ công cụ Tải Phụ đề & Âm thanh YouTube (GUI)

Bộ công cụ gọn nhẹ giúp **thu thập link YouTube**, **tải phụ đề** (đa ngôn ngữ, VTT/SRT) và **tách MP3**, kèm **giao diện Tkinter** dễ dùng. Phù hợp tạo thư viện học tập (bài giảng, pháp thoại, audiobook) với tên file thống nhất, sạch sẽ.

> Repo: **PharmApp_YT_Sub_Audio_Toolkit_GUI** — Giấy phép: **CC0-1.0 (Public Domain)**.

## ✨ Thành phần

- **Thu thập URL**
  - `1_get_url_yt_input_pl_v1.py` — lấy URL từ **playlist** YouTube.
  - `1_get_yt_urls_input_channel.py` — lấy URL từ **channel** YouTube.

- **Tải phụ đề**
  - `download_subs_v4.py` — tải phụ đề hàng loạt (`.vtt`/`.srt`), chọn ngôn ngữ, bỏ qua file đã có.

- **Tách âm thanh**
  - `2_down_mp3_url_yt_v3.py` — tải bằng `yt-dlp` và chuyển sang **MP3** qua `ffmpeg`.

- **Giao diện GUI**
  - `YT_Sub_Audio_Toolkit_GUI_v1.py`, `YT_Sub_Audio_Toolkit_GUI_v2.py`
  - `YT_Toolkit_GUI_wrapper_v3.py`, `YT_Toolkit_GUI_wrapper_v4.py`  
  Chạy GUI để thao tác mà không cần nhớ lệnh.

## 🧱 Yêu cầu

- **Python** 3.10+ (đã thử trên Windows 10/11)
- **ffmpeg** có trong `PATH`
- **yt-dlp** (gói Python), khuyên dùng thêm `rich` để log đẹp

Cài gói cần thiết:
```bash
python -m pip install -U yt-dlp rich
```

> `tkinter` đi kèm hầu hết bản Python cho Windows. Nếu thiếu, cài Python từ python.org.

## 🚀 Bắt đầu nhanh

### 1) Dùng GUI (khuyến nghị)
```bash
python YT_Toolkit_GUI_wrapper_v4.py
```
- Chọn tác vụ: **lấy URL** → **tải phụ đề** → **tách MP3**.
- Làm theo hướng dẫn trên màn hình (ngôn ngữ, thư mục, chế độ ghi đè/bỏ qua).

### 2) Chạy từng bước qua CLI

**A. Lấy URL từ playlist**
```bash
python 1_get_url_yt_input_pl_v1.py
# Tạo file URL (vd: url_yt.txt), mỗi dòng một video.
```

**B. Tải phụ đề**
```bash
python download_subs_v4.py
# Chọn ngôn ngữ (vd: en/vi), trỏ đến url_yt.txt, chọn thư mục lưu, chế độ overwrite/skip.
```

**C. Tách MP3**
```bash
python 2_down_mp3_url_yt_v3.py
# Dùng url_yt.txt để tải hàng loạt file MP3.
```

## 📁 Gợi ý cấu trúc thư mục

```
YT_Sub_Audio_Toolkit/
├─ url_yt.txt
├─ subtitles/      # .vtt / .srt
└─ audio/          # .mp3
```

Mẫu đặt tên thường gặp:
```
<Tên> [<YouTubeID>] - <YYYY-MM-DD>.mp3
<Tên> [<YouTubeID>] - <YYYY-MM-DD>.<lang>.vtt
```

## 🧩 Mẹo & xử lý lỗi

- **Không thấy ffmpeg**: thêm vào PATH và mở terminal mới; kiểm tra `ffmpeg -version`.
- **Đường dẫn Windows**: dùng dấu ngoặc kép hoặc chuỗi raw:
  - `"E:\PhapThoai\url_yt.txt"` **hoặc** `r"E:\PhapThoai\url_yt.txt"`
- **Thiếu phụ đề**: không phải video nào cũng có phụ đề; thử mã ngôn ngữ khác (`en`, `vi`…).
- **Tốc độ chậm**: để `yt-dlp` tự retry; chỉ dùng VPN nếu bị bóp băng thông theo vùng.

## 🗺️ Lộ trình mở rộng

- Quét nhiều thư mục con có `url_yt.txt`
- Tải song song (giới hạn tốc độ hợp lý)
- Lưu cấu hình & theme cho GUI
- Xuất manifest (JSON/CSV) phục vụ tra cứu sau này

## ⚖️ Pháp lý

Vui lòng tôn trọng Điều khoản YouTube và bản quyền của tác giả. Chỉ sử dụng cho mục đích cá nhân/giáo dục nếu bạn không có quyền phân phối lại.

## 🤝 Đóng góp

Hoan nghênh PR/Issue — nhất là các cải tiến về path Unicode Windows và UX GUI.

## 📜 Giấy phép

**CC0-1.0** — Public Domain.
