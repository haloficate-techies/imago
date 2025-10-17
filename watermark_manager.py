"""
Watermark composition utilities for thumbnails.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFont


@dataclass
class WatermarkSettings:
    kind: str  # "none", "text", "image"
    opacity: int = 50  # 0-100
    position: str = "center"

    # Text specific
    text: str = ""
    font_path: Optional[Path] = None
    font_size: int = 48
    color: str = "#FFFFFF"

    # Image specific
    image_path: Optional[Path] = None
    scale: float = 0.3  # relative scale to base image width


class WatermarkManager:
    """Applies image or text watermarks on top of PIL images."""

    POSITIONS = {
        "top-left": (0.05, 0.05),
        "top-right": (0.95, 0.05),
        "center": (0.5, 0.5),
        "bottom-left": (0.05, 0.95),
        "bottom-right": (0.95, 0.95),
    }

    def apply(self, base_image: Image.Image, settings: WatermarkSettings) -> Image.Image:
        if settings.kind == "none":
            return base_image

        if settings.opacity <= 0:
            return base_image

        watermark_layer = Image.new("RGBA", base_image.size, (0, 0, 0, 0))

        if settings.kind == "text":
            overlay = self._create_text_watermark(base_image.size, settings)
        elif settings.kind == "image":
            overlay = self._create_image_watermark(base_image.size, settings)
        else:
            return base_image

        if overlay is None:
            return base_image

        watermark_layer.alpha_composite(overlay)

        combined = Image.alpha_composite(
            base_image.convert("RGBA"),
            watermark_layer,
        )
        return combined.convert("RGB")

    def _create_text_watermark(
        self, base_size: Tuple[int, int], settings: WatermarkSettings
    ) -> Optional[Image.Image]:
        if not settings.text.strip():
            return None

        overlay = Image.new("RGBA", base_size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        font = self._load_font(settings)
        text = settings.text.strip()
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        center = self._resolve_center(base_size, (text_width, text_height), settings)
        center = self._constrain_center(center, base_size, (text_width, text_height))

        color = self._resolve_color(settings.color)
        opacity = max(0, min(settings.opacity, 100))
        rgba_color = (*color, int(255 * (opacity / 100.0)))

        draw.text(center, text, fill=rgba_color, font=font, anchor="mm")
        return overlay

    def _create_image_watermark(
        self, base_size: Tuple[int, int], settings: WatermarkSettings
    ) -> Optional[Image.Image]:
        if not settings.image_path or not Path(settings.image_path).exists():
            return None

        overlay = Image.new("RGBA", base_size, (0, 0, 0, 0))
        watermark = Image.open(settings.image_path).convert("RGBA")

        target_width = int(base_size[0] * max(0.05, min(settings.scale, 1.0)))
        if target_width <= 0:
            return None

        scale_factor = target_width / watermark.width
        new_size = (
            max(1, int(watermark.width * scale_factor)),
            max(1, int(watermark.height * scale_factor)),
        )
        watermark = watermark.resize(new_size, Image.Resampling.LANCZOS)

        opacity = max(0, min(settings.opacity, 100))
        if opacity < 100:
            alpha = watermark.getchannel("A")
            alpha = ImageEnhance.Brightness(alpha).enhance(opacity / 100.0)
            watermark.putalpha(alpha)

        center = self._resolve_center(base_size, watermark.size, settings)
        center = self._constrain_center(center, base_size, watermark.size)
        top_left = (center[0] - watermark.width // 2, center[1] - watermark.height // 2)

        overlay.alpha_composite(watermark, dest=top_left)
        return overlay

    @staticmethod
    def _resolve_color(color: str) -> Tuple[int, int, int]:
        try:
            return ImageColor.getrgb(color)
        except ValueError:
            return 255, 255, 255

    def _load_font(self, settings: WatermarkSettings) -> ImageFont.FreeTypeFont:
        if settings.font_path and Path(settings.font_path).exists():
            try:
                return ImageFont.truetype(
                    str(settings.font_path), size=max(8, settings.font_size)
                )
            except OSError:
                pass
        size = max(8, settings.font_size)
        for candidate in ("DejaVuSans.ttf", "arial.ttf"):
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue
        return ImageFont.load_default()

    def _resolve_center(
        self,
        base_size: Tuple[int, int],
        overlay_size: Tuple[int, int],
        settings: WatermarkSettings,
    ) -> Tuple[int, int]:
        pivot = self.POSITIONS.get(settings.position, self.POSITIONS["center"])
        x = int(base_size[0] * pivot[0])
        y = int(base_size[1] * pivot[1])

        # Anchor the overlay at its center so positioning feels natural.
        return x, y

    @staticmethod
    def _constrain_center(
        center: Tuple[int, int],
        base_size: Tuple[int, int],
        overlay_size: Tuple[int, int],
        margin: int = 16,
    ) -> Tuple[int, int]:
        base_w, base_h = base_size
        overlay_w, overlay_h = overlay_size

        half_w = overlay_w / 2
        half_h = overlay_h / 2

        min_x = margin + half_w
        max_x = base_w - margin - half_w
        min_y = margin + half_h
        max_y = base_h - margin - half_h

        if min_x > max_x:
            min_x = max_x = base_w / 2
        if min_y > max_y:
            min_y = max_y = base_h / 2

        constrained_x = int(max(min(center[0], max_x), min_x))
        constrained_y = int(max(min(center[1], max_y), min_y))
        return constrained_x, constrained_y
