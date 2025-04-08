#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
XPlayer - VLC视频显示组件
提供基于VLC的视频显示功能，替代PyQt5的QVideoWidget
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QFrame
from PyQt5.QtCore import Qt

class VLCVideoWidget(QWidget):
    """VLC视频显示组件，提供视频显示功能"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 创建布局
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建视频显示框架
        # 使用QFrame而不是QVideoWidget，因为VLC需要一个窗口句柄
        self.video_frame = QFrame()
        self.video_frame.setFrameShape(QFrame.StyledPanel)
        self.video_frame.setFrameShadow(QFrame.Raised)
        self.video_frame.setAutoFillBackground(True)
        
        # 设置黑色背景
        palette = self.video_frame.palette()
        palette.setColor(self.video_frame.backgroundRole(), Qt.black)
        self.video_frame.setPalette(palette)
        
        # 添加到布局
        self.layout.addWidget(self.video_frame)
        
        # 设置背景色
        self.setStyleSheet("background-color: black;")
    
    def get_video_widget(self):
        """获取视频控件，用于设置到播放器"""
        return self.video_frame