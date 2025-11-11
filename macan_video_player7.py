import sys
import os
import re
import threading # Diperlukan untuk yt-dlp
from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QFileDialog, QLineEdit, QLabel, QSlider, QMessageBox
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtCore import QUrl, Qt, QTime, QEvent, QSize, QTimer, pyqtSignal, QObject

# Coba import pustaka yang diperlukan
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

# Kelas worker untuk menjalankan yt-dlp di thread terpisah
class YouTubeDLWorker(QObject):
    # Mengirimkan url video, judul, dan error (jika ada)
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
                'no_warnings': True, # Menekan output yang tidak perlu
            }
            with YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(self.url, download=False)
                
                # Ekstrak judul video
                title = info_dict.get('title', 'Judul tidak diketahui')

                formats = info_dict.get('formats', [info_dict])
                
                for f in reversed(formats):
                    if f.get('url') and f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                        self.finished.emit(f['url'], title, None)
                        return # Berhasil, keluar dari fungsi

                self.finished.emit(None, None, "Tidak dapat menemukan URL streaming yang valid dengan video dan audio.")

        except Exception as e:
            self.finished.emit(None, None, f"Error dari yt-dlp: {str(e)}")


class ModernVideoPlayer(QWidget):
    def __init__(self):
        super().__init__()
        self.is_fullscreen = False
        self.subtitles = []
        self.is_muted = False
        self.last_volume = 50
        self.SKIP_INTERVAL = 10000 # 10 detik dalam milidetik

        self._setup_player()
        self._setup_ui()
        self._connect_signals()
        
        self.cursor_hide_timer = QTimer(self)
        self.cursor_hide_timer.setInterval(3000) # 3 detik
        self.cursor_hide_timer.timeout.connect(self._hide_cursor)

    def _setup_player(self):
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)

    def _setup_ui(self):
        self.setWindowTitle("Macan Video Player")
        self.setGeometry(100, 100, 960, 600)
        self.setStyleSheet("""
            QWidget { background-color: #2c3e50; color: #ecf0f1; font-family: 'Segoe UI', Arial, sans-serif; }
            QPushButton { background-color: #34495e; border: 1px solid #2c3e50; padding: 8px; border-radius: 4px; }
            QPushButton:hover { background-color: #4a6278; }
            QPushButton:pressed { background-color: #2c3e50; }
            QPushButton:disabled { background-color: #7f8c8d; color: #bdc3c7; }
            QLineEdit { background-color: #34495e; border: 1px solid #2c3e50; padding: 5px; border-radius: 4px; }
            QSlider::groove:horizontal { height: 5px; background: #34495e; border-radius: 2px; }
            QSlider::handle:horizontal { background: #ecf0f1; border: 1px solid #bdc3c7; width: 14px; margin: -5px 0; border-radius: 7px; }
            QSlider::sub-page:horizontal { background: #3498db; border-radius: 2px; }
            QLabel { font-size: 12px; }
        """)

        # Widget utama dan label subtitle
        self.video_widget = QVideoWidget()
        self.video_widget.installEventFilter(self)
        self.player.setVideoOutput(self.video_widget)

        self.subtitle_label = QLabel(self.video_widget)
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setStyleSheet("background-color: rgba(0, 0, 0, 170); color: white; padding: 8px; border-radius: 5px; font-size: 16px;")
        self.subtitle_label.hide()
        
        # Label Judul/Status
        self.title_label = QLabel("Selamat datang! Buka file video lokal atau masukkan URL untuk memulai.")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 5px; color: #ecf0f1;")

        # URL Input
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Masukkan URL video (termasuk YouTube)...")
        self.url_input.setToolTip("Masukkan URL video dari web (misal: YouTube) lalu tekan Enter.")
        
        self.btn_load_url = QPushButton()
        self.btn_load_url.setToolTip("Muat video dari URL")
        if qta: self.btn_load_url.setIcon(qta.icon('fa5s.link'))

        # Tombol kontrol
        self.btn_open = QPushButton(" Buka File")
        self.btn_open.setToolTip("Buka file video dari komputer Anda")
        if qta: self.btn_open.setIcon(qta.icon('fa5s.folder-open'))
        
        self.btn_open_srt = QPushButton(" Subtitle (.srt)")
        self.btn_open_srt.setToolTip("Buka file subtitle (.srt)")
        if qta: self.btn_open_srt.setIcon(qta.icon('fa5s.closed-captioning'))

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
        
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.setToolTip("Geser untuk mencari posisi video")
        
        self.time_label = QLabel("00:00 / 00:00")

        self.btn_mute = QPushButton()
        self.btn_mute.setToolTip("Bisukan / Aktifkan suara")

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)
        self.audio_output.setVolume(0.5)
        self.volume_slider.setToolTip("Atur volume suara")
        if qta: self._update_volume_icon()

        self.btn_fullscreen = QPushButton()
        self.btn_fullscreen.setToolTip("Mode layar penuh (F11 atau Klik Ganda)")
        if qta: self.btn_fullscreen.setIcon(qta.icon('fa5s.expand'))

        # Penataan Layout
        self.controls_container = QWidget()
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("URL:"))
        url_layout.addWidget(self.url_input)
        url_layout.addWidget(self.btn_load_url)

        time_layout = QHBoxLayout()
        time_layout.addWidget(self.position_slider)
        time_layout.addWidget(self.time_label)

        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.btn_open)
        controls_layout.addWidget(self.btn_open_srt)
        controls_layout.addWidget(self.btn_skip_back)
        controls_layout.addWidget(self.btn_play_pause)
        controls_layout.addWidget(self.btn_skip_forward)
        controls_layout.addWidget(self.btn_stop)
        controls_layout.addStretch()
        controls_layout.addWidget(self.btn_mute)
        controls_layout.addWidget(self.volume_slider)
        controls_layout.addWidget(self.btn_fullscreen)

        container_layout = QVBoxLayout()
        container_layout.addWidget(self.title_label)
        container_layout.addLayout(url_layout)
        container_layout.addLayout(time_layout)
        container_layout.addLayout(controls_layout)
        self.controls_container.setLayout(container_layout)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.video_widget)
        main_layout.addWidget(self.controls_container)
        self.setLayout(main_layout)

    def _connect_signals(self):
        self.btn_open.clicked.connect(self._open_file_dialog)
        self.btn_open_srt.clicked.connect(self._open_srt_dialog)
        self.url_input.returnPressed.connect(self._load_from_url)
        self.btn_load_url.clicked.connect(self._load_from_url)
        self.btn_play_pause.clicked.connect(self._toggle_play_pause)
        self.btn_skip_back.clicked.connect(self._skip_backward)
        self.btn_skip_forward.clicked.connect(self._skip_forward)
        self.btn_stop.clicked.connect(self._stop_video)
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        self.btn_mute.clicked.connect(self._toggle_mute)
        
        self.volume_slider.valueChanged.connect(self._set_volume)
        self.position_slider.sliderMoved.connect(self._set_position)
        
        self.player.positionChanged.connect(self._update_position)
        self.player.positionChanged.connect(self._update_subtitle)
        self.player.durationChanged.connect(self._update_duration)
        self.player.playbackStateChanged.connect(self._update_control_states)
        self.player.mediaStatusChanged.connect(self._handle_media_status_changed)
        self.player.errorOccurred.connect(self._handle_error)
        
    # --- Slot Functions (Logika Aplikasi) ---

    def _open_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Pilih Video", "", "Video Files (*.mp4 *.mkv *.webm *.avi)")
        if file_path:
            self.player.setSource(QUrl.fromLocalFile(file_path))
            self.title_label.setText(f"Memutar: {os.path.basename(file_path)}")
            self.player.play()
            srt_path = os.path.splitext(file_path)[0] + ".srt"
            if os.path.exists(srt_path): self._load_srt_file(srt_path)

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
        label_width = self.video_widget.width() * 0.9
        x = int((self.video_widget.width() - label_width) / 2)
        y = int(self.video_widget.height() - 100)
        self.subtitle_label.setGeometry(x, y, int(label_width), 80)

    def _load_from_url(self):
        url = self.url_input.text().strip()
        if not url: return
        self.url_input.setEnabled(False)
        self.btn_load_url.setEnabled(False)
        self.title_label.setText("Sedang mengambil info video, harap tunggu...")
        self.worker = YouTubeDLWorker(url)
        self.thread = threading.Thread(target=self.worker.run, daemon=True)
        self.worker.finished.connect(self._on_youtube_dl_finished)
        self.thread.start()

    def _on_youtube_dl_finished(self, video_url, title, error):
        self.url_input.setEnabled(True)
        self.btn_load_url.setEnabled(True)
        self.url_input.setPlaceholderText("Masukkan URL video...")
        if error:
            QMessageBox.critical(self, "Error URL", error)
            self.title_label.setText("Gagal memuat video. Silakan coba URL lain.")
            return
        if video_url:
            self.player.setSource(QUrl(video_url))
            if title: self.title_label.setText(f"Memutar: {title}")
            self.player.play()

    def _toggle_play_pause(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _stop_video(self):
        self.player.stop()
        self.title_label.setText("Video dihentikan. Buka file atau masukkan URL.")

    def _skip_forward(self):
        self.player.setPosition(self.player.position() + self.SKIP_INTERVAL)
        
    def _skip_backward(self):
        self.player.setPosition(max(0, self.player.position() - self.SKIP_INTERVAL))

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
        is_media_loaded = self.player.mediaStatus() != QMediaPlayer.MediaStatus.NoMedia and \
                          state != QMediaPlayer.PlaybackState.StoppedState
        self.btn_play_pause.setEnabled(is_media_loaded)
        self.btn_stop.setEnabled(is_media_loaded)
        self.btn_skip_back.setEnabled(is_media_loaded)
        self.btn_skip_forward.setEnabled(is_media_loaded)
        self._update_play_pause_icon(is_playing)

    def _update_play_pause_icon(self, is_playing=False):
        if qta:
            icon = qta.icon('fa5s.pause') if is_playing else qta.icon('fa5s.play')
            self.btn_play_pause.setIcon(icon)
    
    def _handle_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.LoadedMedia and not self.is_fullscreen:
            video_res = self.player.videoSink().videoSize()
            if not video_res.isValid(): return
            available_geom = self.screen().availableGeometry()
            controls_height = self.controls_container.sizeHint().height()
            available_video_space = QSize(available_geom.width(), available_geom.height() - controls_height)
            new_video_size = video_res.scaled(available_video_space, Qt.AspectRatioMode.KeepAspectRatio)
            final_width = new_video_size.width()
            final_height = new_video_size.height() + controls_height
            self.resize(final_width, final_height)

    def _handle_error(self, error):
        error_string = self.player.errorString()
        if error_string:
            QMessageBox.critical(self, "Player Error", f"Terjadi kesalahan pemutar media:\n{error_string}")
            self.title_label.setText("Terjadi kesalahan pada media player.")
        self._update_control_states()
        
    def _toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            self.showFullScreen()
            self.controls_container.setVisible(False)
            self.setMouseTracking(True)
            self.cursor_hide_timer.start()
        else:
            self.showNormal()
            self.controls_container.setVisible(True)
            self.setMouseTracking(False)
            self.cursor_hide_timer.stop()
            self._show_cursor()

    def _hide_cursor(self):
        self.setCursor(Qt.CursorShape.BlankCursor)
        
    def _show_cursor(self):
        self.unsetCursor()
        
    def mouseMoveEvent(self, event):
        if self.is_fullscreen:
            self._show_cursor()
            self.cursor_hide_timer.start()
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

if __name__ == "__main__":
    app = QApplication(sys.argv)
    player = ModernVideoPlayer()
    player.show()
    sys.exit(app.exec())