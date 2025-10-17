"""
Simple JSON settings persistence.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Tuple

from thumbnail_generator import ThumbnailSettings
from watermark_manager import WatermarkSettings

DEFAULT_SETTINGS_PATH = Path("thumbnail_settings.json")


@dataclass
class PersistedSettings:
    thumbnail: ThumbnailSettings
    watermark: WatermarkSettings

    def to_dict(self) -> Dict[str, Any]:
        thumb_dict = asdict(self.thumbnail)
        thumb_dict["output_path"] = str(thumb_dict.get("output_path", ""))
        if thumb_dict.get("resize_to"):
            thumb_dict["resize_to"] = list(thumb_dict["resize_to"])

        water_dict = asdict(self.watermark)
        if water_dict.get("font_path"):
            water_dict["font_path"] = str(water_dict["font_path"])
        if water_dict.get("image_path"):
            water_dict["image_path"] = str(water_dict["image_path"])

        return {
            "thumbnail": thumb_dict,
            "watermark": water_dict,
        }

    @staticmethod
    def from_dict(payload: Dict[str, Any]) -> "PersistedSettings":
        thumb_data = payload.get("thumbnail", {})
        water_data = payload.get("watermark", {})
        return PersistedSettings(
            thumbnail=ThumbnailSettings(
                mode=thumb_data.get("mode", "single"),
                timestamp=float(thumb_data.get("timestamp", 0.0)),
                rows=int(thumb_data.get("rows", 2)),
                columns=int(thumb_data.get("columns", 3)),
                randomize=bool(thumb_data.get("randomize", False)),
                random_seed=(
                    int(thumb_data["random_seed"]) if thumb_data.get("random_seed") is not None else None
                ),
                output_path=Path(thumb_data.get("output_path", "thumbnail.jpg")),
                output_format=thumb_data.get("output_format", "jpg"),
                resize_to=tuple(thumb_data["resize_to"])
                if isinstance(thumb_data.get("resize_to"), (list, tuple))
                and len(thumb_data["resize_to"]) == 2
                else None,
            ),
            watermark=WatermarkSettings(
                kind=water_data.get("kind", "none"),
                opacity=int(water_data.get("opacity", 50)),
                position=water_data.get("position", "center"),
                text=water_data.get("text", ""),
                font_path=Path(water_data["font_path"])
                if water_data.get("font_path")
                else None,
                font_size=int(water_data.get("font_size", 48)),
                color=water_data.get("color", "#FFFFFF"),
                image_path=Path(water_data["image_path"])
                if water_data.get("image_path")
                else None,
                scale=float(water_data.get("scale", 0.3)),
            ),
        )


class SettingsManager:
    """Loads and saves user preferences to JSON."""

    @staticmethod
    def save(
        path: Path,
        thumbnail: ThumbnailSettings,
        watermark: WatermarkSettings,
    ) -> None:
        payload = PersistedSettings(thumbnail=thumbnail, watermark=watermark).to_dict()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2)

    @staticmethod
    def load(path: Path) -> PersistedSettings:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Settings file not found: {path}")
        with path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
        return PersistedSettings.from_dict(payload)
