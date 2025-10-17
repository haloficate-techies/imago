"""
High-level thumbnail generation logic for both single and grid modes.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PIL import Image

from video_processor import VideoInfo, VideoProcessor
from watermark_manager import WatermarkManager, WatermarkSettings

ProgressCallback = Optional[Callable[[int], None]]


@dataclass
class ThumbnailSettings:
    mode: str  # "single" or "grid"
    timestamp: float = 0.0
    rows: int = 2
    columns: int = 3
    randomize: bool = False
    random_seed: Optional[int] = None
    output_path: Path = Path("thumbnail.jpg")
    output_format: str = "jpg"  # "jpg" or "png"


class ThumbnailGenerator:
    """Coordinates frame extraction, grid assembly, watermarking, and saving."""

    def __init__(self, video_path: Path) -> None:
        self.video_path = Path(video_path)
        self.video_processor = VideoProcessor(self.video_path)
        self.watermark_manager = WatermarkManager()

    def get_video_info(self) -> VideoInfo:
        return self.video_processor.get_video_info()

    def generate(
        self,
        thumbnail_settings: ThumbnailSettings,
        watermark_settings: WatermarkSettings,
        progress_callback: ProgressCallback = None,
    ) -> Tuple[Path, Image.Image]:
        watermarked = self.render_image(
            thumbnail_settings,
            watermark_settings,
            progress_callback=progress_callback,
        )

        output_path = self._ensure_output_path(thumbnail_settings)
        pil_format = self._resolve_format(thumbnail_settings.output_format)
        watermarked.save(str(output_path), format=pil_format)

        if progress_callback:
            progress_callback(100)

        return output_path, watermarked

    def render_image(
        self,
        thumbnail_settings: ThumbnailSettings,
        watermark_settings: WatermarkSettings,
        progress_callback: ProgressCallback = None,
    ) -> Image.Image:
        if thumbnail_settings.mode == "single":
            base_image = self._generate_single(thumbnail_settings, progress_callback)
        elif thumbnail_settings.mode == "grid":
            base_image = self._generate_grid(thumbnail_settings, progress_callback)
        else:
            raise ValueError(f"Unsupported mode: {thumbnail_settings.mode}")

        if progress_callback:
            progress_callback(80)

        watermarked = self.watermark_manager.apply(base_image, watermark_settings)
        if progress_callback:
            progress_callback(90)

        return watermarked

    def _generate_single(
        self,
        settings: ThumbnailSettings,
        progress_callback: ProgressCallback,
    ) -> Image.Image:
        frame = self.video_processor.extract_frame(settings.timestamp)
        if progress_callback:
            progress_callback(60)
        return frame.convert("RGB")

    def _generate_grid(
        self,
        settings: ThumbnailSettings,
        progress_callback: ProgressCallback,
    ) -> Image.Image:
        rows = max(1, settings.rows)
        cols = max(1, settings.columns)
        frame_count = rows * cols

        def frame_progress(percent: int) -> None:
            if progress_callback:
                progress_callback(int(percent * 0.6))

        if settings.randomize:
            frames = self.video_processor.extract_frames_random(
                frame_count,
                seed=settings.random_seed,
                progress_callback=frame_progress,
            )
        else:
            frames = self.video_processor.extract_frames_evenly(
                frame_count, progress_callback=frame_progress
            )

        if not frames:
            raise RuntimeError("Failed to extract frames for grid thumbnail.")

        grid = self._compose_grid(frames, rows, cols)
        if progress_callback:
            progress_callback(70)
        return grid.convert("RGB")

    @staticmethod
    def _compose_grid(frames: List[Image.Image], rows: int, cols: int) -> Image.Image:
        first = frames[0]
        frame_width, frame_height = first.size

        grid_width = frame_width * cols
        grid_height = frame_height * rows

        grid_image = Image.new("RGB", (grid_width, grid_height))

        for index, frame in enumerate(frames):
            r = index // cols
            c = index % cols
            if r >= rows:
                break
            resized = frame.resize((frame_width, frame_height), Image.Resampling.LANCZOS)
            top_left = (c * frame_width, r * frame_height)
            grid_image.paste(resized, top_left)

        return grid_image

    @staticmethod
    def _ensure_output_path(settings: ThumbnailSettings) -> Path:
        output_path = Path(settings.output_path)
        if not output_path.suffix:
            output_path = output_path.with_suffix(f".{settings.output_format.lower()}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        return output_path

    @staticmethod
    def _resolve_format(output_format: str) -> str:
        normalized = (output_format or "").strip().lower()
        mapping = {
            "jpg": "JPEG",
            "jpeg": "JPEG",
            "png": "PNG",
        }
        return mapping.get(normalized, normalized.upper() or "PNG")
