# -*- coding: utf-8 -*-
"""
File-header viewer shared by the 1D and 2D Data Treatment windows.

Atomize-saved CSVs carry a leading '#' comment block with the acquisition
parameters (field range, frequency, scans, temperature, …) followed by the
pulse / AWG-pulse lists and, on the last line, the column names. Both treatment
tools used to read only the pieces they needed (column labels in the 1D tool,
Horizontal/Vertical Resolution in the 2D one) and drop the rest; this module
keeps the whole block and shows it in a separate non-modal window.

`HeaderWindow` holds several named sources (one per loaded trace in the 1D
tool, one dataset in the 2D one), renders each as a parsed two-column table
— parameters as key/value, every '{...}' pulse dict as one wrapped row — and
switches to the verbatim text with the "Raw" box. The filter box narrows rows
(or lines, in raw mode) to those containing the typed text. It is only ever
opened by the tools' "Header…" button, never by itself on a load.

Bruker datasets have no '#' block; `params_to_lines` turns the descriptor dict
returned by bruker_opener into the same line list, so the viewer serves them too.
"""

import os
import ast

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QFont, QGuiApplication
from PyQt6.QtWidgets import (QWidget, QLabel, QComboBox, QCheckBox, QLineEdit,
    QPushButton, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPlainTextEdit, QHeaderView, QAbstractItemView)

from atomize.general_modules.gui_style import (BG, BASE, FG, BORDER, ACCENT,
    BUTTON_STYLE, LABEL_STYLE, COMBO_STYLE, LINEEDIT_STYLE, CHECKBOX_STYLE,
    SCROLL_STYLE)

# A file with no data rows (all comments) must not be slurped whole.
MAX_HEADER_LINES = 500

# Selection follows the main window's lists (main_window.py): the panel colour
# with accent text, not a filled highlight.
TABLE_STYLE = f"""
QTableWidget {{ background-color: {BG}; color: {FG};
                border: 1px solid {BORDER}; outline: 0;
                gridline-color: {BASE};
                selection-background-color: {BASE};
                selection-color: {ACCENT}; }}
QTableWidget::item {{ padding: 3px 6px; }}
QHeaderView::section {{ background-color: {BASE}; color: {FG};
                        border: 0px; border-bottom: 1px solid {BORDER};
                        padding: 4px; }}
"""

TEXT_STYLE = f"""
QPlainTextEdit {{ background-color: {BG}; color: {FG};
                  border: 1px solid {BORDER}; }}
"""


# ------------------------------------------------------------------ reading
def read_header(path):
    """The leading '#' comment block of `path` as a list of lines, '#' stripped.
    Returns [] for a file without one (or one that cannot be read): a header is
    a nicety, never a reason to fail a load."""
    lines = []
    if str(path).endswith('.h5'):
        try:
            import h5py
            with h5py.File(path, 'r') as fh:
                lines = str(fh.attrs.get('header', '')).splitlines()
        except Exception:
            return []
        return lines[:MAX_HEADER_LINES]

    try:
        with open(path, 'r', errors='ignore') as fh:
            for line in fh:
                if not line.strip():
                    continue                   # blank line inside the block
                if not line.startswith('#'):
                    break
                lines.append(line.rstrip('\n').lstrip('#').rstrip())
                if len(lines) >= MAX_HEADER_LINES:
                    break
    except Exception:
        return []
    return lines


def params_to_lines(params):
    """A Bruker descriptor dict -> the '<key>: <value>' line list the viewer eats."""
    try:
        return [f'{k}: {v}' for k, v in params.items()]
    except Exception:
        return []


# ------------------------------------------------------------------ parsing
def _fmt(value):
    """Compact scalar rendering; long floats (amp 2.380952380952381) get 4 digits."""
    if isinstance(value, float):
        return f'{value:.4g}'
    if isinstance(value, (list, tuple)):
        return ', '.join(str(v) for v in value) if value else '—'
    return str(value)


def _format_pulse(text):
    """A '{...}' pulse-dict header line -> (pulse name, one-line summary)."""
    try:
        d = ast.literal_eval(text)
        if not isinstance(d, dict):
            raise ValueError
    except Exception:
        return '', text                    # not a dict after all: show it verbatim
    name = str(d.pop('name', '')) or '?'
    parts = []
    channel = d.pop('channel', None)
    if channel is not None:
        parts.append(str(channel))
    parts += [f'{k} {_fmt(v)}' for k, v in d.items()]
    return name, '   '.join(parts)


def _opens_section(title, rest):
    """Does a bare '<title>:' line head a section, or is it just an empty value?
    It heads one when it is named '… List' or is followed by a pulse dict —
    otherwise a parameter left blank would swallow everything after it."""
    if title.lower().endswith('list'):
        return True
    for line in rest:
        s = line.strip()
        if not s or set(s) <= set('-=_* '):
            continue
        return s.startswith('{')
    return False


def parse_header(lines):
    """Split a header line list into [(section title, [(col0, col1), …]), …].

    A line ending in ':' with nothing after it opens a section ('Pulse List:',
    'AWG Pulse List:'); '{...}' lines become one row per pulse; everything else
    splits on the first ':' into key / value. Decorative '-----' separators are
    dropped, and a trailing comma-separated line is the column-name row."""
    sections = [('Parameters', [])]
    last = len(lines) - 1
    for i, raw in enumerate(lines):
        s = raw.strip()
        if not s or set(s) <= set('-=_* '):
            continue
        if s.startswith('{'):
            sections[-1][1].append(_format_pulse(s))
        elif (s.endswith(':') and len(s) < 40
                and _opens_section(s[:-1].strip(), lines[i + 1:])):
            sections.append((s[:-1].strip(), []))
        elif ':' in s:
            k, v = s.split(':', 1)
            sections[-1][1].append((k.strip(), v.strip()))
        elif i == last and ',' in s:
            sections.append(('Data columns', [(c.strip(), '') for c in s.split(',')]))
        else:
            sections[-1][1].append((s, ''))
    return [(title, rows) for title, rows in sections if rows]


# ------------------------------------------------------------------- window
class HeaderWindow(QWidget):
    """Non-modal viewer for the parameter header(s) of the loaded file(s).

    The owner keeps one instance, calls `set_sources` after every load /
    removal and shows it only on demand ("Header…")."""

    NO_HEADER = ('No parameter header — this dataset came from the plot buffer '
                 '("Send to Data Treatment") or from a file without one.')

    def __init__(self, parent=None, title='File header'):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle(title)
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 'gui', 'icon_treat.ico')
        if os.path.isfile(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.setStyleSheet(f'background-color: {BG};')
        self.resize(820, 640)
        self._sources = {}                 # name -> header lines (in load order)
        self._sections = []                # [(section row, title, [(row, text)])]

        root = QVBoxLayout(self)

        top = QHBoxLayout()
        self._src_label = QLabel('Dataset')
        self._src_label.setStyleSheet(LABEL_STYLE)
        top.addWidget(self._src_label)
        self.src_combo = QComboBox()
        self.src_combo.setStyleSheet(COMBO_STYLE)
        self.src_combo.currentIndexChanged.connect(lambda *_: self._render())
        top.addWidget(self.src_combo, 1)
        self.raw_check = QCheckBox('Raw')
        self.raw_check.setStyleSheet(CHECKBOX_STYLE)
        self.raw_check.stateChanged.connect(lambda *_: self._render())
        top.addWidget(self.raw_check)
        copy_btn = QPushButton('Copy')
        copy_btn.setStyleSheet(BUTTON_STYLE)
        copy_btn.clicked.connect(self._copy)
        top.addWidget(copy_btn)
        root.addLayout(top)

        self.filter_edit = QLineEdit()
        self.filter_edit.setStyleSheet(LINEEDIT_STYLE)
        self.filter_edit.setPlaceholderText('Filter…  (e.g. "temp", "P3", "phase")')
        self.filter_edit.textChanged.connect(lambda *_: self._apply_filter())
        root.addWidget(self.filter_edit)

        mono = QFont('Monospace')
        mono.setStyleHint(QFont.StyleHint.TypeWriter)

        # a table, not a tree: the value cells wrap over as many lines as they
        # need (long pulse rows) instead of running off to the right
        self.table = QTableWidget(0, 2)
        self.table.setStyleSheet(TABLE_STYLE + SCROLL_STYLE)
        self.table.setHorizontalHeaderLabels(['Parameter', 'Value'])
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(True)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

        self.text = QPlainTextEdit()
        self.text.setStyleSheet(TEXT_STYLE + SCROLL_STYLE)
        self.text.setReadOnly(True)
        self.text.setFont(mono)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.text.hide()
        root.addWidget(self.text, 1)

    # ---------------------------------------------------------------- public
    def set_sources(self, sources, active=None):
        """Replace the source list with `sources` — a list of (name, lines),
        `lines` empty for a dataset without a header. Keeps the current
        selection when it survives, unless `active` names another one."""
        self._sources = {name: list(lines or []) for name, lines in sources}
        keep = active if active in self._sources else self.src_combo.currentText()
        self.src_combo.blockSignals(True)
        self.src_combo.clear()
        self.src_combo.addItems(list(self._sources))
        if keep in self._sources:
            self.src_combo.setCurrentIndex(list(self._sources).index(keep))
        self.src_combo.blockSignals(False)
        # kept visible with a single source (it names it) but not clickable
        self.src_combo.setEnabled(len(self._sources) > 1)
        self._render()

    def select(self, name):
        """Switch the view to the named source (no-op if it is not loaded)."""
        if name in self._sources:
            self.src_combo.setCurrentIndex(list(self._sources).index(name))

    def show_source(self, name=None):
        """Bring the window up, showing `name` when given."""
        if name:
            self.select(name)
        self.show()
        self.raise_()
        self.activateWindow()

    # --------------------------------------------------------------- private
    def _current_lines(self):
        return self._sources.get(self.src_combo.currentText(), [])

    def _copy(self):
        lines = self._current_lines()
        if lines:
            QGuiApplication.clipboard().setText('\n'.join(lines))

    def _add_row(self, col0, col1='', section=False):
        """Append one table row; a section row is bold and spans both columns."""
        r = self.table.rowCount()
        self.table.insertRow(r)
        item = QTableWidgetItem(col0)
        item.setTextAlignment(int(Qt.AlignmentFlag.AlignLeft
                                  | Qt.AlignmentFlag.AlignVCenter))
        if section:
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        self.table.setItem(r, 0, item)
        if section:
            self.table.setSpan(r, 0, 1, 2)
        else:
            value = QTableWidgetItem(col1)
            value.setTextAlignment(int(Qt.AlignmentFlag.AlignLeft
                                       | Qt.AlignmentFlag.AlignVCenter))
            self.table.setItem(r, 1, value)
        return r

    def _render(self):
        name = self.src_combo.currentText()
        self.setWindowTitle(f'File header — {name}' if name else 'File header')
        lines = self._current_lines()
        raw = self.raw_check.isChecked()
        self.table.setVisible(not raw)
        self.text.setVisible(raw)
        if raw:
            self._apply_filter()               # fills the text view
            return
        self.table.clearSpans()
        self.table.setRowCount(0)
        self._sections = []                    # [(section row, [(row, text), …])]
        if not lines:
            self._add_row(self.NO_HEADER, section=True)
            self._fit_rows()
            return
        for title, rows in parse_header(lines):
            sec_row = self._add_row(title, section=True)
            body = [(self._add_row(c0, c1), f'{c0} {c1}'.lower()) for c0, c1 in rows]
            self._sections.append((sec_row, title.lower(), body))
        self._apply_filter()

    def _fit_rows(self):
        """Re-measure row heights: with word wrap on, a row is as tall as its
        wrapped value needs, so this must re-run whenever the width changes."""
        self.table.resizeRowsToContents()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_rows()

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_rows()                       # widths are only final once shown

    def _apply_filter(self):
        query = self.filter_edit.text().strip().lower()
        if self.raw_check.isChecked():
            lines = self._current_lines()
            if query:
                lines = [ln for ln in lines if query in ln.lower()]
            self.text.setPlainText('\n'.join(lines) or self.NO_HEADER)
            return
        for sec_row, title, body in self._sections:
            # a section whose title matches keeps all its rows visible
            title_hit = bool(query) and query in title
            shown = 0
            for row, text in body:
                hit = not query or title_hit or query in text
                self.table.setRowHidden(row, not hit)
                shown += hit
            self.table.setRowHidden(sec_row, bool(query) and not shown)
        self._fit_rows()
