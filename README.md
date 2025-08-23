# 🐅📺 Macan Video Player

Macan Video Player is a modern video player based on PyQt6, lightweight, and feature-rich interface.
It supports a wide range of video/audio formats without additional codecs and is designed with a focus on a modern UI/UX.
---
## Screenshot 📸
<img width="795" height="589" alt="Screenshot 2025-08-23 074854" src="https://github.com/user-attachments/assets/bbdbbdbf-ed43-4be2-8d03-7e5369585fb1" />

<img width="813" height="584" alt="image" src="https://github.com/user-attachments/assets/ba206671-4f92-4b11-84fe-965198a48fa0" />

<img width="322" height="429" alt="image" src="https://github.com/user-attachments/assets/033a9514-e568-456e-96b7-a6b5b8bb34ef" />

<img width="301" height="433" alt="image" src="https://github.com/user-attachments/assets/b9d00413-8823-4a38-b1d9-d19e78a69bbd" />


---

## ✨ Key Features
- 🎨 **Custom Themes** – Dark, Light, Neon Blue, Dark Blue, Soft Pink.
- 🕒 **Smart Resume** – resumes video from where you left off.
- 📜 **Watch History** – watch history is automatically saved in `.json`.
- 📺 **Mini Window Mode (Always on Top)** – suitable for multitasking.
- 📂 **Drag & Drop Support** – open videos by dragging files.
- 📝 **Subtitle & Lyrics** – supports `.srt` and embedded subtitles.
- ⚡ **Performance Optimization** – hardware acceleration via GPU/OpenGL.
- 🔲 **Responsive Video Size** – automatically adjusts to the window.
- 🌏 **Stream from various sites (YouTube, Twitch, etc.) using yt-dlp.

---

📝 Changelog — Macan Video Player
[3.0.0] — Major Release (2025-08-23)
🚀 Added
Thumbnail Preview Engine Rewritten
Migrated from FFmpeg → OpenCV for frame preview generation.
The result is faster, more responsive, and lighter, without the need to write temporary files to disk.
Supports instant previews when the slider is moved.
Theme System: Full theme support including Dark, Light, Neon Blue, Dark Blue, and Soft Pink with instant switching.
Smart Resume: The app remembers where you last watched a video and automatically resumes when the file is reopened.
JSON-based History & Playlist: Watch history is automatically saved, and playlists support drag and drop.
Enhanced Fullscreen & Windowed Mode: Auto-hide navigation bar, auto-hide cursor, and toggle with spacebar for more intuitive control.
🔧 Improved
UI Refactor: Navigation, title bar, and media controls are reorganized for a cleaner and more consistent experience.
Video Duration Accuracy: The total video duration is now displayed with more precise validation.
Subtitle (.srt) Engine: Improved parsing and synchronization, subtitles appear smoothly without glitches.
Streaming Support: Optimized integration with yt-dlp for streaming from various platforms.
Performance: Optimized video rendering and kept RAM consumption low even when opening multiple files.
🛠 Fixed
A bug with lyrics auto-scroll that previously caused the scrollbar to return to the top.
Fixed video resizing on first load to fit the window, not the native resolution.
Fixed a crash when dragging and dropping certain video files.

⚡ Note:
The source code shared is the base/mainframe. For a stable version with all the above features, use the binary release on the official release page.

---

## 🌙 Nightly Builds

In addition to the stable release, **Nightly Builds** will also be available.
Nightly builds are experimental versions that contain the latest features, bug fixes, or trials before they make it to the official release.
The source code for the nightly build will be **shared periodically** so developers and testers can try it out early.

---

## 🛠️ Build & Run
### Prerequisites
- Python 3.10+
- Library:
```bash
pip install -r requirements.txt
