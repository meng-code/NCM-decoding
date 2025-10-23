#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网易云音乐管理器 GUI - 增强版
添加歌词嵌入功能
"""

import os
import sys
import subprocess
import threading
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext


class MusicManagerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("网易云音乐管理器 v2.1")
        self.root.geometry("900x700")

        # 设置样式
        style = ttk.Style()
        available_themes = style.theme_names()
        if 'clam' in available_themes:
            style.theme_use('clam')

        # 状态变量
        self.current_process = None
        self.processing = False

        # 创建界面
        self.create_widgets()

        # 检查必要的脚本文件
        self.check_scripts()

    def check_scripts(self):
        """检查必要的脚本文件是否存在"""
        required_scripts = [
            'ncm_universal.py',
            'fix_flac_tags_from_filename.py',
            'attach_artwork.py',
            'fetch_album_info.py',
            'embed_lyrics.py'
        ]

        missing = []
        for script in required_scripts:
            if not Path(script).exists():
                missing.append(script)

        if missing:
            msg = "警告：缺少以下脚本文件:\n" + "\n".join(missing)
            msg += "\n\n某些功能可能无法使用"
            print(msg)

    def create_widgets(self):
        """创建界面组件"""

        # 创建选项卡
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)

        # Tab 1: NCM解码
        self.create_decode_tab(notebook)

        # Tab 2: 标签修复
        self.create_tag_tab(notebook)

        # Tab 3: 封面管理
        self.create_cover_tab(notebook)

        # Tab 4: 专辑信息抓取
        self.create_album_info_tab(notebook)

        # Tab 5: 歌词嵌入
        self.create_lyrics_embed_tab(notebook)

        # 状态栏
        self.status_bar = ttk.Label(self.root, text="就绪", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def create_decode_tab(self, notebook):
        """创建NCM解码选项卡"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="NCM解码")

        # 输入输出设置
        io_frame = ttk.LabelFrame(frame, text="输入/输出设置", padding=10)
        io_frame.pack(fill='x', padx=10, pady=10)

        # 输入目录
        ttk.Label(io_frame, text="输入目录/文件:").grid(row=0, column=0, sticky='w', padx=5, pady=5)
        self.decode_input = ttk.Entry(io_frame, width=50)
        self.decode_input.grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(io_frame, text="选择文件",
                   command=lambda: self.browse_file(self.decode_input, [("NCM文件", "*.ncm")])).grid(row=0, column=2,
                                                                                                     padx=2)
        ttk.Button(io_frame, text="选择目录",
                   command=lambda: self.browse_dir(self.decode_input)).grid(row=0, column=3, padx=2)

        # 输出目录
        ttk.Label(io_frame, text="输出目录:").grid(row=1, column=0, sticky='w', padx=5, pady=5)
        self.decode_output = ttk.Entry(io_frame, width=50)
        self.decode_output.grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(io_frame, text="选择目录",
                   command=lambda: self.browse_dir(self.decode_output)).grid(row=1, column=2, padx=2)

        # 说明
        info_label = ttk.Label(io_frame, text="注意：如果不指定输出目录，将在源文件目录生成解码文件", foreground='gray')
        info_label.grid(row=2, column=0, columnspan=4, pady=5)

        # 操作按钮
        button_frame = ttk.Frame(frame)
        button_frame.pack(pady=10)

        self.decode_btn = ttk.Button(button_frame, text="开始解码", command=self.start_decode, width=20)
        self.decode_btn.pack(side='left', padx=5)

        self.stop_btn = ttk.Button(button_frame, text="停止", command=self.stop_process, width=20)
        self.stop_btn.pack(side='left', padx=5)

        # 日志输出
        log_frame = ttk.LabelFrame(frame, text="处理日志", padding=10)
        log_frame.pack(fill='both', expand=True, padx=10, pady=10)

        self.decode_log = scrolledtext.ScrolledText(log_frame, height=15, wrap=tk.WORD)
        self.decode_log.pack(fill='both', expand=True)

    def create_tag_tab(self, notebook):
        """创建标签修复选项卡"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="标签修复(离线)")

        # 设置
        settings_frame = ttk.LabelFrame(frame, text="离线快速标签修复（仅FLAC）", padding=10)
        settings_frame.pack(fill='x', padx=10, pady=10)

        # 说明
        info_text = '功能说明:\n• 从文件名解析"艺人 - 歌名"格式\n• 仅支持FLAC格式\n• 完全离线操作，速度快\n• 仅写入基础标签（艺人、标题、专辑）\n• 如需完整专辑信息，请使用"专辑信息抓取(在线)"标签页'
        ttk.Label(settings_frame, text=info_text, justify='left', foreground='blue').grid(row=0, column=0,
                                                                                           columnspan=3, pady=5)

        # 音频目录
        ttk.Label(settings_frame, text="音频文件目录:").grid(row=1, column=0, sticky='w', padx=5, pady=5)
        self.tag_dir = ttk.Entry(settings_frame, width=50)
        self.tag_dir.grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(settings_frame, text="选择目录",
                   command=lambda: self.browse_dir(self.tag_dir)).grid(row=1, column=2)

        # 选项
        self.tag_overwrite = tk.BooleanVar()
        ttk.Checkbutton(settings_frame, text="覆盖已有标签",
                        variable=self.tag_overwrite).grid(row=2, column=0, columnspan=2, sticky='w', pady=5)

        ttk.Label(settings_frame, text="默认专辑名:").grid(row=3, column=0, sticky='w', pady=5)
        self.tag_album = ttk.Entry(settings_frame, width=30)
        self.tag_album.insert(0, "未知专辑")
        self.tag_album.grid(row=3, column=1, sticky='w', pady=5)

        self.tag_dryrun = tk.BooleanVar()
        ttk.Checkbutton(settings_frame, text="试运行（只显示不修改）",
                        variable=self.tag_dryrun).grid(row=4, column=0, columnspan=2, sticky='w', pady=5)

        # 操作按钮
        ttk.Button(frame, text="开始修复标签", command=self.start_fix_tags, width=20).pack(pady=10)

        # 日志
        log_frame = ttk.LabelFrame(frame, text="处理日志", padding=10)
        log_frame.pack(fill='both', expand=True, padx=10, pady=10)

        self.tag_log = scrolledtext.ScrolledText(log_frame, height=15, wrap=tk.WORD)
        self.tag_log.pack(fill='both', expand=True)

    def create_cover_tab(self, notebook):
        """创建封面管理选项卡"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="封面嵌入")

        # 设置
        settings_frame = ttk.LabelFrame(frame, text="封面嵌入设置", padding=10)
        settings_frame.pack(fill='x', padx=10, pady=10)

        # 音频目录
        ttk.Label(settings_frame, text="音频文件目录:").grid(row=0, column=0, sticky='w', padx=5, pady=5)
        self.cover_audio_dir = ttk.Entry(settings_frame, width=50)
        self.cover_audio_dir.grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(settings_frame, text="选择",
                   command=lambda: self.browse_dir(self.cover_audio_dir)).grid(row=0, column=2)

        # 封面图片目录
        ttk.Label(settings_frame, text="封面图片目录:").grid(row=1, column=0, sticky='w', padx=5, pady=5)
        self.cover_img_dir = ttk.Entry(settings_frame, width=50)
        self.cover_img_dir.grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(settings_frame, text="选择",
                   command=lambda: self.browse_dir(self.cover_img_dir)).grid(row=1, column=2)

        # NCM目录（可选）
        ttk.Label(settings_frame, text="NCM文件目录(可选):").grid(row=2, column=0, sticky='w', padx=5, pady=5)
        self.cover_ncm_dir = ttk.Entry(settings_frame, width=50)
        self.cover_ncm_dir.grid(row=2, column=1, padx=5, pady=5)
        ttk.Button(settings_frame, text="选择",
                   command=lambda: self.browse_dir(self.cover_ncm_dir)).grid(row=2, column=2)

        # 操作按钮
        ttk.Button(frame, text="开始嵌入封面", command=self.start_embed_covers, width=20).pack(pady=10)

        # 日志
        log_frame = ttk.LabelFrame(frame, text="处理日志", padding=10)
        log_frame.pack(fill='both', expand=True, padx=10, pady=10)

        self.cover_log = scrolledtext.ScrolledText(log_frame, height=15, wrap=tk.WORD)
        self.cover_log.pack(fill='both', expand=True)

    def create_album_info_tab(self, notebook):
        """创建专辑信息抓取选项卡"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="专辑信息抓取(在线)")

        # 设置
        settings_frame = ttk.LabelFrame(frame, text="在线完整专辑信息获取（支持多种格式）", padding=10)
        settings_frame.pack(fill='x', padx=10, pady=10)

        # 说明
        info_text = "功能说明:\n• 从网易云API获取完整的专辑信息（需要网络）\n• 支持格式：FLAC、MP3、M4A、AAC\n• 包括：专辑名、专辑艺术家、发行日期、曲目号、碟片号等\n• 同时获取LRC格式的时间轴歌词（保存为.lrc文件）\n• 优先使用NCM文件的元数据（如果提供），否则通过文件名智能搜索\n• 每个文件间隔0.5秒（避免API限流）"
        ttk.Label(settings_frame, text=info_text, justify='left', foreground='green').grid(row=0, column=0,
                                                                                            columnspan=3, pady=5)

        # 音频目录
        ttk.Label(settings_frame, text="音频文件目录:").grid(row=1, column=0, sticky='w', padx=5, pady=5)
        self.album_audio_dir = ttk.Entry(settings_frame, width=50)
        self.album_audio_dir.grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(settings_frame, text="选择",
                   command=lambda: self.browse_dir(self.album_audio_dir)).grid(row=1, column=2)

        # NCM目录（可选）
        ttk.Label(settings_frame, text="NCM文件目录(可选):").grid(row=2, column=0, sticky='w', padx=5, pady=5)
        self.album_ncm_dir = ttk.Entry(settings_frame, width=50)
        self.album_ncm_dir.grid(row=2, column=1, padx=5, pady=5)
        ttk.Button(settings_frame, text="选择",
                   command=lambda: self.browse_dir(self.album_ncm_dir)).grid(row=2, column=2)

        # 选项
        self.album_overwrite = tk.BooleanVar()
        ttk.Checkbutton(settings_frame, text="强制更新已有标签的文件",
                        variable=self.album_overwrite).grid(row=3, column=0, columnspan=2, sticky='w', pady=5)

        self.album_fetch_lyrics = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings_frame, text="同时获取并保存歌词文件（.lrc）",
                        variable=self.album_fetch_lyrics).grid(row=4, column=0, columnspan=2, sticky='w', pady=5)

        # 操作按钮
        ttk.Button(frame, text="开始抓取专辑信息", command=self.start_fetch_album_info, width=20).pack(pady=10)

        # 日志
        log_frame = ttk.LabelFrame(frame, text="处理日志", padding=10)
        log_frame.pack(fill='both', expand=True, padx=10, pady=10)

        self.album_log = scrolledtext.ScrolledText(log_frame, height=15, wrap=tk.WORD)
        self.album_log.pack(fill='both', expand=True)

    def create_lyrics_embed_tab(self, notebook):
        """创建歌词嵌入选项卡（新增）"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="歌词嵌入")

        # 设置
        settings_frame = ttk.LabelFrame(frame, text="歌词嵌入设置", padding=10)
        settings_frame.pack(fill='x', padx=10, pady=10)

        # 音频目录
        ttk.Label(settings_frame, text="音频文件目录:").grid(row=0, column=0, sticky='w', padx=5, pady=5)
        self.lyrics_audio_dir = ttk.Entry(settings_frame, width=50)
        self.lyrics_audio_dir.grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(settings_frame, text="选择",
                   command=lambda: self.browse_dir(self.lyrics_audio_dir)).grid(row=0, column=2)

        # 选项
        self.lyrics_overwrite = tk.BooleanVar()
        ttk.Checkbutton(settings_frame, text="覆盖已有的歌词",
                        variable=self.lyrics_overwrite).grid(row=1, column=0, columnspan=2, sticky='w', pady=5)

        # 说明
        info_text = "歌词嵌入功能说明:\n• 将目录中的 .lrc 歌词文件嵌入到对应的音频文件\n• 支持 FLAC/MP3/M4A 格式\n• 音频文件和歌词文件必须同名（如：歌曲.m4a 和 歌曲.lrc）\n• 嵌入后可在 Apple Music 中直接显示滚动歌词\n• 建议先运行 专辑信息抓取 生成 .lrc 文件"
        ttk.Label(settings_frame, text=info_text, justify='left', foreground='blue').grid(row=2, column=0,
                                                                                           columnspan=3, pady=10)

        # 操作按钮
        ttk.Button(frame, text="开始嵌入歌词", command=self.start_embed_lyrics, width=20).pack(pady=10)

        # 日志
        log_frame = ttk.LabelFrame(frame, text="处理日志", padding=10)
        log_frame.pack(fill='both', expand=True, padx=10, pady=10)

        self.lyrics_log = scrolledtext.ScrolledText(log_frame, height=15, wrap=tk.WORD)
        self.lyrics_log.pack(fill='both', expand=True)

    def browse_file(self, entry_widget, filetypes=None):
        """选择文件"""
        if filetypes is None:
            filetypes = [("所有文件", "*.*")]

        filename = filedialog.askopenfilename(
            title="选择文件",
            filetypes=filetypes
        )
        if filename:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, filename)

    def browse_dir(self, entry_widget):
        """选择目录"""
        dirname = filedialog.askdirectory(title="选择目录")
        if dirname:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, dirname)

    def log_message(self, log_widget, message):
        """写入日志"""

        def write():
            timestamp = datetime.now().strftime('%H:%M:%S')
            log_widget.insert(tk.END, f"[{timestamp}] {message}\n")
            log_widget.see(tk.END)

        self.root.after(0, write)

    def update_status(self, message):
        """更新状态栏"""

        def update():
            self.status_bar['text'] = message

        self.root.after(0, update)

    def run_script(self, script_name, args, log_widget):
        """运行外部Python脚本"""
        try:
            cmd = [sys.executable, script_name] + args

            self.log_message(log_widget, f"执行命令: {' '.join(cmd)}")
            self.update_status(f"正在运行 {script_name}...")

            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            for line in iter(self.current_process.stdout.readline, ''):
                if not self.processing:
                    break
                if line:
                    self.log_message(log_widget, line.strip())

            self.current_process.wait()

            if self.current_process.returncode == 0:
                self.log_message(log_widget, "✅ 执行成功")
                self.update_status("完成")
            else:
                self.log_message(log_widget, f"❌ 执行失败，返回码: {self.current_process.returncode}")
                self.update_status("执行失败")

        except FileNotFoundError:
            self.log_message(log_widget, f"❌ 错误: 找不到脚本文件 {script_name}")
            self.update_status("错误")
        except Exception as e:
            self.log_message(log_widget, f"❌ 错误: {e}")
            self.update_status("错误")
        finally:
            self.current_process = None
            self.processing = False

    def stop_process(self):
        """停止当前进程"""
        self.processing = False
        if self.current_process:
            try:
                self.current_process.terminate()
                self.update_status("已停止")
            except:
                pass

    def start_decode(self):
        """开始NCM解码"""
        if self.processing:
            messagebox.showwarning("警告", "正在处理中，请稍候")
            return

        input_path = self.decode_input.get()
        if not input_path:
            messagebox.showerror("错误", "请选择输入文件或目录")
            return

        args = [input_path]

        output_path = self.decode_output.get()
        if output_path:
            args.extend(['-o', output_path])

        self.decode_log.delete(1.0, tk.END)

        self.processing = True
        thread = threading.Thread(
            target=self.run_script,
            args=('ncm_universal.py', args, self.decode_log)
        )
        thread.daemon = True
        thread.start()

    def start_fix_tags(self):
        """开始修复标签"""
        if self.processing:
            messagebox.showwarning("警告", "正在处理中，请稍候")
            return

        music_dir = self.tag_dir.get()
        if not music_dir:
            messagebox.showerror("错误", "请选择音频文件目录")
            return

        args = [music_dir]

        if self.tag_overwrite.get():
            args.append('--overwrite')

        album = self.tag_album.get()
        if album:
            args.extend(['--default-album', album])

        if self.tag_dryrun.get():
            args.append('--dry-run')

        self.tag_log.delete(1.0, tk.END)

        self.processing = True
        thread = threading.Thread(
            target=self.run_script,
            args=('fix_flac_tags_from_filename.py', args, self.tag_log)
        )
        thread.daemon = True
        thread.start()

    def start_embed_covers(self):
        """开始嵌入封面"""
        if self.processing:
            messagebox.showwarning("警告", "正在处理中，请稍候")
            return

        audio_dir = self.cover_audio_dir.get()
        img_dir = self.cover_img_dir.get()

        if not audio_dir or not img_dir:
            messagebox.showerror("错误", "请设置音频文件目录和封面图片目录")
            return

        args = ['--audios', audio_dir, '--meta_imgs', img_dir]

        ncm_dir = self.cover_ncm_dir.get()
        if ncm_dir:
            args.extend(['--ncm_dir', ncm_dir])

        self.cover_log.delete(1.0, tk.END)

        self.processing = True
        thread = threading.Thread(
            target=self.run_script,
            args=('attach_artwork.py', args, self.cover_log)
        )
        thread.daemon = True
        thread.start()

    def start_fetch_album_info(self):
        """开始抓取专辑信息"""
        if self.processing:
            messagebox.showwarning("警告", "正在处理中，请稍候")
            return

        audio_dir = self.album_audio_dir.get()
        if not audio_dir:
            messagebox.showerror("错误", "请选择音频文件目录")
            return

        args = [audio_dir]

        ncm_dir = self.album_ncm_dir.get()
        if ncm_dir:
            args.extend(['--ncm_dir', ncm_dir])

        if self.album_overwrite.get():
            args.append('--overwrite')

        self.album_log.delete(1.0, tk.END)

        self.processing = True
        thread = threading.Thread(
            target=self.run_script,
            args=('fetch_album_info.py', args, self.album_log)
        )
        thread.daemon = True
        thread.start()

    def start_embed_lyrics(self):
        """开始嵌入歌词（新增）"""
        if self.processing:
            messagebox.showwarning("警告", "正在处理中，请稍候")
            return

        audio_dir = self.lyrics_audio_dir.get()
        if not audio_dir:
            messagebox.showerror("错误", "请选择音频文件目录")
            return

        args = [audio_dir]

        if self.lyrics_overwrite.get():
            args.append('--overwrite')

        self.lyrics_log.delete(1.0, tk.END)

        self.processing = True
        thread = threading.Thread(
            target=self.run_script,
            args=('embed_lyrics.py', args, self.lyrics_log)
        )
        thread.daemon = True
        thread.start()


def main():
    """主函数"""
    try:
        root = tk.Tk()
        app = MusicManagerGUI(root)
        root.mainloop()

    except Exception as e:
        print(f"启动失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()