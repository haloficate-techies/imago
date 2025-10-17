# Imago Thumbnail Generator

PyQt5 desktop application for crafting single or grid thumbnails from video files. The app supports watermarking, previewing, and exporting to JPEG or PNG, with builds targeting both Windows and macOS via PyInstaller.

## Features
- Select `.mp4`, `.mov`, `.avi`, or `.mkv` video files and display duration, resolution, and FPS metadata.
- Generate either a single-frame thumbnail (defaulting to the midpoint) or a grid thumbnail with configurable rows × columns.
- Evenly spaced or random frame sampling for grid thumbnails.
- Image or text watermarking with adjustable opacity, position, color, font, size, and optional logo scaling.
- Live progress bar with preview of the generated thumbnail.
- Save thumbnails as JPG or PNG to a custom location.
- Optional JSON export/import of user preferences (thumbnail + watermark settings).

## Getting Started

```bash
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # macOS / Linux
pip install -r requirements.txt
python main.py
```

MoviePy relies on FFmpeg. Ensure FFmpeg is installed and available on your `PATH` for best results.

## Packaging

The project is structured to work with PyInstaller. After installing requirements, run:

```bash
pyinstaller --onefile --noconsole main.py   # Windows build
pyinstaller --onefile --windowed main.py    # macOS build
```

The generated binary will be located under the `dist/` directory. When packaging for Windows, ensure FFmpeg DLLs are reachable or bundled as needed.

## File Overview

- `main.py` — PyQt5 GUI entry point and application logic.
- `video_processor.py` — Video metadata + frame extraction helpers built on MoviePy.
- `thumbnail_generator.py` — Thumbnail assembly for single/grid outputs.
- `watermark_manager.py` — Watermark rendering for text and image overlays.
- `settings_manager.py` — Optional JSON persistence for UI preferences.
- `requirements.txt` — Python dependencies.
