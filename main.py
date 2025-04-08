#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
XPlayer - 多媒体播放器
基于Python和PyQt5开发的多媒体播放器，支持常见音视频格式播放、音量调节、进度控制、
倍速播放、播放列表管理、主题切换、播放模式设置和快捷键配置。
"""

import sys
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QSlider, QLabel, 
                             QFileDialog, QListWidget, QMenu, QAction, 
                             QSystemTrayIcon, QStyle, QComboBox, QTabWidget,
                             QListWidgetItem, QLineEdit, QMessageBox, QDialog,
                             QShortcut, QGroupBox, QFormLayout, QRadioButton,
                             QButtonGroup)
from PyQt5.QtCore import (Qt, QUrl, QTimer, QTime, QSettings, QPoint, QSize,
                          QDir, QStandardPaths, QEvent)
from PyQt5.QtGui import QIcon, QKeySequence

# 导入VLC播放器组件（替代QMediaPlayer）
from vlc_player import VLCPlayer, VLCPlaylist

# 导入自定义VLC视频显示组件
from vlc_video_widget import VLCVideoWidget

class XPlayer(QMainWindow):
    """主窗口类"""
    
    def __init__(self):
        super().__init__()
        
        # 设置应用程序基本信息
        self.setWindowTitle("XPlayer")
        self.setMinimumSize(800, 600)
        
        # 初始化设置
        self.settings = QSettings("XPlayer", "Settings")
        
        # 初始化播放器和播放列表
        self.init_player()
        
        # 创建UI界面
        self.init_ui()
        
        # 加载设置
        self.load_settings()
        
        # 连接信号和槽
        self.connect_signals()
        
        # 显示窗口
        self.show()
    
    def init_player(self):
        """初始化播放器和播放列表"""
        # 创建VLC媒体播放器（替代QMediaPlayer）
        self.player = VLCPlayer()
        
        # 创建VLC播放列表（替代QMediaPlaylist）
        self.playlist = VLCPlaylist()
        self.player.setPlaylist(self.playlist)
        
        # 播放历史
        self.history = []
        
        # 播放模式
        self.play_modes = {
            "顺序播放": VLCPlaylist.Sequential,
            "随机播放": VLCPlaylist.Random,
            "单个播放": VLCPlaylist.CurrentItemOnce,
            "单个循环": VLCPlaylist.CurrentItemInLoop,
            "列表循环": VLCPlaylist.Loop
        }
    
    def init_ui(self):
        """初始化用户界面"""
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        
        # 创建标签页
        self.tabs = QTabWidget()
        
        # 播放器页面
        player_widget = QWidget()
        player_layout = QVBoxLayout(player_widget)
        
        # 播放列表页面
        playlist_widget = QWidget()
        playlist_layout = QVBoxLayout(playlist_widget)
        
        # 设置页面
        settings_widget = QWidget()
        settings_layout = QVBoxLayout(settings_widget)
        
        # 添加标签页
        self.tabs.addTab(player_widget, "播放器")
        self.tabs.addTab(playlist_widget, "播放列表")
        self.tabs.addTab(settings_widget, "设置")
        
        # 添加标签页到主布局
        main_layout.addWidget(self.tabs)
        
        # 播放器控件
        self.setup_player_controls(player_layout)
        
        # 播放列表控件
        self.setup_playlist_controls(playlist_layout)
        
        # 设置控件
        self.setup_settings_controls(settings_layout)
        
        # 状态栏
        self.statusBar().showMessage("就绪")
        
        # 创建菜单
        self.create_menus()
    
    def setup_player_controls(self, layout):
        """设置播放器控件"""
        # 视频显示区域（使用VLC视频组件）
        self.video_display = VLCVideoWidget()
        self.video_widget = self.video_display.get_video_widget()
        self.player.setVideoOutput(self.video_widget)
        layout.addWidget(self.video_display, 1)  # 1表示拉伸因子
        
        # 进度条
        progress_layout = QHBoxLayout()
        
        self.time_label = QLabel("00:00 / 00:00")
        self.progress_slider = QSlider(Qt.Horizontal)
        self.progress_slider.setRange(0, 0)
        
        progress_layout.addWidget(self.time_label)
        progress_layout.addWidget(self.progress_slider)
        
        layout.addLayout(progress_layout)
        
        # 控制按钮
        controls_layout = QHBoxLayout()
        
        self.play_button = QPushButton("播放")
        self.stop_button = QPushButton("停止")
        self.prev_button = QPushButton("上一个")
        self.next_button = QPushButton("下一个")
        
        # 音量控制
        self.volume_label = QLabel("音量:")
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)
        self.player.setVolume(50)
        
        # 倍速控制
        self.speed_label = QLabel("倍速:")
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x"])
        self.speed_combo.setCurrentIndex(2)  # 默认1.0x
        
        controls_layout.addWidget(self.play_button)
        controls_layout.addWidget(self.stop_button)
        controls_layout.addWidget(self.prev_button)
        controls_layout.addWidget(self.next_button)
        controls_layout.addWidget(self.volume_label)
        controls_layout.addWidget(self.volume_slider)
        controls_layout.addWidget(self.speed_label)
        controls_layout.addWidget(self.speed_combo)
        
        layout.addLayout(controls_layout)
        
        # 打开文件按钮
        open_layout = QHBoxLayout()
        self.open_file_button = QPushButton("打开文件")
        self.open_folder_button = QPushButton("打开文件夹")
        
        open_layout.addWidget(self.open_file_button)
        open_layout.addWidget(self.open_folder_button)
        open_layout.addStretch(1)  # 添加弹性空间
        
        layout.addLayout(open_layout)
    
    def setup_playlist_controls(self, layout):
        """设置播放列表控件"""
        # 搜索框
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索...")
        self.search_button = QPushButton("搜索")
        
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_button)
        
        layout.addLayout(search_layout)
        
        # 播放列表
        self.playlist_widget = QListWidget()
        self.playlist_widget.setAlternatingRowColors(True)
        layout.addWidget(self.playlist_widget)
        
        # 历史播放列表
        history_group = QGroupBox("历史播放")
        history_layout = QVBoxLayout()
        
        self.history_widget = QListWidget()
        self.history_widget.setAlternatingRowColors(True)
        self.clear_history_button = QPushButton("清除历史")
        
        history_layout.addWidget(self.history_widget)
        history_layout.addWidget(self.clear_history_button)
        
        history_group.setLayout(history_layout)
        layout.addWidget(history_group)
    
    def setup_settings_controls(self, layout):
        """设置控件"""
        # 主题设置
        theme_group = QGroupBox("主题设置")
        theme_layout = QVBoxLayout()
        
        self.theme_light = QRadioButton("浅色主题")
        self.theme_dark = QRadioButton("深色主题")
        self.theme_system = QRadioButton("跟随系统")
        
        self.theme_group = QButtonGroup()
        self.theme_group.addButton(self.theme_light, 0)
        self.theme_group.addButton(self.theme_dark, 1)
        self.theme_group.addButton(self.theme_system, 2)
        
        theme_layout.addWidget(self.theme_light)
        theme_layout.addWidget(self.theme_dark)
        theme_layout.addWidget(self.theme_system)
        
        theme_group.setLayout(theme_layout)
        layout.addWidget(theme_group)
        
        # 播放模式设置
        playmode_group = QGroupBox("默认播放模式")
        playmode_layout = QVBoxLayout()
        
        self.mode_sequential = QRadioButton("顺序播放")
        self.mode_random = QRadioButton("随机播放")
        self.mode_once = QRadioButton("单个播放")
        self.mode_repeat_one = QRadioButton("单个循环")
        self.mode_repeat_all = QRadioButton("列表循环")
        
        self.playmode_group = QButtonGroup()
        self.playmode_group.addButton(self.mode_sequential, 0)
        self.playmode_group.addButton(self.mode_random, 1)
        self.playmode_group.addButton(self.mode_once, 2)
        self.playmode_group.addButton(self.mode_repeat_one, 3)
        self.playmode_group.addButton(self.mode_repeat_all, 4)
        
        playmode_layout.addWidget(self.mode_sequential)
        playmode_layout.addWidget(self.mode_random)
        playmode_layout.addWidget(self.mode_once)
        playmode_layout.addWidget(self.mode_repeat_one)
        playmode_layout.addWidget(self.mode_repeat_all)
        
        playmode_group.setLayout(playmode_layout)
        layout.addWidget(playmode_group)
        
        # 快捷键设置
        shortcut_group = QGroupBox("快捷键设置")
        shortcut_layout = QFormLayout()
        
        self.shortcut_play = QLineEdit("Space")
        self.shortcut_stop = QLineEdit("Ctrl+S")
        self.shortcut_next = QLineEdit("Ctrl+Right")
        self.shortcut_prev = QLineEdit("Ctrl+Left")
        self.shortcut_vol_up = QLineEdit("Ctrl+Up")
        self.shortcut_vol_down = QLineEdit("Ctrl+Down")
        
        shortcut_layout.addRow("播放/暂停:", self.shortcut_play)
        shortcut_layout.addRow("停止:", self.shortcut_stop)
        shortcut_layout.addRow("下一个:", self.shortcut_next)
        shortcut_layout.addRow("上一个:", self.shortcut_prev)
        shortcut_layout.addRow("音量增加:", self.shortcut_vol_up)
        shortcut_layout.addRow("音量减少:", self.shortcut_vol_down)
        
        shortcut_group.setLayout(shortcut_layout)
        layout.addWidget(shortcut_group)
        
        # 保存设置按钮
        self.save_settings_button = QPushButton("保存设置")
        layout.addWidget(self.save_settings_button)
    
    def create_menus(self):
        """创建菜单"""
        # 文件菜单
        file_menu = self.menuBar().addMenu("文件")
        
        open_file_action = QAction("打开文件", self)
        open_file_action.triggered.connect(self.open_file)
        file_menu.addAction(open_file_action)
        
        open_folder_action = QAction("打开文件夹", self)
        open_folder_action.triggered.connect(self.open_folder)
        file_menu.addAction(open_folder_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 播放菜单
        play_menu = self.menuBar().addMenu("播放")
        
        play_action = QAction("播放/暂停", self)
        play_action.triggered.connect(self.toggle_play)
        play_menu.addAction(play_action)
        
        stop_action = QAction("停止", self)
        stop_action.triggered.connect(self.stop)
        play_menu.addAction(stop_action)
        
        play_menu.addSeparator()
        
        prev_action = QAction("上一个", self)
        prev_action.triggered.connect(self.prev_media)
        play_menu.addAction(prev_action)
        
        next_action = QAction("下一个", self)
        next_action.triggered.connect(self.next_media)
        play_menu.addAction(next_action)
        
        # 帮助菜单
        help_menu = self.menuBar().addMenu("帮助")
        
        about_action = QAction("关于", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def connect_signals(self):
        """连接信号和槽"""
        # 播放器控制
        self.play_button.clicked.connect(self.toggle_play)
        self.stop_button.clicked.connect(self.stop)
        self.prev_button.clicked.connect(self.prev_media)
        self.next_button.clicked.connect(self.next_media)
        
        # 音量控制
        self.volume_slider.valueChanged.connect(self.player.setVolume)
        
        # 进度控制
        self.progress_slider.sliderMoved.connect(self.set_position)
        self.player.durationChanged.connect(self.update_duration)
        self.player.positionChanged.connect(self.update_position)
        
        # 播放状态
        self.player.stateChanged.connect(self.update_player_state)
        
        # 倍速控制
        self.speed_combo.currentIndexChanged.connect(self.change_playback_rate)
        
        # 文件打开
        self.open_file_button.clicked.connect(self.open_file)
        self.open_folder_button.clicked.connect(self.open_folder)
        
        # 播放列表
        self.playlist_widget.doubleClicked.connect(self.playlist_double_clicked)
        self.history_widget.doubleClicked.connect(self.history_double_clicked)
        self.clear_history_button.clicked.connect(self.clear_history)
        
        # 搜索
        self.search_button.clicked.connect(self.search_media)
        self.search_input.returnPressed.connect(self.search_media)
        
        # 设置
        self.save_settings_button.clicked.connect(self.save_settings)
        
        # 播放列表信号
        self.playlist.currentIndexChanged.connect(self.playlist_position_changed)
    
    def load_settings(self):
        """加载设置"""
        # 主题设置
        theme = self.settings.value("theme", 0, int)
        if theme == 0:
            self.theme_light.setChecked(True)
            self.apply_light_theme()
        elif theme == 1:
            self.theme_dark.setChecked(True)
            self.apply_dark_theme()
        else:
            self.theme_system.setChecked(True)
            self.apply_system_theme()
        
        # 播放模式设置
        play_mode = self.settings.value("play_mode", 0, int)
        if play_mode == 0:
            self.mode_sequential.setChecked(True)
            self.playlist.setPlaybackMode(QMediaPlaylist.Sequential)
        elif play_mode == 1:
            self.mode_random.setChecked(True)
            self.playlist.setPlaybackMode(QMediaPlaylist.Random)
        elif play_mode == 2:
            self.mode_once.setChecked(True)
            self.playlist.setPlaybackMode(QMediaPlaylist.CurrentItemOnce)
        elif play_mode == 3:
            self.mode_repeat_one.setChecked(True)
            self.playlist.setPlaybackMode(QMediaPlaylist.CurrentItemInLoop)
        else:
            self.mode_repeat_all.setChecked(True)
            self.playlist.setPlaybackMode(QMediaPlaylist.Loop)
        
        # 快捷键设置
        self.shortcut_play.setText(self.settings.value("shortcut_play", "Space"))
        self.shortcut_stop.setText(self.settings.value("shortcut_stop", "Ctrl+S"))
        self.shortcut_next.setText(self.settings.value("shortcut_next", "Ctrl+Right"))
        self.shortcut_prev.setText(self.settings.value("shortcut_prev", "Ctrl+Left"))
        self.shortcut_vol_up.setText(self.settings.value("shortcut_vol_up", "Ctrl+Up"))
        self.shortcut_vol_down.setText(self.settings.value("shortcut_vol_down", "Ctrl+Down"))
        
        # 应用快捷键
        self.apply_shortcuts()
        
        # 加载历史记录
        history_list = self.settings.value("history", [])
        if history_list:
            self.history = history_list
            self.update_history_widget()
    
    def save_settings(self):
        """保存设置"""
        # 主题设置
        self.settings.setValue("theme", self.theme_group.checkedId())
        
        # 播放模式设置
        self.settings.setValue("play_mode", self.playmode_group.checkedId())
        
        # 快捷键设置
        self.settings.setValue("shortcut_play", self.shortcut_play.text())
        self.settings.setValue("shortcut_stop", self.shortcut_stop.text())
        self.settings.setValue("shortcut_next", self.shortcut_next.text())
        self.settings.setValue("shortcut_prev", self.shortcut_prev.text())
        self.settings.setValue("shortcut_vol_up", self.shortcut_vol_up.text())
        self.settings.setValue("shortcut_vol_down", self.shortcut_vol_down.text())
        
        # 应用设置
        self.apply_theme()
        self.apply_play_mode()
        self.apply_shortcuts()
        
        # 保存历史记录
        self.settings.setValue("history", self.history)
        
        QMessageBox.information(self, "设置", "设置已保存")
    
    def apply_theme(self):
        """应用主题"""
        theme_id = self.theme_group.checkedId()
        if theme_id == 0:
            self.apply_light_theme()
        elif theme_id == 1:
            self.apply_dark_theme()
        else:
            self.apply_system_theme()
    
    def apply_light_theme(self):
        """应用浅色主题"""
        self.setStyleSheet("""
            QWidget {
                background-color: #f0f0f0;
                color: #333333;
            }
            QMenuBar, QMenu {
                background-color: #e0e0e0;
            }
            QPushButton {
                background-color: #e0e0e0;
                border: 1px solid #c0c0c0;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #d0d0d0;
            }
            QSlider::groove:horizontal {
                background: #c0c0c0;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #808080;
                width: 16px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 8px;
            }
            QTabWidget::pane {
                border: 1px solid #c0c0c0;
            }
            QTabBar::tab {
                background: #e0e0e0;
                border: 1px solid #c0c0c0;
                padding: 6px;
            }
            QTabBar::tab:selected {
                background: #f0f0f0;
            }
        """)
    
    def apply_dark_theme(self):
        """应用深色主题"""
        self.setStyleSheet("""
            QWidget {
                background-color: #2d2d2d;
                color: #e0e0e0;
            }
            QMenuBar, QMenu {
                background-color: #3d3d3d;
            }
            QPushButton {
                background-color: #3d3d3d;
                border: 1px solid #5d5d5d;
                padding: 5px;
                border-radius: 3px;
                color: #e0e0e0;
            }
            QPushButton:hover {
                background-color: #4d4d4d;
            }
            QSlider::groove:horizontal {
                background: #5d5d5d;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #e0e0e0;
                width: 16px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 8px;
            }
            QTabWidget::pane {
                border: 1px solid #5d5d5d;
            }
            QTabBar::tab {
                background: #3d3d3d;
                border: 1px solid #5d5d5d;
                padding: 6px;
            }
            QTabBar::tab:selected {
                background: #2d2d2d;
            }
            QLineEdit, QComboBox {
                background-color: #3d3d3d;
                border: 1px solid #5d5d5d;
                color: #e0e0e0;
            }
        """)
    
    def apply_system_theme(self):
        """应用系统主题"""
        # 这里简化处理，实际上需要检测系统主题
        # 在UOS系统中，可能需要使用特定的API来检测系统主题
        # 这里暂时使用浅色主题作为默认
        self.apply_light_theme()
    
    def apply_play_mode(self):
        """应用播放模式"""
        mode_id = self.playmode_group.checkedId()
        if mode_id == 0:
            self.playlist.setPlaybackMode(QMediaPlaylist.Sequential)
        elif mode_id == 1:
            self.playlist.setPlaybackMode(QMediaPlaylist.Random)
        elif mode_id == 2:
            self.playlist.setPlaybackMode(QMediaPlaylist.CurrentItemOnce)
        elif mode_id == 3:
            self.playlist.setPlaybackMode(QMediaPlaylist.CurrentItemInLoop)
        else:
            self.playlist.setPlaybackMode(QMediaPlaylist.Loop)
    
    def apply_shortcuts(self):
        """应用快捷键"""
        # 清除旧的快捷键
        try:
            self.shortcut_play_key.activated.disconnect()
            self.shortcut_stop_key.activated.disconnect()
            self.shortcut_next_key.activated.disconnect()
            self.shortcut_prev_key.activated.disconnect()
            self.shortcut_vol_up_key.activated.disconnect()
            self.shortcut_vol_down_key.activated.disconnect()
        except:
            pass
        
        # 创建新的快捷键
        self.shortcut_play_key = QShortcut(QKeySequence(self.shortcut_play.text()), self)
        self.shortcut_stop_key = QShortcut(QKeySequence(self.shortcut_stop.text()), self)
        self.shortcut_next_key = QShortcut(QKeySequence(self.shortcut_next.text()), self)
        self.shortcut_prev_key = QShortcut(QKeySequence(self.shortcut_prev.text()), self)
        self.shortcut_vol_up_key = QShortcut(QKeySequence(self.shortcut_vol_up.text()), self)
        self.shortcut_vol_down_key = QShortcut(QKeySequence(self.shortcut_vol_down.text()), self)
        
        # 连接信号
        self.shortcut_play_key.activated.connect(self.toggle_play)
        self.shortcut_stop_key.activated.connect(self.stop)
        self.shortcut_next_key.activated.connect(self.next_media)
        self.shortcut_prev_key.activated.connect(self.prev_media)
        self.shortcut_vol_up_key.activated.connect(self.volume_up)
        self.shortcut_vol_down_key.activated.connect(self.volume_down)
    
    def open_file(self):
        """打开文件"""
        file_dialog = QFileDialog()
        file_dialog.setFileMode(QFileDialog.ExistingFiles)
        file_dialog.setNameFilter("媒体文件 (*.mp3 *.wav *.mp4 *.avi *.mkv)")
        
        if file_dialog.exec_():
            file_paths = file_dialog.selectedFiles()
            self.add_to_playlist(file_paths)
    
    def open_folder(self):
        """打开文件夹"""
        folder_dialog = QFileDialog()
        folder_dialog.setFileMode(QFileDialog.Directory)
        folder_dialog.setOption(QFileDialog.ShowDirsOnly, True)
        
        if folder_dialog.exec_():
            folder_path = folder_dialog.selectedFiles()[0]
            self.add_folder_to_playlist(folder_path)
    
    def add_folder_to_playlist(self, folder_path):
        """将文件夹中的媒体文件添加到播放列表"""
        media_extensions = [".mp3", ".wav", ".mp4", ".avi", ".mkv"]
        
        dir = QDir(folder_path)
        dir.setNameFilters(["*" + ext for ext in media_extensions])
        dir.setFilter(QDir.Files | QDir.NoDotAndDotDot)
        
        file_list = dir.entryList()
        file_paths = [os.path.join(folder_path, file) for file in file_list]
        
        if file_paths:
            self.add_to_playlist(file_paths)
        else:
            QMessageBox.information(self, "提示", "所选文件夹中没有支持的媒体文件")
    
    def add_to_playlist(self, file_paths):
        """将文件添加到播放列表"""
        for path in file_paths:
            # 直接使用文件路径，VLCPlaylist会处理URL转换
            self.playlist.addMedia(path)
            file_name = os.path.basename(path)
            self.playlist_widget.addItem(file_name)
        
        # 如果当前没有播放，则开始播放第一个文件
        if self.player.state() != VLCPlayer.PlayingState:
            self.playlist.setCurrentIndex(0)
            self.player.play()
            
        # 更新状态栏
        self.statusBar().showMessage(f"已添加 {len(file_paths)} 个文件到播放列表")
    
    def toggle_play(self):
        """切换播放/暂停状态"""
        if self.player.state() == VLCPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()
    
    def stop(self):
        """停止播放"""
        self.player.stop()
    
    def prev_media(self):
        """播放上一个媒体"""
        self.playlist.previous()
    
    def next_media(self):
        """播放下一个媒体"""
        self.playlist.next()
    
    def volume_up(self):
        """增加音量"""
        current_volume = self.player.volume()
        new_volume = min(current_volume + 10, 100)
        self.player.setVolume(new_volume)
        self.volume_slider.setValue(new_volume)
    
    def volume_down(self):
        """减小音量"""
        current_volume = self.player.volume()
        new_volume = max(current_volume - 10, 0)
        self.player.setVolume(new_volume)
        self.volume_slider.setValue(new_volume)
    
    def set_position(self, position):
        """设置播放位置"""
        self.player.setPosition(position)
    
    def update_duration(self, duration):
        """更新总时长"""
        self.progress_slider.setRange(0, duration)
        self.update_time_label()
    
    def update_position(self, position):
        """更新当前位置"""
        if not self.progress_slider.isSliderDown():
            self.progress_slider.setValue(position)
        self.update_time_label()
    
    def update_time_label(self):
        """更新时间标签"""
        position = self.player.position()
        duration = self.player.duration()
        
        position_time = QTime(0, 0)
        position_time = position_time.addMSecs(position)
        
        duration_time = QTime(0, 0)
        duration_time = duration_time.addMSecs(duration)
        
        time_format = "mm:ss"
        if duration >= 3600000:  # 如果时长超过1小时
            time_format = "hh:mm:ss"
        
        position_str = position_time.toString(time_format)
        duration_str = duration_time.toString(time_format)
        
        self.time_label.setText(f"{position_str} / {duration_str}")
    
    def update_player_state(self, state):
        """更新播放器状态"""
        if state == VLCPlayer.PlayingState:
            self.play_button.setText("暂停")
            # 添加到历史记录
            current_index = self.playlist.currentIndex()
            if current_index >= 0 and current_index < self.playlist_widget.count():
                current_item = self.playlist_widget.item(current_index).text()
                if current_item not in self.history:
                    self.history.append(current_item)
                    self.update_history_widget()
        else:
            self.play_button.setText("播放")
    
    def change_playback_rate(self, index):
        """更改播放速度"""
        rates = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
        if 0 <= index < len(rates):
            self.player.setPlaybackRate(rates[index])
    
    def playlist_double_clicked(self, index):
        """双击播放列表项"""
        self.playlist.setCurrentIndex(index.row())
        self.player.play()
    
    def history_double_clicked(self, index):
        """双击历史记录项"""
        history_item = self.history_widget.item(index.row()).text()
        
        # 查找播放列表中对应的项
        for i in range(self.playlist_widget.count()):
            if self.playlist_widget.item(i).text() == history_item:
                self.playlist.setCurrentIndex(i)
                self.player.play()
                break
    
    def clear_history(self):
        """清除历史记录"""
        self.history = []
        self.history_widget.clear()
    
    def update_history_widget(self):
        """更新历史记录列表"""
        self.history_widget.clear()
        for item in self.history:
            self.history_widget.addItem(item)
    
    def search_media(self):
        """搜索媒体文件"""
        search_text = self.search_input.text().lower()
        if not search_text:
            # 如果搜索框为空，显示所有项
            for i in range(self.playlist_widget.count()):
                self.playlist_widget.item(i).setHidden(False)
            return
        
        # 搜索并隐藏不匹配的项
        for i in range(self.playlist_widget.count()):
            item = self.playlist_widget.item(i)
            if search_text not in item.text().lower():
                item.setHidden(True)
            else:
                item.setHidden(False)
    
    def playlist_position_changed(self, position):
        """播放列表位置改变"""
        if position >= 0:
            self.playlist_widget.setCurrentRow(position)
    
    def show_about(self):
        """显示关于对话框"""
        QMessageBox.about(self, "关于 XPlayer", 
                          "XPlayer 是一个基于 Python 和 PyQt5 开发的多媒体播放器，\n"
                          "支持常见音视频格式播放、音量调节、进度控制、倍速播放、\n"
                          "播放列表管理、主题切换、播放模式设置和快捷键配置。")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    player = XPlayer()
    sys.exit(app.exec_())