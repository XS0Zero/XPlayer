#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
XPlayer - Deffcode视频显示组件
提供基于Deffcode的视频显示功能，替代VLC视频显示组件
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap

class DeffcodeVideoWidget(QWidget):
    """Deffcode视频显示组件，提供视频显示功能"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 创建布局
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建标签用于显示视频帧
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("background-color: black;")
        
        # 添加到布局
        self.layout.addWidget(self.video_label)
        
        # 设置背景色
        self.setStyleSheet("background-color: black;")
    
    def get_video_widget(self):
        """获取视频控件，用于设置到播放器"""
        return self.video_label
    
    def update_frame(self, qimage):
        """更新视频帧
        :param qimage: QImage对象，表示视频帧
        """
        if qimage:
            # 转换QImage为QPixmap并显示
            pixmap = QPixmap.fromImage(qimage)
            
            # 根据控件大小缩放图像，保持宽高比
            scaled_pixmap = pixmap.scaled(self.video_label.size(), 
                                         Qt.KeepAspectRatio, 
                                         Qt.SmoothTransformation)
            
            self.video_label.setPixmap(scaled_pixmap)
    
    def resizeEvent(self, event):
        """重写大小调整事件，确保视频帧正确缩放"""
        super().resizeEvent(event)
        
        # 如果标签中有图像，重新缩放它
        if not self.video_label.pixmap() is None:
            current_pixmap = self.video_label.pixmap()
            scaled_pixmap = current_pixmap.scaled(self.video_label.size(), 
                                                Qt.KeepAspectRatio, 
                                                Qt.SmoothTransformation)
            self.video_label.setPixmap(scaled_pixmap)