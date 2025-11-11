import sys
import os
import re
import threading
import json
import time
import subprocess
from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QFileDialog, QLineEdit, QLabel, QSlider, QMessageBox, QListWidget, QListWidgetItem,
    QAbstractItemView, QDialog
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtCore import (
    QUrl, Qt, QTime, QEvent, QSize, QTimer, pyqtSignal, QObject, QRect,
    QThread, pyqtSlot
)
from PyQt6.QtGui import QIcon, QPixmap, QAction, QImage

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

# --- IMPLEMENTASI FITUR BARU: THUMBNAIL PREVIEW (DIMULAI) ---

class ThumbnailPreviewWidget(QWidget):
    """
    Widget frameless untuk menampilkan thumbnail preview di atas slider.
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
            # Skalakan pixmap agar pas di dalam label dengan menjaga aspect ratio
            scaled_pixmap = pixmap.scaled(self.size() - QSize(4, 4), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.label.setPixmap(scaled_pixmap)
        else:
            self.label.setText("Gagal")

class ThumbnailGenerator(QObject):
    """
    Worker yang berjalan di thread terpisah untuk generate thumbnail menggunakan FFmpeg.
    """
    thumbnail_ready = pyqtSignal(QPixmap, float)

    @pyqtSlot(str, int, float)
    def generate(self, video_path, timestamp_ms, request_time):
        """Mengekstrak frame dari video pada timestamp tertentu."""
        if not video_path or not os.path.exists(video_path) or timestamp_ms < 0:
            return

        timestamp_sec = timestamp_ms / 1000.0
        
        command = [
            'ffmpeg',
            '-ss', str(timestamp_sec),
            '-i', video_path,
            '-vframes', '1',    # Hanya 1 frame
            '-s', '160x90',      # Ukuran output
            '-f', 'image2pipe',  # Output ke pipe
            '-vcodec', 'png',    # Format output
            '-'                  # Output ke stdout
        ]

        try:
            # Siapkan flag untuk menyembunyikan jendela konsol di Windows
            creation_flags = 0
            if os.name == 'nt':
                creation_flags = subprocess.CREATE_NO_WINDOW

            # Jalankan command FFmpeg dengan flag tambahan untuk menyembunyikan jendela konsol
            process = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                creationflags=creation_flags
            )
            pixmap = QPixmap()
            pixmap.loadFromData(process.stdout, "PNG")
            self.thumbnail_ready.emit(pixmap, request_time)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            # Jika gagal, kirim pixmap kosong
            print(f"Kesalahan FFmpeg: {e.stderr.decode('utf-8') if hasattr(e, 'stderr') else e}")
            self.thumbnail_ready.emit(QPixmap(), request_time)

# --- IMPLEMENTASI FITUR BARU: THUMBNAIL PREVIEW (SELESAI) ---


# --- MODIFIKASI DIMULAI: Membuat slider yang bisa diklik DAN mendeteksi hover ---
class ClickableSlider(QSlider):
    """
    Slider kustom yang memungkinkan pengguna mengklik untuk mengubah posisi
    dan memancarkan sinyal saat cursor mouse bergerak di atasnya.
    """
    # Sinyal baru untuk thumbnail preview
    hover_move = pyqtSignal(int) # Memancarkan posisi x dari cursor
    hover_leave = pyqtSignal()   # Dipancarkan saat cursor meninggalkan widget

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Aktifkan pelacakan mouse untuk mendeteksi hover bahkan saat tombol tidak ditekan
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

    # Event baru untuk menangani hover
    def mouseMoveEvent(self, event):
        """Pancarkan posisi x cursor saat bergerak di atas slider."""
        self.hover_move.emit(event.pos().x())
        super().mouseMoveEvent(event)
        
    def leaveEvent(self, event):
        """Pancarkan sinyal saat cursor meninggalkan slider."""
        self.hover_leave.emit()
        super().leaveEvent(event)
# --- MODIFIKASI SELESAI ---


class MiniPlayerWindow(QWidget):
    """
    Jendela pemutar mini dengan kontrol dasar.
    Berbagi instance QMediaPlayer yang sama dengan jendela utama.
    """
    closing = pyqtSignal()

    def __init__(self, player, audio_output, parent=None):
        super().__init__(parent)
        self.player = player
        self.audio_output = audio_output

        self.is_muted = self.audio_output.isMuted()
        self.last_volume = int(self.audio_output.volume() * 100) if not self.is_muted else 50

        self._setup_ui()
        self._connect_signals()
        
        self._update_play_pause_icon(self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
        self._update_position(self.player.position())
        self._update_duration(self.player.duration())
        self._update_volume_icon()


    def _setup_ui(self):
        self.setWindowTitle("Macan Player - Mini")
        self.setFixedSize(480, 320)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        
        icon_path = "player.ico"
        if hasattr(sys, "_MEIPASS"):
            icon_path = os.path.join(sys._MEIPASS, icon_path)
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.setStyleSheet("""
            background-color: #1c1c1c;
            color: #ecf0f1;
        """)

        self.video_widget = QVideoWidget()

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
        self.btn_play_pause.clicked.connect(self._toggle_play_pause)
        self.btn_stop.clicked.connect(self._stop_video)
        self.position_slider.sliderMoved.connect(self._set_position)
        
        self.btn_mute.clicked.connect(self._toggle_mute)
        self.volume_slider.valueChanged.connect(self._set_volume)
        
        self.player.playbackStateChanged.connect(self._update_control_states)
        self.player.positionChanged.connect(self._update_position)
        self.player.durationChanged.connect(self._update_duration)
        
        self.audio_output.volumeChanged.connect(self._sync_volume_slider)

    def _toggle_play_pause(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _stop_video(self):
        self.player.stop()

    def _set_position(self, position):
        self.player.setPosition(position)
    
    def _set_volume(self, value):
        self.audio_output.setVolume(value / 100.0)

    def _toggle_mute(self):
        self.is_muted = not self.is_muted
        if self.is_muted:
            self.last_volume = self.volume_slider.value()
            self.volume_slider.setValue(0)
        else:
            self.volume_slider.setValue(self.last_volume if self.last_volume > 0 else 50)
        self._update_volume_icon()
        
    def _update_volume_icon(self):
        if not qta: return
        volume = self.volume_slider.value()
        if self.is_muted or volume == 0: icon = qta.icon('fa5s.volume-mute')
        elif 0 < volume <= 50: icon = qta.icon('fa5s.volume-down')
        else: icon = qta.icon('fa5s.volume-up')
        self.btn_mute.setIcon(icon)

    def _sync_volume_slider(self, volume_float):
        value = int(volume_float * 100)
        if not self.volume_slider.isSliderDown():
            self.volume_slider.setValue(value)
        self.is_muted = value == 0
        self._update_volume_icon()

    def _update_position(self, position):
        if not self.position_slider.isSliderDown():
            self.position_slider.setValue(position)

    def _update_duration(self, duration):
        self.position_slider.setRange(0, duration)

    def _update_control_states(self):
        is_playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self._update_play_pause_icon(is_playing)

    def _update_play_pause_icon(self, is_playing):
        if qta:
            icon = qta.icon('fa5s.pause') if is_playing else qta.icon('fa5s.play')
            self.btn_play_pause.setIcon(icon)

    def closeEvent(self, event):
        self.closing.emit()
        super().closeEvent(event)


class YouTubeDLWorker(QObject):
    """
    Worker to run yt-dlp in a separate thread so it doesn't freeze the UI.
    """
    finished = pyqtSignal(str, str, str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        if not YoutubeDL:
            self.finished.emit(None, None, "Pustaka yt-dlp tidak terinstal.")
            return

        try:
            ydl_opts = {
                'format': 'bestvideo+bestaudio/best',
                'quiet': True,
                'no_warnings': True,
            }
            with YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(self.url, download=False)
                title = info_dict.get('title', 'Judul tidak diketahui')
                formats = info_dict.get('formats', [info_dict])

                for f in reversed(formats):
                    if f.get('url') and f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                        self.finished.emit(f['url'], title, None)
                        return

                self.finished.emit(None, None, "Tidak dapat menemukan URL streaming yang valid dengan video dan audio.")

        except Exception as e:
            self.finished.emit(None, None, f"Error dari yt-dlp: {str(e)}")


class PlaylistWidget(QWidget):
    """
    Separate window for managing the video playlist.
    """
    play_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Macan Player - Playlist")
        self.setGeometry(1100, 100, 300, 400)
        icon_path = "player.ico"
        if hasattr(sys, "_MEIPASS"):
            icon_path = os.path.join(sys._MEIPASS, icon_path)
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
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
        self.btn_add_file.setToolTip("Tambahkan file video ke daftar putar")

        self.btn_remove = QPushButton(" Hapus")
        if qta: self.btn_remove.setIcon(qta.icon('fa5s.trash'))
        self.btn_remove.setToolTip("Hapus video dari playlist")

        self.btn_clear = QPushButton(" Hapus Semua")
        if qta: self.btn_clear.setIcon(qta.icon('fa5s.times-circle'))
        self.btn_clear.setToolTip("Hapus semua video dari playlist")

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
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if os.path.exists(file_path):
                file_extension = os.path.splitext(file_path)[1].lower()
                if file_extension in ['.mp4', '.mkv', '.webm', '.avi']:
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
        if 0 <= index < self.list_widget.count():
            self.list_widget.setCurrentRow(index)

    def get_current_index(self):
        return self.list_widget.currentRow()

    def get_playlist_data(self):
        return self.playlist

    def set_playlist_data(self, data):
        self.playlist = data
        self._update_ui()

    def _save_playlist(self):
        config_path = os.path.join(os.path.dirname(__file__), "player_config.json")
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            config = {}

        config['playlist'] = self.playlist

        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)


class HistoryWindow(QDialog):
    """Jendela untuk menampilkan riwayat video yang telah ditonton."""
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
        self.btn_remove_selected.setToolTip("Hapus item yang dipilih dari riwayat")

        self.btn_clear_all = QPushButton(" Hapus Semua")
        if qta: self.btn_clear_all.setIcon(qta.icon('fa5s.times'))
        self.btn_clear_all.setToolTip("Hapus seluruh riwayat tontonan")

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
        selected_data = item.data(Qt.ItemDataRole.UserRole)
        self.history_item_selected.emit(selected_data)
        self.accept()
        
    def _remove_selected(self):
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "Info", "Pilih item yang ingin dihapus terlebih dahulu.")
            return
        
        index = self.list_widget.row(selected_items[0])
        self.delete_selected_requested.emit(index)

    def _clear_all(self):
        reply = QMessageBox.question(self, "Konfirmasi", 
                                     "Anda yakin ingin menghapus SEMUA riwayat tontonan? Tindakan ini tidak dapat dibatalkan.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            self.clear_all_requested.emit()


class ModernVideoPlayer(QWidget):
    """
    Main video player window with all controls.
    """
    # --- PENAMBAHAN BARU: Sinyal untuk thumbnail worker ---
    request_thumbnail = pyqtSignal(str, int, float)

    def __init__(self):
        super().__init__()
        self.is_fullscreen = False
        self.splash_label = None
        self.subtitles = []
        self.is_muted = False
        self.last_volume = 50
        self.SKIP_INTERVAL = 10000
        self.playback_speeds = [0.5, 1.0, 1.5, 2.0]
        self.current_speed_index = 1
        self.audio_modes = ["Flat", "Bass Boost", "Vocal Clarity"]
        self.current_audio_mode_index = 0
        self.config_path = os.path.join(os.path.dirname(__file__), "player_config.json")
        
        self.themes = {}
        self.theme_names = []
        self.current_theme_index = 0
        self.history = []
        self.current_media_info = {}
        self.auto_resume_timer = QTimer(self)
        self.auto_resume_timer.setInterval(5000)

        self.playlist_widget = PlaylistWidget()
        self.history_window = HistoryWindow(self.history, self)

        self.cursor_hide_timer = QTimer(self)
        self.cursor_hide_timer.setInterval(3000)
        self.cursor_hide_timer.setSingleShot(True)

        self.controls_hide_timer = QTimer(self)
        self.controls_hide_timer.setInterval(2500)
        self.controls_hide_timer.setSingleShot(True)

        self._setup_player()
        self.mini_player_widget = MiniPlayerWindow(self.player, self.audio_output)
        
        # --- PENAMBAHAN BARU: Setup untuk thumbnail preview ---
        self._setup_thumbnail_feature()

        self._setup_themes()
        self._load_config()
        self._setup_ui()
        self._connect_signals()
        self._apply_theme(self.theme_names[self.current_theme_index])

        self.setAcceptDrops(True)
        self.video_widget.setAcceptDrops(True)
        self.video_widget.setMouseTracking(True)
        self.controls_container.setMouseTracking(True)
        # --- KOREKSI: Mouse tracking di main window tidak lagi diperlukan untuk kontrol ---
        # self.setMouseTracking(True)

    def _is_ffmpeg_available(self):
        """Mengecek apakah FFmpeg dapat dieksekusi dari PATH."""
        try:
            # Siapkan flag untuk menyembunyikan jendela konsol di Windows
            creation_flags = 0
            if os.name == 'nt':
                creation_flags = subprocess.CREATE_NO_WINDOW
            subprocess.run(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creation_flags)
            return True
        except FileNotFoundError:
            return False

    def _setup_thumbnail_feature(self):
        """Inisialisasi semua komponen untuk fitur thumbnail preview."""
        self.ffmpeg_available = self._is_ffmpeg_available()
        self.last_thumbnail_request_time = 0.0

        if not self.ffmpeg_available:
            print("Peringatan: FFmpeg tidak ditemukan di PATH. Fitur thumbnail preview tidak akan aktif.")
            return

        self.thumbnail_preview = ThumbnailPreviewWidget()
        self.thumbnail_thread = QThread()
        self.thumbnail_generator = ThumbnailGenerator()
        self.thumbnail_generator.moveToThread(self.thumbnail_thread)
        self.thumbnail_thread.start()

    def _setup_player(self):
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)

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
            with open(self.config_path, "r") as f:
                config = json.load(f)

            self.last_volume = config.get('last_volume', 50)
            self.playlist_widget.set_playlist_data(config.get('playlist', []))

            saved_theme = config.get('theme', 'Dark')
            if saved_theme in self.theme_names:
                self.current_theme_index = self.theme_names.index(saved_theme)

            self.history = config.get('history', [])
            self.history_window.history_data = self.history
            self.history_window.populate_list()

            resume_data = config.get('auto_resume')
            if resume_data and resume_data.get('path'):
                QTimer.singleShot(100, lambda: self._handle_auto_resume(resume_data))

        except (FileNotFoundError, json.JSONDecodeError):
            print("File konfigurasi tidak ditemukan atau tidak valid, menggunakan pengaturan default.")

    def _save_config(self):
        auto_resume_data = {}
        if self.player.source().isValid():
            auto_resume_data = {
                'path': self.current_media_info.get('path'),
                'title': self.current_media_info.get('title'),
                'position': self.player.position()
            }
        
        config = {
            'last_volume': self.volume_slider.value(),
            'playlist': self.playlist_widget.get_playlist_data(),
            'theme': self.theme_names[self.current_theme_index],
            'auto_resume': auto_resume_data,
            'history': self.history
        }
        try:
            with open(self.config_path, "w") as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            print(f"Gagal menyimpan konfigurasi: {e}")

    def _setup_ui(self):
        self.setWindowTitle("Macan Video Player")
        self.setGeometry(100, 100, 700, 550)
        icon_path = "player.ico"
        if hasattr(sys, "_MEIPASS"):
            icon_path = os.path.join(sys._MEIPASS, icon_path)
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        self.setStyleSheet(self.themes["Dark"])

        self.video_widget = QVideoWidget()
        self.video_widget.installEventFilter(self)
        self.player.setVideoOutput(self.video_widget)

        self.splash_label = QLabel(self.video_widget)
        splash_path = "splash.png"
        if hasattr(sys, "_MEIPASS"):
            splash_path = os.path.join(sys._MEIPASS, splash_path)

        if os.path.exists(splash_path):
            pixmap = QPixmap(splash_path)
            self.splash_label.setPixmap(pixmap.scaled(QSize(480, 270), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.splash_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.splash_label.setStyleSheet("background-color: transparent;")
        else:
            self.splash_label.setText("Macan Player")
            self.splash_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.splash_label.setStyleSheet("background-color: transparent; font-size: 30px; font-weight: bold;")
        self.splash_label.show()

        self.subtitle_label = QLabel(self.video_widget)
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setStyleSheet("background-color: rgba(0, 0, 0, 170); color: white; padding: 8px; border-radius: 5px; font-size: 16px;")
        self.subtitle_label.hide()

        self.btn_open = QPushButton()
        self.btn_open.setToolTip("Buka file video dari komputer Anda (Ctrl+O)")
        if qta: self.btn_open.setIcon(qta.icon('fa5s.folder-open'))

        self.btn_open_srt = QPushButton()
        self.btn_open_srt.setToolTip("Buka file subtitle (.srt)")
        if qta: self.btn_open_srt.setIcon(qta.icon('fa5s.closed-captioning'))

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Masukkan URL video (termasuk YouTube)...")
        self.url_input.setToolTip("Masukkan URL video dari web (misal: YouTube) lalu tekan Enter.")

        self.btn_load_url = QPushButton()
        self.btn_load_url.setToolTip("Muat video dari URL")
        if qta: self.btn_load_url.setIcon(qta.icon('fa5s.link'))

        self.btn_toggle_url_bar = QPushButton()
        self.btn_toggle_url_bar.setToolTip("Tampilkan/Sembunyikan input URL")
        if qta: self.btn_toggle_url_bar.setIcon(qta.icon('fa5s.globe'))

        self.btn_show_playlist = QPushButton()
        self.btn_show_playlist.setToolTip("Tampilkan/Sembunyikan Playlist")
        if qta: self.btn_show_playlist.setIcon(qta.icon('fa5s.list'))
        
        self.btn_show_history = QPushButton()
        self.btn_show_history.setToolTip("Tampilkan Riwayat Tontonan")
        if qta: self.btn_show_history.setIcon(qta.icon('fa5s.history'))

        self.position_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.setToolTip("Geser atau Klik untuk mencari posisi video")

        self.time_label = QLabel("00:00 / 00:00")

        self.btn_prev_playlist = QPushButton()
        self.btn_prev_playlist.setToolTip("Video Sebelumnya")
        if qta: self.btn_prev_playlist.setIcon(qta.icon('fa5s.step-backward'))
        self.btn_prev_playlist.setEnabled(False)

        self.btn_next_playlist = QPushButton()
        self.btn_next_playlist.setToolTip("Video Berikutnya")
        if qta: self.btn_next_playlist.setIcon(qta.icon('fa5s.step-forward'))
        self.btn_next_playlist.setEnabled(False)

        self.btn_play_pause = QPushButton()
        self._update_play_pause_icon()
        self.btn_play_pause.setEnabled(False)
        self.btn_play_pause.setToolTip("Putar / Jeda (Klik Tombol atau Klik Video)")

        self.btn_stop = QPushButton()
        self.btn_stop.setToolTip("Hentikan video")
        if qta: self.btn_stop.setIcon(qta.icon('fa5s.stop'))
        self.btn_stop.setEnabled(False)

        self.btn_speed = QPushButton(f"{self.playback_speeds[self.current_speed_index]}x")
        self.btn_speed.setToolTip("Ubah kecepatan pemutaran video")

        self.btn_mute = QPushButton()
        self.btn_mute.setToolTip("Bisukan / Aktifkan suara")

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.last_volume)
        self.audio_output.setVolume(self.last_volume / 100.0)
        self.volume_slider.setToolTip("Atur volume suara")
        self.volume_slider.setFixedWidth(120)
        if qta: self._update_volume_icon()
        
        self.btn_mini_player = QPushButton()
        self.btn_mini_player.setToolTip("Tampilkan mode pemutar mini")
        if qta: self.btn_mini_player.setIcon(qta.icon('fa5s.window-minimize'))
        self.btn_mini_player.setEnabled(False)

        self.btn_fullscreen = QPushButton()
        self.btn_fullscreen.setToolTip("Mode layar penuh (F11 atau Klik Ganda)")
        if qta: self.btn_fullscreen.setIcon(qta.icon('fa5s.expand'))
        
        self.btn_change_theme = QPushButton()
        current_theme_name = self.theme_names[self.current_theme_index]
        self.btn_change_theme.setToolTip(f"Ganti Tema (Sekarang: {current_theme_name})")
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
        self.auto_resume_timer.timeout.connect(self._save_current_position)

        self.btn_mini_player.clicked.connect(self._show_mini_player)
        self.mini_player_widget.closing.connect(self._show_main_from_mini)

        self.volume_slider.valueChanged.connect(self._set_volume)
        self.position_slider.sliderMoved.connect(self._set_position)

        self.player.positionChanged.connect(self._update_position)
        self.player.positionChanged.connect(self._update_subtitle)
        self.player.durationChanged.connect(self._update_duration)
        self.player.playbackStateChanged.connect(self._update_control_states)
        self.player.mediaStatusChanged.connect(self._handle_media_status_changed)
        self.player.errorOccurred.connect(self._handle_error)

        self.audio_output.volumeChanged.connect(self._sync_main_volume_slider)
        self.playlist_widget.play_requested.connect(self._load_and_play_from_playlist)
        self.cursor_hide_timer.timeout.connect(self._hide_cursor)
        self.controls_hide_timer.timeout.connect(self._hide_controls)
        
        # --- PENAMBAHAN BARU: Hubungkan sinyal untuk thumbnail ---
        if self.ffmpeg_available:
            self.position_slider.hover_move.connect(self._show_thumbnail_preview)
            self.position_slider.hover_leave.connect(self.thumbnail_preview.hide)
            self.thumbnail_generator.thumbnail_ready.connect(self._update_thumbnail)
            self.request_thumbnail.connect(self.thumbnail_generator.generate, Qt.ConnectionType.QueuedConnection)
    
    # --- PENAMBAHAN BARU: SLOT UNTUK THUMBNAIL PREVIEW ---
    def _show_thumbnail_preview(self, x_pos):
        """Menampilkan dan meminta thumbnail saat mouse hover di atas slider."""
        # Cek apakah video valid dan bisa di-preview
        video_path = self.current_media_info.get('path', '')
        is_url = "://" in video_path
        if not self.player.source().isValid() or self.player.duration() <= 0 or is_url:
            return
        
        # Hitung timestamp berdasarkan posisi x cursor
        value = self.position_slider.minimum() + (self.position_slider.maximum() - self.position_slider.minimum()) * x_pos / self.position_slider.width()
        timestamp_ms = int(value)

        # Atur posisi widget preview di atas cursor
        global_pos = self.position_slider.mapToGlobal(self.pos())
        preview_x = global_pos.x() + self.position_slider.x() + x_pos - (self.thumbnail_preview.width() / 2)
        preview_y = global_pos.y() + self.position_slider.y() - self.thumbnail_preview.height() - 5
        self.thumbnail_preview.move(int(preview_x), int(preview_y))
        
        if not self.thumbnail_preview.isVisible():
            self.thumbnail_preview.show()
            self.thumbnail_preview.label.setText("Memuat...") # Reset label

        # Kirim permintaan untuk generate thumbnail
        current_time = time.time()
        self.last_thumbnail_request_time = current_time
        self.request_thumbnail.emit(video_path, timestamp_ms, current_time)

    @pyqtSlot(QPixmap, float)
    def _update_thumbnail(self, pixmap, request_time):
        """Memperbarui gambar di widget preview, hanya jika request masih yang terbaru."""
        if request_time == self.last_thumbnail_request_time and self.thumbnail_preview.isVisible():
            self.thumbnail_preview.set_thumbnail(pixmap)
    # --- AKHIR PENAMBAHAN SLOT THUMBNAIL ---

    def _handle_auto_resume(self, resume_data):
        file_name = resume_data.get('title', 'video terakhir')
        position_ms = resume_data.get('position', 0)
        pos_time = QTime(0, 0, 0).addMSecs(position_ms)
        
        reply = QMessageBox.question(self, "Lanjutkan Menonton?",
                                     f"Anda terakhir menonton '{file_name}' pada posisi {pos_time.toString('hh:mm:ss')}.\n\nIngin melanjutkan?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.Yes)
        
        if reply == QMessageBox.StandardButton.Yes:
            path = resume_data.get('path')
            title = resume_data.get('title')
            self.current_media_info = {'path': path, 'title': title}
            
            if "://" in path:
                self.player.setSource(QUrl(path))
            else:
                self.player.setSource(QUrl.fromLocalFile(path))
                
            QTimer.singleShot(500, lambda: self.player.setPosition(position_ms))
            self.player.play()
            self._add_to_history(path, title)
            self.setWindowTitle(f"Macan Player - {title}")
            
    def _save_current_position(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._save_config()

    def _show_history_window(self):
        self.history_window.populate_list()
        self.history_window.exec()
        
    def _add_to_history(self, path, title):
        self.history = [item for item in self.history if item.get('path') != path]
        self.history.append({'path': path, 'title': title})
        if len(self.history) > 50:
            self.history = self.history[-50:]

    def _play_from_history(self, item):
        path = item.get('path')
        title = item.get('title')
        if not path: return
        
        self.current_media_info = {'path': path, 'title': title}
        
        if "://" in path:
            self.player.setSource(QUrl(path))
        else:
            self.player.setSource(QUrl.fromLocalFile(path))
        
        self.player.play()
        self._add_to_history(path, title)
        self.setWindowTitle(f"Macan Player - {title}")
    
    def _delete_history_item(self, index):
        actual_index = len(self.history) - 1 - index
        if 0 <= actual_index < len(self.history):
            del self.history[actual_index]
            self.history_window.populate_list()
            self._save_config()
            
    def _clear_all_history_data(self):
        self.history.clear()
        self.history_window.populate_list()
        self._save_config()
    
    def _show_mini_player(self):
        self.player.setVideoOutput(self.mini_player_widget.video_widget)
        self.mini_player_widget.show()
        self.hide()

    def _show_main_from_mini(self):
        self.player.setVideoOutput(self.video_widget)
        self.show()
        self.mini_player_widget.hide()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if os.path.exists(file_path):
                file_extension = os.path.splitext(file_path)[1].lower()
                if file_extension in ['.mp4', '.mkv', '.webm', '.avi']:
                    title = os.path.basename(file_path)
                    self.current_media_info = {'path': file_path, 'title': title}
                    self.playlist_widget.set_playlist_data([self.current_media_info])
                    self._load_and_play_from_playlist(file_path)
                    self.playlist_widget._update_selection(0)
                    self._update_playlist_nav_buttons()
                    self._add_to_history(file_path, title)
                    break
        event.acceptProposedAction()

    def _hide_controls(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.controls_container.setVisible(False)

    def open_file_from_path(self, file_path):
        if file_path and os.path.exists(file_path):
            allowed_extensions = ['.mp4', '.mkv', '.webm', '.avi']
            if any(file_path.lower().endswith(ext) for ext in allowed_extensions):
                title = os.path.basename(file_path)
                self.current_media_info = {'path': file_path, 'title': title}
                self.playlist_widget.set_playlist_data([self.current_media_info])
                self._load_and_play_from_playlist(file_path)
                self.playlist_widget._update_selection(0)
                self._update_playlist_nav_buttons()
                self._add_to_history(file_path, title)
            else:
                QMessageBox.warning(self, "Tipe File Tidak Didukung",
                                    f"File '{os.path.basename(file_path)}' sepertinya bukan file video yang didukung.")

    def _toggle_url_bar(self):
        is_visible = self.url_bar_widget.isVisible()
        self.url_bar_widget.setVisible(not is_visible)

    def _open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Pilih Video", "", "Video Files (*.mp4 *.mkv *.webm *.avi)")
        if file_path:
            title = os.path.basename(file_path)
            self.current_media_info = {'path': file_path, 'title': title}
            self.playlist_widget.set_playlist_data([self.current_media_info])
            self._load_and_play_from_playlist(file_path)
            self.playlist_widget._update_selection(0)
            self._update_playlist_nav_buttons()
            self._add_to_history(file_path, title)

    def _load_and_play_from_playlist(self, file_path):
        title = os.path.basename(file_path)
        self.current_media_info = {'path': file_path, 'title': title}
        self.player.setSource(QUrl.fromLocalFile(file_path))
        self.setWindowTitle(f"Macan Player - {title}")
        self.player.play()
        self._add_to_history(file_path, title)
        
        srt_path = os.path.splitext(file_path)[0] + ".srt"
        if os.path.exists(srt_path): self._load_srt_file(srt_path)
        self._update_playlist_nav_buttons()

    def _play_next_video(self):
        current_index = self.playlist_widget.get_current_index()
        if current_index is None: return

        playlist_data = self.playlist_widget.get_playlist_data()
        new_index = current_index + 1
        if 0 <= new_index < len(playlist_data):
            self._load_and_play_from_playlist(playlist_data[new_index]['path'])
            self.playlist_widget._update_selection(new_index)

    def _play_previous_video(self):
        current_index = self.playlist_widget.get_current_index()
        if current_index is None: return

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
        if self.playlist_widget.isVisible():
            self.playlist_widget.hide()
        else:
            self.playlist_widget.show()

    def _open_srt_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Pilih Subtitle", "", "SRT Files (*.srt)")
        if file_path: self._load_srt_file(file_path)

    def _time_to_ms(self, t):
        return (t.hour() * 3600 + t.minute() * 60 + t.second()) * 1000 + t.msec()

    def _load_srt_file(self, file_path):
        self.subtitles = []
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                content = f.read()
            subtitle_blocks = content.strip().replace('\r\n', '\n').split('\n\n')

            for block in subtitle_blocks:
                lines = block.split('\n')
                if len(lines) >= 3:
                    time_line = lines[1]
                    text = "\n".join(lines[2:])
                    time_match = re.match(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})', time_line)
                    if time_match:
                        start_time_str, end_time_str = time_match.groups()
                        start_time = QTime.fromString(start_time_str, "hh:mm:ss,zzz")
                        end_time = QTime.fromString(end_time_str, "hh:mm:ss,zzz")
                        self.subtitles.append({
                            'start_ms': self._time_to_ms(start_time),
                            'end_ms': self._time_to_ms(end_time),
                            'text': text.strip()
                        })
            if self.subtitles:
                QMessageBox.information(self, "Sukses", f"{len(self.subtitles)} baris subtitle berhasil dimuat.")
            else:
                QMessageBox.warning(self, "Gagal Memuat", "Tidak dapat menemukan subtitle yang valid di dalam file.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Gagal memuat file subtitle: {e}")
            self.subtitles = []

    def _update_subtitle(self, position):
        if not self.subtitles: return
        current_text = ""
        for sub in self.subtitles:
            if sub['start_ms'] <= position <= sub['end_ms']:
                current_text = sub['text']
                break
        if current_text:
            self.subtitle_label.setText(current_text)
            if not self.subtitle_label.isVisible(): self.subtitle_label.show()
        else:
            if self.subtitle_label.isVisible(): self.subtitle_label.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.splash_label:
            self.splash_label.setGeometry(0, 0, self.video_widget.width(), self.video_widget.height())
        label_width = self.video_widget.width() * 0.9
        x = int((self.video_widget.width() - label_width) / 2)
        y = int(self.video_widget.height() - 100)
        self.subtitle_label.setGeometry(x, y, int(label_width), 80)

    def _load_from_url(self):
        url = self.url_input.text().strip()
        if not url: return
        self.setWindowTitle("Macan Player - Mengambil info video...")
        self.worker = YouTubeDLWorker(url)
        self.thread = threading.Thread(target=self.worker.run, daemon=True)
        self.worker.finished.connect(self._on_youtube_dl_finished)
        self.thread.start()

    def _on_youtube_dl_finished(self, video_url, title, error):
        if error:
            QMessageBox.critical(self, "Error URL", error)
            self.setWindowTitle("Macan Player - Gagal memuat URL")
            return
        if video_url:
            self.current_media_info = {'path': video_url, 'title': title}
            self.playlist_widget.set_playlist_data([self.current_media_info])
            self.playlist_widget._update_selection(0)
            self.player.setSource(QUrl(video_url))
            if title: self.setWindowTitle(f"Macan Player - {title}")
            else: self.setWindowTitle("Macan Player - Memutar dari URL")
            self.player.play()
            self._add_to_history(video_url, title)
            self._update_playlist_nav_buttons()

    def _toggle_play_pause(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _stop_video(self):
        self.player.stop()
        self.setWindowTitle("Macan Player - Video dihentikan")
        self.auto_resume_timer.stop()
        self._update_playlist_nav_buttons()

    def _skip_forward(self):
        self.player.setPosition(self.player.position() + self.SKIP_INTERVAL)

    def _skip_backward(self):
        self.player.setPosition(max(0, self.player.position() - self.SKIP_INTERVAL))

    def _change_playback_speed(self):
        self.current_speed_index = (self.current_speed_index + 1) % len(self.playback_speeds)
        new_speed = self.playback_speeds[self.current_speed_index]
        self.player.setPlaybackRate(new_speed)
        self.btn_speed.setText(f"{new_speed}x")

    def _update_position(self, position):
        if not self.position_slider.isSliderDown():
            self.position_slider.setValue(position)
        self._update_time_label(position, self.player.duration())

    def _update_duration(self, duration):
        self.position_slider.setRange(0, duration)
        self._update_time_label(self.player.position(), duration)

    def _set_position(self, position):
        self.player.setPosition(position)

    def _set_volume(self, value):
        self.audio_output.setVolume(value / 100.0)

    def _toggle_mute(self):
        self.is_muted = not self.is_muted
        if self.is_muted:
            self.last_volume = self.volume_slider.value()
            self.volume_slider.setValue(0)
        else:
            self.volume_slider.setValue(self.last_volume if self.last_volume > 0 else 50)

    def _update_volume_icon(self):
        if not qta: return
        volume = self.volume_slider.value()
        if self.is_muted or volume == 0: icon = qta.icon('fa5s.volume-mute')
        elif 0 < volume <= 50: icon = qta.icon('fa5s.volume-down')
        else: icon = qta.icon('fa5s.volume-up')
        self.btn_mute.setIcon(icon)
        
    def _sync_main_volume_slider(self, volume_float):
        value = int(volume_float * 100)
        if not self.volume_slider.isSliderDown():
            self.volume_slider.setValue(value)
        self.is_muted = value == 0
        self._update_volume_icon()

    def _update_time_label(self, position, duration):
        if duration > 0:
            pos_time = QTime(0, 0, 0).addMSecs(position)
            dur_time = QTime(0, 0, 0).addMSecs(duration)
            format_string = 'hh:mm:ss' if duration >= 3600000 else 'mm:ss'
            self.time_label.setText(f"{pos_time.toString(format_string)} / {dur_time.toString(format_string)}")
        else:
            self.time_label.setText("00:00 / 00:00")

    def _update_control_states(self):
        state = self.player.playbackState()
        is_playing = state == QMediaPlayer.PlaybackState.PlayingState
        is_media_loaded = self.player.mediaStatus() != QMediaPlayer.MediaStatus.NoMedia

        if is_playing:
            self.auto_resume_timer.start()
        else:
            self.auto_resume_timer.stop()
            
        if self.player.mediaStatus() == QMediaPlayer.MediaStatus.NoMedia:
            self.splash_label.show()
        else:
            self.splash_label.hide()

        self.btn_play_pause.setEnabled(is_media_loaded)
        self.btn_stop.setEnabled(is_media_loaded)
        self.btn_mini_player.setEnabled(is_media_loaded)
        self._update_play_pause_icon(is_playing)
        self._update_playlist_nav_buttons()

        # Timer untuk menyembunyikan kontrol sekarang ditangani oleh event mouse
        if not self.is_fullscreen:
            if is_playing:
                # Jangan mulai timer di sini, biarkan mouseLeaveEvent yang menanganinya
                pass
            else:
                self.controls_container.setVisible(True)
                self.controls_hide_timer.stop()

    def _update_play_pause_icon(self, is_playing=False):
        if qta:
            icon = qta.icon('fa5s.pause') if is_playing else qta.icon('fa5s.play')
            self.btn_play_pause.setIcon(icon)

    def _handle_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            current_index = self.playlist_widget.get_current_index()
            playlist_data = self.playlist_widget.get_playlist_data()
            if current_index < len(playlist_data) - 1:
                self._play_next_video()
            else:
                self.player.stop()
                self.player.setPosition(0)

    def _handle_error(self, error):
        error_string = self.player.errorString()
        if error_string:
            QMessageBox.critical(self, "Player Error", f"Terjadi kesalahan pemutar media:\n{error_string}")
            self.setWindowTitle("Macan Player - Terjadi Error")
        self._update_control_states()

    def _toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            self.showFullScreen()
            self.controls_container.setVisible(False)
            self.cursor_hide_timer.start()
        else:
            self.showNormal()
            self.controls_container.setVisible(True)
            self.cursor_hide_timer.stop()
            self._show_cursor()
            self._update_control_states()

    def _hide_cursor(self):
        self.setCursor(Qt.CursorShape.BlankCursor)

    def _show_cursor(self):
        self.unsetCursor()

    def mouseMoveEvent(self, event):
        """Hanya menangani kursor saat fullscreen."""
        if self.is_fullscreen:
            self._show_cursor()
            self.controls_container.setVisible(True)
            self.cursor_hide_timer.start()
            self.controls_hide_timer.start()
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_F11: self._toggle_fullscreen()
        elif key == Qt.Key.Key_Escape and self.is_fullscreen: self._toggle_fullscreen()
        elif key == Qt.Key.Key_Space: self._toggle_play_pause()
        elif key == Qt.Key.Key_Right: self._skip_forward()
        elif key == Qt.Key.Key_Left: self._skip_backward()
        else: super().keyPressEvent(event)

    def eventFilter(self, source, event):
        """Filter event untuk menangani interaksi pada video widget."""
        if source is self.video_widget:
            # --- MODIFIKASI DIMULAI: Tampilkan/Sembunyikan kontrol saat hover ---
            if event.type() == QEvent.Type.Enter:
                # Cursor memasuki area video, tampilkan kontrol
                self.controls_container.setVisible(True)
                self.controls_hide_timer.stop()
                return True
            elif event.type() == QEvent.Type.Leave:
                # Cursor meninggalkan area video, mulai timer untuk sembunyikan
                if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                    self.controls_hide_timer.start()
                return True
            # --- MODIFIKASI SELESAI ---

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
        """Menyimpan konfigurasi dan membersihkan thread sebelum aplikasi ditutup."""
        self._save_config()
        self.playlist_widget.close()
        self.mini_player_widget.close()
        self.history_window.close()
        
        # --- PENAMBAHAN BARU: Hentikan thread thumbnail dengan bersih ---
        if self.ffmpeg_available:
            self.thumbnail_thread.quit()
            self.thumbnail_thread.wait() # Tunggu hingga thread benar-benar berhenti
            
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    player = ModernVideoPlayer()

    if len(sys.argv) > 1:
        file_path_to_open = sys.argv[1]
        QTimer.singleShot(0, lambda: player.open_file_from_path(file_path_to_open))

    player.show()
    sys.exit(app.exec())