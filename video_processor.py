"""
Video processing utilities for extracting frames and metadata from videos.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from moviepy.video.io.VideoFileClip import VideoFileClip
from PIL import Image


@dataclass
class VideoInfo:
    """Container with the most relevant metadata we expose to the UI."""

    path: Path
    duration: float  # in seconds
    width: int
    height: int
    fps: float

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"


class VideoProcessor:
    """
    Handles loading video metadata and extracting frames. MoviePy handles the
    heavy lifting while keeping the interface friendlier for the rest of the app.
    """

    def __init__(self, video_path: Path) -> None:
        self.video_path = Path(video_path)
        if not self.video_path.exists():
            raise FileNotFoundError(f"Video file not found: {self.video_path}")

    def get_video_info(self) -> VideoInfo:
        with self._open_clip() as clip:
            return VideoInfo(
                path=self.video_path,
                duration=float(clip.duration or 0.0),
                width=int(clip.w),
                height=int(clip.h),
                fps=float(clip.fps or 0.0),
            )

    def extract_frame(self, timestamp: float) -> Image.Image:
        """Grab a single frame at a specific timestamp (seconds)."""
        with self._open_clip() as clip:
            timestamp = self._clamp_timestamp(timestamp, clip.duration or 0.0)
            frame = clip.get_frame(timestamp)
        return Image.fromarray(frame)

    def extract_frames_evenly(
        self,
        count: int,
        *,
        include_start_end: bool = False,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> List[Image.Image]:
        """
        Extract frames evenly spaced throughout the entire clip.

        include_start_end determines whether timestamps include the very start/end
        or only interior samples. Progress callback receives a percentage [0-100].
        """
        if count <= 0:
            return []

        with self._open_clip() as clip:
            duration = float(clip.duration or 0.0)
            timestamps = self._compute_even_timestamps(
                duration, count, include_start_end=include_start_end
            )
            frames = []
            for idx, ts in enumerate(timestamps, start=1):
                frame = clip.get_frame(ts)
                frames.append(Image.fromarray(frame))
                if progress_callback:
                    progress_callback(int(idx / count * 100))
        return frames

    def extract_frames_random(
        self,
        count: int,
        *,
        seed: Optional[int] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> List[Image.Image]:
        """
        Extract random frames from the clip. Useful for the optional random grid.
        """
        if count <= 0:
            return []

        rng = random.Random(seed) if seed is not None else random

        with self._open_clip() as clip:
            duration = float(clip.duration or 0.0)
            timestamps = sorted(rng.uniform(0.0, duration) for _ in range(count))
            frames = []
            for idx, ts in enumerate(timestamps, start=1):
                frame = clip.get_frame(ts)
                frames.append(Image.fromarray(frame))
                if progress_callback:
                    progress_callback(int(idx / count * 100))
        return frames

    def _open_clip(self) -> VideoFileClip:
        """
        MoviePy clips should be closed to release FFMPEG/reader resources.
        Using a context manager ensures that.
        """
        return VideoFileClip(str(self.video_path))

    @staticmethod
    def _clamp_timestamp(timestamp: float, duration: float) -> float:
        if duration <= 0.0:
            return 0.0
        return min(max(timestamp, 0.0), max(duration - 1e-3, 0.0))

    @staticmethod
    def _compute_even_timestamps(
        duration: float,
        count: int,
        *,
        include_start_end: bool,
    ) -> Iterable[float]:
        if duration <= 0.0 or count <= 0:
            return [0.0]

        if include_start_end:
            if count == 1:
                return [duration / 2.0]
            step = duration / (count - 1)
            return [min(idx * step, duration) for idx in range(count)]

        step = duration / (count + 1)
        return [min((idx + 1) * step, duration) for idx in range(count)]
