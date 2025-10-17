from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Optional

from PIL import Image
from PyQt5.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QColorDialog,
)

from settings_manager import DEFAULT_SETTINGS_PATH, PersistedSettings, SettingsManager
from thumbnail_generator import ThumbnailGenerator, ThumbnailSettings
from watermark_manager import WatermarkSettings


def pil_to_pixmap(image: Image.Image) -> QPixmap:
    """Convert a PIL image into a QPixmap for preview rendering."""
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    data = image.tobytes("raw", "RGBA")
    bytes_per_line = image.width * 4
    qimage = QImage(
        data, image.width, image.height, bytes_per_line, QImage.Format_RGBA8888
    )
    # Copy to detach from the temporary memory buffer
    return QPixmap.fromImage(qimage.copy())


class ThumbnailWorker(QObject):
    progress_changed = pyqtSignal(int)
    finished = pyqtSignal(str, QPixmap)
    error = pyqtSignal(str)

    def __init__(
        self,
        video_path: Path,
        thumbnail_settings: ThumbnailSettings,
        watermark_settings: WatermarkSettings,
    ) -> None:
        super().__init__()
        self.video_path = Path(video_path)
        self.thumbnail_settings = thumbnail_settings
        self.watermark_settings = watermark_settings

    def run(self) -> None:
        try:
            generator = ThumbnailGenerator(self.video_path)
            output_path, image = generator.generate(
                self.thumbnail_settings,
                self.watermark_settings,
                progress_callback=self.progress_changed.emit,
            )
            pixmap = pil_to_pixmap(image)
            self.finished.emit(str(output_path), pixmap)
        except Exception as exc:  # pragma: no cover - GUI error handling
            self.error.emit(str(exc))


class PreviewWorker(QObject):
    finished = pyqtSignal(QPixmap)
    error = pyqtSignal(str)

    def __init__(
        self,
        video_path: Path,
        thumbnail_settings: ThumbnailSettings,
        watermark_settings: WatermarkSettings,
    ) -> None:
        super().__init__()
        self.video_path = Path(video_path)
        self.thumbnail_settings = thumbnail_settings
        self.watermark_settings = watermark_settings

    def run(self) -> None:
        try:
            generator = ThumbnailGenerator(self.video_path)
            image = generator.render_image(
                self.thumbnail_settings,
                self.watermark_settings,
            )
            pixmap = pil_to_pixmap(image)
            self.finished.emit(pixmap)
        except Exception as exc:  # pragma: no cover - GUI error handling
            self.error.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Video Thumbnail Generator")
        self.resize(960, 720)

        self.video_path: Optional[Path] = None
        self.video_info_label = QLabel("No video selected.")
        self.progress_bar = QProgressBar()
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(400, 225)
        self.preview_label.setStyleSheet("border: 1px solid #CCC; background: #111;")
        self.preview_label.setText("Select a video to preview.")

        self.selected_color = "#FFFFFF"
        self.selected_font_path: Optional[Path] = None
        self.current_pixmap: Optional[QPixmap] = None
        self.worker_thread: Optional[QThread] = None
        self.worker: Optional[ThumbnailWorker] = None
        self.random_seed: Optional[int] = None
        self.preview_worker_thread: Optional[QThread] = None
        self.preview_worker: Optional[PreviewWorker] = None
        self.preview_needs_refresh = False

        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(400)
        self.preview_timer.timeout.connect(self._start_preview_worker)

        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        central = QWidget()
        root_layout = QHBoxLayout()
        central.setLayout(root_layout)
        self.setCentralWidget(central)

        controls_layout = QVBoxLayout()
        controls_layout.setAlignment(Qt.AlignTop)
        root_layout.addLayout(controls_layout, 2)

        preview_layout = QVBoxLayout()
        preview_layout.addWidget(QLabel("Preview"))
        preview_layout.addWidget(self.preview_label, stretch=1)
        root_layout.addLayout(preview_layout, 3)

        # Video group
        video_group = QGroupBox("Video")
        video_layout = QVBoxLayout()
        path_layout = QHBoxLayout()
        self.video_path_line = QLineEdit()
        self.video_path_line.setReadOnly(True)
        video_browse_btn = QPushButton("Browse…")
        path_layout.addWidget(self.video_path_line, stretch=1)
        path_layout.addWidget(video_browse_btn)
        video_layout.addLayout(path_layout)
        video_layout.addWidget(self.video_info_label)
        video_group.setLayout(video_layout)
        controls_layout.addWidget(video_group)
        self.video_browse_btn = video_browse_btn

        # Mode group
        mode_group = QGroupBox("Thumbnail Mode")
        mode_form = QFormLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Single Thumbnail", "Grid Thumbnail"])
        mode_form.addRow("Mode", self.mode_combo)

        self.timestamp_spin = QDoubleSpinBox()
        self.timestamp_spin.setSuffix(" s")
        self.timestamp_spin.setDecimals(2)
        self.timestamp_spin.setSingleStep(0.5)
        self.timestamp_spin.setRange(0.0, 0.0)
        mode_form.addRow("Timestamp", self.timestamp_spin)

        grid_container = QWidget()
        grid_layout = QHBoxLayout()
        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(1, 10)
        self.rows_spin.setValue(2)
        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(1, 10)
        self.cols_spin.setValue(3)
        grid_layout.addWidget(QLabel("Rows"))
        grid_layout.addWidget(self.rows_spin)
        grid_layout.addWidget(QLabel("Columns"))
        grid_layout.addWidget(self.cols_spin)
        grid_container.setLayout(grid_layout)
        mode_form.addRow("Grid Size", grid_container)

        self.randomize_frames_checkbox = QCheckBox("Random frame sampling")
        mode_form.addRow("", self.randomize_frames_checkbox)

        mode_group.setLayout(mode_form)
        controls_layout.addWidget(mode_group)

        # Watermark group
        watermark_group = QGroupBox("Watermark")
        watermark_form = QFormLayout()

        self.watermark_type_combo = QComboBox()
        self.watermark_type_combo.addItems(["None", "Text", "Image"])
        watermark_form.addRow("Type", self.watermark_type_combo)

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(50)
        self.opacity_value_label = QLabel("50%")
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(self.opacity_slider)
        opacity_layout.addWidget(self.opacity_value_label)
        opacity_container = QWidget()
        opacity_container.setLayout(opacity_layout)
        watermark_form.addRow("Opacity", opacity_container)

        self.position_combo = QComboBox()
        self.position_combo.addItems(
            ["top-left", "top-right", "center", "bottom-left", "bottom-right"]
        )
        watermark_form.addRow("Position", self.position_combo)

        # Text watermark elements
        self.watermark_text_line = QLineEdit()
        watermark_form.addRow("Text", self.watermark_text_line)

        font_layout = QHBoxLayout()
        self.font_path_display = QLineEdit()
        self.font_path_display.setReadOnly(True)
        self.font_path_display.setPlaceholderText("Default font")
        self.font_browse_btn = QPushButton("Choose Font…")
        font_layout.addWidget(self.font_path_display, stretch=1)
        font_layout.addWidget(self.font_browse_btn)
        font_container = QWidget()
        font_container.setLayout(font_layout)
        watermark_form.addRow("Font", font_container)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 200)
        self.font_size_spin.setValue(48)
        watermark_form.addRow("Font Size", self.font_size_spin)

        color_layout = QHBoxLayout()
        self.color_preview = QLabel("      ")
        self.color_preview.setStyleSheet("background-color: #FFFFFF; border: 1px solid #444;")
        self.color_button = QPushButton("Choose Color…")
        color_layout.addWidget(self.color_preview)
        color_layout.addWidget(self.color_button)
        color_container = QWidget()
        color_container.setLayout(color_layout)
        watermark_form.addRow("Color", color_container)

        # Image watermark elements
        image_layout = QHBoxLayout()
        self.watermark_image_line = QLineEdit()
        self.watermark_image_line.setReadOnly(True)
        self.watermark_image_browse = QPushButton("Select Image…")
        image_layout.addWidget(self.watermark_image_line, stretch=1)
        image_layout.addWidget(self.watermark_image_browse)
        image_container = QWidget()
        image_container.setLayout(image_layout)
        watermark_form.addRow("Image", image_container)

        self.image_scale_slider = QSlider(Qt.Horizontal)
        self.image_scale_slider.setRange(5, 100)
        self.image_scale_slider.setValue(30)
        self.image_scale_label = QLabel("30% width")
        scale_layout = QHBoxLayout()
        scale_layout.addWidget(self.image_scale_slider)
        scale_layout.addWidget(self.image_scale_label)
        scale_container = QWidget()
        scale_container.setLayout(scale_layout)
        watermark_form.addRow("Scale", scale_container)

        watermark_group.setLayout(watermark_form)
        controls_layout.addWidget(watermark_group)

        # Output group
        output_group = QGroupBox("Output")
        output_form = QFormLayout()

        self.output_format_combo = QComboBox()
        self.output_format_combo.addItems(["jpg", "png"])
        output_form.addRow("Format", self.output_format_combo)

        output_path_layout = QHBoxLayout()
        self.output_path_line = QLineEdit()
        self.output_path_browse = QPushButton("Save As…")
        output_path_layout.addWidget(self.output_path_line, stretch=1)
        output_path_layout.addWidget(self.output_path_browse)
        output_container = QWidget()
        output_container.setLayout(output_path_layout)
        output_form.addRow("File", output_container)

        output_group.setLayout(output_form)
        controls_layout.addWidget(output_group)

        # Settings persistence
        settings_group = QGroupBox("Preferences")
        settings_layout = QHBoxLayout()
        self.save_settings_btn = QPushButton("Save Settings")
        self.load_settings_btn = QPushButton("Load Settings")
        settings_layout.addWidget(self.save_settings_btn)
        settings_layout.addWidget(self.load_settings_btn)
        settings_group.setLayout(settings_layout)
        controls_layout.addWidget(settings_group)

        # Generate button + progress
        self.generate_btn = QPushButton("Generate Thumbnail")
        controls_layout.addWidget(self.generate_btn)
        controls_layout.addWidget(self.progress_bar)

        controls_layout.addStretch(1)
        self._update_mode_controls()
        self._update_watermark_controls()

    def _connect_signals(self) -> None:
        self.video_browse_btn.clicked.connect(self._select_video)
        self.mode_combo.currentIndexChanged.connect(self._update_mode_controls)
        self.watermark_type_combo.currentIndexChanged.connect(self._update_watermark_controls)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self.image_scale_slider.valueChanged.connect(self._on_scale_changed)
        self.color_button.clicked.connect(self._choose_color)
        self.font_browse_btn.clicked.connect(self._choose_font)
        self.watermark_image_browse.clicked.connect(self._choose_watermark_image)
        self.output_path_browse.clicked.connect(self._select_output_file)
        self.generate_btn.clicked.connect(self._generate_thumbnail)
        self.save_settings_btn.clicked.connect(self._save_settings)
        self.load_settings_btn.clicked.connect(self._load_settings)
        self._register_preview_triggers()

    def _register_preview_triggers(self) -> None:
        schedule = lambda *_: self._schedule_preview_update()

        self.mode_combo.currentIndexChanged.connect(schedule)
        self.timestamp_spin.valueChanged.connect(schedule)
        self.rows_spin.valueChanged.connect(schedule)
        self.cols_spin.valueChanged.connect(schedule)
        self.randomize_frames_checkbox.toggled.connect(self._on_randomize_toggled)
        self.watermark_type_combo.currentIndexChanged.connect(schedule)
        self.opacity_slider.valueChanged.connect(schedule)
        self.position_combo.currentIndexChanged.connect(schedule)
        self.watermark_text_line.textChanged.connect(schedule)
        self.font_size_spin.valueChanged.connect(schedule)
        self.image_scale_slider.valueChanged.connect(schedule)

    def _schedule_preview_update(self, delay: int = 400) -> None:
        self.preview_timer.stop()
        if not self.video_path or not self.video_path.exists():
            return
        self.preview_timer.start(delay)

    def _on_randomize_toggled(self, checked: bool) -> None:
        self.random_seed = None
        self._schedule_preview_update()

    def _start_preview_worker(self) -> None:
        if not self.video_path or not self.video_path.exists():
            return

        if self.preview_worker_thread and self.preview_worker_thread.isRunning():
            self.preview_needs_refresh = True
            return

        thumbnail_settings = self._gather_thumbnail_settings()
        watermark_settings = self._gather_watermark_settings()

        self.preview_label.setPixmap(QPixmap())
        self.preview_label.setText("Rendering preview…")

        self.preview_worker_thread = QThread(self)
        self.preview_worker = PreviewWorker(
            self.video_path, thumbnail_settings, watermark_settings
        )
        self.preview_worker.moveToThread(self.preview_worker_thread)
        self.preview_worker_thread.started.connect(self.preview_worker.run)
        self.preview_worker.finished.connect(self._on_preview_ready)
        self.preview_worker.error.connect(self._on_preview_error)
        self.preview_worker.finished.connect(self._cleanup_preview_worker)
        self.preview_worker.error.connect(self._cleanup_preview_worker)
        self.preview_worker_thread.start()

    def _on_preview_ready(self, pixmap: QPixmap) -> None:
        self.current_pixmap = pixmap
        self.preview_label.setText("")
        self._refresh_preview()

    def _on_preview_error(self, message: str) -> None:
        self.preview_label.setPixmap(QPixmap())
        self.preview_label.setText(f"Preview failed: {message}")

    def _cleanup_preview_worker(self) -> None:
        if self.preview_worker_thread:
            if self.preview_worker_thread.isRunning():
                self.preview_worker_thread.quit()
                self.preview_worker_thread.wait()
            self.preview_worker_thread.deleteLater()
        if self.preview_worker:
            self.preview_worker.deleteLater()
        self.preview_worker_thread = None
        self.preview_worker = None

        if self.preview_needs_refresh:
            self.preview_needs_refresh = False
            # Restart preview with a slight delay to batch rapid changes.
            self._schedule_preview_update(150)
    def _select_video(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Video", "", "Video Files (*.mp4 *.mov *.avi *.mkv)"
        )
        if not file_path:
            return
        self.video_path = Path(file_path)
        self.random_seed = None
        self.video_path_line.setText(file_path)

        try:
            generator = ThumbnailGenerator(self.video_path)
            info = generator.get_video_info()
            duration_str = f"{info.duration:.2f} s" if info.duration else "Unknown"
            self.video_info_label.setText(
                f"Duration: {duration_str} | Resolution: {info.resolution} | FPS: {info.fps:.2f}"
            )
            self.timestamp_spin.setRange(0.0, max(info.duration, 0.0))
            if info.duration > 0:
                self.timestamp_spin.setValue(round(info.duration / 2.0, 2))
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to read video: {exc}")
            self.video_info_label.setText("Failed to read video metadata.")
            self.video_path = None
            self.video_path_line.clear()
            self.random_seed = None
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("Select a video to preview.")
            return

        # Suggest an output path next to the video
        default_output = self.video_path.with_name(f"{self.video_path.stem}_thumbnail")
        self.output_path_line.setText(str(default_output.with_suffix(".jpg")))
        self._schedule_preview_update(200)

    def _update_mode_controls(self) -> None:
        mode = self.mode_combo.currentIndex()
        is_single = mode == 0
        self.timestamp_spin.setEnabled(is_single)
        self.rows_spin.setEnabled(not is_single)
        self.cols_spin.setEnabled(not is_single)
        self.randomize_frames_checkbox.setEnabled(not is_single)
        if is_single:
            self.random_seed = None
        self._schedule_preview_update()

    def _update_watermark_controls(self) -> None:
        selection = self.watermark_type_combo.currentText().lower()
        is_text = selection == "text"
        is_image = selection == "image"

        for widget in [
            self.watermark_text_line,
            self.font_path_display,
            self.font_browse_btn,
            self.font_size_spin,
            self.color_button,
            self.color_preview,
        ]:
            widget.setEnabled(is_text)

        for widget in [
            self.watermark_image_line,
            self.watermark_image_browse,
            self.image_scale_slider,
        ]:
            widget.setEnabled(is_image)

        self.position_combo.setEnabled(selection != "none")
        self.opacity_slider.setEnabled(selection != "none")
        self._schedule_preview_update()

    def _on_opacity_changed(self, value: int) -> None:
        self.opacity_value_label.setText(f"{value}%")

    def _on_scale_changed(self, value: int) -> None:
        self.image_scale_label.setText(f"{value}% width")

    def _choose_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.selected_color), self, "Select Watermark Color")
        if color.isValid():
            self.selected_color = color.name()
            self.color_preview.setStyleSheet(
                f"background-color: {self.selected_color}; border: 1px solid #444;"
            )
            self._schedule_preview_update()

    def _choose_font(self) -> None:
        font_path, _ = QFileDialog.getOpenFileName(
            self, "Select Font", "", "Font Files (*.ttf *.otf)"
        )
        if not font_path:
            return
        self.selected_font_path = Path(font_path)
        self.font_path_display.setText(font_path)
        self._schedule_preview_update()

    def _choose_watermark_image(self) -> None:
        image_path, _ = QFileDialog.getOpenFileName(
            self, "Select Watermark Image", "", "Image Files (*.png *.jpg *.jpeg *.bmp)"
        )
        if not image_path:
            return
        self.watermark_image_line.setText(image_path)
        self._schedule_preview_update()

    def _select_output_file(self) -> None:
        selected_format = self.output_format_combo.currentText().lower()
        filters = "JPEG Image (*.jpg *.jpeg);;PNG Image (*.png)" if selected_format == "jpg" else "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg)"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Select Output File",
            self.output_path_line.text(),
            filters,
        )
        if not path:
            return
        self.output_path_line.setText(path)

    def _gather_thumbnail_settings(self) -> ThumbnailSettings:
        mode = "single" if self.mode_combo.currentIndex() == 0 else "grid"
        timestamp = float(self.timestamp_spin.value())
        rows = int(self.rows_spin.value())
        cols = int(self.cols_spin.value())
        randomize = bool(self.randomize_frames_checkbox.isChecked())

        output_path = self.output_path_line.text().strip()
        if not output_path:
            # fallback next to video or current working directory
            base = (
                self.video_path.with_name(f"{self.video_path.stem}_thumbnail")
                if self.video_path
                else Path("thumbnail")
            )
            output_path = str(base.with_suffix(f".{self.output_format_combo.currentText()}"))

        output_format = self.output_format_combo.currentText().lower()

        if randomize:
            if self.random_seed is None:
                self.random_seed = random.randint(0, 2_147_483_647)
        else:
            self.random_seed = None

        return ThumbnailSettings(
            mode=mode,
            timestamp=timestamp,
            rows=rows,
            columns=cols,
            randomize=randomize,
            random_seed=self.random_seed,
            output_path=Path(output_path),
            output_format=output_format,
        )

    def _gather_watermark_settings(self) -> WatermarkSettings:
        kind = self.watermark_type_combo.currentText().lower()
        opacity = int(self.opacity_slider.value())
        position = self.position_combo.currentText()
        text = self.watermark_text_line.text().strip()
        font_path = self.selected_font_path
        font_size = int(self.font_size_spin.value())
        color = self.selected_color
        image_path_str = self.watermark_image_line.text().strip()
        image_path = Path(image_path_str) if image_path_str else None
        scale = self.image_scale_slider.value() / 100.0

        return WatermarkSettings(
            kind=kind,
            opacity=opacity,
            position=position,
            text=text,
            font_path=font_path,
            font_size=font_size,
            color=color,
            image_path=image_path,
            scale=scale,
        )

    def _generate_thumbnail(self) -> None:
        if not self.video_path or not self.video_path.exists():
            QMessageBox.warning(self, "Missing video", "Please choose a video file before generating.")
            return

        thumbnail_settings = self._gather_thumbnail_settings()
        watermark_settings = self._gather_watermark_settings()

        self.progress_bar.setValue(0)
        self.generate_btn.setEnabled(False)

        self.worker_thread = QThread(self)
        self.worker = ThumbnailWorker(self.video_path, thumbnail_settings, watermark_settings)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress_changed.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self._on_generation_finished)
        self.worker.error.connect(self._on_generation_error)
        self.worker.finished.connect(self._cleanup_worker)
        self.worker.error.connect(self._cleanup_worker)
        self.worker_thread.start()

    def _on_generation_finished(self, output_path: str, pixmap: QPixmap) -> None:
        self.current_pixmap = pixmap
        self._refresh_preview()
        QMessageBox.information(self, "Success", f"Thumbnail saved to:\n{output_path}")

    def _on_generation_error(self, message: str) -> None:
        QMessageBox.critical(self, "Generation Failed", message)

    def _cleanup_worker(self) -> None:
        self.generate_btn.setEnabled(True)
        if self.worker_thread:
            if self.worker_thread.isRunning():
                self.worker_thread.quit()
                self.worker_thread.wait()
            self.worker_thread.deleteLater()
        if self.worker:
            self.worker.deleteLater()
        self.worker_thread = None
        self.worker = None

    def _save_settings(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Settings",
            str(DEFAULT_SETTINGS_PATH),
            "JSON Files (*.json)",
        )
        if not path:
            return
        try:
            SettingsManager.save(
                Path(path),
                self._gather_thumbnail_settings(),
                self._gather_watermark_settings(),
            )
            QMessageBox.information(self, "Settings Saved", f"Settings stored at {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to save settings: {exc}")

    def _load_settings(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Settings",
            str(DEFAULT_SETTINGS_PATH),
            "JSON Files (*.json)",
        )
        if not path:
            return
        try:
            persisted = SettingsManager.load(Path(path))
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to load settings: {exc}")
            return

        self._apply_persisted_settings(persisted)

    def _apply_persisted_settings(self, persisted: PersistedSettings) -> None:
        thumb = persisted.thumbnail
        water = persisted.watermark

        self.mode_combo.setCurrentIndex(0 if thumb.mode == "single" else 1)
        self.timestamp_spin.setValue(thumb.timestamp)
        self.rows_spin.setValue(thumb.rows)
        self.cols_spin.setValue(thumb.columns)
        self.randomize_frames_checkbox.setChecked(thumb.randomize)
        self.output_path_line.setText(str(thumb.output_path))
        format_index = self.output_format_combo.findText(thumb.output_format.lower())
        if format_index != -1:
            self.output_format_combo.setCurrentIndex(format_index)
        self.random_seed = thumb.random_seed if thumb.randomize else None

        self.watermark_type_combo.setCurrentIndex(
            {"none": 0, "text": 1, "image": 2}.get(water.kind, 0)
        )
        self.opacity_slider.setValue(water.opacity)
        self.position_combo.setCurrentText(water.position)
        self.watermark_text_line.setText(water.text)
        if water.font_path:
            self.selected_font_path = Path(water.font_path)
            self.font_path_display.setText(str(water.font_path))
        else:
            self.selected_font_path = None
            self.font_path_display.clear()
        self.font_size_spin.setValue(water.font_size)
        self.selected_color = water.color or "#FFFFFF"
        self.color_preview.setStyleSheet(
            f"background-color: {self.selected_color}; border: 1px solid #444;"
        )
        if water.image_path:
            self.watermark_image_line.setText(str(water.image_path))
        else:
            self.watermark_image_line.clear()
        self.image_scale_slider.setValue(int(water.scale * 100))

        self._update_mode_controls()
        self._update_watermark_controls()
        self._schedule_preview_update(150)

    def _refresh_preview(self) -> None:
        if self.current_pixmap:
            scaled = self.current_pixmap.scaled(
                self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.preview_label.setPixmap(scaled)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_preview()


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
