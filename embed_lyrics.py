#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
歌词嵌入工具 - 将 .lrc 文件嵌入到音频文件
支持 FLAC/MP3/M4A 格式
"""

import os
import sys
import re
import logging
from pathlib import Path
from glob import glob
from tqdm import tqdm

from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, USLT
from mutagen.mp4 import MP4

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("embed_lyrics")


def clean_lrc_format(lrc_content: str, keep_timestamps: bool = False) -> str:
    """
    清理 LRC 格式

    Args:
        lrc_content: LRC 文件内容
        keep_timestamps: 是否保留时间轴（Apple Music 需要去除）

    Returns:
        清理后的歌词文本
    """
    lines = []

    for line in lrc_content.split('\n'):
        line = line.strip()

        # 跳过空行
        if not line:
            continue

        # 跳过元数据标签 [ar:], [ti:], [al:] 等
        if line.startswith('[') and ':' in line[:10] and not line[1:3].replace(':', '').isdigit():
            continue

        if keep_timestamps:
            # 保留时间轴（用于其他播放器）
            lines.append(line)
        else:
            # 移除时间轴标签 [mm:ss.xx] 或 [mm:ss]
            # 匹配模式：[00:00.00] 或 [00:00]
            cleaned = re.sub(r'\[\d{2}:\d{2}(?:\.\d{2,3})?\]', '', line).strip()

            if cleaned:  # 只保留有内容的行
                lines.append(cleaned)

    return '\n'.join(lines)


def embed_lyrics_to_file(audio_path: str, lyrics_content: str, keep_timestamps: bool = False) -> bool:
    """
    将歌词嵌入到音频文件
    支持 FLAC/MP3/M4A 格式

    Args:
        audio_path: 音频文件路径
        lyrics_content: 歌词内容
        keep_timestamps: 是否保留时间轴（默认 False，Apple Music 需要纯文本）
    """
    ext = os.path.splitext(audio_path)[1].lower()

    # 清理 LRC 格式（去除时间标签）
    cleaned_lyrics = clean_lrc_format(lyrics_content, keep_timestamps=keep_timestamps)

    if not cleaned_lyrics:
        log.warning(f"歌词为空: {os.path.basename(audio_path)}")
        return False

    try:
        if ext == ".flac":
            audio = FLAC(audio_path)
            audio["LYRICS"] = cleaned_lyrics
            audio.save()
            return True

        elif ext == ".mp3":
            try:
                audio = ID3(audio_path)
            except:
                audio = ID3()

            # 删除旧歌词
            audio.delall("USLT")
            # 添加新歌词
            audio.add(USLT(encoding=3, lang='eng', desc='', text=cleaned_lyrics))
            audio.save(audio_path)
            return True

        elif ext in (".m4a", ".alac", ".aac"):
            audio = MP4(audio_path)
            # Apple Music 使用 ©lyr 标签
            audio["\xa9lyr"] = cleaned_lyrics
            audio.save()
            return True

        else:
            log.warning(f"不支持的格式: {ext}")
            return False

    except Exception as e:
        log.error(f"嵌入歌词失败 ({os.path.basename(audio_path)}): {e}")
        return False


def process_directory(audio_dir: str, overwrite: bool = False, keep_timestamps: bool = False) -> tuple:
    """
    批量处理目录中的音频文件
    返回: (成功数, 跳过数, 失败数)
    """
    audio_dir = Path(audio_dir)
    if not audio_dir.exists():
        log.error(f"目录不存在: {audio_dir}")
        return 0, 0, 0

    # 查找所有音频文件和对应的 .lrc 文件
    pairs = []
    for ext in (".flac", ".mp3", ".m4a", ".alac", ".aac"):
        for audio_path in glob(os.path.join(audio_dir, f"*{ext}")):
            lrc_path = os.path.splitext(audio_path)[0] + ".lrc"
            if os.path.exists(lrc_path):
                pairs.append((audio_path, lrc_path))

    if not pairs:
        log.info("没有找到配对的音频和歌词文件")
        return 0, 0, 0

    log.info(f"找到 {len(pairs)} 对音频和歌词文件")

    success = 0
    skipped = 0
    failed = 0

    for audio_path, lrc_path in tqdm(pairs, desc="嵌入歌词"):
        # 检查是否已有歌词（如果不覆盖）
        if not overwrite:
            ext = os.path.splitext(audio_path)[1].lower()
            has_lyrics = False

            try:
                if ext == ".flac":
                    audio = FLAC(audio_path)
                    has_lyrics = bool(audio.get("LYRICS"))
                elif ext == ".mp3":
                    try:
                        audio = ID3(audio_path)
                        has_lyrics = any(k.startswith("USLT") for k in audio.keys())
                    except:
                        pass
                elif ext in (".m4a", ".alac", ".aac"):
                    audio = MP4(audio_path)
                    has_lyrics = "\xa9lyr" in (audio.tags or {})
            except:
                pass

            if has_lyrics:
                skipped += 1
                continue

        # 读取歌词内容
        try:
            with open(lrc_path, "r", encoding="utf-8") as f:
                lyrics_content = f.read()
        except Exception as e:
            log.error(f"读取歌词文件失败 ({os.path.basename(lrc_path)}): {e}")
            failed += 1
            continue

        # 嵌入歌词
        if embed_lyrics_to_file(audio_path, lyrics_content, keep_timestamps=keep_timestamps):
            success += 1
        else:
            failed += 1

    return success, skipped, failed


def main():
    import argparse

    ap = argparse.ArgumentParser(description="将 .lrc 歌词文件嵌入到音频文件")
    ap.add_argument("audio_dir", help="音频文件目录（包含 .lrc 文件）")
    ap.add_argument("--overwrite", action="store_true", help="覆盖已有的歌词")
    ap.add_argument("--keep-timestamps", action="store_true",
                    help="保留时间轴（默认去除，Apple Music 需要纯文本）")

    args = ap.parse_args()

    success, skipped, failed = process_directory(args.audio_dir, args.overwrite, args.keep_timestamps)

    log.info(f"✅ 成功: {success} | ⏭️ 跳过: {skipped} | ❌ 失败: {failed}")


if __name__ == "__main__":
    main()