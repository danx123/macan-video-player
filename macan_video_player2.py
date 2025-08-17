import sys
import os
import re # Diperlukan untuk parsing file .srt
from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QFileDialog, QLineEdit, QLabel, QSlider, QMessageBox
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtCore import QUrl, Qt, QTime, QEvent, QSize

# Coba import qtawesome untuk ikon.
try:
    import qtawesome as qta
except ImportError:
    print("Pustaka 'qtawesome' tidak ditemukan. Silakan install dengan 'pip install qtawesome'")
    qta = None

class ModernVideoPlayer(QWidget):
    def __init__(self):
        super().__init__()
        self.is_fullscreen = False
        self.subtitles = []
        self.current_subtitle_index = -1
        
        self._setup_player()
        self._setup_ui()
        self._connect_signals()

    def _setup_player(self):
        """Inisialisasi komponen media player."""
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)

    def _setup_ui(self):
        """Inisialisasi dan penataan antarmuka pengguna (UI)."""
        self.setWindowTitle("Modern Video Player")
        self.setGeometry(100, 100, 960, 600)
        self.setStyleSheet("""
            /* ... (stylesheet tetap sama, tidak perlu disalin ulang jika sudah ada) ... */
        """)

        # Widget utama dan label subtitle
        self.video_widget = QVideoWidget()
        self.video_widget.installEventFilter(self)
        self.player.setVideoOutput(self.video_widget)

        self.subtitle_label = QLabel(self.video_widget)
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setStyleSheet("""
            background-color: rgba(0, 0, 0, 170);
            color: white;
            padding: 8px;
            border-radius: 5px;
            font-size: 16px;
        """)
        self.subtitle_label.hide() # Sembunyikan di awal

        # ... (Definisi widget lain seperti url_input, btn_open, dll. tetap sama) ...
        # URL Input
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Masukkan URL video...")
        self.btn_load_url = QPushButton()
        if qta: self.btn_load_url.setIcon(qta.icon('fa5s.link'))

        # Tombol kontrol
        self.btn_open = QPushButton(" Buka File")
        if qta: self.btn_open.setIcon(qta.icon('fa5s.folder-open'))
        
        # Tombol baru untuk Subtitle
        self.btn_open_srt = QPushButton(" Subtitle (.srt)")
        if qta: self.btn_open_srt.setIcon(qta.icon('fa5s.closed-captioning'))

        self.btn_play_pause = QPushButton()
        self._update_play_pause_icon()
        self.btn_play_pause.setEnabled(False)

        self.btn_stop = QPushButton()
        if qta: self.btn_stop.setIcon(qta.icon('fa5s.stop'))
        self.btn_stop.setEnabled(False)
        
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)
        self.time_label = QLabel("00:00 / 00:00")

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)
        self.audio_output.setVolume(0.5)
        self.volume_label = QLabel()
        if qta: self.volume_label.setPixmap(qta.icon('fa5s.volume-up').pixmap(16, 16))

        self.btn_fullscreen = QPushButton()
        if qta: self.btn_fullscreen.setIcon(qta.icon('fa5s.expand'))

        # --- Penataan Layout ---
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
        controls_layout.addWidget(self.btn_open_srt) # Tambahkan tombol srt di sini
        controls_layout.addWidget(self.btn_play_pause)
        controls_layout.addWidget(self.btn_stop)
        controls_layout.addStretch()
        controls_layout.addWidget(self.volume_label)
        controls_layout.addWidget(self.volume_slider)
        controls_layout.addWidget(self.btn_fullscreen)

        container_layout = QVBoxLayout()
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
        """Menghubungkan sinyal dari widget ke slot (fungsi)."""
        self.btn_open.clicked.connect(self._open_file_dialog)
        self.btn_open_srt.clicked.connect(self._open_srt_dialog) # Sinyal tombol srt
        self.url_input.returnPressed.connect(self._load_from_url)
        self.btn_load_url.clicked.connect(self._load_from_url)
        self.btn_play_pause.clicked.connect(self._toggle_play_pause)
        self.btn_stop.clicked.connect(self._stop_video)
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        
        self.volume_slider.valueChanged.connect(self._set_volume)
        self.position_slider.sliderMoved.connect(self._set_position)
        
        self.player.positionChanged.connect(self._update_position)
        self.player.positionChanged.connect(self._update_subtitle) # Hubungkan ke update subtitle
        self.player.durationChanged.connect(self._update_duration)
        self.player.playbackStateChanged.connect(self._update_control_states)
        self.player.mediaStatusChanged.connect(self._handle_media_status_changed)
        self.player.errorOccurred.connect(self._handle_error)
        
    # --- Slot Functions (Logika Aplikasi) ---

    def _open_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Pilih Video", "", "Video Files (*.mp4 *.mkv *.webm *.avi)")
        if file_path:
            self.player.setSource(QUrl.fromLocalFile(file_path))
            self.player.play()

            # Cek otomatis file .srt
            srt_path = os.path.splitext(file_path)[0] + ".srt"
            if os.path.exists(srt_path):
                self._load_srt_file(srt_path)

    def _open_srt_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Pilih Subtitle", "", "SRT Files (*.srt)")
        if file_path:
            self._load_srt_file(file_path)
            
    def _time_to_ms(self, t):
        """Konversi format waktu SRT ke milidetik."""
        return (t.hour * 3600 + t.minute * 60 + t.second) * 1000 + t.microsecond // 1000

    def _load_srt_file(self, file_path):
        """Membaca dan mem-parsing file .srt."""
        self.subtitles = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Regex untuk menangkap timecode dan teks
            srt_pattern = re.compile(r'\d+\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*?)\n\n', re.DOTALL)
            matches = srt_pattern.finditer(content)
            
            for match in matches:
                start_time_str, end_time_str, text = match.groups()
                start_time = QTime.fromString(start_time_str, "hh:mm:ss,zzz")
                end_time = QTime.fromString(end_time_str, "hh:mm:ss,zzz")
                
                self.subtitles.append({
                    'start_ms': self._time_to_ms(start_time),
                    'end_ms': self._time_to_ms(end_time),
                    'text': text.strip()
                })
            QMessageBox.information(self, "Sukses", f"{len(self.subtitles)} baris subtitle berhasil dimuat.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Gagal memuat file subtitle: {e}")
            self.subtitles = []
            
    def _update_subtitle(self, position):
        """Menampilkan subtitle yang sesuai dengan posisi video."""
        if not self.subtitles:
            return
            
        current_text = ""
        # Cari subtitle yang cocok (bisa dioptimalkan, tapi ini cukup untuk kebanyakan kasus)
        for sub in self.subtitles:
            if sub['start_ms'] <= position <= sub['end_ms']:
                current_text = sub['text']
                break
        
        if current_text:
            self.subtitle_label.setText(current_text)
            if not self.subtitle_label.isVisible():
                self.subtitle_label.show()
        else:
            if self.subtitle_label.isVisible():
                self.subtitle_label.hide()

    def resizeEvent(self, event):
        """Memastikan posisi label subtitle selalu benar saat ukuran window berubah."""
        super().resizeEvent(event)
        
        # Atur geometri label subtitle di bagian bawah tengah video
        label_width = self.video_widget.width() * 0.9 # Lebar 90% dari video
        x = int((self.video_widget.width() - label_width) / 2)
        y = int(self.video_widget.height() - 100) # Posisi 100px dari bawah
        
        # Ukuran tinggi akan menyesuaikan konten
        self.subtitle_label.setGeometry(x, y, int(label_width), 80)

    # --- (Fungsi-fungsi lain tidak berubah, tetap sama seperti sebelumnya) ---
    def _load_from_url(self):
        url = self.url_input.text()
        if url:
            self.player.setSource(QUrl(url))
            self.player.play()

    def _toggle_play_pause(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _stop_video(self):
        self.player.stop()

    def _update_position(self, position):
        self.position_slider.setValue(position)
        self._update_time_label(position, self.player.duration())

    def _update_duration(self, duration):
        self.position_slider.setRange(0, duration)
        self._update_time_label(self.player.position(), duration)

    def _set_position(self, position):
        self.player.setPosition(position)

    def _set_volume(self, value):
        self.audio_output.setVolume(value / 100.0)

    def _update_time_label(self, position, duration):
        pos_time = QTime(0, 0, 0).addMSecs(position)
        dur_time = QTime(0, 0, 0).addMSecs(duration)
        self.time_label.setText(f"{pos_time.toString('mm:ss')} / {dur_time.toString('mm:ss')}")

    def _update_control_states(self):
        is_playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        is_media_loaded = self.player.mediaStatus() != QMediaPlayer.MediaStatus.NoMedia
        self.btn_play_pause.setEnabled(is_media_loaded)
        self.btn_stop.setEnabled(is_media_loaded)
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
            QMessageBox.critical(self, "Error", f"Terjadi kesalahan:\n{error_string}")
        self._update_control_states()
        
    def _toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            self.showFullScreen()
            self.controls_container.setVisible(False)
        else:
            self.showNormal()
            self.controls_container.setVisible(True)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F11: self._toggle_fullscreen()
        elif event.key() == Qt.Key.Key_Escape and self.is_fullscreen: self._toggle_fullscreen()
        else: super().keyPressEvent(event)

    def eventFilter(self, source, event):
        if source is self.video_widget and event.type() == QEvent.Type.MouseButtonDblClick:
            self._toggle_fullscreen()
            return True
        return super().eventFilter(source, event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    player = ModernVideoPlayer()
    player.show()
    sys.exit(app.exec())