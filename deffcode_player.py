#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
XPlayer - Deffcode播放器组件
提供基于deffcode的播放器功能，替代VLC播放器
"""

import os
import cv2
import numpy as np
import threading
import subprocess
import tempfile
import time
import sounddevice as sd
import soundfile as sf
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
        # 调用父类的构造函数，初始化父类对象
        super().__init__(parent)
        
        # 解码器
        self.decoder = None  # 初始化解码器为None，用于后续设置具体的解码器
        
        # 当前媒体
        self.media_path = None  # 初始化当前媒体路径为None，用于存储当前播放的媒体文件路径
        
        # 播放列表
        self.playlist = None  # 初始化播放列表为None，用于存储播放列表
        
        # 当前状态
        self._state = self.StoppedState  # 初始化当前状态为停止状态
        
        # 当前音量 (0-100)
        self._volume = 50  # 初始化音量为50，范围从0到100
        
        # 播放速率
        self._rate = 1.0  # 初始化播放速率为1.0，表示正常速度
        
        # 视频输出控件
        self.video_widget = None  # 初始化视频输出控件为None，用于后续设置具体的视频输出控件
        
        # 视频属性
        self.duration = 0  # 初始化视频时长为0，单位为秒
        self.current_position = 0  # 初始化当前播放位置为0，单位为秒
        self.frame_rate = 0  # 初始化帧率为0，表示每秒显示的帧数
        
        # 帧缓冲区，用于提高跳转性能
        self.frame_buffer_size = 5  # 缓冲5帧，用于提高跳转时的流畅度
        self.frame_buffer = []  # 初始化帧缓冲区为空列表
        
        # 音频相关
        self.audio_stream = None  # 初始化音频流为None，用于存储音频流数据
        self.audio_data = None  # 初始化音频数据为None，用于存储音频数据
        self.audio_playing = False  # 初始化音频播放状态为False，表示未播放
        self.audio_paused = False  # 初始化音频暂停状态为False，表示未暂停
        self.audio_position = 0  # 初始化音频播放位置为0，单位为秒
        self.audio_thread = None  # 初始化音频线程为None，用于后续设置具体的音频处理线程
        self.audio_sample_rate = 44100  # 默认采样率为44100Hz
        self.audio_channels = 2  # 默认双声道
        
        # 创建定时器，用于更新播放位置和帧
        self.timer = QTimer(self)  # 创建一个QTimer对象，用于定时触发事件
        self.timer.setInterval(33)  # 约30fps
        self.timer.timeout.connect(self._update_frame)
        
        # 创建定时器，用于更新播放位置
        self.position_timer = QTimer(self)
        self.position_timer.setInterval(1000)  # 1000ms(1秒)更新一次
        self.position_timer.timeout.connect(self._update_position)
    
    def _update_frame(self):
        """
        更新视频帧
        由timer定时器触发，负责从解码器获取视频帧并更新显示
        """
        if self._state != self.PlayingState or not self.decoder:
            return
            
        try:
            # 首先检查帧缓冲区是否有帧
            if self.frame_buffer:
                # 从缓冲区获取一帧
                frame = self.frame_buffer.pop(0)
            else:
                # 缓冲区为空，直接从解码器获取帧
                try:
                    frame = next(self.frame_generator, None)
                except Exception as e:
                    print(f"获取下一帧错误: {e}")
                    frame = None
                    
            # 如果没有帧，可能是播放结束
            if frame is None:
                print("没有更多帧，播放结束")
                self.stop()
                # 如果有播放列表，播放下一个
                if self.playlist:
                    self.playlist.next()
                return
                
            # 更新当前位置（基于帧率计算）
            if self.frame_rate > 0:
                # 计算每帧的时间（毫秒）
                frame_time = 1000.0 / self.frame_rate
                # 更新当前位置
                self.current_position += frame_time
                
            # 转换帧为QImage并发送信号
            if isinstance(frame, np.ndarray):
                # 确保帧是BGR格式
                if frame.shape[2] == 3:  # 3通道图像
                    height, width, channels = frame.shape
                    bytes_per_line = channels * width
                    # 创建QImage
                    qimage = QImage(frame.data, width, height, bytes_per_line, QImage.Format_RGB888)
                    # BGR到RGB转换
                    qimage = qimage.rgbSwapped()
                    # 发送帧变化信号
                    self.frameChanged.emit(qimage)
                    
            # 尝试填充帧缓冲区
            while len(self.frame_buffer) < self.frame_buffer_size:
                try:
                    next_frame = next(self.frame_generator, None)
                    if next_frame is None:
                        break
                    self.frame_buffer.append(next_frame)
                except Exception as e:
                    print(f"填充帧缓冲区错误: {e}")
                    break
                    
        except Exception as e:
            print(f"更新帧错误: {e}")
            import traceback
            traceback.print_exc()
    
    def _update_position(self):
        """
        更新播放位置
        由position_timer定时器触发，负责更新和发送当前播放位置
        """
        if self._state == self.PlayingState:
            # 发送位置变化信号
            self.positionChanged.emit(int(self.current_position))
            
            # 检查是否播放结束
            if self.duration > 0 and self.current_position >= self.duration:
                print("播放位置到达结尾，停止播放")
                self.stop()
                # 如果有播放列表，播放下一个
                if self.playlist:
                    self.playlist.next()
        
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
            
            # 初始化音频播放器
            self._init_audio_player()
            
            return True
        except Exception as e:
            print(f"初始化解码器错误: {e}")
            return False
            
    def _audio_callback(self, outdata, frames, time, status):
        """音频回调函数"""
        if status:
            print(f'音频回调状态: {status}')
            
        if not self.audio_playing or self.audio_paused:
            outdata.fill(0)
            return
            
        # 检查是否需要重新定位音频位置
        if hasattr(self, 'seek_position') and self.seek_position > 0:
            try:
                position_samples = int((self.seek_position / 1000.0) * self.audio_sample_rate)
                if position_samples >= len(self.audio_data):
                    position_samples = max(0, len(self.audio_data) - 1)
                self.audio_position = position_samples
                self.seek_position = 0
                outdata.fill(0)
                return
            except Exception as e:
                print(f"音频位置同步错误: {e}")
                self.seek_position = 0
                outdata.fill(0)
                return
        
        # 处理音频数据
        try:
            available = len(self.audio_data) - self.audio_position
            if available < frames:
                outdata[:available] = self.audio_data[self.audio_position:self.audio_position+available]
                outdata[available:] = 0
                self.audio_position += available
            else:
                outdata[:] = self.audio_data[self.audio_position:self.audio_position+frames]
                self.audio_position += frames
        except Exception as e:
            print(f"音频数据处理错误: {e}")
            outdata.fill(0)
    
    def _init_audio_player(self):
        """
        初始化音频播放器
        使用sounddevice和soundfile处理音频播放
        """
        try:
            # 停止之前的音频流
            self._stop_audio()
            
            # 使用FFmpeg提取音频到临时文件
            temp_audio = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            temp_audio_path = temp_audio.name
            temp_audio.close()
            
            # 使用FFmpeg提取音频
            import subprocess
            cmd = [
                'ffmpeg', '-y',
                '-i', self.media_path,
                '-vn',  # 不处理视频
                '-acodec', 'pcm_s16le',  # 转换为WAV格式
                '-ar', str(self.audio_sample_rate),  # 采样率
                '-ac', str(self.audio_channels),  # 声道数
                temp_audio_path
            ]
            
            # 如果有seek位置，添加seek参数
            if hasattr(self, 'seek_position') and self.seek_position > 0:
                cmd.insert(2, '-ss')
                cmd.insert(3, str(self.seek_position / 1000.0))
            
            subprocess.run(cmd, check=True)
            
            # 读取音频文件
            self.audio_data, self.audio_sample_rate = sf.read(temp_audio_path)
            os.unlink(temp_audio_path)  # 删除临时文件
            
            # 创建音频流
            self.audio_stream = sd.OutputStream(
                channels=self.audio_channels,
                samplerate=self.audio_sample_rate,
                callback=self._audio_callback
            )
            
            # 设置播放状态
            self.audio_playing = True
            self.audio_paused = True  # 初始状态为暂停
            
            # 记录音频信息，便于调试
            print(f"音频数据大小: {len(self.audio_data) if self.audio_data is not None else 0} 样本")
            print(f"音频参数: 通道数={self.audio_channels}, 采样率={self.audio_sample_rate}, 总样本数={len(self.audio_data) if self.audio_data is not None else 0}")
            print("音频流已创建")
            
            # 启动音频流 - 注意：不再在这里启动，而是在play方法中统一启动
            # 这样可以确保第一次播放时也能正确启动音频
            
            print(f"音频播放器初始化完成: {self.media_path}")
            
        except Exception as e:
            print(f"初始化音频播放器错误: {e}")
            self.audio_stream = None
            self.audio_data = None
                

                


    
    def _play_audio(self):
        """
        播放音频线程方法
        使用sounddevice播放音频数据
        """
        try:
            # 确保有音频数据
            if self.audio_data is None:
                return
                
            # 创建音频流
            self.audio_stream = sd.OutputStream(
                samplerate=self.audio_sample_rate,
                channels=self.audio_channels,
                callback=self._audio_callback,
                dtype='float32'
            )
            
            # 启动音频流
            self.audio_stream.start()
            self.audio_playing = True
            self.audio_paused = False
            
            # 等待音频播放完成
            while self.audio_playing:
                time.sleep(0.1)
                
        except Exception as e:
            print(f"音频播放错误: {e}")
        finally:
            # 确保停止音频流
            if hasattr(self, 'audio_stream') and self.audio_stream:
                self.audio_stream.stop()
                self.audio_stream.close()
                self.audio_stream = None
            self.audio_playing = False

    def _stop_audio(self):
        """
        停止音频播放
        """
        # 标记音频播放状态为停止
        self.audio_playing = False
        self.audio_paused = True
        
        # 停止并关闭音频流
        if hasattr(self, 'audio_stream') and self.audio_stream:
            try:
                if self.audio_stream.active:
                    self.audio_stream.stop()
                self.audio_stream.close()
                print("音频流已关闭")
            except Exception as e:
                print(f"关闭音频流错误: {e}")
            self.audio_stream = None
        
        # 检查是否是因为跳转位置而调用此方法
        is_seeking = hasattr(self, 'seek_position') and self.seek_position > 0
        
        # 检查是否是暂时性停止（如暂停播放）
        is_temporary_stop = self._state == self.PausedState
        
        # 记录状态信息
        if is_seeking:
            print("跳转位置中，暂停音频播放")
        elif is_temporary_stop:
            print("暂时停止，暂停音频播放")
        else:
            print("音频播放已停止")

    
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
        
        # 确保音频播放状态正确设置
        self.audio_playing = True
        self.audio_paused = False
        print("音频播放状态已设置: playing=True, paused=False")
        
        # 如果需要，初始化音频播放器
        if not hasattr(self, 'audio_data') or self.audio_data is None or self.audio_stream is None:
            print("音频数据或流不存在，初始化音频播放器")
            self._init_audio_player()
            # 重新设置播放状态，因为_init_audio_player会将paused设为True
            self.audio_paused = False
        
        # 启动音频流 - 确保在每次播放时都正确启动音频流
        if hasattr(self, 'audio_stream') and self.audio_stream:
            try:
                # 无论是否active，都尝试先停止再启动，确保状态一致
                if self.audio_stream.active:
                    self.audio_stream.stop()
                    print("停止已激活的音频流")
                
                # 启动音频流
                self.audio_stream.start()
                print("音频流已启动")
                
                # 如果有设置位置，确保音频位置正确
                if hasattr(self, 'current_position') and self.current_position > 0:
                    position_samples = int((self.current_position / 1000.0) * self.audio_sample_rate)
                    if position_samples < len(self.audio_data):
                        self.audio_position = position_samples
                        print(f"音频位置已设置到: {self.current_position}ms (样本位置: {position_samples})")
                else:
                    # 确保从头开始播放
                    self.audio_position = 0
                    print("音频位置已重置为开始位置")
                
                print("音频播放已启动，准备播放音频数据")
                
            except Exception as e:
                print(f"启动音频流错误: {e}")
                # 尝试重新初始化音频
                self._init_audio_player()
                # 重新设置播放状态
                self.audio_paused = False
                # 再次尝试启动
                if hasattr(self, 'audio_stream') and self.audio_stream:
                    try:
                        self.audio_stream.start()
                        print("音频播放已重新初始化并启动")
                    except Exception as e:
                        print(f"第二次尝试启动音频流失败: {e}")
        else:
            print("音频流不可用，尝试重新初始化")
            self._init_audio_player()
            # 重新设置播放状态
            self.audio_paused = False
            # 初始化后再次尝试启动
            if hasattr(self, 'audio_stream') and self.audio_stream:
                try:
                    self.audio_stream.start()
                    print("音频播放已初始化并启动")
                except Exception as e:
                    print(f"初始化后启动音频流失败: {e}")
            
        print("音频播放流程完成")
    
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
        self.audio_paused = True
        print("音频播放已暂停")
    
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
            # 设置当前位置和seek位置
            self.current_position = position
            self.seek_position = position
            self.positionChanged.emit(self.current_position)
            
            # 优化的跳转方法：使用预缓冲和快速seek
            if self.decoder and hasattr(self.decoder, 'frame_generator'):
                # 暂停音频但不完全停止，以便在新位置继续播放
                # 设置音频暂停状态
                self.audio_paused = True
                self.audio_playing = False
                print(f"音频播放暂停，准备跳转到: {position}ms")
                
                # 使用快速seek方法处理视频
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
                        if was_playing:
                            # 恢复音频播放
                            self.audio_paused = False
                            self.audio_playing = True
                            print("音频播放已从新位置继续")
                except Exception as e:
                    print(f"快速seek失败，回退到重新初始化解码器: {e}")
                    # 如果快速seek失败，回退到完全重新初始化解码器
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
                        self.audio_paused = False
                        self.audio_playing = True
                        print("音频播放已从新位置继续")
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
                        self.audio_paused = False
                        self.audio_playing = True
                        print("音频播放已从新位置继续")
                        
                        # 如果需要重新创建音频线程
                        if hasattr(self, 'audio_data') and self.audio_data is not None:
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
        # 限制音量范围
        self._volume = max(0, min(100, volume))
        
        # 存储音量设置，实际音频播放时会应用此音量
        # 注意：DeffcodePlayer没有audio_player属性，只有audio_playing标志
        print(f"音频音量已设置为: {self._volume}%")

    
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