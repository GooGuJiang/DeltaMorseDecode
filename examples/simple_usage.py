#!/usr/bin/env python3
"""
简单使用示例
演示如何使用DeltaMorseDecode的各个组件
"""

import sys
import os

# 添加src目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from morse_decoder.core.decoder import MorseDecoder
from morse_decoder.core.constants import DEFAULT_CONFIG
from morse_decoder.audio.processor import AudioProcessor
from morse_decoder.utils.time_utils import Timer


def example_decoder_usage():
    """演示解码器基本使用"""
    print("=== 解码器使用示例 ===")
    
    # 创建解码器
    decoder = MorseDecoder()
    
    # 模拟信号处理
    signals = [
        (0.03, "短信号 - 点"),
        (0.08, "长信号 - 划"),
        (0.02, "短信号 - 点"),
        (0.09, "长信号 - 划"),
        (0.03, "短信号 - 点")
    ]
    
    for duration, description in signals:
        symbol = decoder.process_signal_duration(duration)
        print(f"{description}: {symbol} (当前码: {decoder.current_code})")
        
        # 模拟字母间隔
        result = decoder.process_silence_duration(1.0)
        if result:
            print(f"解码结果: {result}")
    
    print(f"解码器状态: {decoder.get_current_state()}")


def example_audio_processor():
    """演示音频处理器使用"""
    print("\n=== 音频处理器使用示例 ===")
    
    # 创建音频处理器
    processor = AudioProcessor()
    
    # 模拟音频数据
    import numpy as np
    
    # 生成测试信号
    sample_rate = 44100
    duration = 0.1  # 100ms
    frequency = 4200  # 4.2kHz
    
    t = np.linspace(0, duration, int(sample_rate * duration))
    signal = np.sin(2 * np.pi * frequency * t) * 0.01  # 振幅0.01
    
    # 处理音频块
    result = processor.process_chunk(signal)
    print(f"能量: {result['energy']:.6f}")
    print(f"信号事件: {result['signal_event']}")
    print(f"信号状态: {'开' if result['is_signal_on'] else '关'}")


def example_timer_usage():
    """演示计时器使用"""
    print("\n=== 计时器使用示例 ===")
    
    import time
    
    timer = Timer()
    
    # 开始计时
    timer.start()
    print("计时器已启动...")
    
    # 模拟一些工作
    time.sleep(1)
    
    print(f"经过时间: {timer.elapsed():.2f}秒")
    
    # 停止计时
    elapsed = timer.stop()
    print(f"总用时: {elapsed:.2f}秒")


def example_configuration():
    """演示配置使用"""
    print("\n=== 配置使用示例 ===")
    
    # 查看默认配置
    print("默认音频配置:")
    audio_config = DEFAULT_CONFIG['audio']
    for key, value in audio_config.items():
        print(f"  {key}: {value}")
    
    print("\n默认摩斯电码配置:")
    morse_config = DEFAULT_CONFIG['morse']
    for key, value in morse_config.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    print("DeltaMorseDecode 使用示例")
    print("=" * 50)
    
    try:
        example_decoder_usage()
        example_audio_processor()
        example_timer_usage()
        example_configuration()
        
        print("\n✅ 所有示例运行完成！")
        
    except Exception as e:
        print(f"❌ 运行示例时出错: {e}")
        sys.exit(1) 