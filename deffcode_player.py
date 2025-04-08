#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
XPlayer - Deffcode播放器组件
提供基于deffcode的播放器功能，替代VLC播放器
"""

import os
import cv2
import numpy as np
from deffcode import FFdecoder
from PyQt5.QtCore import QObject, pyqtSignal, QTimer, QUrl, Qt
from PyQt5.QtWidgets import QFrame
from PyQt5.QtGui import QImage, QPixmap

class DeffcodePlayer(QObject):
    """
    Deffcode播放器类，提供与VLCPlayer类似的接口
    使用deffcode库实现更强大的媒体播放功能
    """
    
    # 定义信号，模拟QMediaPlayer的信号
    stateChanged = pyqtSignal(int)
    positionChanged = pyqtSignal(int)
    durationChanged = pyqtSignal(int)
    frameChanged = pyqtSignal(QImage)
    
    # 播放状态常量，与QMediaPlayer保持一致
    StoppedState = 0
    PlayingState = 1
    PausedState = 2
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 解码器
        self.decoder = None
        
        # 当前媒体
        self.media_path = None
        
        # 播放列表
        self.playlist = None
        
        # 当前状态
        self._state = self.StoppedState
        
        # 当前音量 (deffcode不直接支持音量控制，但保留接口兼容性)
        self._volume = 50
        
        # 播放速率
        self._rate = 1.0
        
        # 视频输出控件
        self.video_widget = None
        
        # 视频属性
        self.duration = 0
        self.current_position = 0
        self.frame_rate = 0
        
        # 创建定时器，用于更新播放位置和帧
        self.timer = QTimer(self)
        self.timer.setInterval(33)  # 约30fps
        self.timer.timeout.connect(self._update_frame)
    
    def setVideoOutput(self, video_widget):
        """
        设置视频输出窗口
        :param video_widget: QFrame实例
        """
        self.video_widget = video_widget
    
    def setPlaylist(self, playlist):
        """
        设置播放列表
        :param playlist: DeffcodePlaylist实例
        """
        self.playlist = playlist
    
    def setMedia(self, content):
        """
        设置媒体内容
        :param content: 文件路径
        """
        if hasattr(content, 'canonicalUrl'):
            # 如果是QMediaContent，获取URL
            url = content.canonicalUrl().toString()
            if url.startswith('file:///'):
                url = url[8:]  # 移除file:///前缀
            self.media_path = url
        else:
            # 否则假设是文件路径
            self.media_path = content
        
        # 重置状态
        self._state = self.StoppedState
        self.stateChanged.emit(self._state)
    
    def _init_decoder(self):
        """
        初始化解码器
        """
        if self.decoder:
            try:
                # 尝试关闭解码器，使用terminate方法
                if hasattr(self.decoder, 'terminate'):
                    self.decoder.terminate()
            except Exception:
                pass
            self.decoder = None
            
        if not self.media_path or not os.path.exists(self.media_path):
            return False
            
        try:
            # 初始化解码器
            self.decoder = FFdecoder(self.media_path, frame_format="bgr24").formulate()
            
            # 创建帧生成器
            self.frame_generator = self.decoder.generateFrame()
            
            # 获取视频信息
            metadata = self.decoder.metadata
            # 安全获取帧率
            try:
                self.frame_rate = float(metadata["source_video_framerate"])
            except (KeyError, ValueError, TypeError):
                self.frame_rate = 30.0  # 默认帧率
            
            # 计算视频时长（毫秒）
            try:
                if "duration" in metadata:
                    self.duration = int(float(metadata["duration"]) * 1000)
                else:
                    # 如果无法获取时长，设置一个默认值
                    self.duration = 0
            except (ValueError, TypeError):
                self.duration = 0
                
            self.durationChanged.emit(self.duration)
            return True
        except Exception as e:
            print(f"初始化解码器错误: {e}")
            return False
    
    def _update_frame(self):
        """
        更新视频帧
        """
        if not self.decoder or not hasattr(self, 'frame_generator') or self._state != self.PlayingState:
            return
            
        try:
            # 从生成器获取下一帧
            frame = next(self.frame_generator, None)
            
            if frame is None:
                # 视频结束
                self.stop()
                if self.playlist:
                    self.playlist.next()
                return
                
            # 更新位置
            if self.frame_rate > 0:
                self.current_position += int(1000 / (self.frame_rate * self._rate))
                self.positionChanged.emit(self.current_position)
            
            # 转换帧为QImage并发送信号
            height, width = frame.shape[:2]
            bytes_per_line = 3 * width
            q_image = QImage(frame.data, width, height, bytes_per_line, QImage.Format_RGB888).rgbSwapped()
            self.frameChanged.emit(q_image)
            
        except Exception as e:
            print(f"更新帧错误: {e}")
            self.stop()
    
    def play(self):
        """
        开始播放
        """
        if self._state == self.PlayingState:
            return
            
        if self._state == self.StoppedState:
            # 如果是停止状态，初始化解码器
            if not self._init_decoder():
                return
            self.current_position = 0
            
        # 设置状态为播放
        self._state = self.PlayingState
        self.stateChanged.emit(self._state)
        
        # 启动定时器
        self.timer.start()
    
    def pause(self):
        """
        暂停播放
        """
        if self._state != self.PlayingState:
            return
            
        # 设置状态为暂停
        self._state = self.PausedState
        self.stateChanged.emit(self._state)
        
        # 停止定时器
        self.timer.stop()
    
    def stop(self):
        """
        停止播放
        """
        # 停止定时器
        self.timer.stop()
        
        # 关闭解码器
        if self.decoder:
            try:
                # 使用terminate方法安全地终止所有进程
                self.decoder.terminate()
            except Exception as e:
                print(f"关闭解码器错误: {e}")
            self.decoder = None
        
        # 重置位置
        self.current_position = 0
        self.positionChanged.emit(0)
        
        # 设置状态为停止
        self._state = self.StoppedState
        self.stateChanged.emit(self._state)
    
    def setPosition(self, position):
        """
        设置播放位置
        :param position: 位置（毫秒）
        """
        if not self.decoder or position < 0 or position > self.duration:
            return
            
        # 重新初始化解码器并设置位置
        was_playing = (self._state == self.PlayingState)
        self.stop()
        
        try:
            # 重新初始化解码器
            if self._init_decoder():
                # 设置位置（deffcode不直接支持精确定位，这里是一个简化实现）
                self.current_position = position
                self.positionChanged.emit(position)
                
                # 如果之前是播放状态，继续播放
                if was_playing:
                    self.play()
        except Exception as e:
            print(f"设置位置错误: {e}")
    
    def position(self):
        """
        获取当前播放位置
        :return: 位置（毫秒）
        """
        return self.current_position
    
    def get_duration(self):
        """
        获取媒体时长
        :return: 时长（毫秒）
        """
        return self.duration
    
    def setVolume(self, volume):
        """
        设置音量
        :param volume: 音量（0-100）
        """
        # deffcode不直接支持音量控制，但保留接口兼容性
        self._volume = max(0, min(100, volume))
    
    def volume(self):
        """
        获取当前音量
        :return: 音量（0-100）
        """
        return self._volume
    
    def setPlaybackRate(self, rate):
        """
        设置播放速率
        :param rate: 播放速率
        """
        self._rate = rate
    
    def playbackRate(self):
        """
        获取当前播放速率
        :return: 播放速率
        """
        return self._rate
    
    def state(self):
        """
        获取当前状态
        :return: 状态
        """
        return self._state


class DeffcodePlaylist(QObject):
    """
    Deffcode播放列表类，提供与VLCPlaylist类似的接口
    """
    
    # 定义信号
    currentIndexChanged = pyqtSignal(int)
    
    # 播放模式常量
    Sequential = 0
    Random = 1
    CurrentItemOnce = 2
    CurrentItemInLoop = 3
    Loop = 4
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 播放列表项
        self.items = []
        
        # 当前索引
        self.current_index = -1
        
        # 播放模式
        self.play_mode = self.Sequential
        
        # 播放器
        self.player = None
    
    def setPlayer(self, player):
        """
        设置播放器
        :param player: DeffcodePlayer实例
        """
        self.player = player
    
    def addMedia(self, media):
        """
        添加媒体到播放列表
        :param media: 媒体路径
        """
        if hasattr(media, 'canonicalUrl'):
            # 如果是QMediaContent，获取URL
            url = media.canonicalUrl().toString()
            if url.startswith('file:///'):
                url = url[8:]  # 移除file:///前缀
            self.items.append(url)
        else:
            # 否则假设是文件路径
            self.items.append(media)
    
    def clear(self):
        """
        清空播放列表
        """
        self.items = []
        self.current_index = -1
    
    def mediaCount(self):
        """
        获取媒体数量
        :return: 媒体数量
        """
        return len(self.items)
    
    def currentIndex(self):
        """
        获取当前索引
        :return: 当前索引
        """
        return self.current_index
    
    def setCurrentIndex(self, index):
        """
        设置当前索引
        :param index: 索引
        """
        if 0 <= index < len(self.items):
            self.current_index = index
            # 发出索引改变信号
            self.currentIndexChanged.emit(index)
            if self.player:
                self.player.stop()
                self.player.setMedia(self.items[index])
                self.player.play()
    
    def next(self):
        """
        播放下一个
        """
        if not self.items:
            return
            
        if self.play_mode == self.CurrentItemOnce:
            # 单个播放模式，不切换
            return
            
        if self.play_mode == self.CurrentItemInLoop:
            # 单个循环模式，重新播放当前项
            if self.current_index >= 0 and self.player:
                self.player.stop()
                self.player.setMedia(self.items[self.current_index])
                self.player.play()
            return
            
        if self.play_mode == self.Sequential:
            # 顺序播放模式
            next_index = self.current_index + 1
            if next_index >= len(self.items):
                if self.play_mode == self.Loop:
                    # 列表循环模式，回到开始
                    next_index = 0
                else:
                    # 顺序播放模式，结束
                    return
        elif self.play_mode == self.Random:
            # 随机播放模式
            import random
            next_index = random.randint(0, len(self.items) - 1)
        else:
            # 默认顺序播放
            next_index = (self.current_index + 1) % len(self.items)
        
        self.setCurrentIndex(next_index)
    
    def previous(self):
        """
        播放上一个
        """
        if not self.items:
            return
            
        if self.play_mode == self.CurrentItemOnce or self.play_mode == self.CurrentItemInLoop:
            # 单个播放或单个循环模式，重新播放当前项
            if self.current_index >= 0 and self.player:
                self.player.stop()
                self.player.setMedia(self.items[self.current_index])
                self.player.play()
            return
            
        if self.play_mode == self.Sequential or self.play_mode == self.Loop:
            # 顺序播放或列表循环模式
            prev_index = self.current_index - 1
            if prev_index < 0:
                if self.play_mode == self.Loop:
                    # 列表循环模式，跳到结尾
                    prev_index = len(self.items) - 1
                else:
                    # 顺序播放模式，保持在开始
                    prev_index = 0
        elif self.play_mode == self.Random:
            # 随机播放模式
            import random
            prev_index = random.randint(0, len(self.items) - 1)
        else:
            # 默认顺序播放
            prev_index = (self.current_index - 1) if self.current_index > 0 else 0
        
        self.setCurrentIndex(prev_index)
    
    def setPlaybackMode(self, mode):
        """
        设置播放模式
        :param mode: 播放模式
        """
        self.play_mode = mode