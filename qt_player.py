#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
XPlayer - Qt播放器组件
提供基于PyQt5的QMediaPlayer的播放器功能，替代VLC播放器
"""

from PyQt5.QtCore import QObject, pyqtSignal, QTimer, QUrl
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent, QMediaPlaylist

class QtPlayer(QObject):
    """
    Qt播放器类，使用PyQt5的QMediaPlayer实现媒体播放功能
    提供与VLCPlayer相同的接口，以便无缝替换
    """
    
    # 定义信号
    stateChanged = pyqtSignal(int)
    positionChanged = pyqtSignal(int)
    durationChanged = pyqtSignal(int)
    
    # 播放状态常量
    StoppedState = QMediaPlayer.StoppedState
    PlayingState = QMediaPlayer.PlayingState
    PausedState = QMediaPlayer.PausedState
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 创建媒体播放器
        self.media_player = QMediaPlayer(parent)
        
        # 当前媒体
        self.media = None
        
        # 播放列表
        self.playlist = None
        
        # 当前音量
        self._volume = 50
        self.media_player.setVolume(self._volume)
        
        # 播放速率
        self._rate = 1.0
        
        # 连接信号
        self.media_player.stateChanged.connect(self._on_state_changed)
        self.media_player.positionChanged.connect(self._on_position_changed)
        self.media_player.durationChanged.connect(self._on_duration_changed)
    
    def _on_state_changed(self, state):
        """
        处理状态变化信号
        :param state: QMediaPlayer.State
        """
        # 将QMediaPlayer.State转换为int发送信号
        self.stateChanged.emit(state)
    
    def _on_position_changed(self, position):
        """
        处理位置变化信号
        :param position: qint64
        """
        # 将qint64转换为int发送信号
        self.positionChanged.emit(position)
    
    def _on_duration_changed(self, duration):
        """
        处理时长变化信号
        :param duration: qint64
        """
        # 将qint64转换为int发送信号
        self.durationChanged.emit(duration)
    
    def setVideoOutput(self, video_widget):
        """
        设置视频输出窗口
        :param video_widget: QVideoWidget实例
        """
        self.media_player.setVideoOutput(video_widget)
    
    def setPlaylist(self, playlist):
        """
        设置播放列表
        :param playlist: QtPlaylist实例
        """
        self.playlist = playlist
        self.media_player.setPlaylist(playlist.media_playlist)
    
    def setMedia(self, content):
        """
        设置媒体内容
        :param content: QMediaContent实例或文件路径
        """
        if isinstance(content, str):
            # 如果是文件路径，创建QMediaContent
            url = QUrl.fromLocalFile(content)
            media_content = QMediaContent(url)
            self.media_player.setMedia(media_content)
        else:
            # 否则假设是QMediaContent
            self.media_player.setMedia(content)
    
    def play(self):
        """
        开始播放
        """
        self.media_player.play()
    
    def pause(self):
        """
        暂停播放
        """
        self.media_player.pause()
    
    def stop(self):
        """
        停止播放
        """
        self.media_player.stop()
    
    def state(self):
        """
        获取当前状态
        :return: 播放状态常量
        """
        return self.media_player.state()
    
    def position(self):
        """
        获取当前播放位置（毫秒）
        :return: 当前位置
        """
        return self.media_player.position()
    
    def duration(self):
        """
        获取媒体总时长（毫秒）
        :return: 总时长
        """
        return self.media_player.duration()
    
    def setPosition(self, position):
        """
        设置播放位置
        :param position: 位置（毫秒）
        """
        self.media_player.setPosition(position)
    
    def volume(self):
        """
        获取当前音量
        :return: 音量（0-100）
        """
        return self.media_player.volume()
    
    def setVolume(self, volume):
        """
        设置音量
        :param volume: 音量（0-100）
        """
        self.media_player.setVolume(volume)
        self._volume = volume
    
    def playbackRate(self):
        """
        获取播放速率
        :return: 播放速率
        """
        return self.media_player.playbackRate()
    
    def setPlaybackRate(self, rate):
        """
        设置播放速率
        :param rate: 播放速率
        """
        self.media_player.setPlaybackRate(rate)
        self._rate = rate


class QtPlaylist(QObject):
    """
    Qt播放列表类，使用PyQt5的QMediaPlaylist实现播放列表功能
    提供与VLCPlaylist相同的接口，以便无缝替换
    """
    
    # 播放模式常量
    Sequential = QMediaPlaylist.Sequential
    Random = QMediaPlaylist.Random
    CurrentItemOnce = QMediaPlaylist.CurrentItemOnce
    CurrentItemInLoop = QMediaPlaylist.CurrentItemInLoop
    Loop = QMediaPlaylist.Loop
    
    # 定义信号
    currentIndexChanged = pyqtSignal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 创建媒体播放列表
        self.media_playlist = QMediaPlaylist(parent)
        
        # 连接信号
        self.media_playlist.currentIndexChanged.connect(self.currentIndexChanged)
    
    def addMedia(self, content):
        """
        添加媒体到播放列表
        :param content: QMediaContent实例或文件路径
        :return: 是否成功
        """
        if isinstance(content, str):
            # 如果是文件路径，创建QMediaContent
            url = QUrl.fromLocalFile(content)
            media_content = QMediaContent(url)
            return self.media_playlist.addMedia(media_content)
        else:
            # 否则假设是QMediaContent
            return self.media_playlist.addMedia(content)
    
    def removeMedia(self, position):
        """
        从播放列表移除媒体
        :param position: 位置
        :return: 是否成功
        """
        return self.media_playlist.removeMedia(position)
    
    def clear(self):
        """
        清空播放列表
        :return: 是否成功
        """
        return self.media_playlist.clear()
    
    def mediaCount(self):
        """
        获取播放列表中媒体数量
        :return: 媒体数量
        """
        return self.media_playlist.mediaCount()
    
    def currentIndex(self):
        """
        获取当前播放的媒体索引
        :return: 当前索引
        """
        return self.media_playlist.currentIndex()
    
    def setCurrentIndex(self, position):
        """
        设置当前播放的媒体索引
        :param position: 索引位置
        :return: 是否成功
        """
        return self.media_playlist.setCurrentIndex(position)
    
    def next(self):
        """
        播放下一个媒体
        :return: 是否成功
        """
        return self.media_playlist.next()
    
    def previous(self):
        """
        播放上一个媒体
        :return: 是否成功
        """
        return self.media_playlist.previous()
    
    def playbackMode(self):
        """
        获取播放模式
        :return: 播放模式常量
        """
        return self.media_playlist.playbackMode()
    
    def setPlaybackMode(self, mode):
        """
        设置播放模式
        :param mode: 播放模式常量
        """
        self.media_playlist.setPlaybackMode(mode)
    
    def mediaUrl(self, position):
        """
        获取指定位置的媒体URL
        :param position: 位置
        :return: QUrl
        """
        return self.media_playlist.media(position).canonicalUrl()