import sys
import os
import re
import threading
import json
from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QFileDialog, QLineEdit, QLabel, QSlider, QMessageBox, QListWidget, QListWidgetItem,
    QAbstractItemView
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtCore import QUrl, Qt, QTime, QEvent, QSize, QTimer, pyqtSignal, QObject, QRect
from PyQt6.QtGui import QIcon, QPixmap

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

# --- FIX 1 DIMULAI: Membuat slider yang bisa diklik ---
class ClickableSlider(QSlider):
    """
    Slider kustom yang memungkinkan pengguna mengklik untuk mengubah posisi.
    """
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Menghitung nilai berdasarkan posisi klik mouse
            if self.orientation() == Qt.Orientation.Horizontal:
                value = self.minimum() + (self.maximum() - self.minimum()) * event.pos().x() / self.width()
            else:
                value = self.minimum() + (self.maximum() - self.minimum()) * event.pos().y() / self.height()
            
            self.setValue(int(value))
            
            # Memastikan sinyal terkirim agar video berpindah posisi
            # Ini meniru perilaku slider digeser (drag)
            self.sliderMoved.emit(int(value))

        # Panggil implementasi asli untuk menjaga fungsionalitas drag
        super().mousePressEvent(event)
# --- FIX 1 SELESAI ---


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
    # Signal to notify the main player that a video needs to be played
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

        # Enable drag-and-drop feature in the playlist widget
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

    # --- Drag-and-Drop implementation for Playlist ---
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
        """Saves the playlist to a JSON file."""
        config_path = os.path.join(os.path.dirname(__file__), "player_config.json")
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            config = {}

        config['playlist'] = self.playlist

        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)


class ModernVideoPlayer(QWidget):
    """
    Main video player window with all controls.
    """
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

        self.playlist_widget = PlaylistWidget()

        # Inisialisasi Timer
        self.cursor_hide_timer = QTimer(self)
        self.cursor_hide_timer.setInterval(3000)
        self.cursor_hide_timer.setSingleShot(True)

        self.controls_hide_timer = QTimer(self)
        self.controls_hide_timer.setInterval(2500)
        self.controls_hide_timer.setSingleShot(True)

        self._setup_player()

        # Read config before creating the UI
        self._load_config()
        self._setup_ui()
        self._connect_signals()

        # Enable drag-and-drop on the main and video widgets
        self.setAcceptDrops(True)
        self.video_widget.setAcceptDrops(True)

        # Aktifkan pelacakan mouse untuk menampilkan/menyembunyikan kontrol
        self.setMouseTracking(True)
        self.video_widget.setMouseTracking(True) # Pastikan widget video juga melacak mouse
        self.controls_container.setMouseTracking(True)


    def _setup_player(self):
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)

    def _load_config(self):
        """Loads volume and playlist configuration from a JSON file."""
        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)

            # Load volume
            last_volume = config.get('last_volume')
            if last_volume is not None:
                self.last_volume = last_volume

            # Load playlist
            playlist_data = config.get('playlist', [])
            self.playlist_widget.set_playlist_data(playlist_data)

        except (FileNotFoundError, json.JSONDecodeError):
            print("File konfigurasi tidak ditemukan atau tidak valid, menggunakan pengaturan default.")

    def _save_config(self):
        """Saves the current configuration to a JSON file."""
        config = {
            'last_volume': self.volume_slider.value(),
            'playlist': self.playlist_widget.get_playlist_data()
        }
        try:
            with open(self.config_path, "w") as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            print(f"Gagal menyimpan konfigurasi: {e}")

    def _setup_ui(self):
        # --- PERUBAHAN DIMULAI: Set judul awal dan hapus QLabel ---
        self.setWindowTitle("Selamat datang di Macan Player!")
        # --- PERUBAHAN SELESAI ---

        self.setGeometry(100, 100, 960, 600)
        icon_path = "player.ico"
        if hasattr(sys, "_MEIPASS"):
            icon_path = os.path.join(sys._MEIPASS, icon_path)
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.setStyleSheet("""
            QWidget {
                background-color: #1c1c1c;
                color: #ecf0f1;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QPushButton {
                background-color: transparent;
                border: none;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #3a3a3a; }
            QPushButton:pressed { background-color: #4a4a4a; }
            QPushButton:disabled { color: #555; }
            QLineEdit {
                background-color: #2c2c2c;
                border: 1px solid #444;
                padding: 5px;
                border-radius: 4px;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #444;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #3498db;
                border: 1px solid #3498db;
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::sub-page:horizontal {
                background: #3498db;
                border-radius: 2px;
            }
            QLabel { font-size: 12px; }
        """)

        # Main widget and subtitle label
        self.video_widget = QVideoWidget()
        self.video_widget.installEventFilter(self)
        self.player.setVideoOutput(self.video_widget)

        # --- Splash Screen Setup ---
        self.splash_label = QLabel(self.video_widget)
        splash_path = "splash.png"
        if hasattr(sys, "_MEIPASS"):
            splash_path = os.path.join(sys._MEIPASS, splash_path)

        if os.path.exists(splash_path):
            pixmap = QPixmap(splash_path)
            # Scale pixmap to a reasonable size for display
            self.splash_label.setPixmap(pixmap.scaled(QSize(480, 270), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.splash_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.splash_label.setStyleSheet("background-color: #1c1c1c;")
        else:
            # Fallback if image is missing
            self.splash_label.setText("Macan Player")
            self.splash_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.splash_label.setStyleSheet("background-color: #1c1c1c; font-size: 30px; font-weight: bold;")
        self.splash_label.show()

        self.subtitle_label = QLabel(self.video_widget)
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setStyleSheet("background-color: rgba(0, 0, 0, 170); color: white; padding: 8px; border-radius: 5px; font-size: 16px;")
        self.subtitle_label.hide()

        # --- Create Widgets ---
        # --- PERUBAHAN DIMULAI: Hapus deklarasi self.title_label ---
        # self.title_label = QLabel("Selamat datang di Macan Player!")
        # self.title_label.setObjectName("TitleLabel")
        # self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # --- PERUBAHAN SELESAI ---

        self.btn_open = QPushButton()
        self.btn_open.setToolTip("Buka file video dari komputer Anda (Ctrl+O)")
        if qta: self.btn_open.setIcon(qta.icon('fa5s.folder-open'))

        self.btn_open_srt = QPushButton()
        self.btn_open_srt.setToolTip("Buka file subtitle (.srt)")
        if qta: self.btn_open_srt.setIcon(qta.icon('fa5s.closed-captioning'))

        # -- URL Input Widgets --
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Masukkan URL video (termasuk YouTube)...")
        self.url_input.setToolTip("Masukkan URL video dari web (misal: YouTube) lalu tekan Enter.")

        self.btn_load_url = QPushButton()
        self.btn_load_url.setToolTip("Muat video dari URL")
        if qta: self.btn_load_url.setIcon(qta.icon('fa5s.link'))

        self.btn_toggle_url_bar = QPushButton()
        self.btn_toggle_url_bar.setToolTip("Tampilkan/Sembunyikan input URL")
        if qta: self.btn_toggle_url_bar.setIcon(qta.icon('fa5s.globe'))
        # -- End URL Input Widgets --

        self.btn_show_playlist = QPushButton()
        self.btn_show_playlist.setToolTip("Tampilkan/Sembunyikan Playlist")
        if qta: self.btn_show_playlist.setIcon(qta.icon('fa5s.list'))

        # --- FIX 1: Menggunakan ClickableSlider baru ---
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

        self.btn_skip_back = QPushButton()
        self.btn_skip_back.setToolTip("Mundur 10 detik (Panah Kiri)")
        if qta: self.btn_skip_back.setIcon(qta.icon('fa5s.backward'))
        self.btn_skip_back.setEnabled(False)

        self.btn_play_pause = QPushButton()
        self._update_play_pause_icon()
        self.btn_play_pause.setEnabled(False)
        self.btn_play_pause.setToolTip("Putar / Jeda (Spasi atau Klik Video)")

        self.btn_skip_forward = QPushButton()
        self.btn_skip_forward.setToolTip("Maju 10 detik (Panah Kanan)")
        if qta: self.btn_skip_forward.setIcon(qta.icon('fa5s.forward'))
        self.btn_skip_forward.setEnabled(False)

        self.btn_stop = QPushButton()
        self.btn_stop.setToolTip("Hentikan video")
        if qta: self.btn_stop.setIcon(qta.icon('fa5s.stop'))
        self.btn_stop.setEnabled(False)

        self.btn_speed = QPushButton(f"{self.playback_speeds[self.current_speed_index]}x")
        self.btn_speed.setToolTip("Ubah kecepatan pemutaran video")

        self.btn_audio_mode = QPushButton()
        self.btn_audio_mode.setToolTip("Ubah mode audio")
        if qta: self.btn_audio_mode.setIcon(qta.icon('fa5s.music'))


        self.btn_mute = QPushButton()
        self.btn_mute.setToolTip("Bisukan / Aktifkan suara")

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.last_volume)
        self.audio_output.setVolume(self.last_volume / 100.0)
        self.volume_slider.setToolTip("Atur volume suara")
        self.volume_slider.setFixedWidth(120)
        if qta: self._update_volume_icon()

        self.btn_fullscreen = QPushButton()
        self.btn_fullscreen.setToolTip("Mode layar penuh (F11 atau Klik Ganda)")
        if qta: self.btn_fullscreen.setIcon(qta.icon('fa5s.expand'))

        # --- New Compact Layout Arrangement ---
        self.controls_container = QWidget()

        # URL bar (initially hidden)
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

        # Left side
        bottom_controls_layout.addWidget(self.btn_play_pause)
        bottom_controls_layout.addWidget(self.btn_stop)
        bottom_controls_layout.addWidget(self.btn_prev_playlist)
        bottom_controls_layout.addWidget(self.btn_next_playlist)
        bottom_controls_layout.addWidget(self.time_label)
        bottom_controls_layout.addSpacing(20)

        # --- PERUBAHAN DIMULAI: Ganti title_label dengan addStretch ---
        # Center (Title)
        bottom_controls_layout.addStretch(1) # Stretch factor of 1
        # --- PERUBAHAN SELESAI ---

        # Right side
        bottom_controls_layout.addSpacing(20)
        bottom_controls_layout.addWidget(self.btn_open)
        bottom_controls_layout.addWidget(self.btn_toggle_url_bar) # New button
        bottom_controls_layout.addWidget(self.btn_open_srt)
        bottom_controls_layout.addWidget(self.btn_speed)
        bottom_controls_layout.addWidget(self.btn_show_playlist)
        bottom_controls_layout.addWidget(self.btn_mute)
        bottom_controls_layout.addWidget(self.volume_slider)
        bottom_controls_layout.addWidget(self.btn_fullscreen)

        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 5, 0, 0)
        container_layout.setSpacing(5)
        container_layout.addWidget(self.url_bar_widget) # Add hidden URL bar
        container_layout.addLayout(slider_layout)
        container_layout.addLayout(bottom_controls_layout)

        self.controls_container.setLayout(container_layout)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.video_widget, 1) # Video takes up all available space
        main_layout.addWidget(self.controls_container)
        self.setLayout(main_layout)

    def _connect_signals(self):
        self.btn_open.clicked.connect(self._open_file)
        self.btn_open_srt.clicked.connect(self._open_srt_dialog)
        self.url_input.returnPressed.connect(self._load_from_url)
        self.btn_load_url.clicked.connect(self._load_from_url)
        self.btn_toggle_url_bar.clicked.connect(self._toggle_url_bar) # New signal
        self.btn_play_pause.clicked.connect(self._toggle_play_pause)
        self.btn_skip_back.clicked.connect(self._skip_backward)
        self.btn_skip_forward.clicked.connect(self._skip_forward)
        self.btn_stop.clicked.connect(self._stop_video)
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        self.btn_mute.clicked.connect(self._toggle_mute)
        self.btn_speed.clicked.connect(self._change_playback_speed)
        self.btn_audio_mode.clicked.connect(self._change_audio_mode)
        self.btn_show_playlist.clicked.connect(self._toggle_playlist_window)
        self.btn_prev_playlist.clicked.connect(self._play_previous_video)
        self.btn_next_playlist.clicked.connect(self._play_next_video)

        self.volume_slider.valueChanged.connect(self._set_volume)
        self.position_slider.sliderMoved.connect(self._set_position)

        self.player.positionChanged.connect(self._update_position)
        self.player.positionChanged.connect(self._update_subtitle)
        self.player.durationChanged.connect(self._update_duration)
        self.player.playbackStateChanged.connect(self._update_control_states)
        self.player.mediaStatusChanged.connect(self._handle_media_status_changed)
        self.player.errorOccurred.connect(self._handle_error)

        # Connect signal from PlaylistWidget to the main player
        self.playlist_widget.play_requested.connect(self._load_and_play_from_playlist)

        # Hubungkan timer
        self.cursor_hide_timer.timeout.connect(self._hide_cursor)
        self.controls_hide_timer.timeout.connect(self._hide_controls)


    # --- Drag-and-Drop implementation ---
    def dragEnterEvent(self, event):
        """Accepts drag events if the data contains a URL (file path)."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """Loads the video file that was dropped."""
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if os.path.exists(file_path):
                # Simple validation if the file is a video
                file_extension = os.path.splitext(file_path)[1].lower()
                if file_extension in ['.mp4', '.mkv', '.webm', '.avi']:
                    self.playlist_widget.set_playlist_data([{'path': file_path, 'title': os.path.basename(file_path)}])
                    self._load_and_play_from_playlist(file_path)
                    self.playlist_widget._update_selection(0)
                    self._update_playlist_nav_buttons()
                    break # Play the first valid file found
        event.acceptProposedAction()

    # --- Slot Functions (Application Logic) ---

    # --- FIX 3: Memperbaiki logika hide controls ---
    def _hide_controls(self):
        """Sembunyikan panel kontrol jika video sedang diputar."""
        # Logika ini sekarang berlaku untuk mode windowed dan fullscreen
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.controls_container.setVisible(False)

    def open_file_from_path(self, file_path):
        """
        Loads and plays a video file from a given path. This is used for the
        'Open with...' functionality.
        """
        if file_path and os.path.exists(file_path):
            allowed_extensions = ['.mp4', '.mkv', '.webm', '.avi']
            if any(file_path.lower().endswith(ext) for ext in allowed_extensions):
                self.playlist_widget.set_playlist_data([{'path': file_path, 'title': os.path.basename(file_path)}])
                self._load_and_play_from_playlist(file_path)
                self.playlist_widget._update_selection(0)
                self._update_playlist_nav_buttons()
            else:
                # Optionally show a warning for unsupported files
                QMessageBox.warning(self, "Tipe File Tidak Didukung",
                                    f"File '{os.path.basename(file_path)}' sepertinya bukan file video yang didukung.")

    def _toggle_url_bar(self):
        """Shows or hides the URL input bar."""
        is_visible = self.url_bar_widget.isVisible()
        self.url_bar_widget.setVisible(not is_visible)

    def _open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Pilih Video", "", "Video Files (*.mp4 *.mkv *.webm *.avi)")
        if file_path:
            self.playlist_widget.set_playlist_data([{'path': file_path, 'title': os.path.basename(file_path)}])
            self._load_and_play_from_playlist(file_path)
            self.playlist_widget._update_selection(0)
            self._update_playlist_nav_buttons()

    def _load_and_play_from_playlist(self, file_path):
        self.player.setSource(QUrl.fromLocalFile(file_path))
        # --- PERUBAHAN DIMULAI: Atur judul jendela ---
        self.setWindowTitle(f"Macan Player - {os.path.basename(file_path)}")
        # --- PERUBAHAN SELESAI ---
        self.player.play()
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
        """Enables/disables next/prev playlist buttons."""
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
        return (t.hour * 3600 + t.minute * 60 + t.second) * 1000 + t.microsecond // 1000

    def _load_srt_file(self, file_path):
        self.subtitles = []
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f: content = f.read()
            srt_pattern = re.compile(r'\d+\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*?)\n\n', re.DOTALL)
            matches = srt_pattern.finditer(content + "\n\n")
            for match in matches:
                start_time_str, end_time_str, text = match.groups()
                start_time = QTime.fromString(start_time_str, "hh:mm:ss,zzz")
                end_time = QTime.fromString(end_time_str, "hh:mm:ss,zzz")
                self.subtitles.append({'start_ms': self._time_to_ms(start_time), 'end_ms': self._time_to_ms(end_time), 'text': text.strip()})
            QMessageBox.information(self, "Sukses", f"{len(self.subtitles)} baris subtitle berhasil dimuat.")
        except Exception as e:
            #QMessageBox.warning(self, "Error", f"Gagal memuat file subtitle: {e}")
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
        # Position splash screen
        if self.splash_label:
            self.splash_label.setGeometry(0, 0, self.video_widget.width(), self.video_widget.height())

        # Adjust the position of the subtitle label when the window is resized
        label_width = self.video_widget.width() * 0.9
        x = int((self.video_widget.width() - label_width) / 2)
        y = int(self.video_widget.height() - 100)
        self.subtitle_label.setGeometry(x, y, int(label_width), 80)

    def _load_from_url(self):
        url = self.url_input.text().strip()
        if not url: return
        # --- PERUBAHAN DIMULAI: Atur judul jendela ---
        self.setWindowTitle("Macan Player - Mengambil info video...")
        # --- PERUBAHAN SELESAI ---
        self.worker = YouTubeDLWorker(url)
        self.thread = threading.Thread(target=self.worker.run, daemon=True)
        self.worker.finished.connect(self._on_youtube_dl_finished)
        self.thread.start()

    def _on_youtube_dl_finished(self, video_url, title, error):
        if error:
            QMessageBox.critical(self, "Error URL", error)
            # --- PERUBAHAN DIMULAI: Atur judul jendela ---
            self.setWindowTitle("Macan Player - Gagal memuat URL")
            # --- PERUBAHAN SELESAI ---
            return
        if video_url:
            self.playlist_widget.set_playlist_data([{'path': video_url, 'title': title}])
            self.playlist_widget._update_selection(0)
            self.player.setSource(QUrl(video_url))
            # --- PERUBAHAN DIMULAI: Atur judul jendela ---
            if title:
                self.setWindowTitle(f"Macan Player - {title}")
            else:
                self.setWindowTitle("Macan Player - Memutar dari URL")
            # --- PERUBAHAN SELESAI ---
            self.player.play()
            self._update_playlist_nav_buttons()

    def _toggle_play_pause(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _stop_video(self):
        self.player.stop()
        # --- PERUBAHAN DIMULAI: Atur judul jendela ---
        self.setWindowTitle("Macan Player - Video dihentikan")
        # --- PERUBAHAN SELESAI ---
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

    def _change_audio_mode(self):
        self.current_audio_mode_index = (self.current_audio_mode_index + 1) % len(self.audio_modes)
        new_mode = self.audio_modes[self.current_audio_mode_index]
        # This is a placeholder for actual audio processing
        QMessageBox.information(self, "Mode Audio", f"Mode audio diubah ke: {new_mode}")
        print(f"Mengubah mode audio ke: {new_mode}")

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
        self._save_config() # Save volume every time it changes
        if value > 0 and self.is_muted:
            self.is_muted = False
        elif value == 0 and not self.is_muted:
            self.is_muted = True
        self._update_volume_icon()

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

    def _update_time_label(self, position, duration):
        if duration > 0:
            pos_time = QTime(0, 0, 0).addMSecs(position)
            dur_time = QTime(0, 0, 0).addMSecs(duration)
            self.time_label.setText(f"{pos_time.toString('mm:ss')} / {dur_time.toString('mm:ss')}")
        else:
            self.time_label.setText("00:00 / 00:00")

    def _update_control_states(self):
        state = self.player.playbackState()
        is_playing = state == QMediaPlayer.PlaybackState.PlayingState

        is_media_loaded = self.player.mediaStatus() != QMediaPlayer.MediaStatus.NoMedia

        if self.player.mediaStatus() == QMediaPlayer.MediaStatus.NoMedia:
            self.splash_label.show()
        else:
            self.splash_label.hide()

        self.btn_play_pause.setEnabled(is_media_loaded)
        self.btn_stop.setEnabled(is_media_loaded)
        self.btn_skip_back.setEnabled(is_media_loaded)
        self.btn_skip_forward.setEnabled(is_media_loaded)
        self._update_play_pause_icon(is_playing)
        self._update_playlist_nav_buttons()

        # Logika untuk auto-hide kontrol
        if not self.is_fullscreen:
            if is_playing:
                # Saat mulai diputar, mulai timer untuk menyembunyikan kontrol
                self.controls_hide_timer.start()
            else:
                # Jika dijeda atau dihentikan, selalu tampilkan kontrol dan hentikan timer
                self.controls_container.setVisible(True)
                self.controls_hide_timer.stop()


    def _update_play_pause_icon(self, is_playing=False):
        if qta:
            icon = qta.icon('fa5s.pause') if is_playing else qta.icon('fa5s.play')
            self.btn_play_pause.setIcon(icon)

    def _handle_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            # Coba putar video berikutnya di playlist
            current_index = self.playlist_widget.get_current_index()
            playlist_data = self.playlist_widget.get_playlist_data()
            if current_index < len(playlist_data) - 1:
                self._play_next_video()
            else:
                # Jika video terakhir, berhenti dan posisikan di awal
                self.player.stop()
                self.player.setPosition(0)

        # --- FIX: MENCEGAH JENDELA AUTO-RESIZE ---
        if status == QMediaPlayer.MediaStatus.LoadedMedia and not self.is_fullscreen:
            pass # Cukup lewati logika auto-resize

    def _handle_error(self, error):
        error_string = self.player.errorString()
        if error_string:
            QMessageBox.critical(self, "Player Error", f"Terjadi kesalahan pemutar media:\n{error_string}")
            # --- PERUBAHAN DIMULAI: Atur judul jendela ---
            self.setWindowTitle("Macan Player - Terjadi Error")
            # --- PERUBAHAN SELESAI ---
        self._update_control_states()

    def _toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            self.showFullScreen()
            self.controls_container.setVisible(False)
            self.cursor_hide_timer.start() # Sembunyikan kursor setelah beberapa detik
        else:
            self.showNormal()
            self.controls_container.setVisible(True)
            self.cursor_hide_timer.stop()
            self._show_cursor() # Pastikan kursor selalu terlihat
            self._update_control_states()

    def _hide_cursor(self):
        self.setCursor(Qt.CursorShape.BlankCursor)

    def _show_cursor(self):
        self.unsetCursor()

    # --- FIX 2 & 3: Memperbaiki logika pergerakan mouse ---
    def mouseMoveEvent(self, event):
        if self.is_fullscreen:
            # Tampilkan kursor dan kontrol
            self._show_cursor()
            if not self.controls_container.isVisible():
                self.controls_container.setVisible(True)
            
            # Mulai ulang timer untuk menyembunyikan kursor dan kontrol
            self.cursor_hide_timer.start()
            self.controls_hide_timer.start()
        else: # Mode Jendela (Windowed)
            # Tentukan "zona panas" di bagian bawah jendela (misal: 80 piksel)
            hot_zone_height = 80 
            hot_zone = QRect(0, self.height() - hot_zone_height, self.width(), hot_zone_height)

            if hot_zone.contains(event.pos()):
                # Jika kursor di area kontrol, tampilkan dan hentikan timer
                if not self.controls_container.isVisible():
                    self.controls_container.setVisible(True)
                self.controls_hide_timer.stop()
            else:
                # Jika kursor di luar area, mulai timer untuk menyembunyikan (jika video diputar)
                if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                    self.controls_hide_timer.start()

        super().mouseMoveEvent(event)


    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_F11: self._toggle_fullscreen()
        elif key == Qt.Key.Key_Escape and self.is_fullscreen: self._toggle_fullscreen()
        elif key == Qt.Key.Key_Space and self.btn_play_pause.isEnabled(): self._toggle_play_pause()
        elif key == Qt.Key.Key_Right and self.btn_skip_forward.isEnabled(): self._skip_forward()
        elif key == Qt.Key.Key_Left and self.btn_skip_back.isEnabled(): self._skip_backward()
        else: super().keyPressEvent(event)

    def eventFilter(self, source, event):
        if source is self.video_widget:
            if event.type() == QEvent.Type.MouseButtonPress:
                if self.btn_play_pause.isEnabled():
                    self._toggle_play_pause()
                    return True
            elif event.type() == QEvent.Type.MouseButtonDblClick:
                self._toggle_fullscreen()
                return True
        return super().eventFilter(source, event)

    def closeEvent(self, event):
        """Saves configuration and closes the playlist window when the application is closed."""
        self._save_config()
        self.playlist_widget.close() # Ensure the playlist window is closed
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    player = ModernVideoPlayer()

    if len(sys.argv) > 1:
        file_path_to_open = sys.argv[1]
        QTimer.singleShot(0, lambda: player.open_file_from_path(file_path_to_open))

    player.show()
    sys.exit(app.exec())