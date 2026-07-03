#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网易云音乐管理器 GUI v3.0
按工作流引导的界面：向导首页 + 编号步骤页 + 目录全局共享记忆
"""

import os
import sys
import json
import subprocess
import threading
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

# 记住上次使用的目录等设置
CONFIG_PATH = Path.home() / ".ncm_manager_gui.json"

# 网易云红，用作强调色
ACCENT = "#C20C0C"
ACCENT_ACTIVE = "#E33030"


class MusicManagerGUI:
    # 脚本所在目录（以本文件为基准），保证从任意目录启动 GUI 都能找到脚本
    SCRIPT_DIR = Path(__file__).resolve().parent

    def __init__(self, root):
        self.root = root
        self.root.title("网易云音乐管理器 v3.0")
        self.root.geometry("980x760")
        self.root.minsize(860, 640)

        self._init_style()

        # 状态
        self.current_process = None
        self.processing = False
        self.start_buttons = []      # 运行中需要禁用的按钮
        self.active_progress = None  # 当前动画中的进度条

        # 全局共享目录（填一次，所有步骤同步；持久化记忆）
        cfg = self._load_config()
        self.var_ncm_dir = tk.StringVar(value=cfg.get("ncm_dir", ""))
        self.var_audio_dir = tk.StringVar(value=cfg.get("audio_dir", ""))
        self.var_img_dir = tk.StringVar(value=cfg.get("img_dir", ""))
        for v in (self.var_ncm_dir, self.var_audio_dir, self.var_img_dir):
            v.trace_add("write", lambda *_: self._save_config())

        self.create_widgets()
        self.check_scripts()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- 样式 ----------------

    def _init_style(self):
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")

        base_font = ("PingFang SC", 12) if sys.platform == "darwin" else ("Segoe UI", 10)
        style.configure(".", font=base_font)
        style.configure("Title.TLabel", font=(base_font[0], 20, "bold"))
        style.configure("Sub.TLabel", foreground="#666")
        style.configure("Step.TLabel", font=(base_font[0], 15, "bold"), foreground=ACCENT)
        style.configure("StepName.TLabel", font=(base_font[0], 13, "bold"))
        style.configure("Hint.TLabel", foreground="#666")
        style.configure("Desc.TLabel", foreground="#444")

        # 主操作按钮：网易云红
        style.configure("Accent.TButton", font=(base_font[0], 12, "bold"),
                        foreground="white", background=ACCENT,
                        padding=(18, 8), borderwidth=0)
        style.map("Accent.TButton",
                  background=[("disabled", "#c9a0a0"), ("active", ACCENT_ACTIVE)],
                  foreground=[("disabled", "#f2eaea")])

        style.configure("Go.TButton", padding=(10, 3))
        style.configure("TNotebook.Tab", padding=(14, 7))
        style.configure("Card.TFrame", background="#fafafa", relief="solid", borderwidth=1)

    # ---------------- 配置持久化 ----------------

    def _load_config(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_config(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "ncm_dir": self.var_ncm_dir.get(),
                    "audio_dir": self.var_audio_dir.get(),
                    "img_dir": self.var_img_dir.get(),
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _on_close(self):
        self._save_config()
        self.stop_process()
        self.root.destroy()

    # ---------------- 依赖检查 ----------------

    def check_scripts(self):
        required = [
            "ncm_utils.py", "filename_parser.py",
            "ncm_universal.py", "fix_flac_tags_from_filename.py",
            "attach_artwork.py", "fetch_album_info.py", "embed_lyrics.py",
        ]
        missing = [s for s in required if not (self.SCRIPT_DIR / s).exists()]
        if missing:
            messagebox.showwarning(
                "缺少脚本文件",
                "以下文件缺失，部分功能不可用：\n" + "\n".join(missing)
                + "\n\n请完整下载/克隆整个项目。")

    # ---------------- 界面骨架 ----------------

    def create_widgets(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(10, 4))

        self.create_guide_tab()          # 🏠 向导
        self.create_decode_tab()         # ① 解码
        self.create_album_info_tab()     # ② 专辑信息(在线)
        self.create_tag_tab()            # ②′ 标签修复(离线)
        self.create_cover_tab()          # ③ 封面
        self.create_lyrics_embed_tab()   # ④ 歌词

        self.status_bar = tk.Label(self.root, text="就绪", anchor="w",
                                   fg="#333", bg="#e8e8e8", padx=10, pady=4)
        self.status_bar.pack(side="bottom", fill="x")

    # ---------- 可复用小部件 ----------

    def _dir_row(self, parent, row, label, var, hint=""):
        """标签 + 输入框 + 浏览按钮 的一行；var 为全局共享变量则自动跨页同步"""
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(2, 8), pady=5)
        entry = ttk.Entry(parent, textvariable=var)
        entry.grid(row=row, column=1, sticky="ew", pady=5)
        ttk.Button(parent, text="浏览…", width=7,
                   command=lambda: self._pick_dir(var)).grid(row=row, column=2, padx=(6, 2))
        if hint:
            ttk.Label(parent, text=hint, style="Hint.TLabel").grid(
                row=row + 1, column=1, sticky="w", pady=(0, 4))
        parent.columnconfigure(1, weight=1)
        return entry

    def _pick_dir(self, var):
        d = filedialog.askdirectory(title="选择目录", initialdir=var.get() or str(Path.home()))
        if d:
            var.set(d)

    def _desc_banner(self, parent, text):
        """页面顶部的功能说明横幅"""
        f = tk.Frame(parent, bg="#fff7f7", highlightbackground="#e5c5c5",
                     highlightthickness=1)
        f.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(f, text=text, justify="left", anchor="w", bg="#fff7f7",
                 fg="#5a3030", padx=12, pady=8).pack(fill="x")

    def _action_area(self, parent, start_text, start_cmd):
        """开始/停止按钮 + 进度条"""
        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=10, pady=6)
        btn = ttk.Button(bar, text=start_text, style="Accent.TButton", command=start_cmd)
        btn.pack(side="left")
        self.start_buttons.append(btn)
        ttk.Button(bar, text="停止", command=self.stop_process).pack(side="left", padx=8)
        prog = ttk.Progressbar(bar, mode="indeterminate", length=220)
        prog.pack(side="left", padx=12)
        return prog

    def _log_area(self, parent):
        frame = ttk.LabelFrame(parent, text="处理日志", padding=6)
        frame.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        log = scrolledtext.ScrolledText(frame, height=12, wrap="word",
                                        font=("Menlo", 11) if sys.platform == "darwin"
                                        else ("Consolas", 10))
        log.pack(fill="both", expand=True)
        # 按内容着色
        log.tag_config("ok", foreground="#2e7d32")
        log.tag_config("err", foreground="#c62828")
        log.tag_config("warn", foreground="#e08000")
        return log

    def _open_dir_button(self, parent, var, text="打开音频目录"):
        ttk.Button(parent, text=text, style="Go.TButton",
                   command=lambda: self._open_in_file_manager(var.get())).pack(
            side="right", padx=8)

    def _open_in_file_manager(self, path):
        if not path or not os.path.isdir(path):
            messagebox.showinfo("提示", "目录尚未设置或不存在")
            return
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", path])
            elif os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开目录: {e}")

    # ---------------- 🏠 向导页 ----------------

    def create_guide_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=" 🏠 使用向导 ")

        ttk.Label(frame, text="网易云音乐管理器", style="Title.TLabel").pack(
            anchor="w", padx=24, pady=(22, 2))
        ttk.Label(frame, text="从 .ncm 加密文件到可导入 Apple Music 的完整工具链",
                  style="Sub.TLabel").pack(anchor="w", padx=24)

        # 全局目录设置（填一次，所有步骤共享）
        dirs = ttk.LabelFrame(frame, text="第一步：设置目录（只需填一次，所有步骤自动共享并记住）",
                              padding=12)
        dirs.pack(fill="x", padx=24, pady=(18, 6))
        self._dir_row(dirs, 0, "NCM 文件目录", self.var_ncm_dir,
                      "网易云下载的 .ncm 文件所在的文件夹")
        self._dir_row(dirs, 2, "音频输出目录", self.var_audio_dir,
                      "解码后的 flac/mp3 存放处，也是后续所有步骤的处理对象")
        self._dir_row(dirs, 4, "封面图片目录", self.var_img_dir,
                      "网易云的 meta 缓存目录（含 track-*.jpg），仅步骤③需要")

        # 推荐流程
        flow = ttk.LabelFrame(frame, text="第二步：按顺序执行（点击「前往」直达对应页面）", padding=12)
        flow.pack(fill="both", expand=True, padx=24, pady=6)

        steps = [
            ("①", "NCM 解码", "把 .ncm 解密成标准 flac/mp3（含自动修复损坏文件）", 1),
            ("②", "专辑信息抓取（在线）", "联网补全 标题/艺人/专辑/日期 标签，并下载 .lrc 歌词文件", 2),
            ("③", "封面嵌入", "把封面图写入音频文件，Apple Music 中显示专辑封面", 4),
            ("④", "歌词嵌入", "把 .lrc 歌词写入音频文件，Apple Music 中显示歌词", 5),
        ]
        for i, (num, name, desc, tab_idx) in enumerate(steps):
            row = ttk.Frame(flow)
            row.pack(fill="x", pady=5)
            ttk.Label(row, text=num, style="Step.TLabel", width=3).pack(side="left")
            box = ttk.Frame(row)
            box.pack(side="left", fill="x", expand=True)
            ttk.Label(box, text=name, style="StepName.TLabel").pack(anchor="w")
            ttk.Label(box, text=desc, style="Desc.TLabel").pack(anchor="w")
            ttk.Button(row, text="前往 ➜", style="Go.TButton",
                       command=lambda t=tab_idx: self.notebook.select(t)).pack(
                side="right", padx=6)

        ttk.Label(frame, style="Hint.TLabel", justify="left", text=(
            "小贴士：无网络时可用「标签修复(离线)」代替步骤②（仅从文件名提取基础标签）；"
            "已有完整标签的文件会自动跳过，重复运行是安全的。"
        )).pack(anchor="w", padx=26, pady=(4, 16))

    # ---------------- ① 解码 ----------------

    def create_decode_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=" ① NCM解码 ")

        self._desc_banner(frame, "把网易云的 .ncm 加密文件解密成标准 flac/mp3。"
                                 "需要：NCM 文件目录 → 输出到：音频目录")

        form = ttk.LabelFrame(frame, text="目录设置（与其他页面共享）", padding=10)
        form.pack(fill="x", padx=10, pady=4)
        self._dir_row(form, 0, "NCM 文件目录", self.var_ncm_dir)
        self._dir_row(form, 1, "音频输出目录", self.var_audio_dir,
                      "留空则输出到 NCM 文件所在目录")

        prog = self._action_area(frame, "▶ 开始解码", self.start_decode)
        self.decode_progress = prog
        self.decode_log = self._log_area(frame)

    def start_decode(self):
        ncm_dir = self.var_ncm_dir.get().strip()
        if not ncm_dir:
            messagebox.showerror("缺少目录", "请先选择「NCM 文件目录」\n（向导页或本页均可设置）")
            return
        args = [ncm_dir]
        out = self.var_audio_dir.get().strip()
        if out:
            args += ["-o", out]
        self._launch("ncm_universal.py", args, self.decode_log, self.decode_progress)

    # ---------------- ② 专辑信息（在线） ----------------

    def create_album_info_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=" ② 专辑信息(在线) ")

        self._desc_banner(frame, "联网从网易云补全 标题/艺人/专辑/发行日期 等标签，"
                                 "并把歌词保存为同名 .lrc 文件（供步骤④嵌入）。"
                                 "已有完整标签的文件自动跳过。")

        form = ttk.LabelFrame(frame, text="目录设置（与其他页面共享）", padding=10)
        form.pack(fill="x", padx=10, pady=4)
        self._dir_row(form, 0, "音频目录", self.var_audio_dir)
        self._dir_row(form, 1, "NCM 目录（可选）", self.var_ncm_dir,
                      "提供后可从 NCM 元数据精确匹配歌曲，无需猜文件名")

        opts = ttk.Frame(frame)
        opts.pack(fill="x", padx=14, pady=2)
        self.album_overwrite = tk.BooleanVar()
        ttk.Checkbutton(opts, text="强制更新已有标签的文件",
                        variable=self.album_overwrite).pack(side="left")
        self.album_fetch_lyrics = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="同时下载歌词（.lrc）",
                        variable=self.album_fetch_lyrics).pack(side="left", padx=16)

        prog = self._action_area(frame, "▶ 开始抓取", self.start_fetch_album_info)
        self.album_progress = prog
        self.album_log = self._log_area(frame)

    def start_fetch_album_info(self):
        audio_dir = self.var_audio_dir.get().strip()
        if not audio_dir:
            messagebox.showerror("缺少目录", "请先选择「音频目录」")
            return
        args = [audio_dir]
        ncm_dir = self.var_ncm_dir.get().strip()
        if ncm_dir:
            args += ["--ncm_dir", ncm_dir]
        if self.album_overwrite.get():
            args.append("--force")
        if not self.album_fetch_lyrics.get():
            args.append("--no-lyrics")
        self._launch("fetch_album_info.py", args, self.album_log, self.album_progress)

    # ---------------- ②′ 标签修复（离线） ----------------

    def create_tag_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=" 标签修复(离线) ")

        self._desc_banner(frame, "无网络时的替代方案：从「艺人 - 歌名」格式的文件名提取基础标签。"
                                 "仅支持 FLAC；只写 艺人/标题/专辑 三项。")

        form = ttk.LabelFrame(frame, text="目录设置（与其他页面共享）", padding=10)
        form.pack(fill="x", padx=10, pady=4)
        self._dir_row(form, 0, "音频目录", self.var_audio_dir)

        opts = ttk.Frame(frame)
        opts.pack(fill="x", padx=14, pady=2)
        self.tag_overwrite = tk.BooleanVar()
        ttk.Checkbutton(opts, text="覆盖已有标签",
                        variable=self.tag_overwrite).pack(side="left")
        self.tag_dryrun = tk.BooleanVar()
        ttk.Checkbutton(opts, text="试运行（只预览不写入）",
                        variable=self.tag_dryrun).pack(side="left", padx=16)
        ttk.Label(opts, text="默认专辑名:").pack(side="left", padx=(16, 4))
        self.tag_album = ttk.Entry(opts, width=16)
        self.tag_album.insert(0, "未知专辑")
        self.tag_album.pack(side="left")
        ttk.Label(opts, text="（清空则不写专辑）", style="Hint.TLabel").pack(side="left", padx=4)

        prog = self._action_area(frame, "▶ 开始修复", self.start_fix_tags)
        self.tag_progress = prog
        self.tag_log = self._log_area(frame)

    def start_fix_tags(self):
        audio_dir = self.var_audio_dir.get().strip()
        if not audio_dir:
            messagebox.showerror("缺少目录", "请先选择「音频目录」")
            return
        args = [audio_dir]
        if self.tag_overwrite.get():
            args.append("--overwrite")
        # 始终传递：空串 = 不写专辑
        args += ["--default-album", self.tag_album.get()]
        if self.tag_dryrun.get():
            args.append("--dry-run")
        self._launch("fix_flac_tags_from_filename.py", args, self.tag_log, self.tag_progress)

    # ---------------- ③ 封面 ----------------

    def create_cover_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=" ③ 封面嵌入 ")

        self._desc_banner(frame, "把网易云 meta 缓存里的封面图（track-*.jpg）写入对应音频文件。"
                                 "需要：音频目录 + 封面图片目录；提供 NCM 目录可精确匹配。")

        form = ttk.LabelFrame(frame, text="目录设置（与其他页面共享）", padding=10)
        form.pack(fill="x", padx=10, pady=4)
        self._dir_row(form, 0, "音频目录", self.var_audio_dir)
        self._dir_row(form, 1, "封面图片目录", self.var_img_dir,
                      "通常在 网易云音乐/meta 下，文件名形如 track-123456.jpg")
        self._dir_row(form, 3, "NCM 目录（可选）", self.var_ncm_dir)

        prog = self._action_area(frame, "▶ 开始嵌入封面", self.start_embed_covers)
        self.cover_progress = prog
        self.cover_log = self._log_area(frame)

    def start_embed_covers(self):
        audio_dir = self.var_audio_dir.get().strip()
        img_dir = self.var_img_dir.get().strip()
        if not audio_dir or not img_dir:
            messagebox.showerror("缺少目录", "本步骤需要「音频目录」和「封面图片目录」")
            return
        args = ["--audios", audio_dir, "--meta_imgs", img_dir]
        ncm_dir = self.var_ncm_dir.get().strip()
        if ncm_dir:
            args += ["--ncm_dir", ncm_dir]
        self._launch("attach_artwork.py", args, self.cover_log, self.cover_progress)

    # ---------------- ④ 歌词 ----------------

    def create_lyrics_embed_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=" ④ 歌词嵌入 ")

        self._desc_banner(frame, "把音频目录中的同名 .lrc 歌词写入音频文件"
                                 "（步骤②会自动生成 .lrc）。嵌入后 Apple Music 可直接显示歌词。")

        form = ttk.LabelFrame(frame, text="目录设置（与其他页面共享）", padding=10)
        form.pack(fill="x", padx=10, pady=4)
        self._dir_row(form, 0, "音频目录", self.var_audio_dir,
                      "音频与 .lrc 需同名，如 歌曲.flac + 歌曲.lrc")

        opts = ttk.Frame(frame)
        opts.pack(fill="x", padx=14, pady=2)
        self.lyrics_overwrite = tk.BooleanVar()
        ttk.Checkbutton(opts, text="覆盖已有歌词",
                        variable=self.lyrics_overwrite).pack(side="left")

        prog = self._action_area(frame, "▶ 开始嵌入歌词", self.start_embed_lyrics)
        self.lyrics_progress = prog
        self.lyrics_log = self._log_area(frame)

    def start_embed_lyrics(self):
        audio_dir = self.var_audio_dir.get().strip()
        if not audio_dir:
            messagebox.showerror("缺少目录", "请先选择「音频目录」")
            return
        args = [audio_dir]
        if self.lyrics_overwrite.get():
            args.append("--overwrite")
        self._launch("embed_lyrics.py", args, self.lyrics_log, self.lyrics_progress)

    # ---------------- 任务执行 ----------------

    def _launch(self, script, args, log_widget, progress):
        """统一入口：校验运行状态 → 清日志 → 启动线程"""
        if self.processing:
            messagebox.showwarning("请稍候", "已有任务正在运行，请等待完成或点击「停止」")
            return
        log_widget.delete("1.0", tk.END)
        self.processing = True
        self._set_running(True, progress)
        t = threading.Thread(target=self.run_script,
                             args=(script, args, log_widget), daemon=True)
        t.start()

    def _set_running(self, running, progress=None):
        def apply():
            for b in self.start_buttons:
                b.configure(state="disabled" if running else "normal")
            if running and progress is not None:
                self.active_progress = progress
                progress.start(12)
            elif not running and self.active_progress is not None:
                self.active_progress.stop()
                self.active_progress = None
        self.root.after(0, apply)

    def log_message(self, log_widget, message):
        def write():
            ts = datetime.now().strftime("%H:%M:%S")
            tag = ()
            if any(k in message for k in ("✅", "成功", "完成:")):
                tag = ("ok",)
            elif any(k in message for k in ("❌", "失败", "Error", "Traceback")):
                tag = ("err",)
            elif "⚠" in message:
                tag = ("warn",)
            log_widget.insert(tk.END, f"[{ts}] {message}\n", tag)
            log_widget.see(tk.END)
        self.root.after(0, write)

    def update_status(self, message, color="#333"):
        def update():
            self.status_bar.config(text=message, fg=color)
        self.root.after(0, update)

    def run_script(self, script_name, args, log_widget):
        try:
            script_path = str(self.SCRIPT_DIR / script_name)
            cmd = [sys.executable, script_path] + args
            self.log_message(log_widget, f"执行命令: {' '.join(cmd)}")
            self.update_status(f"正在运行 {script_name}…", ACCENT)

            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                encoding="utf-8",
                errors="replace",
            )

            for line in iter(self.current_process.stdout.readline, ""):
                if not self.processing:
                    break
                if line:
                    self.log_message(log_widget, line.rstrip())

            self.current_process.wait()

            if self.current_process.returncode == 0:
                self.log_message(log_widget, "✅ 执行成功")
                self.update_status("完成", "#2e7d32")
            else:
                self.log_message(log_widget,
                                 f"❌ 执行失败，返回码: {self.current_process.returncode}")
                self.update_status("执行失败", "#c62828")

        except FileNotFoundError:
            self.log_message(log_widget, f"❌ 找不到脚本文件 {script_name}")
            self.update_status("错误", "#c62828")
        except Exception as e:
            self.log_message(log_widget, f"❌ 错误: {e}")
            self.update_status("错误", "#c62828")
        finally:
            self.current_process = None
            self.processing = False
            self._set_running(False)

    def stop_process(self):
        self.processing = False
        if self.current_process:
            try:
                self.current_process.terminate()
                self.update_status("已停止", "#e08000")
            except Exception:
                pass
        self._set_running(False)


def main():
    try:
        root = tk.Tk()
        MusicManagerGUI(root)
        root.mainloop()
    except Exception as e:
        print(f"启动失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
