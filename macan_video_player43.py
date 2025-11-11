import sys
import os
import re
import threading
import json
import time
import subprocess
# --- PERUBAHAN: tempfile tidak lagi dibutuhkan untuk audio ---
# import tempfile
from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QFileDialog, QLineEdit, QLabel, QSlider, QMessageBox, QListWidget, QListWidgetItem,
    QAbstractItemView, QDialog
)
# --- PERUBAHAN UTAMA: Impor baru untuk video sink ---
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink
from PyQt6.QtCore import (
    QUrl, Qt, QTime, QEvent, QSize, QTimer, pyqtSignal, QObject,
    QThread, pyqtSlot
)
from PyQt6.QtGui import QIcon, QPixmap, QImage
import numpy as np

# --- PERUBAHAN UTAMA: Pustaka moviepy tidak lagi diperlukan untuk playback ---
try:
    import cv2
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Kesalahan: Pustaka 'opencv-python-headless' dan 'Pillow' diperlukan.")
    print("Silakan install dengan: pip install opencv-python-headless Pillow")
    sys.exit(1)

# Try to import necessary libraries
try:
    import qtawesome as qta
except ImportError:
    print("Pustaka 'qtawesome' tidak ditemukan. Silakan install dengan 'pip install qtawesome'")
    qta = None

try:
    from yt_dlp import YoutubeDL
except ImportError:
    print("Pustaka 'yt-dlp' tidak ditemukan. Silakan install dengan 'pip install yt-dlp'")
    YoutubeDL = None

# --- IMPLEMENTASI FITUR BARU: THUMBNAIL PREVIEW (DIMODIFIKASI TOTAL) ---

class ThumbnailPreviewWidget(QWidget):
    """
    Widget frameless untuk menampilkan thumbnail preview di atas slider.
    (Tidak ada perubahan di kelas ini)
    """
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.ToolTip)
        self.setLayout(QVBoxLayout())
        self.label = QLabel("Memuat...")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout().addWidget(self.label)
        self.setFixedSize(160, 120)
        self.setStyleSheet("background-color: black; border: 1px solid white; color: white; border-radius: 4px;")

    def set_thumbnail(self, pixmap):
        if not pixmap.isNull():
            scaled_pixmap = pixmap.scaled(self.size() - QSize(4, 4), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.label.setPixmap(scaled_pixmap)
        else:
            self.label.setText("Gagal")

class ThumbnailGenerator(QObject):
    thumbnail_ready = pyqtSignal(QPixmap, float)

    @pyqtSlot(str, int, float)
    def generate(self, video_path, timestamp_ms, request_time):
        if not video_path or not os.path.exists(video_path) or timestamp_ms < 0:
            self.thumbnail_ready.emit(QPixmap(), request_time)
            return
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                self.thumbnail_ready.emit(QPixmap(), request_time)
                return
            cap.set(cv2.CAP_PROP_POS_MSEC, timestamp_ms)
            ret, frame = cap.read()
            cap.release()
            if ret:
                rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                pixmap = QPixmap.fromImage(qt_image)
                self.thumbnail_ready.emit(pixmap, request_time)
            else:
                self.thumbnail_ready.emit(QPixmap(), request_time)
        except Exception as e:
            print(f"Kesalahan saat generate thumbnail dengan OpenCV: {e}")
            self.thumbnail_ready.emit(QPixmap(), request_time)

# --- IMPLEMENTASI FITUR BARU: THUMBNAIL PREVIEW (SELESAI) ---


# --- MODIFIKASI DIMULAI: Membuat slider yang bisa diklik DAN mendeteksi hover ---
class ClickableSlider(QSlider):
    """
    Slider kustom yang memungkinkan pengguna mengklik untuk mengubah posisi
    dan memancarkan sinyal saat cursor mouse bergerak di atasnya.
    (Tidak ada perubahan di kelas ini)
    """
    hover_move = pyqtSignal(int)
    hover_leave = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.orientation() == Qt.Orientation.Horizontal:
                value = self.minimum() + (self.maximum() - self.minimum()) * event.pos().x() / self.width()
            else:
                value = self.minimum() + (self.maximum() - self.minimum()) * event.pos().y() / self.height()

            self.setValue(int(value))
            self.sliderMoved.emit(int(value))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self.hover_move.emit(event.pos().x())
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.hover_leave.emit()
        super().leaveEvent(event)
# --- MODIFIKASI SELESAI ---

# --- PERUBAHAN UTAMA: Kelas OpenCVVideoThread DIHAPUS ---
# Kelas ini tidak lagi diperlukan karena QMediaPlayer dan QVideoSink
# akan menangani pemutaran dan pengambilan frame.

class MiniPlayerWindow(QWidget):
    """
    Jendela pemutar mini. Sekarang menggunakan QLabel untuk menampilkan frame.
    """
    closing = pyqtSignal()

    # --- PERUBAHAN: Hanya butuh audio_output, bukan player terpisah ---
    def __init__(self, audio_output, parent=None):
        super().__init__(parent)
        self.audio_output = audio_output
        self.is_muted = self.audio_output.isMuted()
        self.last_volume = int(self.audio_output.volume() * 100) if not self.is_muted else 50
        self.is_playing = False

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        self.setWindowTitle("Macan Player - Mini")
        self.setFixedSize(480, 320)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        icon_path = "player.ico"
        if hasattr(sys, "_MEIPASS"): icon_path = os.path.join(sys._MEIPASS, icon_path)
        if os.path.exists(icon_path): self.setWindowIcon(QIcon(icon_path))

        self.setStyleSheet("background-color: #1c1c1c; color: #ecf0f1;")

        self.video_widget = QLabel("Mini Player")
        self.video_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_widget.setStyleSheet("background-color: black;")

        self.position_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)

        self.btn_play_pause = QPushButton()
        if qta: self.btn_play_pause.setIcon(qta.icon('fa5s.play'))

        self.btn_stop = QPushButton()
        if qta: self.btn_stop.setIcon(qta.icon('fa5s.stop'))

        self.btn_mute = QPushButton()
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(int(self.audio_output.volume() * 100))
        self.volume_slider.setFixedWidth(100)
        self._update_volume_icon() # Panggil sekali saat setup

        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.btn_play_pause)
        controls_layout.addWidget(self.btn_stop)
        controls_layout.addStretch()
        controls_layout.addWidget(self.btn_mute)
        controls_layout.addWidget(self.volume_slider)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        main_layout.addWidget(self.video_widget, 1)
        main_layout.addWidget(self.position_slider)
        main_layout.addLayout(controls_layout)
        self.setLayout(main_layout)

    def _connect_signals(self):
        self.btn_mute.clicked.connect(self._toggle_mute)
        self.volume_slider.valueChanged.connect(self._set_volume)
        # --- PERUBAHAN: Hubungkan sinyal volume audio output ke slider ---
        self.audio_output.volumeChanged.connect(self._sync_volume_slider)

    @pyqtSlot(QImage)
    def update_frame(self, image):
        """Slot untuk menerima frame baru dari player utama."""
        pixmap = QPixmap.fromImage(image)
        self.video_widget.setPixmap(pixmap.scaled(self.video_widget.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def _set_volume(self, value):
        self.audio_output.setVolume(value / 100.0)

    def _toggle_mute(self):
        self.is_muted = not self.is_muted
        if self.is_muted:
            self.last_volume = self.volume_slider.value()
            self.audio_output.setMuted(True)
        else:
            self.audio_output.setMuted(False)
            # Kembalikan ke volume terakhir atau 50 jika volume terakhir 0
            self.volume_slider.setValue(self.last_volume if self.last_volume > 0 else 50)
        self._update_volume_icon()

    def _update_volume_icon(self):
        if not qta: return
        volume = self.volume_slider.value()
        is_muted = self.audio_output.isMuted()

        if is_muted or volume == 0:
            icon = qta.icon('fa5s.volume-mute')
        elif 0 < volume <= 50:
            icon = qta.icon('fa5s.volume-down')
        else:
            icon = qta.icon('fa5s.volume-up')
        self.btn_mute.setIcon(icon)

    def _sync_volume_slider(self):
        # --- PERBAIKAN: Logika sinkronisasi volume dan mute ---
        volume_float = self.audio_output.volume()
        is_muted = self.audio_output.isMuted()
        self.is_muted = is_muted

        if not self.volume_slider.isSliderDown():
            if is_muted:
                self.volume_slider.setValue(0)
            else:
                self.volume_slider.setValue(int(volume_float * 100))
        self._update_volume_icon()


    def update_position(self, position):
        if not self.position_slider.isSliderDown():
            self.position_slider.setValue(position)

    def update_duration(self, duration):
        self.position_slider.setRange(0, duration)

    def update_play_pause_icon(self, is_playing):
        self.is_playing = is_playing
        if qta:
            icon = qta.icon('fa5s.pause') if is_playing else qta.icon('fa5s.play')
            self.btn_play_pause.setIcon(icon)

    def closeEvent(self, event):
        self.closing.emit()
        super().closeEvent(event)


# Kelas YouTubeDLWorker, PlaylistWidget, HistoryWindow tidak diubah.
class YouTubeDLWorker(QObject):
    finished = pyqtSignal(str, str, str)
    def __init__(self, url):
        super().__init__()
        self.url = url
    def run(self):
        if not YoutubeDL:
            self.finished.emit(None, None, "Pustaka yt-dlp tidak terinstal.")
            return
        try:
            ydl_opts = {'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best', 'quiet': True, 'no_warnings': True}
            with YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(self.url, download=False)
                title = info_dict.get('title', 'Judul tidak diketahui')
                self.finished.emit(info_dict['url'], title, None)
        except Exception as e:
            self.finished.emit(None, None, f"Error dari yt-dlp: {str(e)}")

class PlaylistWidget(QWidget):
    play_requested = pyqtSignal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Macan Player - Playlist")
        self.setGeometry(1100, 100, 300, 400)
        icon_path = "player.ico"
        if hasattr(sys, "_MEIPASS"): icon_path = os.path.join(sys._MEIPASS, icon_path)
        if os.path.exists(icon_path): self.setWindowIcon(QIcon(icon_path))
        self.playlist = []
        self._setup_ui()
        self._connect_signals()
        self.setAcceptDrops(True)
    def _setup_ui(self):
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.setStyleSheet("background-color: #34495e;")
        self.btn_add_file = QPushButton(" Tambah File")
        if qta: self.btn_add_file.setIcon(qta.icon('fa5s.plus'))
        self.btn_remove = QPushButton(" Hapus")
        if qta: self.btn_remove.setIcon(qta.icon('fa5s.trash'))
        self.btn_clear = QPushButton(" Hapus Semua")
        if qta: self.btn_clear.setIcon(qta.icon('fa5s.times-circle'))
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.btn_add_file)
        controls_layout.addWidget(self.btn_remove)
        controls_layout.addWidget(self.btn_clear)
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.list_widget)
        main_layout.addLayout(controls_layout)
        self.setLayout(main_layout)
    def _connect_signals(self):
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.btn_add_file.clicked.connect(self._add_to_playlist)
        self.btn_remove.clicked.connect(self._remove_from_playlist)
        self.btn_clear.clicked.connect(self._clear_playlist)
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
        else: event.ignore()
    def dropEvent(self, event):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if os.path.exists(file_path):
                if os.path.splitext(file_path)[1].lower() in ['.mp4', '.mkv', '.webm', '.avi']:
                    self.playlist.append({'path': file_path, 'title': os.path.basename(file_path)})
                    self._update_ui()
                    self._save_playlist()
        event.acceptProposedAction()
    def _on_item_double_clicked(self, item):
        index = self.list_widget.row(item)
        if 0 <= index < len(self.playlist):
            self.play_requested.emit(self.playlist[index]['path'])
            self._update_selection(index)
    def _add_to_playlist(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Tambahkan ke Playlist", "", "Video Files (*.mp4 *.mkv *.webm *.avi)")
        if file_path:
            self.playlist.append({'path': file_path, 'title': os.path.basename(file_path)})
            self._update_ui()
            self._save_playlist()
    def _remove_from_playlist(self):
        selected_items = self.list_widget.selectedItems()
        if not selected_items: return
        index = self.list_widget.row(selected_items[0])
        del self.playlist[index]
        self._update_ui()
        self._save_playlist()
    def _clear_playlist(self):
        self.playlist.clear()
        self._update_ui()
        self._save_playlist()
    def _update_ui(self):
        self.list_widget.clear()
        for item in self.playlist:
            self.list_widget.addItem(item['title'])
    def _update_selection(self, index):
        if 0 <= index < self.list_widget.count(): self.list_widget.setCurrentRow(index)
    def get_current_index(self): return self.list_widget.currentRow()
    def get_playlist_data(self): return self.playlist
    def set_playlist_data(self, data):
        self.playlist = data
        self._update_ui()
    def _save_playlist(self):
        config_path = os.path.join(os.path.dirname(__file__), "player_config.json")
        try:
            with open(config_path, "r") as f: config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): config = {}
        config['playlist'] = self.playlist
        with open(config_path, "w") as f: json.dump(config, f, indent=4)

class HistoryWindow(QDialog):
    history_item_selected = pyqtSignal(dict)
    delete_selected_requested = pyqtSignal(int)
    clear_all_requested = pyqtSignal()
    def __init__(self, history_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Riwayat Tontonan")
        self.setGeometry(1100, 550, 300, 400)
        self.history_data = history_data
        self._setup_ui()
        self._connect_signals()
        self.populate_list()
    def _setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.btn_remove_selected = QPushButton(" Hapus Pilihan")
        if qta: self.btn_remove_selected.setIcon(qta.icon('fa5s.trash-alt'))
        self.btn_clear_all = QPushButton(" Hapus Semua")
        if qta: self.btn_clear_all.setIcon(qta.icon('fa5s.times'))
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.btn_remove_selected)
        button_layout.addWidget(self.btn_clear_all)
        self.main_layout.addWidget(self.list_widget)
        self.main_layout.addLayout(button_layout)
    def _connect_signals(self):
        self.list_widget.itemDoubleClicked.connect(self._on_item_selected)
        self.btn_remove_selected.clicked.connect(self._remove_selected)
        self.btn_clear_all.clicked.connect(self._clear_all)
    def populate_list(self):
        self.list_widget.clear()
        for item in reversed(self.history_data):
            list_item = QListWidgetItem(item.get('title', 'Judul Tidak Diketahui'))
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self.list_widget.addItem(list_item)
    def _on_item_selected(self, item):
        self.history_item_selected.emit(item.data(Qt.ItemDataRole.UserRole))
        self.accept()
    def _remove_selected(self):
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "Info", "Pilih item yang ingin dihapus.")
            return
        # --- PERBAIKAN: Index riwayat dibalik, jadi perlu dihitung ulang ---
        original_index = len(self.history_data) - 1 - self.list_widget.row(selected_items[0])
        self.delete_selected_requested.emit(original_index)

    def _clear_all(self):
        if QMessageBox.question(self, "Konfirmasi", "Yakin hapus SEMUA riwayat?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.clear_all_requested.emit()


class ModernVideoPlayer(QWidget):
    request_thumbnail = pyqtSignal(str, int, float)

    def __init__(self):
        super().__init__()
        self.is_fullscreen = False
        # --- PERBAIKAN: Variabel untuk menyimpan geometri jendela sebelum layar penuh ---
        self.normal_geometry = None 
        # self.is_muted tidak lagi dikelola di sini, tapi di audio_output
        self.last_volume = 50
        self.SKIP_INTERVAL = 10000
        self.playback_speeds = [0.5, 1.0, 1.5, 2.0]
        self.current_speed_index = 1
        self.config_path = os.path.join(os.path.dirname(__file__), "player_config.json")
        self.themes = {}
        self.theme_names = []
        self.current_theme_index = 0
        self.history = []
        self.current_media_info = {}
        self.subtitles = [] # --- BARU: State untuk subtitle ---

        self.playlist_widget = PlaylistWidget()
        self.history_window = HistoryWindow(self.history, self)
        self.controls_hide_timer = QTimer(self)
        self.controls_hide_timer.setInterval(2500)
        self.controls_hide_timer.setSingleShot(True)

        self._setup_player()
        self.mini_player_widget = MiniPlayerWindow(self.audio_output)

        self._setup_thumbnail_feature()
        self._setup_themes()
        self._load_config()
        self._setup_ui()
        self._connect_signals()
        self._apply_theme(self.theme_names[self.current_theme_index])

        self.setAcceptDrops(True)
        self.video_widget.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.video_widget.setMouseTracking(True)
        self.controls_container.setMouseTracking(True)

    def _setup_thumbnail_feature(self):
        self.last_thumbnail_request_time = 0.0
        self.thumbnail_preview = ThumbnailPreviewWidget()
        self.thumbnail_thread = QThread()
        self.thumbnail_generator = ThumbnailGenerator()
        self.thumbnail_generator.moveToThread(self.thumbnail_thread)
        self.thumbnail_thread.start()

    # --- PERUBAHAN UTAMA: Metode setup player baru menggunakan QVideoSink ---
    def _setup_player(self):
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)

        # Siapkan video sink untuk "mencuri" frame
        self.video_sink = QVideoSink()
        self.player.setVideoSink(self.video_sink)
        # Hubungkan sinyal saat frame baru tersedia
        self.video_sink.videoFrameChanged.connect(self.process_frame)

        # Pengaturan font subtitle, dipindahkan ke sini
        self.subtitle_font_path = "arial.ttf"
        self.subtitle_font_size = 24
        self.subtitle_color = (255, 255, 255, 220) # RGBA
        self.subtitle_outline_color = (0, 0, 0, 220) # RGBA


    def _setup_themes(self):
        self.themes = {
            "Dark": """
                QWidget { background-color: #1c1c1c; color: #ecf0f1; font-family: 'Segoe UI', Arial, sans-serif; }
                QPushButton { background-color: transparent; border: none; padding: 8px; border-radius: 4px; }
                QPushButton:hover { background-color: #3a3a3a; } QPushButton:pressed { background-color: #4a4a4a; }
                QLineEdit { background-color: #2c2c2c; border: 1px solid #444; padding: 5px; border-radius: 4px; }
                QSlider::groove:horizontal { height: 4px; background: #444; border-radius: 2px; }
                QSlider::handle:horizontal { background: #3498db; width: 12px; margin: -4px 0; border-radius: 6px; }
                QSlider::sub-page:horizontal { background: #3498db; border-radius: 2px; }
                QLabel { font-size: 12px; }
                QListWidget { background-color: #2c3e50; }
            """,
            "Light": """
                QWidget { background-color: #f0f0f0; color: #2c3e50; font-family: 'Segoe UI', Arial, sans-serif; }
                QPushButton { background-color: transparent; border: none; padding: 8px; border-radius: 4px; }
                QPushButton:hover { background-color: #dcdcdc; } QPushButton:pressed { background-color: #c0c0c0; }
                QLineEdit { background-color: #ffffff; border: 1px solid #bdc3c7; padding: 5px; border-radius: 4px; }
                QSlider::groove:horizontal { height: 4px; background: #bdc3c7; border-radius: 2px; }
                QSlider::handle:horizontal { background: #e74c3c; width: 12px; margin: -4px 0; border-radius: 6px; }
                QSlider::sub-page:horizontal { background: #e74c3c; border-radius: 2px; }
                QLabel { font-size: 12px; }
                QListWidget { background-color: #ffffff; }
            """,
            "Neon Blue": """
                QWidget { background-color: #0d0221; color: #b4f1f1; font-family: 'Segoe UI', Arial, sans-serif; }
                QPushButton { background-color: transparent; border: none; padding: 8px; border-radius: 4px; }
                QPushButton:hover { background-color: #261a3b; } QPushButton:pressed { background-color: #4d3375; }
                QLineEdit { background-color: #261a3b; border: 1px solid #00aaff; padding: 5px; border-radius: 4px; color: #ffffff; }
                QSlider::groove:horizontal { height: 4px; background: #261a3b; border-radius: 2px; }
                QSlider::handle:horizontal { background: #00aaff; width: 12px; margin: -4px 0; border-radius: 6px; }
                QSlider::sub-page:horizontal { background: #00aaff; border-radius: 2px; }
                QLabel { font-size: 12px; }
                QListWidget { background-color: #261a3b; }
            """,
            "Dark Blue": """
                QWidget { background-color: #0d1b2a; color: #e0e1dd; font-family: 'Segoe UI', Arial, sans-serif; }
                QPushButton { background-color: transparent; border: none; padding: 8px; border-radius: 4px; }
                QPushButton:hover { background-color: #1b263b; } QPushButton:pressed { background-color: #415a77; }
                QLineEdit { background-color: #1b263b; border: 1px solid #415a77; padding: 5px; border-radius: 4px; }
                QSlider::groove:horizontal { height: 4px; background: #415a77; border-radius: 2px; }
                QSlider::handle:horizontal { background: #778da9; width: 12px; margin: -4px 0; border-radius: 6px; }
                QSlider::sub-page:horizontal { background: #778da9; border-radius: 2px; }
                QLabel { font-size: 12px; }
                QListWidget { background-color: #1b263b; }
            """,
            "Soft Pink": """
                QWidget { background-color: #fce4ec; color: #444; font-family: 'Segoe UI', Arial, sans-serif; }
                QPushButton { background-color: transparent; border: none; padding: 8px; border-radius: 4px; }
                QPushButton:hover { background-color: #f8bbd0; } QPushButton:pressed { background-color: #f48fb1; }
                QLineEdit { background-color: #ffffff; border: 1px solid #f48fb1; padding: 5px; border-radius: 4px; }
                QSlider::groove:horizontal { height: 4px; background: #f8bbd0; border-radius: 2px; }
                QSlider::handle:horizontal { background: #ec407a; width: 12px; margin: -4px 0; border-radius: 6px; }
                QSlider::sub-page:horizontal { background: #ec407a; border-radius: 2px; }
                QLabel { font-size: 12px; }
                QListWidget { background-color: #fff8f9; }
            """
        }
        self.theme_names = list(self.themes.keys())

    def _apply_theme(self, theme_name):
        if theme_name in self.themes:
            self.setStyleSheet(self.themes[theme_name])
            self.playlist_widget.setStyleSheet(self.themes[theme_name])
            self.history_window.setStyleSheet(self.themes[theme_name])
            self.mini_player_widget.setStyleSheet(self.themes[theme_name])

    def _change_theme(self):
        self.current_theme_index = (self.current_theme_index + 1) % len(self.theme_names)
        new_theme_name = self.theme_names[self.current_theme_index]
        self._apply_theme(new_theme_name)
        self.btn_change_theme.setToolTip(f"Ganti Tema (Sekarang: {new_theme_name})")

    def _load_config(self):
        try:
            with open(self.config_path, "r") as f: config = json.load(f)
            self.last_volume = config.get('last_volume', 50)
            self.audio_output.setVolume(self.last_volume / 100.0) # Set volume saat load
            self.playlist_widget.set_playlist_data(config.get('playlist', []))
            saved_theme = config.get('theme', 'Dark')
            if saved_theme in self.theme_names:
                self.current_theme_index = self.theme_names.index(saved_theme)
            self.history = config.get('history', [])
            self.history_window.history_data = self.history
            self.history_window.populate_list()
        except (FileNotFoundError, json.JSONDecodeError): pass

    def _save_config(self):
        config = {
            'last_volume': int(self.audio_output.volume() * 100), # Ambil volume dari audio_output
            'playlist': self.playlist_widget.get_playlist_data(),
            'theme': self.theme_names[self.current_theme_index],
            'history': self.history
        }
        try:
            with open(self.config_path, "w") as f: json.dump(config, f, indent=4)
        except Exception as e: print(f"Gagal menyimpan konfigurasi: {e}")

    def _setup_ui(self):
        self.setWindowTitle("Macan Video Player")
        self.setGeometry(100, 100, 700, 550)
        icon_path = "player.ico"
        if hasattr(sys, "_MEIPASS"): icon_path = os.path.join(sys._MEIPASS, icon_path)
        if os.path.exists(icon_path): self.setWindowIcon(QIcon(icon_path))

        self.video_widget = QLabel()
        self.video_widget.setObjectName("video_widget")
        self.video_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_widget.installEventFilter(self)

        self.splash_label = QLabel(self.video_widget)
        splash_path = "splash.png"
        if hasattr(sys, "_MEIPASS"): splash_path = os.path.join(sys._MEIPASS, splash_path)
        if os.path.exists(splash_path):
            pixmap = QPixmap(splash_path)
            self.splash_label.setPixmap(pixmap.scaled(QSize(480, 480), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.splash_label.setText("Macan Video Player")
        self.splash_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.splash_label.setStyleSheet("background-color: transparent; font-size: 30px; font-weight: bold;")
        self.splash_label.show()

        self.btn_open = QPushButton()
        if qta: self.btn_open.setIcon(qta.icon('fa5s.folder-open'))
        self.btn_open_srt = QPushButton()
        if qta: self.btn_open_srt.setIcon(qta.icon('fa5s.closed-captioning'))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("URL video (YouTube, dll)...")
        self.btn_load_url = QPushButton()
        if qta: self.btn_load_url.setIcon(qta.icon('fa5s.link'))
        self.btn_toggle_url_bar = QPushButton()
        if qta: self.btn_toggle_url_bar.setIcon(qta.icon('fa5s.globe'))
        self.btn_show_playlist = QPushButton()
        if qta: self.btn_show_playlist.setIcon(qta.icon('fa5s.list'))
        self.btn_show_history = QPushButton()
        if qta: self.btn_show_history.setIcon(qta.icon('fa5s.history'))

        self.position_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)
        self.time_label = QLabel("00:00 / 00:00")

        self.btn_prev_playlist = QPushButton()
        if qta: self.btn_prev_playlist.setIcon(qta.icon('fa5s.step-backward'))
        self.btn_next_playlist = QPushButton()
        if qta: self.btn_next_playlist.setIcon(qta.icon('fa5s.step-forward'))
        self.btn_play_pause = QPushButton()
        if qta: self.btn_play_pause.setIcon(qta.icon('fa5s.play'))
        self.btn_stop = QPushButton()
        if qta: self.btn_stop.setIcon(qta.icon('fa5s.stop'))
        self.btn_speed = QPushButton(f"{self.playback_speeds[self.current_speed_index]}x")
        self.btn_mute = QPushButton()
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.last_volume)
        self.volume_slider.setFixedWidth(120)
        if qta: self._update_volume_icon()

        self.btn_mini_player = QPushButton()
        if qta: self.btn_mini_player.setIcon(qta.icon('fa5s.window-minimize'))
        self.btn_fullscreen = QPushButton()
        if qta: self.btn_fullscreen.setIcon(qta.icon('fa5s.expand'))
        self.btn_change_theme = QPushButton()
        if qta: self.btn_change_theme.setIcon(qta.icon('fa5s.palette'))

        self.controls_container = QWidget()
        self.url_bar_widget = QWidget()
        url_bar_layout = QHBoxLayout()
        url_bar_layout.setContentsMargins(10, 0, 10, 5)
        url_bar_layout.addWidget(self.url_input)
        url_bar_layout.addWidget(self.btn_load_url)
        self.url_bar_widget.setLayout(url_bar_layout)
        self.url_bar_widget.setVisible(False)
        slider_layout = QHBoxLayout()
        slider_layout.setContentsMargins(10, 0, 10, 0)
        slider_layout.addWidget(self.position_slider)
        bottom_controls_layout = QHBoxLayout()
        bottom_controls_layout.setContentsMargins(10, 0, 10, 5)
        bottom_controls_layout.addWidget(self.btn_play_pause)
        bottom_controls_layout.addWidget(self.btn_stop)
        bottom_controls_layout.addWidget(self.btn_prev_playlist)
        bottom_controls_layout.addWidget(self.btn_next_playlist)
        bottom_controls_layout.addWidget(self.time_label)
        bottom_controls_layout.addStretch(1)
        bottom_controls_layout.addWidget(self.btn_open)
        bottom_controls_layout.addWidget(self.btn_toggle_url_bar)
        bottom_controls_layout.addWidget(self.btn_open_srt)
        bottom_controls_layout.addWidget(self.btn_speed)
        bottom_controls_layout.addWidget(self.btn_show_playlist)
        bottom_controls_layout.addWidget(self.btn_show_history)
        bottom_controls_layout.addWidget(self.btn_mute)
        bottom_controls_layout.addWidget(self.volume_slider)
        bottom_controls_layout.addWidget(self.btn_mini_player)
        bottom_controls_layout.addWidget(self.btn_fullscreen)
        bottom_controls_layout.addWidget(self.btn_change_theme)
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 5, 0, 0)
        container_layout.setSpacing(5)
        container_layout.addWidget(self.url_bar_widget)
        container_layout.addLayout(slider_layout)
        container_layout.addLayout(bottom_controls_layout)
        self.controls_container.setLayout(container_layout)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.video_widget, 1)
        main_layout.addWidget(self.controls_container)
        self.setLayout(main_layout)

    def _connect_signals(self):
        self.btn_open.clicked.connect(self._open_file)
        self.btn_open_srt.clicked.connect(self._open_srt_dialog)
        self.url_input.returnPressed.connect(self._load_from_url)
        self.btn_load_url.clicked.connect(self._load_from_url)
        self.btn_toggle_url_bar.clicked.connect(self._toggle_url_bar)
        self.btn_play_pause.clicked.connect(self._toggle_play_pause)
        self.btn_stop.clicked.connect(self._stop_video)
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        self.btn_mute.clicked.connect(self._toggle_mute)
        self.btn_speed.clicked.connect(self._change_playback_speed)
        self.btn_show_playlist.clicked.connect(self._toggle_playlist_window)
        self.btn_prev_playlist.clicked.connect(self._play_previous_video)
        self.btn_next_playlist.clicked.connect(self._play_next_video)
        self.btn_change_theme.clicked.connect(self._change_theme)
        self.btn_show_history.clicked.connect(self._show_history_window)
        self.history_window.history_item_selected.connect(self._play_from_history)
        self.history_window.delete_selected_requested.connect(self._delete_history_item)
        self.history_window.clear_all_requested.connect(self._clear_all_history_data)

        self.btn_mini_player.clicked.connect(self._show_mini_player)
        self.mini_player_widget.closing.connect(self._show_main_from_mini)
        self.mini_player_widget.btn_play_pause.clicked.connect(self._toggle_play_pause)
        self.mini_player_widget.btn_stop.clicked.connect(self._stop_video)
        self.mini_player_widget.position_slider.sliderMoved.connect(self._set_position)

        self.volume_slider.valueChanged.connect(self._set_volume)
        self.position_slider.sliderMoved.connect(self._set_position)

        # --- PERUBAHAN UTAMA: Menghubungkan sinyal dari QMediaPlayer ---
        self.player.positionChanged.connect(self._update_position)
        self.player.durationChanged.connect(self._update_duration)
        self.player.playbackStateChanged.connect(self._update_play_pause_icon)
        self.player.mediaStatusChanged.connect(self._handle_media_status_changed)

        self.audio_output.volumeChanged.connect(self._sync_main_volume_slider)
        self.playlist_widget.play_requested.connect(self._load_and_play_from_playlist)
        self.controls_hide_timer.timeout.connect(self._hide_controls)

        self.position_slider.hover_move.connect(self._show_thumbnail_preview)
        self.position_slider.hover_leave.connect(self.thumbnail_preview.hide)
        self.thumbnail_generator.thumbnail_ready.connect(self._update_thumbnail)
        self.request_thumbnail.connect(self.thumbnail_generator.generate, Qt.ConnectionType.QueuedConnection)

    # --- PERUBAHAN UTAMA: Slot baru untuk memproses frame dari QVideoSink ---
    @pyqtSlot("QVideoFrame")
    def process_frame(self, frame):
        if not frame.isValid():
            return

        # Konversi QVideoFrame ke QImage
        qt_image = frame.toImage()
        # Pastikan formatnya bisa di-handle oleh OpenCV
        qt_image = qt_image.convertToFormat(QImage.Format.Format_RGB888)

        # Konversi QImage ke array NumPy (frame OpenCV)
        h, w, _ = qt_image.height(), qt_image.width(), 3
        bytes_per_line = 3 * w
        ptr = qt_image.bits()
        ptr.setsize(h * bytes_per_line)
        np_frame_rgb = np.frombuffer(ptr, np.uint8).reshape((h, w, 3))

        # Render subtitle jika ada
        if self.subtitles:
            # Konversi RGB ke BGR untuk fungsi draw_subtitle
            np_frame_bgr = cv2.cvtColor(np_frame_rgb, cv2.COLOR_RGB2BGR)
            modified_frame_bgr = self.draw_subtitle(np_frame_bgr, self.player.position())
            # Konversi kembali ke RGB untuk ditampilkan
            np_frame_rgb = cv2.cvtColor(modified_frame_bgr, cv2.COLOR_BGR2RGB)

        # Tampilkan frame yang sudah dimodifikasi
        final_image = QImage(np_frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        self.video_widget.setPixmap(QPixmap.fromImage(final_image).scaled(self.video_widget.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

        if self.mini_player_widget.isVisible():
             self.mini_player_widget.update_frame(final_image)

    def draw_subtitle(self, frame, current_pos_ms):
        """Merender teks subtitle ke frame video menggunakan Pillow."""
        text_to_draw = ""
        for sub in self.subtitles:
            if sub['start_ms'] <= current_pos_ms <= sub['end_ms']:
                text_to_draw = sub['text']
                break

        if not text_to_draw:
            return frame

        try:
            pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(pil_img, "RGBA")

            try:
                font = ImageFont.truetype(self.subtitle_font_path, self.subtitle_font_size)
            except IOError:
                font = ImageFont.load_default()

            text_bbox = draw.textbbox((0, 0), text_to_draw, font=font, align="center")
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]

            img_width, img_height = pil_img.size
            x = (img_width - text_width) / 2
            y = img_height - text_height - 30

            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx != 0 or dy != 0:
                        draw.text((x+dx, y+dy), text_to_draw, font=font, fill=self.subtitle_outline_color, align="center")

            draw.text((x, y), text_to_draw, font=font, fill=self.subtitle_color, align="center")

            return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        except Exception as e:
            print(f"Error saat merender subtitle: {e}")
            return frame

    def _show_thumbnail_preview(self, x_pos):
        video_path = self.current_media_info.get('path', '')
        is_url = "://" in video_path
        if not self.player.hasVideo() or self.player.duration() <= 0 or is_url or not os.path.exists(video_path): return
        value = self.position_slider.minimum() + (self.position_slider.maximum() - self.position_slider.minimum()) * x_pos / self.position_slider.width()
        timestamp_ms = int(value)
        global_slider_pos = self.position_slider.mapToGlobal(self.position_slider.rect().topLeft())
        preview_x = global_slider_pos.x() + x_pos - (self.thumbnail_preview.width() / 2)
        preview_y = global_slider_pos.y() - self.thumbnail_preview.height() - 5
        self.thumbnail_preview.move(int(preview_x), int(preview_y))
        if not self.thumbnail_preview.isVisible():
            self.thumbnail_preview.show()
            self.thumbnail_preview.label.setText("Memuat...")
        current_time = time.time()
        if current_time - self.last_thumbnail_request_time > 0.1:
            self.last_thumbnail_request_time = current_time
            self.request_thumbnail.emit(video_path, timestamp_ms, current_time)

    @pyqtSlot(QPixmap, float)
    def _update_thumbnail(self, pixmap, request_time):
        if request_time == self.last_thumbnail_request_time and self.thumbnail_preview.isVisible():
            self.thumbnail_preview.set_thumbnail(pixmap)

    def _show_history_window(self):
        self.history_window.populate_list()
        self.history_window.exec()
    def _add_to_history(self, path, title):
        self.history = [item for item in self.history if item.get('path') != path]
        self.history.append({'path': path, 'title': title})
        if len(self.history) > 50: self.history = self.history[-50:]
    def _play_from_history(self, item):
        path = item.get('path')
        if not path: return
        self._load_video_file(path)
    def _delete_history_item(self, index):
        if 0 <= index < len(self.history):
            del self.history[index]
            self.history_window.populate_list()
            self._save_config()
    def _clear_all_history_data(self):
        self.history.clear()
        self.history_window.populate_list()
        self._save_config()

    def _show_mini_player(self):
        self.mini_player_widget.show()
        self.hide()

    def _show_main_from_mini(self):
        self.show()
        self.mini_player_widget.hide()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
    def dropEvent(self, event):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if os.path.exists(file_path):
                if os.path.splitext(file_path)[1].lower() in ['.mp4', '.mkv', '.webm', '.avi']:
                    self._load_video_file(file_path)
                    break
        event.acceptProposedAction()

    def _hide_controls(self):
        is_playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        if self.is_fullscreen and is_playing:
            self.setCursor(Qt.CursorShape.BlankCursor)
            self.controls_container.setVisible(False)

    def open_file_from_path(self, file_path):
        if file_path and os.path.exists(file_path):
            if any(file_path.lower().endswith(ext) for ext in ['.mp4', '.mkv', '.webm', '.avi']):
                self._load_video_file(file_path)
            else:
                QMessageBox.warning(self, "Tipe File Tidak Didukung", "File bukan video yang didukung.")

    def _toggle_url_bar(self):
        self.url_bar_widget.setVisible(not self.url_bar_widget.isVisible())

    def _open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Pilih Video", "", "Video Files (*.mp4 *.mkv *.webm *.avi)")
        if file_path: self._load_video_file(file_path)

    # --- PERUBAHAN UTAMA: Logika baru untuk memuat video, jauh lebih sederhana ---
    def _load_video_file(self, file_path_or_url):
        self.setWindowTitle(f"Macan Player - Memuat...")
        self._stop_video()
        self.subtitles = [] # Reset subtitle

        is_url = "://" in file_path_or_url
        if is_url:
            source = QUrl(file_path_or_url)
            title = self.current_media_info.get('title', file_path_or_url)
            path_for_history = file_path_or_url
        else:
            source = QUrl.fromLocalFile(file_path_or_url)
            title = os.path.basename(file_path_or_url)
            path_for_history = file_path_or_url
            # Cek subtitle otomatis
            srt_path = os.path.splitext(file_path_or_url)[0] + ".srt"
            if os.path.exists(srt_path):
                self._load_srt_file(srt_path)

        self.current_media_info = {'path': path_for_history, 'title': title}
        self.player.setSource(source)
        self.player.play()

        self.setWindowTitle(f"Macan Player - {title}")
        self._update_control_states()
        self._add_to_history(path_for_history, title)

    def _load_and_play_from_playlist(self, file_path):
        self._load_video_file(file_path)
        self._update_playlist_nav_buttons()

    def _play_next_video(self):
        current_index = self.playlist_widget.get_current_index()
        playlist_data = self.playlist_widget.get_playlist_data()
        new_index = current_index + 1
        if 0 <= new_index < len(playlist_data):
            self._load_and_play_from_playlist(playlist_data[new_index]['path'])
            self.playlist_widget._update_selection(new_index)

    def _play_previous_video(self):
        current_index = self.playlist_widget.get_current_index()
        playlist_data = self.playlist_widget.get_playlist_data()
        new_index = current_index - 1
        if 0 <= new_index < len(playlist_data):
            self._load_and_play_from_playlist(playlist_data[new_index]['path'])
            self.playlist_widget._update_selection(new_index)

    def _update_playlist_nav_buttons(self):
        playlist_data = self.playlist_widget.get_playlist_data()
        current_index = self.playlist_widget.get_current_index()
        self.btn_prev_playlist.setEnabled(current_index > 0)
        self.btn_next_playlist.setEnabled(current_index < len(playlist_data) - 1)

    def _toggle_playlist_window(self):
        if self.playlist_widget.isVisible(): self.playlist_widget.hide()
        else: self.playlist_widget.show()

    def _open_srt_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Pilih Subtitle", "", "SRT Files (*.srt)")
        if file_path: self._load_srt_file(file_path)

    def _time_to_ms(self, t):
        return (t.hour() * 3600 + t.minute() * 60 + t.second()) * 1000 + t.msec()

    def _load_srt_file(self, file_path):
        subs = []
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f: content = f.read()
            subtitle_blocks = content.strip().replace('\r\n', '\n').split('\n\n')
            for block in subtitle_blocks:
                lines = block.split('\n')
                if len(lines) >= 3:
                    time_match = re.match(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})', lines[1])
                    if time_match:
                        start_time = QTime.fromString(time_match.group(1), "hh:mm:ss,zzz")
                        end_time = QTime.fromString(time_match.group(2), "hh:mm:ss,zzz")
                        subs.append({'start_ms': self._time_to_ms(start_time), 'end_ms': self._time_to_ms(end_time), 'text': "\n".join(lines[2:]).strip()})
            self.subtitles = subs
            QMessageBox.information(self, "Sukses", f"{len(subs)} baris subtitle dimuat.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Gagal memuat subtitle: {e}")
            self.subtitles = []

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.splash_label:
            self.splash_label.setGeometry(0, 0, self.video_widget.width(), self.video_widget.height())

    def _load_from_url(self):
        url = self.url_input.text().strip()
        if not url: return
        self.setWindowTitle("Macan Player - Mengambil info video...")
        self.worker = YouTubeDLWorker(url)
        self.thread = threading.Thread(target=self.worker.run, daemon=True)
        self.worker.finished.connect(self._on_youtube_dl_finished)
        self.thread.start()

    def _on_youtube_dl_finished(self, video_url, title, error):
        if error or not video_url:
            QMessageBox.critical(self, "Error URL", error or "URL tidak valid.")
            self.setWindowTitle("Macan Player")
            return
        self.current_media_info = {'path': video_url, 'title': title}
        self._load_video_file(video_url)

    def _toggle_play_pause(self):
        state = self.player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _stop_video(self):
        self.player.stop()
        self.subtitles = []
        self._update_time_label(0, 0)
        self.position_slider.setValue(0)
        # Hapus frame terakhir dari tampilan
        self.video_widget.clear()
        self._update_control_states()


    def _skip_forward(self):
        new_pos = self.player.position() + self.SKIP_INTERVAL
        self._set_position(new_pos)

    def _skip_backward(self):
        new_pos = max(0, self.player.position() - self.SKIP_INTERVAL)
        self._set_position(new_pos)

    def _change_playback_speed(self):
        self.current_speed_index = (self.current_speed_index + 1) % len(self.playback_speeds)
        new_speed = self.playback_speeds[self.current_speed_index]
        self.player.setPlaybackRate(new_speed)
        self.btn_speed.setText(f"{new_speed}x")

    def _update_position(self, position):
        if not self.position_slider.isSliderDown():
            self.position_slider.setValue(position)
        self._update_time_label(position, self.player.duration())
        self.mini_player_widget.update_position(position)

    def _update_duration(self, duration):
        self.position_slider.setRange(0, duration)
        self.mini_player_widget.update_duration(duration)

    def _set_position(self, position):
        self.player.setPosition(position)

    def _set_volume(self, value):
        self.audio_output.setVolume(value / 100.0)
        # Jika volume > 0, pastikan tidak di-mute
        if value > 0 and self.audio_output.isMuted():
            self.audio_output.setMuted(False)
        elif value == 0:
             self.audio_output.setMuted(True)


    def _toggle_mute(self):
        self.audio_output.setMuted(not self.audio_output.isMuted())

    def _update_volume_icon(self):
        if not qta: return
        volume = int(self.audio_output.volume() * 100)
        is_muted = self.audio_output.isMuted()

        if is_muted or volume == 0:
            icon = qta.icon('fa5s.volume-mute')
        elif 0 < volume <= 50:
            icon = qta.icon('fa5s.volume-down')
        else:
            icon = qta.icon('fa5s.volume-up')
        self.btn_mute.setIcon(icon)

    def _sync_main_volume_slider(self):
        volume_float = self.audio_output.volume()
        is_muted = self.audio_output.isMuted()
        if not self.volume_slider.isSliderDown():
            if is_muted:
                self.volume_slider.setValue(0)
            else:
                self.volume_slider.setValue(int(volume_float * 100))
        self._update_volume_icon()


    def _update_time_label(self, position, duration):
        if duration > 0:
            pos_time = QTime(0, 0, 0).addMSecs(position)
            dur_time = QTime(0, 0, 0).addMSecs(duration)
            fmt = 'hh:mm:ss' if duration >= 3600000 else 'mm:ss'
            self.time_label.setText(f"{pos_time.toString(fmt)} / {dur_time.toString(fmt)}")
        else:
            self.time_label.setText("00:00 / 00:00")

    def _update_control_states(self):
        is_media_loaded = self.player.mediaStatus() != QMediaPlayer.MediaStatus.NoMedia

        if is_media_loaded:
            self.splash_label.hide()
        else:
            self.splash_label.show()
            self.video_widget.clear()

        self.btn_play_pause.setEnabled(is_media_loaded)
        self.btn_stop.setEnabled(is_media_loaded)
        self.btn_mini_player.setEnabled(is_media_loaded)
        self._update_playlist_nav_buttons()

    def _update_play_pause_icon(self, state):
        is_playing = state == QMediaPlayer.PlaybackState.PlayingState
        if qta:
            icon = qta.icon('fa5s.pause') if is_playing else qta.icon('fa5s.play')
            self.btn_play_pause.setIcon(icon)
        self.mini_player_widget.update_play_pause_icon(is_playing)

    def _handle_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            current_index = self.playlist_widget.get_current_index()
            playlist_data = self.playlist_widget.get_playlist_data()
            if current_index < len(playlist_data) - 1:
                self._play_next_video()
            else:
                self._stop_video()

    # --- PERBAIKAN: Logika untuk toggle layar penuh ---
    def _toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            # Simpan posisi dan ukuran jendela sebelum masuk mode layar penuh
            self.normal_geometry = self.geometry()
            self.showFullScreen()
            # Kontrol akan disembunyikan oleh timer saat mouse tidak bergerak
        else:
            self.showNormal()
            # Kembalikan ke posisi dan ukuran jendela sebelumnya
            if self.normal_geometry:
                self.setGeometry(self.normal_geometry)
            self.controls_container.setVisible(True)
            self.setCursor(Qt.CursorShape.ArrowCursor) # Pastikan kursor terlihat lagi

    # --- PERBAIKAN: Logika untuk event tombol keyboard ---
    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_F11:
            self._toggle_fullscreen()
        elif key == Qt.Key.Key_Escape and self.is_fullscreen:
            self._toggle_fullscreen()
        # --- PERUBAHAN: Tombol spasi kini untuk menampilkan kontrol di mode layar penuh ---
        elif key == Qt.Key.Key_Space:
            if self.is_fullscreen:
                self.controls_container.setVisible(True)
                self.setCursor(Qt.CursorShape.ArrowCursor)
                self.controls_hide_timer.start()
            # Fungsi play/pause untuk spasi dihilangkan
        elif key == Qt.Key.Key_Right:
            self._skip_forward()
        elif key == Qt.Key.Key_Left:
            self._skip_backward()
        else:
            super().keyPressEvent(event)
    
    def mouseMoveEvent(self, event):
        # Tampilkan kontrol dan reset timer saat mouse bergerak
        if self.is_fullscreen:
            self.controls_container.setVisible(True)
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.controls_hide_timer.start()
        super().mouseMoveEvent(event)

    def eventFilter(self, source, event):
        if source is self.video_widget:
            if not self.is_fullscreen:
                if event.type() == QEvent.Type.Enter:
                    self.controls_container.setVisible(True)
                    return True
            if event.type() == QEvent.Type.DragEnter:
                self.dragEnterEvent(event)
                return True
            elif event.type() == QEvent.Type.Drop:
                self.dropEvent(event)
                return True
            if event.type() == QEvent.Type.MouseButtonPress:
                if self.btn_play_pause.isEnabled():
                    self._toggle_play_pause()
                    return True
            elif event.type() == QEvent.Type.MouseButtonDblClick:
                self._toggle_fullscreen()
                return True
        return super().eventFilter(source, event)

    def closeEvent(self, event):
        self._save_config()
        self.playlist_widget.close()
        self.mini_player_widget.close()
        self.history_window.close()
        
        # Hentikan thread thumbnail
        self.thumbnail_thread.quit()
        self.thumbnail_thread.wait()
        
        self.player.stop()

        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    player = ModernVideoPlayer()

    if len(sys.argv) > 1:
        QTimer.singleShot(0, lambda: player.open_file_from_path(sys.argv[1]))

    player.show()
    sys.exit(app.exec())