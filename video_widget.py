#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
XPlayer - 视频显示组件
提供视频显示功能，与主播放器集成
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtCore import Qt

class VideoDisplayWidget(QWidget):
    """视频显示组件，封装QVideoWidget并提供额外功能"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 创建布局
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建视频显示控件
        self.video_widget = QVideoWidget()
        self.video_widget.setAspectRatioMode(Qt.KeepAspectRatio)
        
        # 添加到布局
        self.layout.addWidget(self.video_widget)
        
        # 设置背景色
        self.setStyleSheet("background-color: black;")
    
    def get_video_widget(self):
        """获取视频控件，用于设置到播放器"""
        return self.video_widget