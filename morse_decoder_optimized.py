import time
import numpy as np
import soundfile as sf
from scipy import signal
from win_capture_audio import AudioCapture, AudioStream, find_process_by_name
import threading
import queue
from collections import deque
import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.layout import Layout
from rich.text import Text
from rich.align import Align
from rich.progress import Progress, SpinnerColumn, TextColumn
from datetime import datetime
import msvcrt  # Windows平台的键盘输入
import itertools  # 用于生成排列组合

class MorseCodeDecoderGUI:
    def __init__(self):
        # 初始化Rich控制台
        self.console = Console()
        
        # 数字摩斯电码字典（仅保留数字）
        self.morse_dict = {
            '-----': '0', '.----': '1', '..---': '2',
            '...--': '3', '....-': '4', '.....': '5', 
            '-....': '6', '--...': '7', '---..': '8', 
            '----.': '9'
        }
        
        # 解码参数
        self.threshold = 0.003
        self.dot_duration = 0.02
        self.dash_duration = 0.05
        self.letter_gap = 0.8
        self.word_gap = 0.4
        
        # 数字序列相关参数
        self.current_number_sequence = ""
        self.expected_digits = [3, 4]  # 三角洲游戏中的数字是3位或4位
        self.number_sequences = []  # 存储完整的数字序列
        self.last_digit_time = 0
        
        # 密码排列分析
        self.password_candidates = []  # 存储可能的密码排列
        self.show_permutations = True  # 是否显示排列组合
        
        # 状态管理
        self.is_signal_on = False
        self.signal_start_time = 0
        self.last_signal_time = 0
        self.current_code = ""
        self.decoded_text = ""
        self.running = True
        self.signal_history = deque(maxlen=10)  # 存储最近的信号
        
        # 滤波器参数
        self.sample_rate = 44100
        self.lowcut = 4150.0
        self.highcut = 4300.0
        
        # 创建带通滤波器
        self.b, self.a = self.create_bandpass_filter()
        
        # 音频缓冲区和处理
        self.audio_buffer = deque(maxlen=1024)
        self.energy_history = deque(maxlen=50)
        
        # 统计信息
        self.total_signals = 0
        self.total_letters = 0
        self.start_time = time.time()
        
        # 创建布局
        self.layout = Layout()
        self.setup_layout()

    def create_bandpass_filter(self):
        """创建带通滤波器"""
        nyquist = 0.5 * self.sample_rate
        low = self.lowcut / nyquist
        high = self.highcut / nyquist
        
        # 确保频率范围有效
        low = max(0.01, min(low, 0.99))  # 限制在有效范围内
        high = max(low + 0.01, min(high, 0.99))  # 确保high > low
        
        try:
            b, a = signal.butter(5, [low, high], btype='band', output='ba')
            return b, a
        except Exception as e:
            # 如果滤波器创建失败，使用更保守的参数
            print(f"滤波器创建失败，使用默认参数: {e}")
            b, a = signal.butter(3, [0.1, 0.4], btype='band', output='ba')
            return b, a

    def apply_bandpass_filter(self, data):
        """应用带通滤波器"""
        return signal.lfilter(self.b, self.a, data)

    def calculate_energy(self, data):
        """计算音频数据的能量"""
        return np.sqrt(np.mean(data**2))

    def setup_layout(self):
        """设置界面布局"""
        self.layout.split_column(
            Layout(name="header", size=4),
            Layout(name="main"),
            Layout(name="footer", size=6)
        )
        
        self.layout["main"].split_row(
            Layout(name="left", ratio=2),
            Layout(name="right", ratio=3)
        )

    def create_header(self):
        """创建头部显示"""
        title = "🎮 三角洲行动摩斯电码数字解码器 v1.0"
        runtime = f"运行时间: {self.get_runtime()}"
        
        header_content = f"[bold cyan]{title}[/bold cyan]\n[dim]{runtime}[/dim]"
        
        return Panel(
            Align.center(header_content),
            style="bright_blue",
            height=4,
            padding=(0, 1)
        )

    def create_status_panel(self):
        """创建状态面板"""
        table = Table(show_header=False, box=None)
        table.add_column("参数", style="cyan")
        table.add_column("值", style="green")
        
        table.add_row("🎯 阈值", f"{self.threshold:.6f}")
        table.add_row("⏱️ 点持续时间", f"{self.dot_duration:.3f}s")
        table.add_row("⏱️ 划持续时间", f"{self.dash_duration:.3f}s")
        table.add_row("📏 字母间隔", f"{self.letter_gap:.3f}s")
        table.add_row("📏 单词间隔", f"{self.word_gap:.3f}s")
        table.add_row("🔊 频率范围", f"{self.lowcut:.0f}-{self.highcut:.0f}Hz")
        
        # 添加分隔线
        table.add_row("", "")
        table.add_row("📊 总信号数", str(self.total_signals))
        table.add_row("� 总数字数", str(self.total_letters))
        table.add_row("📋 完整序列数", str(len(self.number_sequences)))
        
        if self.energy_history:
            current_energy = self.energy_history[-1] if self.energy_history else 0
            table.add_row("⚡ 当前能量", f"{current_energy:.6f}")
        
        return Panel(table, title="[bold cyan]系统状态[/bold cyan]", border_style="cyan")

    def create_decoding_panel(self):
        """创建解码面板"""
        # 当前摩斯码
        current_morse = Text(self.current_code if self.current_code else "等待信号...", style="yellow bold")
        
        # 当前数字序列
        current_sequence = Text(self.current_number_sequence if self.current_number_sequence else "无", style="blue bold")
        
        # 完整的数字序列
        sequences_text = ""
        if self.number_sequences:
            for i, seq in enumerate(self.number_sequences[-3:]):  # 显示最近3个序列
                forced = " (强制)" if seq.get('forced', False) else ""
                sequences_text += f"{seq['sequence']} ({seq['length']}位{forced}) "
                if i < 2:  # 除了最后一个，都加换行
                    sequences_text += "\n"
        else:
            sequences_text = "暂无完整序列"
        
        # 密码候选分析
        password_candidates_text = ""
        if self.show_permutations and self.number_sequences:
            candidates = self.analyze_recent_sequences()
            if candidates:
                password_candidates_text = "\n[bold magenta]🔍 可能的密码组合 (按置信度排序):[/bold magenta]\n"
                
                # 按原始序列分组显示
                current_original = None
                for i, candidate in enumerate(candidates[:8]):  # 显示前8个
                    if candidate['original'] != current_original:
                        current_original = candidate['original']
                        password_candidates_text += f"\n[dim]原序列 {current_original}:[/dim] "
                    
                    confidence = candidate['confidence']
                    color = "green" if confidence >= 80 else "yellow" if confidence >= 60 else "red"
                    password_candidates_text += f"[{color}]{candidate['password']}({confidence}%)[/{color}] "
            else:
                password_candidates_text = "\n[dim]等待更多数据进行分析...[/dim]"
        
        # 最近信号历史
        signal_text = ""
        for i, (signal_type, timestamp) in enumerate(self.signal_history):
            signal_text += f"{signal_type} "
            if i % 15 == 14:  # 每15个信号换行
                signal_text += "\n"
        
        content = f"""[bold yellow]当前摩斯码:[/bold yellow]
{current_morse}

[bold blue]当前数字序列:[/bold blue]
{current_sequence} ({len(self.current_number_sequence)}位)

[bold green]最近完整序列:[/bold green]
{sequences_text}{password_candidates_text}

[bold cyan]最近信号:[/bold cyan]
{signal_text}"""
        
        return Panel(content, title="[bold green]数字解码状态[/bold green]", border_style="green")

    def create_footer(self):
        """创建底部信息"""
        help_text = """[dim]按键控制:[/dim]
[cyan]ESC[/cyan] - 退出程序  [cyan]r[/cyan] - 重置文本  [cyan]s[/cyan] - 保存结果  [cyan]p[/cyan] - 切换排列显示
[cyan]↑[/cyan] - 增加阈值  [cyan]↓[/cyan] - 减少阈值  [cyan]1-9[/cyan] - 快速设置阈值
[yellow]💡 如果密码顺序错误，查看"可能的密码组合"部分[/yellow]"""
        
        return Panel(help_text, style="dim", height=6)

    def get_runtime(self):
        """获取运行时间"""
        runtime = time.time() - self.start_time
        hours = int(runtime // 3600)
        minutes = int((runtime % 3600) // 60)
        seconds = int(runtime % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def render_interface(self):
        """渲染界面"""
        self.layout["header"].update(self.create_header())
        self.layout["left"].update(self.create_status_panel())
        self.layout["right"].update(self.create_decoding_panel())
        self.layout["footer"].update(self.create_footer())
        return self.layout

    def process_audio_chunk(self, audio_data):
        """处理音频块并检测摩斯电码"""
        # 应用带通滤波器
        if audio_data.ndim == 2:
            audio_data = np.mean(audio_data, axis=1)
        
        filtered_data = self.apply_bandpass_filter(audio_data)
        energy = self.calculate_energy(filtered_data)
        self.energy_history.append(energy)
        
        current_time = time.time()
        
        # 检测信号状态
        if energy > self.threshold:
            if not self.is_signal_on:
                self.is_signal_on = True
                self.signal_start_time = current_time
        else:
            if self.is_signal_on:
                self.is_signal_on = False
                signal_duration = current_time - self.signal_start_time
                self.process_signal_duration(signal_duration)
                self.last_signal_time = current_time
                self.total_signals += 1
        
        # 检查间隔时间
        if not self.is_signal_on and self.last_signal_time > 0:
            silence_duration = current_time - self.last_signal_time
            self.process_silence_duration(silence_duration)

    def process_signal_duration(self, duration):
        """根据信号持续时间判断是点还是划"""
        if duration < self.dot_duration:
            return
        elif duration < self.dash_duration:
            self.current_code += "."
            self.signal_history.append((".", time.time()))
        else:
            self.current_code += "-"
            self.signal_history.append(("-", time.time()))

    def process_silence_duration(self, duration):
        """根据静默持续时间判断数字间隔或序列结束"""
        if duration > self.word_gap:
            # 长间隔：可能是序列结束
            if self.current_code:
                self.decode_current_code()
            
            # 如果当前序列不为空且超过一定时间，强制完成序列
            if self.current_number_sequence and len(self.current_number_sequence) >= 3:
                self.force_complete_sequence()
                
        elif duration > self.letter_gap:
            # 数字间隔
            if self.current_code:
                self.decode_current_code()
    
    def force_complete_sequence(self):
        """强制完成当前数字序列"""
        if self.current_number_sequence:
            sequence_info = {
                'sequence': self.current_number_sequence,
                'length': len(self.current_number_sequence),
                'timestamp': datetime.now().strftime('%H:%M:%S'),
                'complete_time': time.time(),
                'forced': True  # 标记为强制完成
            }
            self.number_sequences.append(sequence_info)
            self.current_number_sequence = ""

    def decode_current_code(self):
        """解码当前的摩斯电码"""
        if self.current_code in self.morse_dict:
            digit = self.morse_dict[self.current_code]
            self.current_number_sequence += digit
            self.last_digit_time = time.time()
            self.total_letters += 1
            
            # 检查是否完成了一个有效的数字序列
            self.check_complete_sequence()
        
        self.current_code = ""
    
    def check_complete_sequence(self):
        """检查是否完成了一个完整的数字序列"""
        seq_length = len(self.current_number_sequence)
        
        # 如果达到预期长度（3位或4位），保存序列
        if seq_length in self.expected_digits:
            sequence_info = {
                'sequence': self.current_number_sequence,
                'length': seq_length,
                'timestamp': datetime.now().strftime('%H:%M:%S'),
                'complete_time': time.time()
            }
            self.number_sequences.append(sequence_info)
            
            # 重置当前序列
            self.current_number_sequence = ""
        elif seq_length > max(self.expected_digits):
            # 如果超过最大预期长度，重置序列
            self.current_number_sequence = ""

    def audio_callback(self, audio_data, frames):
        """音频回调函数"""
        self.process_audio_chunk(audio_data)

    def save_result(self):
        """保存解码结果"""
        if self.number_sequences:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"morse_numbers_{timestamp}.txt"
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(f"三角洲摩斯电码数字解码结果\n")
                    f.write(f"解码时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"运行时长: {self.get_runtime()}\n")
                    f.write(f"总信号数: {self.total_signals}\n")
                    f.write(f"总数字数: {self.total_letters}\n")
                    f.write(f"完整序列数: {len(self.number_sequences)}\n")
                    f.write(f"当前序列: {self.current_number_sequence}\n\n")
                    
                    f.write("完整数字序列:\n")
                    f.write("-" * 50 + "\n")
                    for i, seq in enumerate(self.number_sequences, 1):
                        forced = " (强制完成)" if seq.get('forced', False) else ""
                        f.write(f"{i:3d}. {seq['sequence']} ({seq['length']}位) - {seq['timestamp']}{forced}\n")
                    
                    # 添加密码候选分析
                    f.write("\n" + "="*50 + "\n")
                    f.write("密码候选分析 (容错排列)\n")
                    f.write("="*50 + "\n\n")
                    
                    candidates = self.analyze_recent_sequences(max_sequences=5)
                    if candidates:
                        current_original = None
                        for candidate in candidates:
                            if candidate['original'] != current_original:
                                current_original = candidate['original']
                                f.write(f"\n原始序列: {current_original}\n")
                                f.write("-" * 30 + "\n")
                            
                            confidence_desc = "高" if candidate['confidence'] >= 80 else "中" if candidate['confidence'] >= 60 else "低"
                            f.write(f"  密码: {candidate['password']} (置信度: {candidate['confidence']}% - {confidence_desc})\n")
                    else:
                        f.write("暂无足够数据进行密码候选分析\n")
                    
                    f.write(f"\n注意: 如果密码顺序不对，请尝试上述候选密码\n")
                    f.write(f"置信度说明: 高(≥80%) > 中(≥60%) > 低(<60%)\n")
                
                self.console.print(f"[green]结果已保存到: {filename}[/green]")
            except Exception as e:
                self.console.print(f"[red]保存失败: {e}[/red]")

    def reset_text(self):
        """重置解码数据"""
        self.current_number_sequence = ""
        self.current_code = ""
        self.total_letters = 0
        self.number_sequences.clear()
        self.signal_history.clear()
        self.password_candidates.clear()

    def handle_keyboard_events(self):
        """处理键盘事件"""
        while self.running:
            try:
                if msvcrt.kbhit():
                    key = msvcrt.getch()
                    
                    # 处理特殊键（箭头键等）
                    if key == b'\xe0':  # 特殊键前缀
                        key = msvcrt.getch()
                        if key == b'H':  # 上箭头
                            self.adjust_threshold(0.001)
                        elif key == b'P':  # 下箭头
                            self.adjust_threshold(-0.001)
                    else:
                        # 处理普通键
                        try:
                            key_char = key.decode('utf-8').lower()
                            if key_char == '\x1b':  # ESC键
                                self.running = False
                                break
                            elif key_char == 'r':
                                self.reset_text()
                            elif key_char == 's':
                                self.save_result()
                            elif key_char == 'p':
                                self.show_permutations = not self.show_permutations
                            elif key_char.isdigit() and key_char != '0':
                                # 数字键1-9快速设置阈值
                                quick_threshold = int(key_char) * 0.001
                                self.threshold = quick_threshold
                        except UnicodeDecodeError:
                            continue
                            
                time.sleep(0.1)
            except Exception:
                continue
    
    def adjust_threshold(self, delta):
        """调节阈值"""
        new_threshold = self.threshold + delta
        if new_threshold > 0:
            self.threshold = new_threshold

    def generate_password_permutations(self, password):
        """生成密码的所有可能排列"""
        if len(password) < 3 or len(password) > 4:
            return []
        
        # 生成所有排列
        all_perms = list(itertools.permutations(password))
        # 转换为字符串列表
        perm_strings = [''.join(perm) for perm in all_perms]
        # 去重并排序
        unique_perms = sorted(list(set(perm_strings)))
        
        return unique_perms

    def analyze_recent_sequences(self, max_sequences=3):
        """分析最近的数字序列，生成可能的密码组合"""
        if len(self.number_sequences) == 0:
            return []
        
        recent_sequences = self.number_sequences[-max_sequences:]
        all_candidates = []
        
        for seq_info in recent_sequences:
            sequence = seq_info['sequence']
            timestamp = seq_info['timestamp']
            
            # 生成该序列的所有排列
            permutations = self.generate_password_permutations(sequence)
            
            # 为每个排列添加分析信息
            for perm in permutations:
                candidate = {
                    'password': perm,
                    'original': sequence,
                    'timestamp': timestamp,
                    'confidence': self.calculate_confidence(perm, sequence),
                    'length': len(perm)
                }
                all_candidates.append(candidate)
        
        # 按置信度排序
        all_candidates.sort(key=lambda x: x['confidence'], reverse=True)
        
        return all_candidates[:12]  # 返回最多12个候选

    def calculate_confidence(self, permutation, original):
        """计算密码排列的置信度"""
        confidence = 50  # 基础置信度
        
        # 如果排列与原序列相同，置信度最高
        if permutation == original:
            confidence = 95
        
        # 检查常见密码模式
        # 顺序递增模式 (如123, 1234)
        if self.is_sequential_ascending(permutation):
            confidence += 20
        
        # 顺序递减模式 (如321, 4321)
        elif self.is_sequential_descending(permutation):
            confidence += 15
        
        # 重复数字较少的排列置信度更高
        unique_digits = len(set(permutation))
        if unique_digits == len(permutation):  # 所有数字都不重复
            confidence += 10
        elif unique_digits == len(permutation) - 1:  # 只有一个重复
            confidence += 5
        
        # 避免过多连续相同数字
        max_consecutive = self.get_max_consecutive_digits(permutation)
        if max_consecutive > 2:
            confidence -= 10 * (max_consecutive - 2)
        
        return min(max(confidence, 0), 100)  # 限制在0-100之间

    def is_sequential_ascending(self, sequence):
        """检查是否为递增序列"""
        for i in range(len(sequence) - 1):
            if int(sequence[i]) >= int(sequence[i + 1]):
                return False
        return True

    def is_sequential_descending(self, sequence):
        """检查是否为递减序列"""
        for i in range(len(sequence) - 1):
            if int(sequence[i]) <= int(sequence[i + 1]):
                return False
        return True

    def get_max_consecutive_digits(self, sequence):
        """获取最大连续相同数字的长度"""
        if len(sequence) <= 1:
            return len(sequence)
        
        max_count = 1
        current_count = 1
        
        for i in range(1, len(sequence)):
            if sequence[i] == sequence[i-1]:
                current_count += 1
                max_count = max(max_count, current_count)
            else:
                current_count = 1
        
        return max_count

def find_delta_force_process():
    """查找三角洲相关进程"""
    possible_process_names = [
        "DeltaForceClient-Win64-Shipping.exe",
    ]
    
    console = Console()
    
    for process_name in possible_process_names:
        try:
            pid = find_process_by_name(process_name)
            if pid is not None:
                console.print(f"[green]✅ 找到进程: {process_name}，PID: {pid}[/green]")
                return pid, process_name
        except Exception as e:
            console.print(f"[yellow]查找进程 {process_name} 时出错: {e}[/yellow]")
            continue
    
    # 如果没有找到，列出建议
    console.print("[yellow]💡 未找到三角洲行动进程，请确保游戏正在运行[/yellow]")
    console.print("[dim]支持的进程名称：[/dim]")
    for name in possible_process_names:
        console.print(f"[dim]  - {name}[/dim]")
    
    return None, None

def main():
    console = Console()
    
    try:
        # 显示启动信息
        console.print(Panel.fit(
            "[bold cyan]🎮 三角洲行动摩斯电码数字解码器 v1.0[/bold cyan]\n"
            "[dim]专门用于解码3位或4位数字序列[/dim]\n"
            "[yellow]正在搜索游戏进程...[/yellow]",
            border_style="cyan"
        ))
        
        # 查找进程
        pid, process_name = find_delta_force_process()
        if pid is None:
            console.print("[red]❌ 无法找到游戏进程，请确保游戏正在运行后重试[/red]")
            input("按回车键退出...")
            return
        
        # 创建摩斯电码解码器
        decoder = MorseCodeDecoderGUI()
        
        # 启动键盘监听线程
        keyboard_thread = threading.Thread(target=decoder.handle_keyboard_events, daemon=True)
        keyboard_thread.start()

        # 创建音频捕获
        try:
            with AudioCapture() as capture:
                if not capture.start_capture(pid, sample_rate=decoder.sample_rate, channels=2):
                    console.print("[red]❌ 无法启动音频捕获，请检查进程权限[/red]")
                    input("按回车键退出...")
                    return

                console.print("[green]🎵 音频捕获已启动，开始监听摩斯电码...[/green]")
                console.print("[cyan]💡 使用↑↓键调节阈值，1-9键快速设置阈值[/cyan]")
                time.sleep(2)  # 给用户时间看到消息

                stream = AudioStream(capture, callback=decoder.audio_callback)
                stream.start()

                try:
                    with Live(decoder.render_interface(), refresh_per_second=10, screen=True) as live:
                        while decoder.running:
                            live.update(decoder.render_interface())
                            time.sleep(0.1)
                except KeyboardInterrupt:
                    pass
                finally:
                    decoder.running = False
                    stream.stop()
                    console.print("\n[cyan]🛑 程序已停止[/cyan]")
                    if decoder.number_sequences:
                        console.print(f"[green]📝 共解码 {len(decoder.number_sequences)} 个完整数字序列[/green]")
                        # 显示最后几个序列
                        console.print("[cyan]最近的序列：[/cyan]")
                        for seq in decoder.number_sequences[-3:]:
                            forced = " (强制完成)" if seq.get('forced', False) else ""
                            console.print(f"  🔢 {seq['sequence']} ({seq['length']}位){forced}")
                        
                        # 显示密码候选分析
                        candidates = decoder.analyze_recent_sequences()
                        if candidates:
                            console.print(f"\n[magenta]🔍 可能的正确密码组合：[/magenta]")
                            current_original = None
                            for candidate in candidates[:6]:  # 显示前6个最佳候选
                                if candidate['original'] != current_original:
                                    current_original = candidate['original']
                                    console.print(f"\n[dim]基于序列 {current_original}:[/dim]")
                                
                                confidence = candidate['confidence']
                                if confidence >= 80:
                                    console.print(f"  🟢 {candidate['password']} (置信度: {confidence}% - 推荐)")
                                elif confidence >= 60:
                                    console.print(f"  🟡 {candidate['password']} (置信度: {confidence}% - 可能)")
                                else:
                                    console.print(f"  🔴 {candidate['password']} (置信度: {confidence}% - 备选)")
                    else:
                        console.print("[yellow]📝 未解码到完整的数字序列[/yellow]")
        
        except Exception as e:
            console.print(f"[red]❌ 音频捕获错误: {e}[/red]")
            console.print("[yellow]请确保以管理员身份运行程序[/yellow]")
            input("按回车键退出...")
            
    except ImportError as e:
        console.print(f"[red]❌ 导入错误: {e}[/red]")
        console.print("[yellow]请确保所有依赖库已正确安装[/yellow]")
        input("按回车键退出...")
    except Exception as e:
        console.print(f"[red]❌ 程序错误: {e}[/red]")
        input("按回车键退出...")

if __name__ == "__main__":
    main()
