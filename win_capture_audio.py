"""
Windows Audio Capture Python Interface

这个模块提供了一个简单的Python接口来捕获特定进程的音频。
使用Windows的进程循环回调API来实现低延迟的音频捕获。
"""

import ctypes
import ctypes.wintypes
import numpy as np
from typing import Optional, Tuple
import time
import threading
from ctypes import Structure, c_float, c_uint, c_ushort, c_void_p, POINTER


class AudioCapture:
    """音频捕获类，用于从特定进程捕获音频数据"""
    
    def __init__(self, dll_path: str = "./win-capture-audio-wrapper.dll"):
        """
        初始化音频捕获器
        
        Args:
            dll_path: DLL文件路径
        """
        try:
            self.dll = ctypes.CDLL(dll_path)
        except OSError as e:
            raise RuntimeError(f"无法加载DLL文件 {dll_path}: {e}")
        
        # 定义C函数签名
        self._setup_function_signatures()
        
        self.handle = None
        self.is_capturing = False
        self.sample_rate = 44100
        self.channels = 2
        
    def _setup_function_signatures(self):
        """设置C函数的参数和返回值类型"""
        # sca_create_capture(pid, sample_rate, channels) -> handle
        self.dll.sca_create_capture.argtypes = [c_uint, c_uint, c_ushort]
        self.dll.sca_create_capture.restype = c_void_p
        
        # sca_read_audio_frames(handle, buffer, frames) -> frames_read
        self.dll.sca_read_audio_frames.argtypes = [c_void_p, POINTER(c_float), c_uint]
        self.dll.sca_read_audio_frames.restype = c_uint
        
        # sca_destroy_capture(handle)
        self.dll.sca_destroy_capture.argtypes = [c_void_p]
        self.dll.sca_destroy_capture.restype = None
    
    def start_capture(self, pid: int, sample_rate: int = 44100, channels: int = 2) -> bool:
        """
        开始捕获指定进程的音频
        
        Args:
            pid: 目标进程ID
            sample_rate: 采样率，默认44100Hz
            channels: 声道数，默认2（立体声）
            
        Returns:
            bool: 是否成功开始捕获
        """
        if self.is_capturing:
            self.stop_capture()
            
        self.sample_rate = sample_rate
        self.channels = channels
        
        self.handle = self.dll.sca_create_capture(pid, sample_rate, channels)
        
        if self.handle is None or self.handle == 0:
            return False
            
        self.is_capturing = True
        return True
    
    def read_audio(self, frames: int = 1024) -> Optional[np.ndarray]:
        """
        读取音频数据
        
        Args:
            frames: 要读取的音频帧数
            
        Returns:
            numpy数组包含音频数据，形状为(frames_read, channels)，如果没有数据则返回None
        """
        if not self.is_capturing or self.handle is None:
            return None
            
        # 创建缓冲区
        buffer_size = frames * self.channels
        buffer = (c_float * buffer_size)()
        
        # 读取音频数据
        frames_read = self.dll.sca_read_audio_frames(self.handle, buffer, frames)
        
        if frames_read == 0:
            return None
            
        # 转换为numpy数组 - 使用ctypes.cast和from_address来获取正确的缓冲区
        buffer_ptr = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_float))
        audio_data = np.ctypeslib.as_array(buffer_ptr, shape=(frames_read * self.channels,))
        
        # 重塑为(frames, channels)格式
        if self.channels > 1:
            audio_data = audio_data.reshape(-1, self.channels)
        else:
            audio_data = audio_data.reshape(-1, 1)
            
        return audio_data
    
    def stop_capture(self):
        """停止音频捕获"""
        if self.handle is not None:
            self.dll.sca_destroy_capture(self.handle)
            self.handle = None
        self.is_capturing = False
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出，自动清理资源"""
        self.stop_capture()


class AudioStream:
    """音频流类，提供连续的音频数据流"""
    
    def __init__(self, capture: AudioCapture, callback=None, frames_per_buffer: int = 1024):
        """
        初始化音频流
        
        Args:
            capture: AudioCapture实例
            callback: 音频数据回调函数，接收(audio_data, frames)参数
            frames_per_buffer: 每次读取的帧数
        """
        self.capture = capture
        self.callback = callback
        self.frames_per_buffer = frames_per_buffer
        self.is_streaming = False
        self.thread = None
    
    def start(self):
        """开始音频流"""
        if self.is_streaming:
            return
            
        self.is_streaming = True
        self.thread = threading.Thread(target=self._stream_worker)
        self.thread.start()
    
    def stop(self):
        """停止音频流"""
        self.is_streaming = False
        if self.thread is not None:
            self.thread.join()
            self.thread = None
    
    def _stream_worker(self):
        """音频流工作线程"""
        while self.is_streaming:
            audio_data = self.capture.read_audio(self.frames_per_buffer)
            
            if audio_data is not None and self.callback is not None:
                self.callback(audio_data, len(audio_data))
            
            # 短暂休眠避免CPU占用过高
            time.sleep(0.001)


def get_process_list() -> list:
    """
    获取当前运行的进程列表
    
    Returns:
        包含(pid, process_name)元组的列表
    """
    import psutil
    processes = []
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            processes.append((proc.info['pid'], proc.info['name']))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return processes


def find_process_by_name(name: str) -> Optional[int]:
    """
    根据进程名查找进程ID
    
    Args:
        name: 进程名（例如："chrome.exe"）
        
    Returns:
        进程ID，如果未找到则返回None
    """
    import psutil
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if proc.info['name'].lower() == name.lower():
                return proc.info['pid']
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None


# 示例用法
if __name__ == "__main__":
    def audio_callback(audio_data, frames):
        """音频数据回调函数示例"""
        # 计算音频的音量（RMS）
        rms = np.sqrt(np.mean(audio_data ** 2))
        print(f"收到 {frames} 帧音频数据，音量: {rms:.4f}")
        
    
    # 查找Chrome进程（示例）
    chrome_pid = find_process_by_name("cloudmusic.exe")
    if chrome_pid is None:
        print("未找到Chrome进程，请先启动Chrome浏览器")
        exit(1)
    
    print(f"找到Chrome进程，PID: {chrome_pid}")
    
    # 创建音频捕获器
    with AudioCapture() as capture:
        # 开始捕获Chrome的音频
        if capture.start_capture(chrome_pid, sample_rate=44100, channels=2):
            print("开始捕获音频...")
            
            # 创建音频流
            stream = AudioStream(capture, callback=audio_callback)
            stream.start()
            
            try:
                # 运行10秒
                time.sleep(10)
            except KeyboardInterrupt:
                print("用户中断")
            finally:
                stream.stop()
                print("停止捕获")
        else:
            print("无法开始音频捕获，请检查进程ID是否正确") 