#     chyp - An interactive theorem prover for string diagrams 
#     Copyright (C) 2022 - Aleks Kissinger
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#    http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations
from typing import Callable, List, Optional
from PySide6.QtCore import QByteArray, QDir, QFileInfo, QSettings, Qt
from PySide6.QtGui import QActionGroup, QCloseEvent, QKeySequence, QTextCursor
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMenuBar, QMessageBox, QTabWidget, QVBoxLayout, QWidget

from . import editor


class MainWindow(QMainWindow):
    """The main window for the Chyp GUI

    This is responsible for the main top-level menus and contains a collection of `Editor` widgets, displayed in tabs. Most
    of the functionality accessible from the menu is passed on to the currently-visible editor, accessible via `self.active_editor`.
    """

    def __init__(self) -> None:
        super().__init__()
        conf = QSettings('chyp', 'chyp')

        self.setWindowTitle("chyp")

        self.tabs = QTabWidget()
        self.tabs.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tabs.currentChanged.connect(self.tab_changed)

        w = QWidget(self)
        w.setLayout(QVBoxLayout())
        self.setCentralWidget(w)
        w.layout().setContentsMargins(0,0,0,0)
        w.layout().setSpacing(0)
        w.layout().addWidget(self.tabs)
        self.resize(1600, 800)
        
        geom = conf.value("editor_window_geometry")
        if geom and isinstance(geom, QByteArray): self.restoreGeometry(geom)
        self.show()

        self.active_editor: Optional[editor.Editor] = None
        self.add_tab(editor.Editor(), "Untitled")
        self.update_file_name()
        self.build_menu()


    def remove_empty_editor(self) -> None:
        """Remove the active editor, provided it doesn't have a filename or any text

        When Chyp opens, it displays an empty chyp file called "Untitled". If the use opens a file straight away,
        this method is used to close this empty editor instead of keeping it open as an extra tab.
        """

        if self.active_editor:
            if self.active_editor.title() == 'Untitled' and self.active_editor.doc.toPlainText() == '':
                self.tabs.removeTab(self.tabs.indexOf(self.active_editor))
                self.active_editor = None

    def update_file_name(self) -> None:
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, editor.Editor):
                self.tabs.setTabText(i, w.title())
        if self.active_editor:
            self.setWindowTitle('chyp - ' + self.active_editor.title())

    def tab_changed(self, i: int) -> None:
        w = self.tabs.widget(i)
        if isinstance(w, editor.Editor):
            self.active_editor = w
            self.active_editor.code_view.setFocus()
            self.update_file_name()

    def update_themes(self) -> None:
        conf = QSettings('chyp', 'chyp')
        theme_name = conf.value('theme')
        if not theme_name or not isinstance(theme_name, str):
            theme_name = 'catppuccin_macchiato'

        def set_th(t: str) -> Callable:
            def f() -> None:
                conf.setValue('theme', t)
                QMessageBox.information(self, 'Theme set',
                                        'You must restart Chyp for the new theme to take effect.')
            return f

        themes_group = QActionGroup(self)

        view_themes_dark = self.view_themes.addAction("Dark")
        view_themes_dark.setCheckable(True)
        view_themes_dark.setChecked(theme_name == 'catppuccin_macchiato')
        view_themes_dark.triggered.connect(set_th('catppuccin_macchiato'))

        view_themes_light = self.view_themes.addAction("Light")
        view_themes_light.setCheckable(True)
        view_themes_light.setChecked(theme_name == 'catppuccin_latte')
        view_themes_light.triggered.connect(set_th('catppuccin_latte'))

        themes_group.addAction(view_themes_dark)
        themes_group.addAction(view_themes_light)

    def recent_files(self) -> List[str]:
        conf = QSettings('chyp', 'chyp')
        o = conf.value('recent_files', [])
        return o if isinstance(o, list) else []

    def update_recent_files(self) -> None:
        def open_recent(f: str) -> Callable:
            return lambda: self.open(f)

        self.file_open_recent.clear()
        for f in self.recent_files():
            fi = QFileInfo(f)
            action = self.file_open_recent.addAction(fi.fileName())
            action.triggered.connect(open_recent(f))

    def add_tab(self, ed: editor.Editor, title: str) -> None:
        self.tabs.addTab(ed, title)
        ed.doc.fileNameChanged.connect(self.update_file_name)
        ed.doc.modificationChanged.connect(self.update_file_name)
        self.tabs.setCurrentWidget(ed)
        ed.reset_state()

    def close_tab(self, ed: Optional[editor.Editor]=None) -> bool:
        if ed is None:
            ed = self.active_editor

        if ed:
            i = self.tabs.indexOf(ed)
            if i != -1 and ed.doc.confirm_close():
                ed.doc.fileNameChanged.disconnect(self.update_file_name)
                ed.doc.modificationChanged.disconnect(self.update_file_name)
                self.tabs.removeTab(i)

                if self.tabs.count() == 0:
                    app = QApplication.instance()
                    if app:
                        app.quit()

                return True

        return False

    def new(self) -> None:
        self.remove_empty_editor()
        ed = editor.Editor()
        self.add_tab(ed, "Untitled")

    def open(self, file_name: str='', line_number: int=-1) -> None:
        conf = QSettings('chyp', 'chyp')

        # if no file name provided, show open dialog
        if file_name == '':
            o = conf.value('last_dir')
            last_dir = o if isinstance(o, str) else QDir.home().absolutePath()
            file_name, _ = QFileDialog.getOpenFileName(self,
                                                       "Open File",
                                                       last_dir,
                                                       'chyp files (*.chyp)')

        ed: Optional[editor.Editor] = None

        # if file is already open, just focus the tab
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, editor.Editor) and w.doc.file_name == file_name:
                ed = w
                self.tabs.setCurrentWidget(w)

        if not ed:
            try:
                ed = editor.Editor()
                ed.doc.open(file_name)
                conf.setValue('last_dir', QFileInfo(file_name).absolutePath())
                self.remove_empty_editor()
                self.update_recent_files()
                ed.doc.fileNameChanged.connect(self.update_file_name)
                self.add_tab(ed, ed.title())
            except FileNotFoundError:
                QMessageBox.warning(self, "File not found", "File not found: " + file_name)

        if ed and line_number != -1:
            cur = QTextCursor(ed.code_view.document().findBlockByNumber(line_number - 1))
            ed.code_view.moveCursor(QTextCursor.MoveOperation.End)
            ed.code_view.setTextCursor(cur)
            ed.code_view.setFocus()


    def save(self) -> None:
        if self.active_editor:
            self.active_editor.doc.save()
            self.update_recent_files()

    def save_as(self) -> None:
        if self.active_editor:
            self.active_editor.doc.save_as()
            self.update_recent_files()
    
    def undo(self) -> None:
        if self.active_editor:
            self.active_editor.code_view.undo()

    def redo(self) -> None:
        if self.active_editor:
            self.active_editor.code_view.redo()

    def add_rewrite_step(self) -> None:
        if self.active_editor:
            self.active_editor.code_view.add_line_below("  = ? by ")

    def repeat_rewrite_step(self) -> None:
        if self.active_editor:
            self.active_editor.repeat_step_at_cursor()

    def next_rewrite(self) -> None:
        if self.active_editor:
            self.active_editor.next_rewrite_at_cursor()

    def next_part(self) -> None:
        if self.active_editor:
            self.active_editor.next_part(step=1)

    def previous_part(self) -> None:
        if self.active_editor:
            self.active_editor.next_part(step=-1)

    def next_tab(self) -> None:
        c = self.tabs.count()
        if c != 0:
            i = (self.tabs.currentIndex() + 1) % c
            self.tabs.setCurrentIndex(i)

    def previous_tab(self) -> None:
        c = self.tabs.count()
        if c != 0:
            i = (self.tabs.currentIndex() - 1) % c
            self.tabs.setCurrentIndex(i)

    def goto_import(self) -> None:
        if self.active_editor:
            f = self.active_editor.import_at_cursor()
            if f:
                self.open(f)


    def closeEvent(self, event: QCloseEvent) -> None:
        conf = QSettings('chyp', 'chyp')
        conf.setValue("editor_window_geometry", self.saveGeometry())

        if self.active_editor:
            conf.setValue("editor_splitter_state", self.active_editor.splitter.saveState())
            sizes = self.active_editor.splitter.sizes()
            if sizes[2] != 0:
                conf.setValue('error_panel_size', sizes[2])

        while self.tabs.count() > 0:
            w = self.tabs.widget(0)
            if isinstance(w, editor.Editor):
                if not self.close_tab(w):
                    event.ignore()
                    return
            else:
                raise RuntimeError("Unexpected widget in tab list")

        event.accept()

    def build_menu(self) -> None:
        menu = QMenuBar()
        file_menu = menu.addMenu("&File")
        edit_menu = menu.addMenu("&Edit")
        code_menu = menu.addMenu("&Code")
        view_menu = menu.addMenu("&View")

        self.file_open_recent = file_menu.addMenu("Open &Recent")
        self.update_recent_files()

        # code_run = code_menu.addAction("&Run")
        # code_run.setShortcut(QKeySequence("Ctrl+R"))
        # code_run.triggered.connect(self.update_state)

        view_menu.addSeparator()
        self.view_themes = view_menu.addMenu("&Themes")
        self.update_themes()

        self.setMenuBar(menu)
