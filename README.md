<div align="center">



# 🐅 Macan Video Player

**A modern, high-performance desktop video player built on PySide6.**  
Lightweight. Feature-rich. Designed for serious users.

[![Release](https://img.shields.io/github/v/release/danx123/macan-video-player?style=flat-square&color=2ea043)](https://github.com/danx123/macan-video-player/releases)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-blue?style=flat-square)](https://github.com/danx123/macan-video-player/releases)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/github/license/danx123/macan-video-player?style=flat-square)](LICENSE)

</div>

---

## Overview

Macan Video Player is a feature-complete desktop media player with a focus on performance, modern UI/UX, and developer extensibility. Built on the PySide6 framework, it supports a wide range of video and audio formats natively — no additional codec packs required.

The player is designed for users who demand precision and control: from fine-grained audio equalization to immersive VR 360° playback, every feature is built with a professional workflow in mind.

---

## Features

### Playback & Performance
- **Hardware Acceleration** — GPU-accelerated decoding via platform-native backends (DXVA2, VAAPI, VideoToolbox)
- **Force 60 FPS** — Frame interpolation engine that upscales any source framerate to 60 fps using adaptive blending
- **Smart Resume** — Automatically resumes playback from the last watched position per file
- **Variable Playback Speed** — Fine-grained speed control without audio pitch distortion
- **Stream Support** — Direct URL playback from YouTube, Twitch, and other platforms via `yt-dlp` integration

### Visual & Audio
- **Picture Settings** — Real-time adjustment of brightness, contrast, saturation, and gamma
- **Auto Enhanced Video** — One-click picture profile optimized for general content, with automatic restore on toggle-off
- **10-Band Audio Equalizer** — Parametric biquad EQ from 31 Hz to 16 kHz, with 10 built-in presets and custom preset management
- **VR 180°/360° Playback** — Immersive equirectangular projection with real-time pan, tilt, and zoom. Supports both 180° and 360° formats with cached remap maps for minimal per-frame overhead

### Subtitles
- **External Subtitle Support** — Load `.srt` and other external subtitle files
- **Embedded Subtitle Extraction** — Automatic extraction and rendering of subtitles embedded in MKV and other containers
- **Subtitle Customization** — Adjustable font size, color, and on-screen position

### Interface & Usability
- **Custom Themes** — Choose from Dark, Light, Neon Blue, Dark Blue, and Soft Pink
- **Mini Window Mode** — Always-on-top compact mode suitable for multitasking
- **Watch History** — Persistent playback history saved in structured JSON format
- **Playlist Support** — Built-in playlist panel with sequential and shuffle playback
- **Drag & Drop** — Open files by dragging directly onto the player window
- **Responsive Layout** — Video display automatically adapts to any window size and aspect ratio

---

## Screenshots
<img width="1365" height="767" alt="Screenshot 2026-03-09 213021" src="https://github.com/user-attachments/assets/014b6dee-6fdd-4009-897b-7210ac70785c" />

<img width="1365" height="767" alt="Screenshot 2026-03-09 212832" src="https://github.com/user-attachments/assets/ac5cb640-276c-4062-9cd8-c80884b6c427" />




---

## Getting Started

### Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | 3.10 or higher |
| pip | Latest recommended |

### Installation

**1. Clone the repository**
```bash
git clone https://github.com/danx123/macan-video-player.git
cd macan-video-player
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Run the player**
```bash
python macan_video_player.py
```

---

## Binary Releases

Pre-built binaries for Windows are available on the [Releases page](https://github.com/danx123/macan-video-player/releases). No Python installation required.

> **Note:** The source code available in this repository represents the base framework. The binary release on the official release page contains the complete, stable feature set.

---

## Nightly Builds

Nightly builds are experimental releases that include the latest features and fixes ahead of the next stable release. They are intended for developers and early testers.

- Nightly build binaries are published periodically alongside the corresponding source snapshot
- Features in nightly builds may be incomplete or subject to change before promotion to stable
- Bug reports and feedback on nightly builds are welcomed via the [Issues tracker](https://github.com/danx123/macan-video-player/issues)


---

## License

This project is licensed under the terms specified in the [LICENSE](LICENSE) file.

---

<div align="center">
  <sub>Built with PySide6 · Powered by Qt Multimedia · Macan Video Player</sub>
</div>
