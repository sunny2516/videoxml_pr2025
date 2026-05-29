"""
PR口播工具 - 主界面
"""
import sys
import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog,
    QListWidget, QListWidgetItem, QTextEdit,
    QCheckBox, QSpinBox, QGroupBox, QScrollArea,
    QMessageBox, QProgressBar, QSizePolicy, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from data.models import (
    ProjectConfig, VocalGroup, KeywordMapping,
    load_recent_projects, add_recent_project,
)
from core.scanner import scan_footage_folder, scan_vocal_folder
from core.generator import process_project, process_single_file

# ─── 样式 ─────────────────────────────────────────────────────────────────────
STYLE = """
QMainWindow, QDialog { background: #1a1a2e; }
QWidget { background: #1a1a2e; color: #e0e0e0;
          font-family: 'Microsoft YaHei UI','Segoe UI',sans-serif; font-size: 13px; }
QTabWidget::pane { border: 1px solid #2d2d44; background: #16213e; border-radius: 6px; }
QTabBar::tab { background: #2d2d44; color: #888; padding: 8px 22px;
               border-radius: 4px 4px 0 0; margin-right: 3px; min-width: 90px; }
QTabBar::tab:selected { background: #0f3460; color: #e94560; font-weight: bold;
                        border-top: 2px solid #e94560; }
QTabBar::tab:hover:!selected { background: #2a2a50; color: #ccc; }

QPushButton {
    background: #2d2d44; color: #ccc; border: 1px solid #3d3d60;
    border-radius: 5px; padding: 5px 14px; font-size: 12px;
}
QPushButton:hover { background: #3d3d60; border-color: #e94560; color: #fff; }
QPushButton:pressed { background: #e94560; color: #fff; border-color: #e94560; }
QPushButton#btn_primary { background: #0f3460; color: #e0e0e0;
                          border: 1px solid #1a5276; font-weight: bold; }
QPushButton#btn_primary:hover { background: #1a4a80; border-color: #e94560; }
QPushButton#btn_success { background: #145a32; color: #a9dfbf;
                           border: 1px solid #1e8449; font-weight: bold; }
QPushButton#btn_success:hover { background: #1e8449; color: #fff; }
QPushButton#btn_danger { background: #641e16; color: #f1948a;
                          border: 1px solid #922b21; }
QPushButton#btn_danger:hover { background: #922b21; color: #fff; }
QPushButton#btn_warn { background: #784212; color: #f0b27a;
                        border: 1px solid #a04000; }
QPushButton#btn_warn:hover { background: #a04000; color: #fff; }
QPushButton:disabled { background: #222; color: #555; border-color: #333; }

QLineEdit {
    background: #0d1b2a; border: 1px solid #2d2d44;
    border-radius: 4px; padding: 5px 8px; color: #e0e0e0;
}
QLineEdit:focus { border-color: #e94560; }
QLineEdit:read-only { background: #111827; color: #888; }

QGroupBox {
    border: 1px solid #2d2d44; border-radius: 6px;
    margin-top: 10px; padding-top: 10px; color: #e94560; font-weight: bold;
}
QGroupBox::title { subcontrol-origin: margin; padding: 0 8px; }

QTableWidget {
    background: #0d1b2a; border: 1px solid #2d2d44;
    gridline-color: #1a2a3a; alternate-background-color: #111827;
    border-radius: 4px;
}
QTableWidget::item { padding: 4px 6px; }
QTableWidget::item:selected { background: #0f3460; color: #e94560; }
QHeaderView::section {
    background: #16213e; color: #888; border: none;
    border-bottom: 1px solid #2d2d44; padding: 5px;
    font-weight: bold; font-size: 11px;
}

QTextEdit {
    background: #0a0f1a; border: 1px solid #1a2a3a;
    border-radius: 4px; color: #00ff88;
    font-family: 'Consolas','Courier New',monospace; font-size: 11px;
}
QCheckBox { color: #ccc; spacing: 6px; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #3d3d60; border-radius: 3px; }
QCheckBox::indicator:checked { background: #e94560; border-color: #e94560; }
QSpinBox {
    background: #0d1b2a; border: 1px solid #2d2d44;
    border-radius: 4px; padding: 4px 6px; color: #e0e0e0;
}
QSpinBox:focus { border-color: #e94560; }
QProgressBar {
    background: #0d1b2a; border: none; border-radius: 3px; height: 6px;
}
QProgressBar::chunk { background: #e94560; border-radius: 3px; }
QScrollBar:vertical { background: #0d1b2a; width: 7px; border-radius: 3px; }
QScrollBar::handle:vertical { background: #2d2d44; border-radius: 3px; min-height: 20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QListWidget {
    background: #0d1b2a; border: 1px solid #2d2d44;
    border-radius: 4px; alternate-background-color: #111827;
}
QListWidget::item { padding: 5px 8px; }
QListWidget::item:selected { background: #0f3460; color: #e94560; }
QLabel#lbl_hint { color: #555; font-size: 11px; }
QLabel#lbl_section { color: #e94560; font-weight: bold; font-size: 12px; }
QFrame#sep { background: #2d2d44; max-height: 1px; }
"""

# ─── 生成线程 ──────────────────────────────────────────────────────────────────
class GenerateThread(QThread):
    log_signal      = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)
    done_signal     = pyqtSignal(dict)

    def __init__(self, config, single=False, sv='', ss='', so=''):
        super().__init__()
        self.config = config
        self.single = single
        self.sv, self.ss, self.so = sv, ss, so

    def run(self):
        try:
            if self.single:
                ok = process_single_file(
                    video_path=self.sv, srt_path=self.ss, output_folder=self.so,
                    keyword_mappings=self.config.keyword_mappings,
                    sequence_fps=self.config.fps,
                    width=self.config.width, height=self.config.height,
                    png_path=getattr(self.config, 'png_path', ''),
                    log_fn=self.log_signal.emit,
                )
                self.done_signal.emit({'success': 1 if ok else 0, 'failed': 0 if ok else 1})
            else:
                result = process_project(
                    config=self.config,
                    log_fn=self.log_signal.emit,
                    progress_fn=self.progress_signal.emit,
                )
                self.done_signal.emit(result)
        except Exception as e:
            import traceback
            self.log_signal.emit(f'✗ 严重错误：{e}\n{traceback.format_exc()}')
            self.done_signal.emit({'success': 0, 'failed': 1})


# ─── 口播组行控件 ──────────────────────────────────────────────────────────────
class VocalGroupRow(QWidget):
    removed = pyqtSignal(object)

    def __init__(self, group: VocalGroup, parent=None):
        super().__init__(parent)
        self.group = group
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(6)

        self.chk = QCheckBox()
        self.chk.setChecked(group.enabled)
        self.chk.setToolTip('启用/禁用此口播组')
        self.chk.toggled.connect(lambda v: setattr(self.group, 'enabled', v))
        lay.addWidget(self.chk)

        self.edit_name = QLineEdit(group.name)
        self.edit_name.setPlaceholderText('组名')
        self.edit_name.setFixedWidth(90)
        self.edit_name.setToolTip('口播组名称，将作为XML文件名')
        self.edit_name.textChanged.connect(lambda v: setattr(self.group, 'name', v))
        lay.addWidget(self.edit_name)

        self.edit_input = QLineEdit(group.input_folder)
        self.edit_input.setPlaceholderText('口播文件夹路径...')
        self.edit_input.setToolTip('包含口播视频和SRT字幕的文件夹')
        self.edit_input.textChanged.connect(lambda v: setattr(self.group, 'input_folder', v))
        lay.addWidget(self.edit_input)

        btn_in = QPushButton('📂 选择输入')
        btn_in.setToolTip('选择口播文件夹')
        btn_in.setFixedWidth(90)
        btn_in.clicked.connect(self._pick_input)
        lay.addWidget(btn_in)

        self.edit_output = QLineEdit(group.output_folder)
        self.edit_output.setPlaceholderText('XML输出文件夹...')
        self.edit_output.setToolTip('生成的XML文件保存位置')
        self.edit_output.textChanged.connect(lambda v: setattr(self.group, 'output_folder', v))
        lay.addWidget(self.edit_output)

        btn_out = QPushButton('📂 选择输出')
        btn_out.setToolTip('选择XML输出文件夹')
        btn_out.setFixedWidth(90)
        btn_out.clicked.connect(self._pick_output)
        lay.addWidget(btn_out)

        btn_del = QPushButton('🗑 删除')
        btn_del.setObjectName('btn_danger')
        btn_del.setToolTip('删除此口播组')
        btn_del.setFixedWidth(70)
        btn_del.clicked.connect(lambda: self.removed.emit(self))
        lay.addWidget(btn_del)

    def _pick_input(self):
        d = QFileDialog.getExistingDirectory(self, '选择口播文件夹')
        if d: self.edit_input.setText(d)

    def _pick_output(self):
        d = QFileDialog.getExistingDirectory(self, '选择XML输出文件夹')
        if d: self.edit_output.setText(d)


# ─── 关键词行控件 ──────────────────────────────────────────────────────────────
class KeywordRow(QWidget):
    removed = pyqtSignal(object)

    def __init__(self, km: KeywordMapping, parent=None):
        super().__init__(parent)
        self.km = km
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 1, 2, 1)
        lay.setSpacing(6)

        self.chk = QCheckBox()
        self.chk.setChecked(km.enabled)
        self.chk.setToolTip('启用/禁用此关键词')
        self.chk.toggled.connect(lambda v: setattr(self.km, 'enabled', v))
        lay.addWidget(self.chk)

        self.lbl = QLabel(km.keyword)
        self.lbl.setFixedWidth(150)
        self.lbl.setToolTip('关键词（A~B表示范围匹配）')
        color = '#f0b27a' if '~' in km.keyword else '#a9cce3'
        self.lbl.setStyleSheet(f'color:{color}; font-weight:bold; font-size:12px;')
        lay.addWidget(self.lbl)

        lbl_arr = QLabel('→')
        lbl_arr.setStyleSheet('color:#555;')
        lbl_arr.setFixedWidth(16)
        lay.addWidget(lbl_arr)

        self.edit_path = QLineEdit(km.folder_path)
        self.edit_path.setToolTip('对应的镜头素材文件夹')
        self.edit_path.textChanged.connect(lambda v: setattr(self.km, 'folder_path', v))
        lay.addWidget(self.edit_path)

        btn_pick = QPushButton('📂')
        btn_pick.setToolTip('选择镜头文件夹')
        btn_pick.setFixedWidth(36)
        btn_pick.clicked.connect(self._pick)
        lay.addWidget(btn_pick)

        btn_del = QPushButton('✕')
        btn_del.setObjectName('btn_danger')
        btn_del.setToolTip('删除此关键词')
        btn_del.setFixedWidth(32)
        btn_del.clicked.connect(lambda: self.removed.emit(self))
        lay.addWidget(btn_del)

    def _pick(self):
        d = QFileDialog.getExistingDirectory(self, '选择镜头文件夹')
        if d: self.edit_path.setText(d)


# ─── Tab1：工程管理 ────────────────────────────────────────────────────────────
class ProjectTab(QWidget):
    project_loaded = pyqtSignal(ProjectConfig, str)

    def __init__(self):
        super().__init__()
        self._path = ''
        self._config: ProjectConfig = None
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(14)

        title = QLabel('工程管理')
        title.setStyleSheet('font-size:18px; font-weight:bold; color:#e94560;')
        lay.addWidget(title)

        # 新建
        grp_new = QGroupBox('新建工程')
        gl = QHBoxLayout(grp_new)
        gl.addWidget(QLabel('工程名称：'))
        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText('如：感康、杞药消渴...')
        gl.addWidget(self.edit_name)
        btn_new = QPushButton('✚ 新建')
        btn_new.setObjectName('btn_primary')
        btn_new.setToolTip('创建一个新工程')
        btn_new.clicked.connect(self._new)
        gl.addWidget(btn_new)
        lay.addWidget(grp_new)

        # 打开/保存
        grp_file = QGroupBox('打开 / 保存')
        fl = QHBoxLayout(grp_file)
        btn_open = QPushButton('📂 打开工程')
        btn_open.setToolTip('打开已保存的 .prtool.json 工程文件')
        btn_open.clicked.connect(self._open)
        fl.addWidget(btn_open)
        btn_save = QPushButton('💾 保存工程')
        btn_save.setObjectName('btn_success')
        btn_save.setToolTip('保存当前工程到文件')
        btn_save.clicked.connect(self._save)
        fl.addWidget(btn_save)
        btn_saveas = QPushButton('📋 另存为')
        btn_saveas.setToolTip('另存为新文件')
        btn_saveas.clicked.connect(self._saveas)
        fl.addWidget(btn_saveas)
        lay.addWidget(grp_file)

        # 最近工程
        grp_recent = QGroupBox('最近打开的工程')
        rl = QVBoxLayout(grp_recent)
        self.list_recent = QListWidget()
        self.list_recent.setAlternatingRowColors(True)
        self.list_recent.setToolTip('双击打开最近使用的工程')
        self.list_recent.itemDoubleClicked.connect(
            lambda item: self._load_path(item.text()))
        rl.addWidget(self.list_recent)
        hint = QLabel('双击列表中的工程快速打开')
        hint.setObjectName('lbl_hint')
        rl.addWidget(hint)
        lay.addWidget(grp_recent)
        lay.addStretch()
        self._refresh_recent()

    def _refresh_recent(self):
        self.list_recent.clear()
        for p in load_recent_projects():
            self.list_recent.addItem(QListWidgetItem(p))

    def _new(self):
        name = self.edit_name.text().strip() or '新工程'
        cfg = ProjectConfig(project_name=name)
        self._config = cfg
        self._path = ''
        self.project_loaded.emit(cfg, '')
        QMessageBox.information(self, '新建工程', f'工程「{name}」已创建，请在「素材配置」Tab进行配置。')

    def _open(self):
        p, _ = QFileDialog.getOpenFileName(self, '打开工程', '', '工程文件 (*.prtool.json)')
        if p: self._load_path(p)

    def _load_path(self, p):
        try:
            cfg = ProjectConfig.load(p)
            self._config = cfg
            self._path = p
            add_recent_project(p)
            self._refresh_recent()
            self.project_loaded.emit(cfg, p)
        except Exception as e:
            QMessageBox.critical(self, '错误', f'打开失败：{e}')

    def _save(self):
        if not self._config:
            QMessageBox.warning(self, '提示', '请先新建或打开工程'); return
        if not self._path:
            self._saveas(); return
        self._config.save(self._path)
        QMessageBox.information(self, '保存', '工程已保存 ✓')

    def _saveas(self):
        if not self._config:
            QMessageBox.warning(self, '提示', '请先新建或打开工程'); return
        p, _ = QFileDialog.getSaveFileName(
            self, '另存为', f'{self._config.project_name}.prtool.json',
            '工程文件 (*.prtool.json)')
        if p:
            self._config.save(p)
            self._path = p
            add_recent_project(p)
            self._refresh_recent()

    def sync(self, cfg, path):
        self._config = cfg
        self._path = path

    def request_save(self):
        self._save()


# ─── Tab2：素材配置 ────────────────────────────────────────────────────────────
class ConfigTab(QWidget):
    def __init__(self):
        super().__init__()
        self._config: ProjectConfig = None
        self._kw_rows = []
        self._grp_rows = []
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        title = QLabel('素材配置')
        title.setStyleSheet('font-size:18px; font-weight:bold; color:#e94560;')
        lay.addWidget(title)

        # ── 序列参数 ──
        grp_seq = QGroupBox('序列参数')
        sl = QHBoxLayout(grp_seq)
        sl.addWidget(QLabel('帧率 (fps)：'))
        self.spin_fps = QSpinBox()
        self.spin_fps.setRange(1, 120); self.spin_fps.setValue(30)
        self.spin_fps.setToolTip('序列帧率，默认30fps')
        sl.addWidget(self.spin_fps)
        sl.addSpacing(20)
        sl.addWidget(QLabel('宽：'))
        self.spin_w = QSpinBox()
        self.spin_w.setRange(1, 9999); self.spin_w.setValue(1080)
        sl.addWidget(self.spin_w)
        sl.addWidget(QLabel('× 高：'))
        self.spin_h = QSpinBox()
        self.spin_h.setRange(1, 9999); self.spin_h.setValue(1920)
        sl.addWidget(self.spin_h)
        sl.addSpacing(20)
        sl.addWidget(QLabel('广审PNG (V3轨)：'))
        self.edit_png = QLineEdit()
        self.edit_png.setPlaceholderText('可选，选择透明PNG图片...')
        self.edit_png.setToolTip('可选：广审PNG将放在V3轨道，全口播时长覆盖')
        sl.addWidget(self.edit_png)
        btn_png = QPushButton('📂 选择PNG')
        btn_png.setToolTip('选择广审透明PNG文件')
        btn_png.clicked.connect(self._pick_png)
        sl.addWidget(btn_png)
        sl.addStretch()
        lay.addWidget(grp_seq)

        # ── 关键词标签 ──
        grp_kw = QGroupBox('关键词标签（子文件夹名 = 关键词，支持「A~B」范围匹配）')
        kl = QVBoxLayout(grp_kw)

        # 镜头库路径行
        lib_row = QHBoxLayout()
        lib_row.addWidget(QLabel('镜头母文件夹：'))
        self.edit_lib = QLineEdit()
        self.edit_lib.setPlaceholderText('选择包含多个子文件夹的镜头库根目录...')
        self.edit_lib.setToolTip('镜头库根目录，子文件夹名自动成为关键词')
        lib_row.addWidget(self.edit_lib)
        btn_lib = QPushButton('📂 选择文件夹')
        btn_lib.setToolTip('选择镜头库根目录')
        btn_lib.clicked.connect(self._pick_lib)
        lib_row.addWidget(btn_lib)
        btn_scan = QPushButton('🔍 扫描并导入')
        btn_scan.setObjectName('btn_primary')
        btn_scan.setToolTip('扫描子文件夹，自动生成关键词（已存在的自动跳过）')
        btn_scan.clicked.connect(self._scan)
        lib_row.addWidget(btn_scan)
        kl.addLayout(lib_row)

        # 操作栏
        op_row = QHBoxLayout()
        lbl_kw = QLabel('关键词列表：')
        lbl_kw.setObjectName('lbl_section')
        op_row.addWidget(lbl_kw)
        op_row.addStretch()
        btn_all = QPushButton('☑ 全选')
        btn_all.setToolTip('启用所有关键词')
        btn_all.setFixedWidth(70)
        btn_all.clicked.connect(self._select_all)
        op_row.addWidget(btn_all)
        btn_inv = QPushButton('⊘ 反选')
        btn_inv.setToolTip('反转所有关键词的启用状态')
        btn_inv.setFixedWidth(70)
        btn_inv.clicked.connect(self._invert_sel)
        op_row.addWidget(btn_inv)
        op_row.addSpacing(10)
        hint_kw = QLabel('蓝色=普通关键词  橙色=A~B范围匹配')
        hint_kw.setObjectName('lbl_hint')
        op_row.addWidget(hint_kw)
        kl.addLayout(op_row)

        # 关键词滚动区
        self.kw_scroll = QScrollArea()
        self.kw_scroll.setWidgetResizable(True)
        self.kw_scroll.setMinimumHeight(180)
        self.kw_container = QWidget()
        self.kw_layout = QVBoxLayout(self.kw_container)
        self.kw_layout.setSpacing(2)
        self.kw_layout.setContentsMargins(2, 2, 2, 2)
        self.kw_layout.addStretch()
        self.kw_scroll.setWidget(self.kw_container)
        kl.addWidget(self.kw_scroll)

        # 手动添加行
        add_row = QHBoxLayout()
        add_row.addWidget(QLabel('手动添加：'))
        self.edit_new_kw = QLineEdit()
        self.edit_new_kw.setPlaceholderText('关键词（支持 A~B 格式）')
        self.edit_new_kw.setToolTip('输入关键词，A~B格式表示范围匹配')
        self.edit_new_kw.setFixedWidth(180)
        add_row.addWidget(self.edit_new_kw)
        self.edit_new_path = QLineEdit()
        self.edit_new_path.setPlaceholderText('对应镜头文件夹路径...')
        add_row.addWidget(self.edit_new_path)
        btn_new_pick = QPushButton('📂')
        btn_new_pick.setFixedWidth(36)
        btn_new_pick.setToolTip('选择镜头文件夹')
        btn_new_pick.clicked.connect(self._pick_new_path)
        add_row.addWidget(btn_new_pick)
        btn_add = QPushButton('✚ 添加')
        btn_add.setObjectName('btn_primary')
        btn_add.setToolTip('添加关键词')
        btn_add.clicked.connect(self._add_kw_manual)
        add_row.addWidget(btn_add)
        kl.addLayout(add_row)
        lay.addWidget(grp_kw)

        # ── 口播文件夹组 ──
        grp_grp = QGroupBox('口播文件夹组（每组对应一套文案，生成一个XML文件）')
        gl2 = QVBoxLayout(grp_grp)

        # 列头说明
        hdr = QHBoxLayout()
        for txt, w in [('启', 30), ('组名', 90), ('口播输入文件夹', 0),
                        ('', 90), ('XML输出文件夹', 0), ('', 90), ('', 70)]:
            l = QLabel(txt)
            l.setStyleSheet('color:#555; font-size:10px;')
            if w: l.setFixedWidth(w)
            hdr.addWidget(l)
        gl2.addLayout(hdr)

        self.grp_scroll = QScrollArea()
        self.grp_scroll.setWidgetResizable(True)
        self.grp_scroll.setMinimumHeight(160)
        self.grp_container = QWidget()
        self.grp_layout = QVBoxLayout(self.grp_container)
        self.grp_layout.setSpacing(3)
        self.grp_layout.setContentsMargins(2, 2, 2, 2)
        self.grp_layout.addStretch()
        self.grp_scroll.setWidget(self.grp_container)
        gl2.addWidget(self.grp_scroll)

        btn_add_grp = QPushButton('✚ 添加口播组')
        btn_add_grp.setObjectName('btn_primary')
        btn_add_grp.setToolTip('添加一个口播文件夹组')
        btn_add_grp.clicked.connect(self._add_grp)
        gl2.addWidget(btn_add_grp)
        lay.addWidget(grp_grp)

    # ── 关键词操作 ──
    def _select_all(self):
        for row in self._kw_rows:
            row.chk.setChecked(True)

    def _invert_sel(self):
        for row in self._kw_rows:
            row.chk.setChecked(not row.chk.isChecked())

    def _pick_lib(self):
        d = QFileDialog.getExistingDirectory(self, '选择镜头母文件夹')
        if d: self.edit_lib.setText(d)

    def _pick_png(self):
        p, _ = QFileDialog.getOpenFileName(self, '选择广审PNG', '', 'PNG图片 (*.png)')
        if p: self.edit_png.setText(p)

    def _scan(self):
        folder = self.edit_lib.text().strip()
        if not folder:
            QMessageBox.warning(self, '提示', '请先选择镜头母文件夹'); return
        try:
            kw_folders = scan_footage_folder(folder)
        except Exception as e:
            QMessageBox.critical(self, '错误', f'扫描失败：{e}'); return
        if not kw_folders:
            QMessageBox.information(self, '扫描结果', '未找到任何子文件夹'); return

        # 已存在的文件夹路径去重（需求5）
        existing_paths = {row.km.folder_path for row in self._kw_rows}
        existing_kws = {row.km.keyword for row in self._kw_rows}
        added = 0
        for kw, fp in kw_folders:
            if kw in existing_kws or fp in existing_paths:
                continue
            km = KeywordMapping(keyword=kw, folder_path=fp, enabled=True)
            if self._config:
                self._config.keyword_mappings.append(km)
            self._add_kw_row(km)
            added += 1
        skipped = len(kw_folders) - added
        msg = f'扫描完成：新增 {added} 个关键词'
        if skipped: msg += f'，跳过 {skipped} 个重复'
        QMessageBox.information(self, '扫描完成', msg)

    def _pick_new_path(self):
        d = QFileDialog.getExistingDirectory(self, '选择镜头文件夹')
        if d: self.edit_new_path.setText(d)

    def _add_kw_manual(self):
        kw = self.edit_new_kw.text().strip()
        if not kw:
            QMessageBox.warning(self, '提示', '请输入关键词'); return
        # 检查重复
        existing_kws = {row.km.keyword for row in self._kw_rows}
        if kw in existing_kws:
            QMessageBox.warning(self, '提示', f'关键词「{kw}」已存在'); return
        fp = self.edit_new_path.text().strip()
        km = KeywordMapping(keyword=kw, folder_path=fp, enabled=True)
        if self._config:
            self._config.keyword_mappings.append(km)
        self._add_kw_row(km)
        self.edit_new_kw.clear()
        self.edit_new_path.clear()

    def _add_kw_row(self, km: KeywordMapping):
        row = KeywordRow(km, self.kw_container)
        row.removed.connect(self._remove_kw_row)
        self._kw_rows.append(row)
        self.kw_layout.insertWidget(self.kw_layout.count() - 1, row)

    def _remove_kw_row(self, row: KeywordRow):
        if self._config and row.km in self._config.keyword_mappings:
            self._config.keyword_mappings.remove(row.km)
        self._kw_rows.remove(row)
        row.deleteLater()

    def _add_grp(self):
        grp = VocalGroup(name=f'文案{len(self._grp_rows)+1}')
        if self._config:
            self._config.vocal_groups.append(grp)
        self._add_grp_row(grp)

    def _add_grp_row(self, grp: VocalGroup):
        row = VocalGroupRow(grp, self.grp_container)
        row.removed.connect(self._remove_grp_row)
        self._grp_rows.append(row)
        self.grp_layout.insertWidget(self.grp_layout.count() - 1, row)

    def _remove_grp_row(self, row: VocalGroupRow):
        if self._config and row.group in self._config.vocal_groups:
            self._config.vocal_groups.remove(row.group)
        self._grp_rows.remove(row)
        row.deleteLater()

    def load_config(self, cfg: ProjectConfig):
        self._config = cfg
        self.spin_fps.setValue(cfg.fps)
        self.spin_w.setValue(cfg.width)
        self.spin_h.setValue(cfg.height)
        self.edit_lib.setText(cfg.footage_folder)
        self.edit_png.setText(getattr(cfg, 'png_path', ''))

        for row in self._kw_rows[:]: row.deleteLater()
        self._kw_rows.clear()
        for km in cfg.keyword_mappings:
            self._add_kw_row(km)

        for row in self._grp_rows[:]: row.deleteLater()
        self._grp_rows.clear()
        for grp in cfg.vocal_groups:
            self._add_grp_row(grp)

    def sync_to_config(self):
        if not self._config: return
        self._config.fps = self.spin_fps.value()
        self._config.width = self.spin_w.value()
        self._config.height = self.spin_h.value()
        self._config.footage_folder = self.edit_lib.text().strip()
        self._config.png_path = self.edit_png.text().strip()


# ─── Tab3：生成 ────────────────────────────────────────────────────────────────
class GenerateTab(QWidget):
    log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._config = None
        self._thread = None
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(14)

        title = QLabel('生成 XML')
        title.setStyleSheet('font-size:18px; font-weight:bold; color:#e94560;')
        lay.addWidget(title)

        # ── 批量生成 ──
        grp_batch = QGroupBox('批量生成（按工程配置，所有口播组）')
        bl = QVBoxLayout(grp_batch)
        self.lbl_status = QLabel('当前工程：未加载')
        self.lbl_status.setStyleSheet('color:#a9cce3; font-size:12px;')
        bl.addWidget(self.lbl_status)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        bl.addWidget(self.progress)

        btn_row = QHBoxLayout()
        self.btn_gen = QPushButton('▶  开始生成全部口播组')
        self.btn_gen.setObjectName('btn_success')
        self.btn_gen.setToolTip('生成工程中所有启用的口播组')
        self.btn_gen.clicked.connect(self._start_batch)
        btn_row.addWidget(self.btn_gen)
        self.btn_stop = QPushButton('■  停止')
        self.btn_stop.setObjectName('btn_danger')
        self.btn_stop.setToolTip('强制停止当前生成任务')
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop)
        btn_row.addWidget(self.btn_stop)
        bl.addLayout(btn_row)
        lay.addWidget(grp_batch)

        # ── 单文件 ──
        grp_single = QGroupBox('单文件生成（快速测试单条口播）')
        gl = QGridLayout(grp_single)

        gl.addWidget(QLabel('口播视频：'), 0, 0)
        self.edit_sv = QLineEdit()
        self.edit_sv.setPlaceholderText('选择 .mp4 文件...')
        gl.addWidget(self.edit_sv, 0, 1)
        btn_sv = QPushButton('📂 选择视频')
        btn_sv.setToolTip('选择口播视频文件')
        btn_sv.setFixedWidth(100)
        btn_sv.clicked.connect(self._pick_sv)
        gl.addWidget(btn_sv, 0, 2)

        gl.addWidget(QLabel('字幕文件：'), 1, 0)
        self.edit_ss = QLineEdit()
        self.edit_ss.setPlaceholderText('选择 .srt 文件（选视频后自动填充）...')
        gl.addWidget(self.edit_ss, 1, 1)
        btn_ss = QPushButton('📂 选择字幕')
        btn_ss.setToolTip('选择SRT字幕文件')
        btn_ss.setFixedWidth(100)
        btn_ss.clicked.connect(self._pick_ss)
        gl.addWidget(btn_ss, 1, 2)

        gl.addWidget(QLabel('输出文件夹：'), 2, 0)
        self.edit_so = QLineEdit()
        self.edit_so.setPlaceholderText('选择XML输出文件夹...')
        gl.addWidget(self.edit_so, 2, 1)
        btn_so = QPushButton('📂 选择输出')
        btn_so.setToolTip('选择XML输出文件夹')
        btn_so.setFixedWidth(100)
        btn_so.clicked.connect(self._pick_so)
        gl.addWidget(btn_so, 2, 2)

        btn_single = QPushButton('▶  单文件生成')
        btn_single.setObjectName('btn_primary')
        btn_single.setToolTip('仅生成这一条口播的XML，用于快速测试')
        btn_single.clicked.connect(self._start_single)
        gl.addWidget(btn_single, 3, 1)
        lay.addWidget(grp_single)
        lay.addStretch()

    def load_config(self, cfg):
        self._config = cfg
        n = len([g for g in cfg.vocal_groups if g.enabled])
        self.lbl_status.setText(
            f'工程：{cfg.project_name}  |  帧率：{cfg.fps}fps  |  '
            f'分辨率：{cfg.width}×{cfg.height}  |  启用口播组：{n} 个')

    def _start_batch(self):
        if not self._config:
            QMessageBox.warning(self, '提示', '请先加载工程'); return
        if not any(g.enabled for g in self._config.vocal_groups):
            QMessageBox.warning(self, '提示', '没有启用的口播组'); return
        self._run()

    def _start_single(self):
        sv = self.edit_sv.text().strip()
        ss = self.edit_ss.text().strip()
        so = self.edit_so.text().strip()
        if not sv or not ss or not so:
            QMessageBox.warning(self, '提示', '请填写视频、字幕和输出文件夹'); return
        if not self._config:
            QMessageBox.warning(self, '提示', '请先加载工程（需要关键词配置）'); return
        self._run(single=True, sv=sv, ss=ss, so=so)

    def _run(self, single=False, sv='', ss='', so=''):
        if self._thread and self._thread.isRunning():
            QMessageBox.warning(self, '提示', '正在生成中，请等待'); return
        self.btn_gen.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self._thread = GenerateThread(self._config, single, sv, ss, so)
        self._thread.log_signal.connect(self.log_signal.emit)
        self._thread.progress_signal.connect(self._on_progress)
        self._thread.done_signal.connect(self._on_done)
        self._thread.start()

    def _on_progress(self, cur, total):
        self.progress.setRange(0, total)
        self.progress.setValue(cur)

    def _on_done(self, result):
        self.btn_gen.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress.setVisible(False)
        s, f = result.get('success', 0), result.get('failed', 0)
        QMessageBox.information(self, '完成', f'生成完成！\n✓ 成功：{s} 个\n✗ 失败：{f} 个')

    def _stop(self):
        if self._thread and self._thread.isRunning():
            self._thread.terminate()
        self.btn_gen.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress.setVisible(False)

    def _pick_sv(self):
        p, _ = QFileDialog.getOpenFileName(self, '选择口播视频', '', '视频文件 (*.mp4 *.mov)')
        if p:
            self.edit_sv.setText(p)
            srt = Path(p).with_suffix('.srt')
            if srt.exists(): self.edit_ss.setText(str(srt))

    def _pick_ss(self):
        p, _ = QFileDialog.getOpenFileName(self, '选择字幕文件', '', '字幕文件 (*.srt)')
        if p: self.edit_ss.setText(p)

    def _pick_so(self):
        d = QFileDialog.getExistingDirectory(self, '选择输出文件夹')
        if d: self.edit_so.setText(d)


# ─── Tab4：日志 ────────────────────────────────────────────────────────────────
class LogTab(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(8)

        hdr = QHBoxLayout()
        title = QLabel('运行日志')
        title.setStyleSheet('font-size:18px; font-weight:bold; color:#e94560;')
        hdr.addWidget(title)
        hdr.addStretch()
        btn_clear = QPushButton('🗑 清空')
        btn_clear.setToolTip('清空日志')
        btn_clear.clicked.connect(self._clear)
        hdr.addWidget(btn_clear)
        btn_copy = QPushButton('📋 复制')
        btn_copy.setToolTip('复制全部日志到剪贴板')
        btn_copy.clicked.connect(self._copy)
        hdr.addWidget(btn_copy)
        lay.addLayout(hdr)

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        lay.addWidget(self.log_edit)

    def append(self, msg: str):
        self.log_edit.append(msg)
        sb = self.log_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _clear(self): self.log_edit.clear()
    def _copy(self):
        QApplication.clipboard().setText(self.log_edit.toPlainText())


# ─── 主窗口 ────────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('PR 口播工具 v2.0')
        self.resize(1080, 760)
        self.setStyleSheet(STYLE)
        self._config = None
        self._path = ''
        self._build()

    def _build(self):
        cw = QWidget(); self.setCentralWidget(cw)
        root = QVBoxLayout(cw)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 顶部栏
        top = QFrame()
        top.setStyleSheet('background:#0f3460; border-bottom:1px solid #e94560;')
        tl = QHBoxLayout(top)
        tl.setContentsMargins(12, 6, 12, 6)

        lbl_title = QLabel('PR 口播工具')
        lbl_title.setStyleSheet('color:#e94560; font-size:16px; font-weight:900; letter-spacing:1px;')
        tl.addWidget(lbl_title)

        self.lbl_proj = QLabel('未加载工程')
        self.lbl_proj.setStyleSheet('color:#888; font-size:11px; margin-left:16px;')
        tl.addWidget(self.lbl_proj)
        tl.addStretch()

        btn_save = QPushButton('💾 保存工程')
        btn_save.setObjectName('btn_success')
        btn_save.setToolTip('快速保存当前工程')
        btn_save.clicked.connect(self._quick_save)
        tl.addWidget(btn_save)
        root.addWidget(top)

        # Tab容器
        self.tabs = QTabWidget()
        self.proj_tab = ProjectTab()
        self.conf_tab = ConfigTab()
        self.gen_tab  = GenerateTab()
        self.log_tab  = LogTab()

        self.tabs.addTab(self.proj_tab, '📁  工程管理')
        self.tabs.addTab(self.conf_tab, '⚙  素材配置')
        self.tabs.addTab(self.gen_tab,  '▶  生成 XML')
        self.tabs.addTab(self.log_tab,  '📋  运行日志')
        root.addWidget(self.tabs)

        # 信号连接
        self.proj_tab.project_loaded.connect(self._on_loaded)
        self.gen_tab.log_signal.connect(self.log_tab.append)
        self.tabs.currentChanged.connect(self._on_tab)

    def _on_loaded(self, cfg, path):
        self._config = cfg
        self._path = path
        self.lbl_proj.setText(
            f'工程：{cfg.project_name}' + (f'  [{Path(path).name}]' if path else '  [未保存]'))
        self.conf_tab.load_config(cfg)
        self.gen_tab.load_config(cfg)
        self.proj_tab.sync(cfg, path)
        self.log_tab.append(f'✓ 工程已加载：{cfg.project_name}')
        self.tabs.setCurrentIndex(1)

    def _on_tab(self, idx):
        if idx in (2, 3) and self._config:
            self.conf_tab.sync_to_config()
            self.gen_tab.load_config(self._config)

    def _quick_save(self):
        if not self._config: return
        self.conf_tab.sync_to_config()
        if self._path:
            self._config.save(self._path)
            self.log_tab.append('✓ 工程已保存')
        else:
            self.proj_tab.request_save()

    def closeEvent(self, event):
        if self._config:
            r = QMessageBox.question(
                self, '退出',
                '退出前是否保存工程？',
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel)
            if r == QMessageBox.StandardButton.Save:
                self._quick_save()
            elif r == QMessageBox.StandardButton.Cancel:
                event.ignore(); return
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName('PR口播工具')
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
