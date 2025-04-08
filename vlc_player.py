#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
XPlayer - VLC播放器组件
提供基于python-vlc的播放器功能，替代PyQt5的QMediaPlayer
"""

import os
import vlc
from PyQt5.QtCore import QObject, pyqtSignal, QTimer, QUrl
from PyQt5.QtWidgets import QFrame

class VLCPlayer(QObject):
    """
    VLC播放器类，提供与QMediaPlayer类似的接口
    使用python-vlc库实现更强大的媒体播放功能
    """
    
    # 定义信号，模拟QMediaPlayer的信号
    stateChanged = pyqtSignal(int)
    positionChanged = pyqtSignal(int)
    durationChanged = pyqtSignal(int)
    
    # 播放状态常量，与QMediaPlayer保持一致
    StoppedState = 0
    PlayingState = 1
    PausedState = 2
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 创建VLC实例
        self.instance = vlc.Instance()
        
        # 创建媒体播放器
        self.media_player = self.instance.media_player_new()
        
        # 当前媒体
        self.media = None
        
        # 播放列表
        self.playlist = None
        
        # 当前状态
        self._state = self.StoppedState
        
        # 当前音量
        self._volume = 50
        self.media_player.audio_set_volume(self._volume)
        
        # 播放速率
        self._rate = 1.0
        
        # 创建定时器，用于更新播放位置
        self.timer = QTimer(self)
        self.timer.setInterval(200)  # 200毫秒更新一次
        self.timer.timeout.connect(self._update_position)
    
    def setVideoOutput(self, video_widget):
        """
        设置视频输出窗口
        :param video_widget: QVideoWidget或QFrame实例
        """
        if isinstance(video_widget, QFrame):
            # 如果是QFrame，直接使用其窗口ID
            if os.name == "nt":  # Windows
                self.media_player.set_hwnd(int(video_widget.winId()))
            else:  # Linux/Unix
                self.media_player.set_xwindow(int(video_widget.winId()))
        else:
            # 尝试获取窗口ID
            try:
                if os.name == "nt":  # Windows
                    self.media_player.set_hwnd(int(video_widget.winId()))
                else:  # Linux/Unix
                    self.media_player.set_xwindow(int(video_widget.winId()))
            except AttributeError:
                print("错误：无法设置视频输出窗口")
    
    def setPlaylist(self, playlist):
        """
        设置播放列表
        :param playlist: VLCPlaylist实例
        """
        self.playlist = playlist
    
    def setMedia(self, content):
        """
        设置媒体内容
        :param content: QMediaContent实例或文件路径
        """
        if hasattr(content, 'canonicalUrl'):
            # 如果是QMediaContent，获取URL
            url = content.canonicalUrl().toString()
            if url.startswith('file:///'):
                url = url[8:]  # 移除file:///前缀
        else:
            # 否则假设是文件路径
            url = content
        
        # 创建媒体
        self.media = self.instance.media_new(url)
        
        # 设置到播放器
        self.media_player.set_media(self.media)
        
        # 获取媒体信息
        self.media.parse()
        
        # 发送时长变化信号
        duration = self.media_player.get_length()
        self.durationChanged.emit(duration)
    
    def play(self):
        """
        开始播放
        """
        result = self.media_player.play()
        if result == 0:  # 成功
            self._state = self.PlayingState
            self.stateChanged.emit(self._state)
            self.timer.start()  # 启动定时器
    
    def pause(self):
        """
        暂停播放
        """
        self.media_player.pause()
        self._state = self.PausedState
        self.stateChanged.emit(self._state)
    
    def stop(self):
        """
        停止播放
        """
        self.media_player.stop()
        self._state = self.StoppedState
        self.stateChanged.emit(self._state)
        self.timer.stop()  # 停止定时器
    
    def state(self):
        """
        获取当前状态
        :return: 播放状态常量
        """
        return self._state
    
    def position(self):
        """
        获取当前播放位置（毫秒）
        :return: 当前位置
        """
        return self.media_player.get_time()
    
    def duration(self):
        """
        获取媒体总时长（毫秒）
        :return: 总时长
        """
        return self.media_player.get_length()
    
    def setPosition(self, position):
        """
        设置播放位置
        :param position: 位置（毫秒）
        """
        self.media_player.set_time(position)
    
    def volume(self):
        """
        获取当前音量
        :return: 音量（0-100）
        """
        return self._volume
    
    def setVolume(self, volume):
        """
        设置音量
        :param volume: 音量（0-100）
        """
        self._volume = volume
        self.media_player.audio_set_volume(volume)
    
    def playbackRate(self):
        """
        获取播放速率
        :return: 播放速率
        """
        return self._rate
    
    def setPlaybackRate(self, rate):
        """
        设置播放速率
        :param rate: 播放速率
        """
        self._rate = rate
        self.media_player.set_rate(rate)
    
    def _update_position(self):
        """
        更新播放位置（内部使用）
        """
        if self._state == self.PlayingState:
            position = self.media_player.get_time()
            self.positionChanged.emit(position)


class VLCPlaylist(QObject):
    """
    VLC播放列表类，提供与QMediaPlaylist类似的接口
    """
    
    # 定义信号
    currentIndexChanged = pyqtSignal(int)
    
    # 播放模式常量，与QMediaPlaylist保持一致
    Sequential = 0
    Random = 1
    CurrentItemOnce = 2
    CurrentItemInLoop = 3
    Loop = 4
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 创建VLC实例
        self.instance = vlc.Instance()
        
        # 媒体列表
        self.media_list = self.instance.media_list_new()
        
        # 媒体列表播放器
        self.list_player = self.instance.media_list_player_new()
        self.list_player.set_media_list(self.media_list)
        
        # 获取内部的媒体播放器
        self.media_player = self.list_player.get_media_player()
        
        # 当前索引
        self._current_index = -1
        
        # 播放模式
        self._playback_mode = self.Sequential
        
        # 媒体项列表（保存路径）
        self.media_items = []
    
    def addMedia(self, content):
        """
        添加媒体到播放列表
        :param content: QMediaContent实例或文件路径
        :return: 是否成功
        """
        if hasattr(content, 'canonicalUrl'):
            # 如果是QMediaContent，获取URL
            url = content.canonicalUrl().toString()
            if url.startswith('file:///'):
                url = url[8:]  # 移除file:///前缀
        else:
            # 否则假设是文件路径
            url = content
        
        # 创建媒体并添加到列表
        media = self.instance.media_new(url)
        self.media_list.add_media(media)
        self.media_items.append(url)
        
        return True
    
    def clear(self):
        """
        清空播放列表
        """
        # VLC没有直接的清空方法，我们创建一个新的列表
        self.media_list = self.instance.media_list_new()
        self.list_player.set_media_list(self.media_list)
        self.media_items = []
        self._current_index = -1
    
    def currentIndex(self):
        """
        获取当前播放项的索引
        :return: 索引
        """
        return self._current_index
    
    def setCurrentIndex(self, index):
        """
        设置当前播放项
        :param index: 索引
        """
        if 0 <= index < len(self.media_items):
            self.list_player.play_item_at_index(index)
            self._current_index = index
            self.currentIndexChanged.emit(index)
    
    def next(self):
        """
        播放下一项
        """
        self.list_player.next()
        self._update_current_index()
    
    def previous(self):
        """
        播放上一项
        """
        self.list_player.previous()
        self._update_current_index()
    
    def playbackMode(self):
        """
        获取播放模式
        :return: 播放模式常量
        """
        return self._playback_mode
    
    def setPlaybackMode(self, mode):
        """
        设置播放模式
        :param mode: 播放模式常量
        """
        self._playback_mode = mode
        
        # 设置VLC播放模式
        if mode == self.Sequential:
            self.list_player.set_playback_mode(vlc.PlaybackMode.default)
        elif mode == self.Loop:
            self.list_player.set_playback_mode(vlc.PlaybackMode.loop)
        elif mode == self.Random:
            self.list_player.set_playback_mode(vlc.PlaybackMode.repeat)
        # VLC不直接支持CurrentItemOnce和CurrentItemInLoop，需要在外部处理
    
    def _update_current_index(self):
        """
        更新当前索引（内部使用）
        """
        # 获取当前媒体
        current_media = self.media_player.get_media()
        if current_media:
            # 查找媒体在列表中的索引
            for i, media_path in enumerate(self.media_items):
                media = self.instance.media_new(media_path)
                if media.get_mrl() == current_media.get_mrl():
                    self._current_index = i
                    self.currentIndexChanged.emit(i)
                    break