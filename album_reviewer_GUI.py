import sys
import os
import base64
import json
import csv
import numpy as np
from datetime import datetime
from numpy import mean
from requests import post, get

from dotenv import load_dotenv
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, 
    QHBoxLayout, QListWidget, QListWidgetItem, QTextEdit, 
    QFileDialog, QMessageBox, QDoubleSpinBox, QSpacerItem, QSizePolicy,
    QCheckBox, QMenu, QInputDialog, QTabWidget
)
from PyQt5.QtGui import QPixmap, QColor, QPainter, QLinearGradient, QImage
from PyQt5.QtCore import Qt, QSettings, pyqtSignal
from io import BytesIO
from PIL import Image, ImageGrab

from colour_temp import cluster_image, convert_colour

load_dotenv()

client_id = os.getenv("CLIENT_ID")
client_secret = os.getenv("CLIENT_SECRET")

date = datetime.today().strftime('%Y-%m-%d')

# ---------------- Screenshots ----------------
def take_screenshot(window, margin, path):
    '''Take a screenshot nicely centred on the window'''
    bbox = (window.x() - margin, window.y() - margin, window.x() + window.width() + margin, window.y() + window.height() + margin + 32)

    if window.ntabs == 1:
        snapshot = ImageGrab.grab(bbox)
        save_path = path + f".png"
        snapshot.save(save_path)
    else:
        tab_widget = getattr(window, "tab_widget", None)
        for t in range(window.ntabs):
            if tab_widget is not None:
                tab_widget.setCurrentIndex(t)
                QApplication.processEvents()        # update gui forcefully

            snapshot = ImageGrab.grab(bbox)
            save_path = path + f" ({t+1}).png"
            snapshot.save(save_path)
            

# ---------------- Spotify API ----------------
def get_token():
    auth_string = client_id + ":" + client_secret
    auth_bytes = auth_string.encode("utf-8")
    auth_base64 = str(base64.b64encode(auth_bytes), "utf-8")

    url = "https://accounts.spotify.com/api/token"
    headers = {"Authorization": "Basic " + auth_base64,
               "Content-Type": "application/x-www-form-urlencoded"}
    data = {"grant_type": "client_credentials"}
    result = post(url, headers=headers, data=data)
    return json.loads(result.content)["access_token"]


def get_auth_header(token):
    return {"Authorization": "Bearer " + token}


def search_for_album(token, album_name, no_of_results=5):
    url = "https://api.spotify.com/v1/search"
    headers = get_auth_header(token)
    query = f"?q={album_name}&type=album&limit={no_of_results}"
    result = get(url + query, headers=headers)
    return json.loads(result.content)["albums"]["items"]


def get_album_info(token, album_id):
    url = f"https://api.spotify.com/v1/albums/{album_id}?market=GB"
    headers = get_auth_header(token)
    result = get(url, headers=headers)
    return json.loads(result.content)


# Parse tags into YAML list format
def format_tags(raw_text):
    tags = [t.strip() for t in raw_text.replace("\n", ",").split(",") if t.strip()]
    if not tags:
        return "[]"
    return "\n  - " + "\n  - ".join(tags)


class ColourBand(QWidget):
    def __init__(self, colours, width=10, orientation='v'):
        super().__init__()
        self.colours = colours
        if orientation == 'v':
            self.setFixedWidth(width)
        if orientation == 'h':
            self.setFixedHeight(width)
        self.orientation = orientation

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.orientation == 'v':
            total_h = self.height()
        if self.orientation == 'h':
            total_h = self.width()
        n = len(self.colours)

        for i, c in enumerate(self.colours):
            top = int(i * total_h / n)
            bottom = int((i + 1) * total_h / n)
            height = bottom - top

            if self.orientation == 'v':
                painter.fillRect(0, top, self.width(), height, QColor(c))
            if self.orientation == 'h':
                painter.fillRect(top, 0, height, self.height(), QColor(c))


class GradientBand(QWidget):
    def __init__(self, colours, width=10):
        super().__init__()
        self.colours = colours
        self.setFixedWidth(width)

    def paintEvent(self, event):
        painter = QPainter(self)
        rect = self.rect()

        # Create vertical gradient
        gradient = QLinearGradient(0, 0, 0, rect.height())

        # Add evenly spaced color stops
        n = len(self.colours)
        for i, c in enumerate(self.colours):
            position = i / (n - 1) if n > 1 else 0
            gradient.setColorAt(position, QColor(c))

        painter.fillRect(rect, gradient)


class TrackList(QWidget):
    '''Widget for list of tracks to be rated'''
    rename = pyqtSignal(int, str)   # Signal for renaming a track (index, new name)
    remove = pyqtSignal(int)        # Signal for removing a track (index)

    def __init__(self, idx, track, parent=None):
        super().__init__(parent)
        self.idx = idx
        self.track = track

        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)

        self.label = QLabel(f"{idx+1}. {track['name']}", wordWrap=True)
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.length = QLabel(f"({int((track['duration_ms']/1000) // 60)}:{"%02d" % int((track['duration_ms']/1000) % 60)})")
        self.spin = QDoubleSpinBox()
        self.spin.setRange(0, 10)
        self.spin.setDecimals(1)
        self.spin.setSingleStep(0.5)
        self.spin.setFixedWidth(50)
        self.spin.setValue(5.0)

        hbox.addWidget(self.label)
        hbox.addWidget(self.length, stretch=0)
        hbox.addWidget(self.spin, stretch=0)

        self.setLayout(hbox)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.custom_context_menu)

    def custom_context_menu(self, position):
        menu = QMenu()
        rename_action = menu.addAction('Rename Track')
        remove_action = menu.addAction('Remove Track')

        action = menu.exec_(self.mapToGlobal(position))

        if action == rename_action:
            current_text = self.label.text()
            current_name = current_text.split(". ", 1)[1] if ". " in current_text else current_text

            new_name, ok = QInputDialog.getText(
                self, 
                "Rename Track", 
                "Enter new track name:", 
                QLineEdit.Normal, 
                current_name
            )

            if ok and new_name:
                self.track['name'] = new_name
                self.label.setText(f"{self.idx+1}. {new_name}")
                self.rename.emit(self.idx, new_name)
        
        elif action == remove_action:
            self.remove.emit(self.idx)


class EditableLabel(QLabel):
    '''A QLabel that can be edited by right-clicking'''
    edited = pyqtSignal(str)    # Signal for editing the label

    def __init__(self, label_text, value_text, parent=None, **kwargs):
        super().__init__(f"{label_text} {value_text}", parent, **kwargs)
        self.label_text = label_text
        self.value_text = value_text

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.custom_context_menu)

    def custom_context_menu(self, position):
        menu = QMenu()
        edit_action = menu.addAction('Edit')

        action = menu.exec_(self.mapToGlobal(position))

        if action == edit_action:
            current_value = self.text().replace(self.label_text + " ", "")
            
            # Show input dialog
            new_value, ok = QInputDialog.getText(
                self, 
                "Edit Value", 
                f"Enter new value for {self.label_text.rstrip(':')}:", 
                QLineEdit.Normal, 
                current_value
            )
            
            if ok and new_value:
                self.value_text = new_value
                self.setText(f"{self.label_text} {new_value}")
                self.edited.emit(new_value)


# ---------------- GUI ----------------
class AlbumReviewer(QWidget):
    def __init__(self, track_colours=False):
        super().__init__()
        self.token = get_token()
        self.draw_track_colours = track_colours
        self.album_info = None
        self.track_inputs = []
        self.cover_data = None
        self.settings = QSettings("MyApp", "AlbumReviewer")  # "org", "app name"

        self.setWindowTitle("Album Reviewer")
        self.setGeometry(660, 240, 600, 568)

        # main container layout set once
        self.container_layout = QVBoxLayout()
        self.setLayout(self.container_layout)

        self.init_search_ui()
        
    def clear_layout(self, layout):
        """Remove all widgets from a layout"""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
            else:
                self.clear_layout(item.layout())

    def init_search_ui(self):
        self.clear_layout(self.container_layout)
        
        layout = QVBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter album name...")
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search_album)

        self.results_list = QListWidget()
        self.results_list.itemDoubleClicked.connect(self.load_album)

        options_layout = QHBoxLayout()

        self.use_tab_checkbox = QCheckBox("Use Tab Layout?")

        n_wrap_layout = QHBoxLayout()
        self.n_wrap_option = QDoubleSpinBox()
        self.n_wrap_option.setRange(0, 32)
        self.n_wrap_option.setDecimals(0)
        self.n_wrap_option.setSingleStep(1)
        self.n_wrap_option.setFixedWidth(50)
        self.n_wrap_option.setValue(16)
        n_wrap_layout.addWidget(QLabel("N tracks per page: "))
        n_wrap_layout.addWidget(self.n_wrap_option)

        n_comments_layout = QHBoxLayout()
        self.n_comments_option = QDoubleSpinBox()
        self.n_comments_option.setRange(0, 32)
        self.n_comments_option.setDecimals(0)
        self.n_comments_option.setSingleStep(1)
        self.n_comments_option.setFixedWidth(50)
        self.n_comments_option.setValue(1)
        n_comments_layout.addWidget(QLabel("N comment pages: "))
        n_comments_layout.addWidget(self.n_comments_option)

        options_layout.addWidget(self.use_tab_checkbox)
        options_layout.addLayout(n_wrap_layout)
        options_layout.addLayout(n_comments_layout)

        layout.addWidget(self.search_input)
        layout.addWidget(self.search_button)
        layout.addWidget(QLabel("Search Results:"))
        layout.addWidget(self.results_list)
        layout.addLayout(options_layout)

        self.container_layout.addLayout(layout)

    def search_album(self):
        query = self.search_input.text()
        if not query:
            return
        albums = search_for_album(self.token, query, 10)
        self.results_list.clear()
        for album in albums:
            item = QListWidgetItem(f"{album['artists'][0]['name']} - {album['name']}")
            item.setData(Qt.UserRole, album["id"])
            self.results_list.addItem(item)

    def load_album(self, item):
        album_id = item.data(Qt.UserRole)
        self.album_info = get_album_info(self.token, album_id)
        self.build_review_ui()

    def textify_runtime(self):
        # Total length
        runtime_hours = int((self.runtime/1000) // 3600)
        runtime_minutes = int(((self.runtime/1000) % 3600) // 60)
        runtime_seconds = int((self.runtime/1000) % 60)
        self.runtime_text = ""
        if runtime_hours > 0:
            self.runtime_text += f"{runtime_hours} hr "
        self.runtime_text += f"{"%02d" % runtime_minutes} min {"%02d" % runtime_seconds} sec"

    def remove_track(self, idx):
        if 0 <= idx < len(self.track_lines):
            # Remove line
            track_line = self.track_lines[idx]
            track_line.setParent(None)

            # Update album runtime
            self.runtime -= self.album_info['tracks']['items'][idx]['duration_ms']
            self.textify_runtime()
            self.runtime_label.setText(f"Runtime: {self.runtime_text}")

            # Update internal lists of tracks
            del self.track_lines[idx]
            del self.track_inputs[idx]
            #del self.draw_track_colours[idx]
            del self.album_info['tracks']['items'][idx]

            # Reindex tracks in UI
            for new_idx, track_widget in enumerate(self.track_lines):
                track_widget.idx = new_idx
                track = track_widget.track
                track_widget.label.setText(f"{new_idx+1}. {track['name']}")

    def on_title_changed(self, new_title):
        self.album_info['name'] = new_title
        self.update_window_title()
    
    def on_artists_changed(self, new_artists):
        artist_list = [a.strip() for a in new_artists.split(",")]
        self.album_info["artists"] = [{"name": artist} for artist in artist_list]
        self.update_window_title()
    
    def on_release_date_changed(self, new_date):
        self.album_info['release_date'] = new_date
    
    def update_window_title(self):
        album_title = self.album_info["name"]
        artists = ", ".join([a["name"] for a in self.album_info["artists"]])
        self.setWindowTitle(f"{artists} - {album_title}")

    # Source - https://stackoverflow.com/a
    # Posted by Michael, modified by community. See post 'Timeline' for change history
    # Retrieved 2025-11-24, License - CC BY-SA 3.0

    def pil2pixmap(self, im):
        if im.mode == "RGB":
            r, g, b = im.split()
            im = Image.merge("RGB", (b, g, r))
        elif  im.mode == "RGBA":
            r, g, b, a = im.split()
            im = Image.merge("RGBA", (b, g, r, a))
        elif im.mode == "L":
            im = im.convert("RGBA")
        # Bild in RGBA konvertieren, falls nicht bereits passiert
        im2 = im.convert("RGBA")
        data = im2.tobytes("raw", "RGBA")
        qim = QImage(data, im.size[0], im.size[1], QImage.Format_ARGB32)
        pixmap = QPixmap.fromImage(qim)
        return pixmap
    
    def build_tracks(self, n_wrap=20):
        if n_wrap != 0:
            self.n_track_layouts = len(self.album_info["tracks"]["items"]) // n_wrap
            rem = len(self.album_info["tracks"]["items"]) % n_wrap
            if rem != 0:
                self.n_track_layouts += 1

            self.tracks_layout = []
            for n in range(self.n_track_layouts):
                self.tracks_layout.append(QVBoxLayout())
                if self.n_track_layouts == 1:
                    self.tracks_layout[0].addWidget(QLabel("Track Ratings:"))
                else:
                    self.tracks_layout[n].addWidget(QLabel(f"Track Ratings ({n+1}/{self.n_track_layouts}):"))

            self.ntabs = self.n_track_layouts + self.n_comment_layouts

        if n_wrap == 0:
            self.n_track_layouts = 1
            self.tracks_layout = [QVBoxLayout()]
            self.tracks_layout[0].addWidget(QLabel("Track Ratings:"))

            self.ntabs = 1
            rem = 0

        self.track_inputs = []
        self.track_lines = []
        self.n_tracks_per = np.zeros(shape=self.n_track_layouts)
        self.runtime = 0
        i = 0
        j = 0

        for idx, track in enumerate(self.album_info["tracks"]["items"]):
            self.runtime += track['duration_ms']

            track_line = TrackList(idx, track)
            track_line.remove.connect(lambda i: self.remove_track(i))

            self.track_inputs.append(track_line.spin)
            self.track_lines.append(track_line)
            self.tracks_layout[i].addWidget(track_line)

            j += 1

            if (idx >= (n_wrap * (i + 1)) - 1) and (n_wrap != 0):
                self.n_tracks_per[i] = j
                i += 1
                j = 0

        if rem != 0:
            self.n_tracks_per[i] = j

    def build_overall_score(self):
        self.overall_score = QDoubleSpinBox()
        self.overall_score.setRange(0, 11)
        self.overall_score.setDecimals(1)
        self.overall_score.setSingleStep(0.5)
        self.overall_score.setValue(5.0)

        self.overall_score_layout = QVBoxLayout()
        self.overall_score_layout.addWidget(QLabel("Overall Score:"))
        self.overall_score_layout.addWidget(self.overall_score)

    def build_comments(self):
        if self.use_tabs:
            self.comments_layout = []
            self.comments_box = []
            for n in range(self.n_comment_layouts):
                self.comments_layout.append(QVBoxLayout())
                comments_box_i = QTextEdit()
                comments_box_i.setPlaceholderText("Comments...")
                self.comments_box.append(comments_box_i)
                if self.n_comment_layouts == 1:
                    self.comments_layout[0].addWidget(QLabel("Comments:"))
                    self.comments_layout[0].addWidget(comments_box_i)
                else:
                    self.comments_layout[n].addWidget(QLabel(f"Comments ({n+1}/{self.n_comment_layouts}):"))
                    self.comments_layout[n].addWidget(comments_box_i)
        
        if not self.use_tabs:
            self.comments_layout = QVBoxLayout()
            self.comments_layout.addWidget(QLabel("Comments:"))

            self.comments_box = QTextEdit()
            self.comments_box.setPlaceholderText("Comments...")
            self.comments_layout.addWidget(self.comments_box)

    def build_cover(self, downsampl=1, posterise=False, **kwargs):
        cover_url = self.album_info["images"][0]["url"]
        self.cover_data = get(cover_url).content
        img = np.asarray(Image.open(BytesIO(self.cover_data)))

        # Generate the colours
        sample_space = 'Oklab'
        downsampl = downsampl
        img_downsampl = img[::downsampl, ::downsampl]
        img_clusters, img_labels = cluster_image(img_downsampl, sample_space, output_space='sRGB',
                                                 clustering_method='mean-shift', quantile=0.125, return_labels=True)
                                                # clustering_method='k-means', n_clusters=range(8, 10), n_runs=1, return_labels=True)

        self.colours = [convert_colour(value, 'sRGB', 'Hex') for value in img_clusters]
        
        if posterise:
            img_clusters_srgb = (img_clusters * 255).astype('uint8')
            img_posterised_array = img_clusters_srgb[img_labels].reshape(img_downsampl.shape[0], img_downsampl.shape[1], 3)
            img = Image.fromarray(img_posterised_array, 'RGB')

        # Album cover pixmap
        pixmap = QPixmap()
        pixmap.loadFromData(self.cover_data)
        self.cover_label = QLabel()
        self.cover_label.setPixmap(pixmap.scaled(300, 300, Qt.KeepAspectRatio))

        self.colour_band_cover = ColourBand(self.colours, width=5, orientation='h')

        self.cover_layout = QVBoxLayout()
        self.cover_layout.addWidget(self.cover_label, alignment=Qt.AlignmentFlag.AlignTop)
        self.cover_layout.addWidget(self.colour_band_cover)

    def build_info_panel(self):
        # Metadata labels
        self.title_label = EditableLabel("Title:", self.album_info['name'], wordWrap=True)
        self.title_label.edited.connect(self.on_title_changed)
        
        artists = ", ".join([a['name'] for a in self.album_info['artists']])
        if len(self.album_info['artists']) >= 2:
            artist_text = "Artists:"
        else:
            artist_text = "Artist:"
        self.artists_label = EditableLabel(artist_text, artists, wordWrap=True)
        self.artists_label.edited.connect(self.on_artists_changed)
        
        self.textify_runtime()
        self.runtime_label = QLabel(f"Runtime: {self.runtime_text}")
        
        self.release_date_label = EditableLabel("Release Date:", self.album_info['release_date'])
        self.release_date_label.edited.connect(self.on_release_date_changed)
        
        self.genre_tags_input = QLineEdit()
        self.genre_tags_input.setPlaceholderText("Enter genre tags (comma-separated)")

        self.mood_tags_input = QLineEdit()
        self.mood_tags_input.setPlaceholderText("Enter mood tags (comma-separated)")

        self.first_listen = QCheckBox("First Listen")

        self.info_panel_layout = QVBoxLayout()

        self.info_panel_layout.addWidget(self.title_label, alignment=Qt.AlignTop)
        self.info_panel_layout.addWidget(self.artists_label, alignment=Qt.AlignTop)
        self.info_panel_layout.addWidget(self.runtime_label, alignment=Qt.AlignTop)
        self.info_panel_layout.addWidget(self.release_date_label, alignment=Qt.AlignTop)
        self.info_panel_layout.addWidget(QLabel(f"Popularity: {self.album_info['popularity']}"), alignment=Qt.AlignTop)
        self.info_panel_layout.addWidget(QLabel("Genre Tags:"))
        self.info_panel_layout.addWidget(self.genre_tags_input)
        self.info_panel_layout.addWidget(QLabel("Mood Tags:"))
        self.info_panel_layout.addWidget(self.mood_tags_input)
        self.info_panel_layout.addWidget(self.first_listen)

    def build_review_ui(self):
        self.use_tabs = self.use_tab_checkbox.isChecked()
        self.n_wrap = int(self.n_wrap_option.value())
        self.n_comment_layouts = int(self.n_comments_option.value())

        self.clear_layout(self.container_layout)

        album_title = self.album_info["name"]
        artists = ", ".join([a["name"] for a in self.album_info["artists"]])
        self.setWindowTitle(artists + ' - ' + album_title)

        # Build components from functions to be arranged
        # Track listing(s)
        if not self.use_tabs:
            self.build_tracks(n_wrap=0)
        if self.use_tabs:
            self.build_tracks(n_wrap=self.n_wrap)

        # Overall score & comments
        self.build_overall_score()
        self.build_comments()

        # Cover & Info panel
        self.build_cover()
        self.build_info_panel()

        # SAVE
        save_button = QPushButton("Save Review")
        save_button.clicked.connect(self.save_review)


        # Right side: album cover & metadata
        right_layout = QVBoxLayout()
        
        right_layout.addLayout(self.cover_layout)
        right_layout.addLayout(self.info_panel_layout)

        # Add spacer so everything stays at the top
        #right_layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))

        right_layout.addWidget(save_button)

        main_layout = QHBoxLayout()
        main_main_layout = QVBoxLayout()

        # TABS
        if not self.use_tabs:
            left_layout = QVBoxLayout()

            # Left side: track ratings
            left_layout.addLayout(self.tracks_layout[0])
            left_layout.addLayout(self.comments_layout)
            left_layout.addLayout(self.overall_score_layout)

            # Put left + right together
            main_layout.addLayout(left_layout, 3)
            main_layout.addLayout(right_layout, 2)
            #main_layout.addWidget(colour_band)
            #main_layout.addWidget(colour_gradient)
        
        if self.use_tabs:
            actual_left_layout = QVBoxLayout()
            left_layout = QTabWidget()
            self.tab_widget = left_layout       # so that tabs can be switched in take_screenshot()
            self.tabs = []
            n = 0

            for i in range(self.ntabs):
                tab = QWidget()
                tab_layout = QVBoxLayout()

                # Left side: track ratings
                if i < self.n_track_layouts:
                    tab_layout.addLayout(self.tracks_layout[i])
                    if self.n_track_layouts == 1:
                        tab_name = f"Tracks"
                    if self.n_track_layouts > 1:
                        tab_name = f"Tracks {int(n + 1)}-{int(n + self.n_tracks_per[i])}"
                    n += self.n_tracks_per[i]

                    tab_layout.addSpacerItem(QSpacerItem(20, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))

                if i >= self.n_track_layouts:
                    tab_layout.addLayout(self.comments_layout[i - self.n_track_layouts])
                    if self.n_comment_layouts == 1:
                        tab_name = f"Comments"
                    if self.n_comment_layouts > 1:
                        tab_name = f"Comments ({i - self.n_track_layouts + 1})"

                tab.setLayout(tab_layout)
                left_layout.addTab(tab, tab_name)
                self.tabs.append(tab)

            actual_left_layout.addWidget(left_layout)
            actual_left_layout.addLayout(self.overall_score_layout)

            # Put left + right together
            main_layout.addLayout(actual_left_layout, 3)
            main_layout.addLayout(right_layout, 2)
            #main_layout.addWidget(colour_band)
            #main_layout.addWidget(colour_gradient)

        # Generate colour band(s)
        #colour_band = ColourBand(self.colours, width=2, orientation='v')
        #colour_gradient = GradientBand(self.colours, width=5)

        main_main_layout.addLayout(main_layout)
        self.container_layout.addLayout(main_main_layout)

    def save_review(self):
        folder_path = f"C:\\Users\\thoma\\Pictures\\Album Reviews\\[{date}] {window.album_info["name"]}"
        if not os.path.isdir(folder_path):
            os.makedirs(folder_path)
        insta_path = os.path.join(folder_path, f"[{date}] {window.album_info["name"]}")
        take_screenshot(self, 100, insta_path)

        # Prepare data
        album_title = self.album_info["name"]
        artists = ", ".join([a["name"] for a in self.album_info["artists"]])
        release_date = self.album_info["release_date"]
        genres = self.album_info.get("genres", [])
        popularity = self.album_info["popularity"]
        genre_tags = format_tags(self.genre_tags_input.text())
        mood_tags = format_tags(self.mood_tags_input.text())
        first_listen = self.first_listen.isChecked()

        ratings = [spin.value() for spin in self.track_inputs]
        avg_track_score = mean(ratings)
        overall_score = self.overall_score.value()

        if not self.use_tabs:
            comments = self.comments_box.toPlainText()
        if self.use_tabs:
            comments = ""
            for c in range(len(self.comments_box)):
                comment = self.comments_box[c].toPlainText()
                if c != 0:
                    comments += "\n\n"
                comments += comment

        # Prefix every line of comments with '>> ' for the file_data section
        if comments and comments.strip():
            # Replace every newline with a newline followed by the quote prefix so
            # every line starts with '>> '. Blank lines will become '>> '.
            comments_prefixed = ">> " + comments.replace("\n", "\n>> ")
        else:
            comments_prefixed = ""

        # Build track listing
        tracks = ""
        insta_tracks = ""
        for idx, track in enumerate(self.album_info["tracks"]["items"]):
            tracks += f">> **{idx+1} - {track['name']}:** {ratings[idx]}\n"
            insta_tracks += f"{idx+1} - {track['name']}: {ratings[idx]}\n"

        file_data = (f"---\n"
                     f"Date: {date}\n"
                     f"Title: {album_title}\n"
                     f"Artist: {artists}\n"
                     f"Runtime: {self.runtime_text}\n"
                     f"Release Date: {release_date}\n"
                     f"Genres: {genres}\n"
                     f"Popularity: {popularity}\n"
                     f"Overall Score: {overall_score}\n"
                     f"Average Track Score: {avg_track_score:.2f}\n"
                     f"Genre Tags: {genre_tags}\n"
                     f"Mood Tags: {mood_tags}\n"
                     f"First Listen: {first_listen}\n"
                     f"Cover Art: [[{album_title}.jpg]]\n"
                     f"---\n"
                     f"![[{album_title}.jpg]]\n\n"
                     f"> [!multi-column]\n>\n"
                     f">> [!music-tracks]+ Track Listing\n{tracks}>\n"
                     f">> [!music-comments]+ Comments\n{comments_prefixed}\n\n"
                     f"> [!music-scores]+ Scores\n"
                     f"> # **Overall Score:** {overall_score}\n"
                     f"> <br/>\n>\n"
                     f"> ## **Average Track Score:** {avg_track_score:.2f}\n\n"
                     f"#album_review")

        # Load last directory (if available), else default to home
        last_dir = self.settings.value("lastSaveDir", os.path.expanduser("~"))

        save_dir = QFileDialog.getExistingDirectory(self, "Select Save Directory", last_dir)

        if not save_dir:
            return

        # Save last directory for next time
        self.settings.setValue("lastSaveDir", save_dir)

        # Save markdown
        file_path = os.path.join(save_dir, f"{artists} - {album_title}.md")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(file_data)

        # Save cover
        cover_path = os.path.join(save_dir, f"Cover Art/{album_title}.jpg")
        with open(cover_path, "wb") as img:
            img.write(self.cover_data)

        # Save data to CSV
        review_data = [
            date,
            album_title,
            [a["name"] for a in self.album_info["artists"]],
            self.runtime,
            release_date,
            popularity,
            overall_score,
            ratings,
            avg_track_score,
            self.genre_tags_input.text(),
            self.mood_tags_input.text(),
            first_listen,
        ]

        dir_path = os.path.dirname(os.path.realpath(__file__))
        csv_path = os.path.join(dir_path, "review_data.csv")
        review_writer = csv.writer(open(csv_path, 'a'))
        review_writer.writerow(review_data)

        # Save text file containing Instagram description
        insta_text = (
            f"{artists} - {album_title}: {overall_score}/10"
            "\n------------------------------\n"
            f"{insta_tracks}"
            "------------------------------\n"
            f"{comments}"
            "\n------------------------------"
        )

        with open(insta_path + ".txt", "w") as txt:
            txt.write(insta_text)

        QMessageBox.information(self, "Saved", f"Review saved to {file_path}")


if __name__ == "__main__":
    '''
    use_tabs_input = input("Use Tabs Layout? ([y]/n)")
    if use_tabs_input == 'n':
        use_tabs = False
    else:
        use_tabs = True
    '''
    
    app = QApplication(sys.argv)
    window = AlbumReviewer(track_colours=False)
    window.show()
    sys.exit(app.exec_())
