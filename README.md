# 🐅📺 Macan Video Player

Macan Video Player is a modern video player based on PyQt6 + FFmpeg 7.1.1 (LGPL) with a premium, lightweight, and feature-rich interface.
It supports a wide range of video/audio formats without additional codecs and is designed with a focus on a modern UI/UX.
---
## Screenshot 📸
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

# 📌 **Changelog Macan Video Player v2.0.0 – 2025-08-18**

### **Added**

* **Custom Theme Support** 🎨
Users can choose a theme according to their preference (Dark, Light, Neon Blue, Dark Blue, Soft Pink).
* **Smart Resume** 🕒
Videos automatically resume from where they left off.
* **Watch History** 📜
Watch history is automatically saved in a `.json` file and appears in the playlist.
* Mini Window Mode (Always on Top) 📺
Watch videos in a small window that always stays on top of other apps.
* Drag & Drop Support 📂
Videos can be opened directly by dragging files into the app.

### Improved

* UI Themes Engine 🔧
Smoother and more consistent theme switching, powered by QSS + JSON.
* Fullscreen & Windowed Auto Hide 🖥️
The navigation bar automatically hides and can be reappeared by clicking/reappearing the space bar.
* Subtitle & Lyrics Handling 📝
`.srt` subtitles and embedded subtitles are displayed more neatly and stably.
* Performance Optimization ⚡
Smoother playback with hardware acceleration (GPU/OpenGL) support.

### **Fixed**

* **Video Size Handling** 🔲
Video adjusts to window size, no longer forced to the original size.
* **Cursor Auto Hide** 🖱️
The cursor automatically hides when fullscreen, reappearing during interaction.
* **Duration Display** ⏱️
The total video duration is now displayed validly and accurately.
* **Drag & Drop Stability** 📂
More stable performance when opening large videos via drag & drop.

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
