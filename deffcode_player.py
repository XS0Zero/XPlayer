#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
XPlayer - Deffcode播放器组件
提供基于deffcode的播放器功能，替代VLC播放器
"""

import os
import cv2
import numpy as np
import pyaudio
import wave
import threading
import subprocess
import tempfile
import time
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
        
        # 当前音量 (0-100)
        self._volume = 50
        
        # 播放速率
        self._rate = 1.0
        
        # 视频输出控件
        self.video_widget = None
        
        # 视频属性
        self.duration = 0
        self.current_position = 0
        self.frame_rate = 0
        
        # 帧缓冲区，用于提高跳转性能
        self.frame_buffer_size = 5  # 缓冲5帧
        self.frame_buffer = []
        
        # 音频相关
        self.audio_stream = None
        self.audio_thread = None
        self.audio_playing = False
        self.audio_paused = False
        self.audio_file = None
        self.pyaudio_instance = pyaudio.PyAudio()
        
        # 创建定时器，用于更新播放位置和帧
        self.timer = QTimer(self)
        self.timer.setInterval(33)  # 约30fps
        self.timer.timeout.connect(self._update_frame)
        
        # 创建定时器，用于更新播放位置
        self.position_timer = QTimer(self)
        self.position_timer.setInterval(100)  # 100ms更新一次位置
        self.position_timer.timeout.connect(self._update_position)
        
        # 标记是否已经发送过时长信号
        self._duration_sent = False
        
        # 音视频同步相关
        self._last_sync_time = 0  # 上次同步时间
        self._last_seek_position = 0  # 上次跳转位置
    
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
            
        # 停止音频播放
        self._stop_audio()
            
        if not self.media_path or not os.path.exists(self.media_path):
            return False
            
        try:
            # 初始化解码器
            # 检查是否需要从特定位置开始播放
            if hasattr(self, 'seek_position') and self.seek_position > 0:
                seek_seconds = self.seek_position / 1000.0
                print(f"使用seek初始化解码器，跳转到: {seek_seconds}秒")
                self.decoder = FFdecoder(
                    self.media_path, 
                    frame_format="bgr24",
                    **{'-ss': str(seek_seconds)}  # 使用FFmpeg的seek参数
                ).formulate()
                # 重置seek位置
                self.current_position = self.seek_position
                self.seek_position = 0
            else:
                self.decoder = FFdecoder(self.media_path, frame_format="bgr24").formulate()
            
            # 创建帧生成器
            self.frame_generator = self.decoder.generateFrame()
            
            # 清空并填充帧缓冲区
            self.frame_buffer = []
            # 预读取几帧到缓冲区
            for _ in range(self.frame_buffer_size):
                try:
                    frame = next(self.frame_generator, None)
                    if frame is None:
                        break
                    self.frame_buffer.append(frame)
                except Exception as e:
                    print(f"初始填充帧缓冲区错误: {e}")
                    break
            
            print(f"初始化解码器完成，已预加载{len(self.frame_buffer)}帧")
            
            # 获取视频信息
            metadata = self.decoder.metadata
            print(f"视频元数据: {metadata}")
            
            # 安全获取帧率
            try:
                if isinstance(metadata, dict) and "source_video_framerate" in metadata:
                    self.frame_rate = float(metadata["source_video_framerate"])
                    print(f"获取到帧率: {self.frame_rate}")
                else:
                    self.frame_rate = 30.0  # 默认帧率
                    print(f"使用默认帧率: {self.frame_rate}")
            except (KeyError, ValueError, TypeError) as e:
                print(f"获取帧率错误: {e}")
                self.frame_rate = 30.0  # 默认帧率
            
            # 计算视频时长（毫秒）
            try:
                # 重置时长
                self.duration = 0
                
                # 直接从source_duration_sec字段获取时长（这是deffcode提供的标准字段）
                if isinstance(metadata, dict) and "source_duration_sec" in metadata:
                    try:
                        # 强制转换为字符串再转为浮点数，避免类型问题
                        duration_str = str(metadata["source_duration_sec"])
                        duration_sec = float(duration_str)
                        if duration_sec > 0:
                            self.duration = int(duration_sec * 1000)
                            print(f"从source_duration_sec获取到视频时长: {self.duration}ms")
                    except (ValueError, TypeError) as e:
                        print(f"处理source_duration_sec错误: {e}")
                
                # 如果上面的方法失败，尝试从FFmpeg格式信息中获取时长
                if self.duration <= 0 and isinstance(metadata, dict):
                    # 尝试多种可能的键名
                    duration_keys = ["duration", "Duration", "DURATION"]
                    
                    # 遍历所有可能的键
                    for key in duration_keys:
                        if key in metadata:
                            duration_str = metadata[key]
                            if isinstance(duration_str, (int, float, str)):
                                try:
                                    # 尝试将字符串转换为浮点数
                                    duration_float = float(str(duration_str))
                                    if duration_float > 0:
                                        self.duration = int(duration_float * 1000)
                                        print(f"从键'{key}'获取到视频时长: {self.duration}ms")
                                        break
                                except ValueError:
                                    print(f"无法将'{duration_str}'转换为浮点数")
                
                # 如果上面的方法失败，尝试从帧数和帧率计算
                if self.duration <= 0 and isinstance(metadata, dict) and self.frame_rate > 0:
                    frame_keys = ["nb_frames", "NUMBER_OF_FRAMES", "frames", "approx_video_nframes"]
                    
                    for key in frame_keys:
                        if key in metadata:
                            try:
                                nb_frames = float(str(metadata[key]))
                                if nb_frames > 0:
                                    self.duration = int((nb_frames / self.frame_rate) * 1000)
                                    print(f"通过帧数计算视频时长: {self.duration}ms")
                                    break
                            except (ValueError, TypeError):
                                print(f"无法将'{metadata[key]}'转换为帧数")
                
                # 如果仍然无法获取时长，尝试使用其他元数据字段
                if self.duration <= 0 and isinstance(metadata, dict):
                    # 打印所有元数据，帮助调试
                    print("所有元数据字段:")
                    for key, value in metadata.items():
                        print(f"  {key}: {value}")
                    
                    # 尝试从比特率和文件大小估算
                    if "bit_rate" in metadata and "size" in metadata:
                        try:
                            bit_rate = float(str(metadata["bit_rate"]))
                            size = float(str(metadata["size"]))
                            if bit_rate > 0:
                                # 估算时长 = 文件大小(字节) * 8 / 比特率(bps)
                                self.duration = int((size * 8 / bit_rate) * 1000)
                                print(f"通过比特率估算视频时长: {self.duration}ms")
                        except (ValueError, TypeError, ZeroDivisionError):
                            pass
            except Exception as e:
                print(f"计算视频时长错误: {e}")
                self.duration = 0
                
            # 确保时长大于0，否则UI可能无法正常显示
            if self.duration <= 0:
                # 尝试使用FFprobe直接获取时长
                try:
                    command = [
                        "ffprobe", 
                        "-v", "error", 
                        "-show_entries", "format=duration", 
                        "-of", "default=noprint_wrappers=1:nokey=1", 
                        self.media_path
                    ]
                    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    if result.returncode == 0 and result.stdout.strip():
                        duration_sec = float(result.stdout.strip())
                        if duration_sec > 0:
                            self.duration = int(duration_sec * 1000)
                            print(f"通过FFprobe获取视频时长: {self.duration}ms")
                except Exception as e:
                    print(f"FFprobe获取时长失败: {e}")
                
                # 如果仍然无法获取时长，设置一个默认值
                if self.duration <= 0:
                    # 设置一个更合理的默认时长，避免UI问题
                    self.duration = 3600000  # 默认1小时
                    print("无法获取准确时长，使用默认值1小时")
                
            # 发送时长变化信号
            self.durationChanged.emit(self.duration)
            print(f"发送时长信号: {self.duration}ms")
            
            # 提取音频
            self._extract_audio()
            
            return True
        except Exception as e:
            print(f"初始化解码器错误: {e}")
            return False
            
    def _extract_audio(self):
        """
        从视频文件中提取音频
        """
        try:
            # 创建临时文件用于存储提取的音频
            temp_dir = tempfile.gettempdir()
            self.audio_file = os.path.join(temp_dir, f"xplayer_audio_{os.path.basename(self.media_path)}.wav")
            
            print(f"开始提取音频到: {self.audio_file}")
            
            # 使用ffmpeg提取音频
            command = [
                "ffmpeg",
                "-i", self.media_path,
                "-vn",  # 不处理视频
                "-acodec", "pcm_s16le",  # 转换为WAV格式
                "-ar", "44100",  # 采样率
                "-ac", "2",  # 双声道
                "-y",  # 覆盖已有文件
                self.audio_file
            ]
            
            # 执行命令
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # 检查命令执行结果
            if result.returncode != 0:
                print(f"ffmpeg命令执行失败: {result.stderr.decode('utf-8', errors='ignore')}")
            
            # 检查音频文件是否成功创建
            if not os.path.exists(self.audio_file):
                print("音频文件未创建")
                self.audio_file = None
            elif os.path.getsize(self.audio_file) == 0:
                print("音频文件为空")
                self.audio_file = None
            else:
                print(f"音频提取成功: {self.audio_file}, 大小: {os.path.getsize(self.audio_file)} 字节")
                
        except Exception as e:
            print(f"提取音频错误: {e}")
            self.audio_file = None
    
    def _update_frame(self):
        """
        更新视频帧
        """
        if not self.decoder or not hasattr(self, 'frame_generator') or self._state != self.PlayingState:
            return
            
        try:
            # 检查缓冲区是否有帧
            if self.frame_buffer:
                # 从缓冲区获取帧
                frame = self.frame_buffer.pop(0)
            else:
                # 从生成器获取下一帧
                frame = next(self.frame_generator, None)
            
            if frame is None:
                # 视频结束
                self.stop()
                if self.playlist:
                    self.playlist.next()
                return
            
            # 转换帧为QImage并发送信号
            height, width = frame.shape[:2]
            bytes_per_line = 3 * width
            q_image = QImage(frame.data, width, height, bytes_per_line, QImage.Format_RGB888).rgbSwapped()
            self.frameChanged.emit(q_image)
            
            # 填充帧缓冲区
            self._fill_frame_buffer()
            
        except Exception as e:
            print(f"更新帧错误: {e}")
            self.stop()
            
    def _fill_frame_buffer(self):
        """
        填充帧缓冲区，提高跳转性能
        """
        if not self.decoder or not hasattr(self, 'frame_generator') or self._state != self.PlayingState:
            return
            
        # 如果缓冲区未满，尝试填充
        # 使用更高效的填充策略，一次性获取多帧
        frames_to_fetch = self.frame_buffer_size - len(self.frame_buffer)
        if frames_to_fetch <= 0:
            return
            
        # 限制一次性获取的帧数，避免阻塞主线程太久
        frames_to_fetch = min(frames_to_fetch, 5)
        
        for _ in range(frames_to_fetch):
            try:
                # 尝试获取下一帧并添加到缓冲区
                frame = next(self.frame_generator, None)
                if frame is None:
                    # 视频结束
                    break
                self.frame_buffer.append(frame)
            except Exception as e:
                print(f"填充帧缓冲区错误: {e}")
                break
    
    def _update_position(self):
        """
        更新播放位置
        """
        if self._state != self.PlayingState:
            return
            
        # 更新位置
        if self.duration > 0:
            # 增加位置，考虑播放速率
            self.current_position += int(100 * self._rate)  # 每100ms更新一次
            
            # 确保不超过总时长
            if self.current_position > self.duration:
                self.current_position = self.duration
                
            # 发送位置变化信号
            self.positionChanged.emit(self.current_position)
            
            # 确保时长信号已发送
            if not self._duration_sent and self.duration > 0:
                self.durationChanged.emit(self.duration)
                self._duration_sent = True
                print(f"重新发送时长信号: {self.duration}ms")
            
            # 打印调试信息，每1000ms打印一次
            if self.current_position % 1000 == 0:
                print(f"当前位置: {self.current_position}ms, 总时长: {self.duration}ms")
    
    def _play_audio(self):
        """
        播放音频线程
        """
        if not self.audio_file or not os.path.exists(self.audio_file):
            print("没有可用的音频文件")
            return
            
        try:
            print(f"开始播放音频: {self.audio_file}")
            
            # 检查文件大小
            file_size = os.path.getsize(self.audio_file)
            print(f"音频文件大小: {file_size} 字节")
            
            if file_size == 0:
                print("音频文件为空，无法播放")
                return
            
            # 打开音频文件
            wf = wave.open(self.audio_file, 'rb')
            
            # 获取音频参数
            channels = wf.getnchannels()
            width = wf.getsampwidth()
            rate = wf.getframerate()
            frames = wf.getnframes()
            
            print(f"音频参数: 通道数={channels}, 采样宽度={width}, 采样率={rate}, 总帧数={frames}")
            
            # 如果有设置seek位置，跳转到对应位置
            if hasattr(self, 'seek_position') and self.seek_position > 0:
                # 计算音频帧位置
                position_frames = int((self.seek_position / 1000.0) * rate)
                # 确保位置在有效范围内
                if position_frames >= frames:
                    position_frames = max(0, frames - 1)
                wf.setpos(position_frames)
                print(f"音频初始化时设置位置: {self.seek_position}ms (帧位置: {position_frames})")
            
            # 创建音频流
            format = self.pyaudio_instance.get_format_from_width(width)
            self.audio_stream = self.pyaudio_instance.open(
                format=format,
                channels=channels,
                rate=rate,
                output=True,
                stream_callback=self._audio_callback
            )
            
            print("音频流已创建")
            
            # 设置音频播放状态
            self.audio_playing = True
            self.audio_paused = False
            
            # 设置音量
            # PyAudio不直接支持音量控制，可以在回调函数中实现
            
            # 开始播放
            self.audio_stream.start_stream()
            print("音频流已启动")
            
            # 等待播放完成
            while self.audio_stream and self.audio_stream.is_active() and self.audio_playing and not self.audio_paused:
                time.sleep(0.1)
                
                # 检查音视频同步状态（每100ms检查一次）
                if hasattr(self, 'current_position') and self._state == self.PlayingState:
                    # 获取当前音频位置（帧数）
                    if hasattr(self, '_wf') and self._wf is not None:
                        try:
                            current_audio_pos = self._wf.tell()
                            audio_time_ms = int((current_audio_pos / rate) * 1000)
                            
                            # 计算音视频差距（毫秒）
                            sync_diff = abs(audio_time_ms - self.current_position)
                            video_time_ms = self.current_position
                            
                            # 如果差距超过阈值（200ms），记录不同步情况
                            if sync_diff > 200:
                                print(f"检测到音视频不同步: 音频={audio_time_ms}ms, 视频={video_time_ms}ms, 差距={sync_diff}ms")
                                
                                # 如果差距非常大（超过1000ms），且不是刚刚进行过跳转，则尝试强制同步
                                if sync_diff > 1000 and not hasattr(self, '_last_sync_time') or \
                                   (time.time() - getattr(self, '_last_sync_time', 0)) > 2.0:
                                    # 设置seek_position以触发音频回调中的同步
                                    self.seek_position = video_time_ms
                                    # 记录最后同步时间，避免频繁同步
                                    self._last_sync_time = time.time()
                                    print(f"触发强制音视频同步: 设置seek_position={video_time_ms}ms")
                        except Exception as e:
                            print(f"检查音视频同步错误: {e}")
                
            print("音频播放结束或被中断")
                
            # 停止并关闭流
            if self.audio_stream:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
                self.audio_stream = None
                print("音频流已关闭")
                
            # 关闭音频文件
            wf.close()
            print("音频文件已关闭")
            
        except Exception as e:
            print(f"播放音频错误: {e}")
            import traceback
            traceback.print_exc()
            self._stop_audio()
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """
        音频回调函数
        """
        try:
            # 检查是否需要重新打开音频文件或重新定位
            if not hasattr(self, '_wf') or self._wf is None:
                self._wf = wave.open(self.audio_file, 'rb')
                print(f"打开音频文件: {self.audio_file}")
                
                # 如果有设置seek位置，跳转到对应位置
                if hasattr(self, 'seek_position') and self.seek_position > 0:
                    # 计算音频帧位置
                    frame_rate = self._wf.getframerate()
                    position_frames = int((self.seek_position / 1000.0) * frame_rate)
                    # 确保位置在有效范围内
                    if position_frames >= self._wf.getnframes():
                        position_frames = max(0, self._wf.getnframes() - 1)
                    self._wf.setpos(position_frames)
                    print(f"音频位置已设置到: {self.seek_position}ms (帧位置: {position_frames})")
                    # 记录最后一次设置的位置，用于后续同步检查
                    self._last_seek_position = self.seek_position
                    # 重置seek_position，避免重复跳转
                    self.seek_position = 0
            
            # 检查是否需要重新定位（当前播放位置与seek_position不匹配）
            elif hasattr(self, 'seek_position') and self.seek_position > 0:
                # 获取当前音频位置（帧数）
                current_audio_pos = self._wf.tell()
                frame_rate = self._wf.getframerate()
                
                # 计算期望的音频帧位置
                expected_pos = int((self.seek_position / 1000.0) * frame_rate)
                # 确保位置在有效范围内
                if expected_pos >= self._wf.getnframes():
                    expected_pos = max(0, self._wf.getnframes() - 1)
                
                # 如果当前位置与期望位置相差太大，重新定位
                # 允许一定的误差范围（约50ms的帧数）
                tolerance = int(0.05 * frame_rate)  # 降低容差以提高精度
                if abs(current_audio_pos - expected_pos) > tolerance:
                    print(f"音频位置同步: 当前={current_audio_pos}, 期望={expected_pos}, 差距={(current_audio_pos - expected_pos) / frame_rate * 1000:.2f}ms")
                    self._wf.setpos(expected_pos)
                    # 记录最后一次设置的位置，用于后续同步检查
                    self._last_seek_position = self.seek_position
                    # 重置seek_position，避免重复跳转
                    self.seek_position = 0
                    # 清空缓冲区中的旧数据
                    return (b'', pyaudio.paContinue)
                else:
                    # 位置已经足够接近，只需重置seek_position
                    self._last_seek_position = self.seek_position
                    self.seek_position = 0
            
            # 持续监控音视频同步状态
            elif hasattr(self, 'current_position') and self._state == self.PlayingState:
                # 获取当前音频位置（帧数）和视频位置
                current_audio_pos = self._wf.tell()
                frame_rate = self._wf.getframerate()
                audio_time_ms = int((current_audio_pos / frame_rate) * 1000)
                video_time_ms = self.current_position
                
                # 计算音视频差距（毫秒）
                sync_diff = abs(audio_time_ms - video_time_ms)
                
                # 如果差距超过阈值（300ms），尝试同步
                if sync_diff > 300:
                    print(f"检测到音视频严重不同步: 音频={audio_time_ms}ms, 视频={video_time_ms}ms, 差距={sync_diff}ms")
                    # 计算新的音频位置
                    new_pos = int((video_time_ms / 1000.0) * frame_rate)
                    # 确保位置在有效范围内
                    if new_pos >= self._wf.getnframes():
                        new_pos = max(0, self._wf.getnframes() - 1)
                    # 设置新位置
                    self._wf.setpos(new_pos)
                    print(f"自动调整音频位置到: {video_time_ms}ms (帧位置: {new_pos})")
                    # 清空缓冲区中的旧数据
                    return (b'', pyaudio.paContinue)
                
            # 读取音频帧
            data = self._wf.readframes(frame_count)
            
            # 检查是否到达文件末尾
            if len(data) == 0:
                print("音频播放完成")
                # 关闭文件并返回完成状态
                if hasattr(self, '_wf') and self._wf is not None:
                    self._wf.close()
                    self._wf = None
                # 返回继续状态而不是完成状态，这样可以防止音频流在文件结束时立即关闭
                # 特别是在跳转位置时，可能会暂时没有数据，但不应该结束播放
                return (b'', pyaudio.paContinue)
            
            # 应用音量控制
            if data and self._volume < 100:
                # 将字节数据转换为数组以调整音量
                import array
                data_array = array.array('h', data)
                for i in range(len(data_array)):
                    data_array[i] = int(data_array[i] * (self._volume / 100.0))
                data = data_array.tobytes()
                
            return (data, pyaudio.paContinue)
        except Exception as e:
            print(f"音频回调错误: {e}")
            # 确保关闭文件
            if hasattr(self, '_wf') and self._wf is not None:
                try:
                    self._wf.close()
                except:
                    pass
                self._wf = None
            # 返回继续状态而不是完成状态，这样可以防止音频流在出错时立即关闭
            # 这样在跳转位置时，即使出现临时错误，音频流也不会被关闭
            return (b'', pyaudio.paContinue)
    
    def _stop_audio(self):
        """
        停止音频播放
        """
        # 标记音频播放状态为停止
        self.audio_playing = False
        
        # 检查是否是因为跳转位置而调用此方法
        is_seeking = hasattr(self, 'seek_position') and self.seek_position > 0
        
        if self.audio_stream:
            try:
                # 停止音频流
                self.audio_stream.stop_stream()
                
                # 只有在非跳转情况下才完全关闭音频流
                # 在跳转位置时，我们希望保持音频流打开以便从新位置继续播放
                if not is_seeking:
                    self.audio_stream.close()
                    self.audio_stream = None
                else:
                    # 在跳转位置时，只标记为暂停而不关闭
                    self.audio_paused = True
            except Exception as e:
                print(f"停止音频流错误: {e}")
                # 出错时完全关闭
                if self.audio_stream:
                    try:
                        self.audio_stream.close()
                    except:
                        pass
                    self.audio_stream = None
        
        # 关闭音频文件
        # 在跳转位置时，我们希望在音频回调中重新打开文件，而不是在这里关闭
        if not is_seeking and hasattr(self, '_wf') and self._wf is not None:
            try:
                self._wf.close()
                print("关闭音频文件")
                self._wf = None
            except Exception as e:
                print(f"关闭音频文件错误: {e}")
                self._wf = None
                
        # 只在非跳转情况下等待音频线程结束
        if not is_seeking and self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.join(1)  # 等待最多1秒
    
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
        
        # 确保时长信号已发送
        if self.duration > 0:
            self.durationChanged.emit(self.duration)
            self._duration_sent = True
            print(f"播放时发送时长信号: {self.duration}ms")
        
        # 启动定时器
        self.timer.start()
        self.position_timer.start()
        
        # 启动音频播放
        if self.audio_file and os.path.exists(self.audio_file):
            if self.audio_paused and self.audio_stream:
                # 恢复暂停的音频
                self.audio_paused = False
                self.audio_stream.start_stream()
            else:
                # 开始新的音频播放
                self._stop_audio()  # 确保之前的音频已停止
                self.audio_thread = threading.Thread(target=self._play_audio)
                self.audio_thread.daemon = True
                self.audio_thread.start()
    
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
        self.position_timer.stop()
        
        # 暂停音频
        if self.audio_stream and self.audio_stream.is_active():
            self.audio_paused = True
            self.audio_stream.stop_stream()
    
    def stop(self):
        """
        停止播放
        """
        # 停止定时器
        self.timer.stop()
        self.position_timer.stop()
        
        # 停止音频播放
        self._stop_audio()
        
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
        
        # 重置时长发送标记
        self._duration_sent = False
        
        # 设置状态为停止
        self._state = self.StoppedState
        self.stateChanged.emit(self._state)
    
    def setPosition(self, position):
        """
        设置播放位置
        :param position: 位置（毫秒）
        """
        # 确保解码器已初始化且位置有效
        if not self.decoder:
            return
            
        # 确保位置在有效范围内
        if position < 0:
            position = 0
        if position > self.duration:
            position = self.duration
            
        print(f"尝试设置位置到: {position}ms")
        
        # 保存当前状态
        was_playing = (self._state == self.PlayingState)
        
        # 计算目标时间（秒）
        target_time = position / 1000.0
        print(f"目标时间位置: {target_time}秒")
        
        # 暂停当前播放但不重置位置
        if self.timer.isActive():
            self.timer.stop()
        if self.position_timer.isActive():
            self.position_timer.stop()
        
        try:
            # 设置当前位置和seek位置，供音频播放使用
            self.current_position = position
            self.seek_position = position
            self.positionChanged.emit(self.current_position)
            
            # 优化的跳转方法：使用预缓冲和快速seek
            if self.decoder and hasattr(self.decoder, 'frame_generator'):
                # 暂停音频但不完全停止，以便在新位置继续播放
                audio_was_active = False
                if self.audio_stream and self.audio_stream.is_active():
                    audio_was_active = True
                    self.audio_stream.stop_stream()
                    self.audio_paused = True
                
                # 使用快速seek方法
                seek_seconds = position / 1000.0
                
                # 保存当前解码器的参数
                current_format = self.decoder.frame_format if hasattr(self.decoder, 'frame_format') else "bgr24"
                
                # 尝试使用更高效的seek方法
                try:
                    # 关闭当前解码器但不完全释放资源
                    if hasattr(self.decoder, 'close'):
                        self.decoder.close()
                    
                    # 使用相同的参数但添加seek参数创建新的解码器
                    # 增加缓冲区大小以提高跳转后的流畅度
                    self.decoder = FFdecoder(
                        self.media_path, 
                        frame_format=current_format,
                        **{
                            '-ss': str(seek_seconds),  # 使用FFmpeg的seek参数
                            '-analyzeduration': '10000000',  # 增加分析时间
                            '-probesize': '10000000'  # 增加探测大小
                        }
                    ).formulate()
                    
                    # 创建新的帧生成器
                    self.frame_generator = self.decoder.generateFrame()
                    
                    # 清空并预加载更多帧到缓冲区以提高响应速度
                    self.frame_buffer = []
                    
                    # 增加缓冲区大小以提高跳转后的流畅度
                    temp_buffer_size = self.frame_buffer_size * 2
                    
                    # 预读取更多帧到缓冲区
                    for _ in range(temp_buffer_size):
                        try:
                            frame = next(self.frame_generator, None)
                            if frame is None:
                                break
                            self.frame_buffer.append(frame)
                        except Exception as e:
                            print(f"填充帧缓冲区错误: {e}")
                            break
                    
                    print(f"成功使用快速seek跳转到: {position}ms，已预加载{len(self.frame_buffer)}帧")
                    
                    # 如果之前是播放状态，继续播放
                    if was_playing:
                        # 设置状态为播放
                        self._state = self.PlayingState
                        self.stateChanged.emit(self._state)
                        
                        # 启动定时器
                        self.timer.start()
                        self.position_timer.start()
                        
                        # 继续音频播放（从新位置开始）
                        if self.audio_file and os.path.exists(self.audio_file):
                            if audio_was_active and self.audio_stream and self.audio_paused:
                                # 如果音频流存在且已暂停，直接从新位置继续播放
                                self.audio_paused = False
                                self.audio_stream.start_stream()
                            else:
                                # 否则创建新的音频播放线程
                                # 注意：不要在这里调用_stop_audio()，因为它会完全关闭音频流
                                # 只有在必要时才创建新的音频线程
                                if not self.audio_thread or not self.audio_thread.is_alive():
                                    self.audio_thread = threading.Thread(target=self._play_audio)
                                    self.audio_thread.daemon = True
                                    self.audio_thread.start()
                except Exception as e:
                    print(f"快速seek失败，回退到重新初始化解码器: {e}")
                    # 如果快速seek失败，回退到完全重新初始化解码器
                    # 保存音频状态，避免在_init_decoder中被完全停止
                    audio_was_playing = self.audio_playing
                    audio_was_paused = self.audio_paused
                    
                    if not self._init_decoder():
                        raise Exception("重新初始化解码器失败")
                    
                    # 如果之前是播放状态，继续播放
                    if was_playing:
                        # 设置状态为播放
                        self._state = self.PlayingState
                        self.stateChanged.emit(self._state)
                        
                        # 启动定时器
                        self.timer.start()
                        self.position_timer.start()
                        
                        # 确保音频播放被重新启动
                        if self.audio_file and os.path.exists(self.audio_file):
                            # 始终创建新的音频播放线程，因为_init_decoder已经停止了之前的音频
                            self.audio_thread = threading.Thread(target=self._play_audio)
                            self.audio_thread.daemon = True
                            self.audio_thread.start()
            else:
                # 如果解码器不可用或没有帧生成器，回退到完全重新初始化
                print("解码器不可用，使用完全重新初始化方法")
                if self._init_decoder():
                    # 如果之前是播放状态，继续播放
                    if was_playing:
                        # 设置状态为播放
                        self._state = self.PlayingState
                        self.stateChanged.emit(self._state)
                        
                        # 启动定时器
                        self.timer.start()
                        self.position_timer.start()
                        
                        # 启动音频播放
                        if self.audio_file and os.path.exists(self.audio_file):
                            # 始终创建新的音频播放线程
                            self.audio_thread = threading.Thread(target=self._play_audio)
                            self.audio_thread.daemon = True
                            self.audio_thread.start()
                
            print(f"位置已设置到: {self.current_position}ms")
        except Exception as e:
            print(f"设置位置错误: {e}")
            import traceback
            traceback.print_exc()
    
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