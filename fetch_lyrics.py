#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
歌词抓取脚本
从网易云API获取带时间轴的LRC歌词
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from typing import Dict, Optional, Tuple
from tqdm import tqdm
import re
import unicodedata

# 音频标签库
from mutagen import File as MFile
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

# NCM元数据读取
import struct
import binascii
import base64
from Crypto.Cipher import AES

# 固定密钥
CORE_KEY = binascii.a2b_hex('687A4852416D736F356B496E62617857')
META_KEY = binascii.a2b_hex('2331346C6A6B5F215C5D2630553C2728')


def unpad(s):
    """移除PKCS7填充"""
    if not s:
        return s
    pad = s[-1] if isinstance(s[-1], int) else ord(s[-1])
    if pad > len(s) or pad == 0:
        return s
    return s[:-pad]


def read_ncm_meta(ncm_path: str) -> Optional[dict]:
    """读取NCM文件的元数据"""
    try:
        with open(ncm_path, 'rb') as f:
            # 验证文件头
            if binascii.b2a_hex(f.read(8)) != b'4354454e4644414d':
                return None
            f.seek(2, 1)

            # 读取并解密密钥
            key_len = struct.unpack('<I', f.read(4))[0]
            key_data = bytearray(f.read(key_len))
            for i in range(len(key_data)):
                key_data[i] ^= 0x64

            cipher = AES.new(CORE_KEY, AES.MODE_ECB)
            key_data = unpad(cipher.decrypt(bytes(key_data)))[17:]

            # 跳到meta区
            meta_len = struct.unpack('<I', f.read(4))[0]
            if meta_len == 0:
                return None

            meta_data = bytearray(f.read(meta_len))
            for i in range(len(meta_data)):
                meta_data[i] ^= 0x63

            meta_data = base64.b64decode(bytes(meta_data)[22:])
            cipher = AES.new(META_KEY, AES.MODE_ECB)
            meta_data = unpad(cipher.decrypt(meta_data))

            meta = json.loads(meta_data.decode('utf-8')[6:])
            return meta
    except Exception as e:
        print(f"读取NCM元数据失败: {e}")
        return None


def search_song(title: str, artist: str = "") -> Optional[int]:
    """搜索歌曲获取ID"""
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://music.163.com",
    }

    query = f"{artist} {title}".strip() if artist else title

    try:
        # 使用网易云搜索API
        url = "https://music.163.com/api/search/get/web"
        data = {
            "csrf_token": "",
            "type": 1,
            "s": query,
            "offset": 0,
            "total": "true",
            "limit": 5
        }

        resp = requests.post(url, data=data, headers=headers, timeout=10)
        resp.raise_for_status()
        result = resp.json()

        songs = result.get("result", {}).get("songs", [])
        if songs:
            return songs[0].get("id")

        return None

    except Exception as e:
        print(f"搜索歌曲失败: {e}")
        return None


def get_lyrics(song_id: int) -> Tuple[Optional[str], Optional[str]]:
    """
    获取歌词
    返回: (lrc歌词, 翻译歌词)
    """
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://music.163.com"
    }

    try:
        url = "https://music.163.com/api/song/lyric"
        params = {
            "id": song_id,
            "lv": 1,  # 原始歌词
            "tv": 1  # 翻译歌词
        }

        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        result = resp.json()

        # 获取原始歌词
        lrc = None
        if "lrc" in result:
            lrc = result["lrc"].get("lyric", None)

        # 获取翻译歌词
        tlrc = None
        if "tlyric" in result:
            tlrc = result["tlyric"].get("lyric", None)

        return lrc, tlrc

    except Exception as e:
        print(f"获取歌词失败: {e}")
        return None, None


def merge_lyrics(lrc: str, tlrc: str = None) -> str:
    """
    合并原始歌词和翻译歌词
    如果有翻译，会在每行原文后添加翻译
    """
    if not lrc:
        return ""

    if not tlrc:
        return lrc

    # 解析LRC格式
    def parse_lrc(text):
        lines = {}
        for line in text.split('\n'):
            # 匹配时间标签 [mm:ss.xx] 或 [mm:ss]
            match = re.match(r'\[(\d{2}):(\d{2})(?:\.(\d{2}))?\](.*)', line)
            if match:
                minutes = int(match.group(1))
                seconds = int(match.group(2))
                milliseconds = int(match.group(3)) if match.group(3) else 0
                timestamp = minutes * 60000 + seconds * 1000 + milliseconds * 10
                content = match.group(4).strip()
                if content:  # 只保存有内容的行
                    lines[timestamp] = content
        return lines

    # 解析原文和翻译
    lrc_lines = parse_lrc(lrc)
    tlrc_lines = parse_lrc(tlrc)

    # 合并歌词
    merged = []

    # 保留原始文件的元数据（如[ar:], [ti:]等）
    for line in lrc.split('\n'):
        if line.startswith('[') and not re.match(r'\[\d{2}:\d{2}', line):
            merged.append(line)

    # 合并时间轴歌词
    for timestamp in sorted(lrc_lines.keys()):
        time_str = f"[{timestamp // 60000:02d}:{(timestamp % 60000) // 1000:02d}.{(timestamp % 1000) // 10:02d}]"
        original = lrc_lines[timestamp]

        # 检查是否有对应的翻译
        if timestamp in tlrc_lines:
            translation = tlrc_lines[timestamp]
            merged.append(f"{time_str}{original}")
            merged.append(f"{time_str}【{translation}】")  # 用【】标记翻译
        else:
            merged.append(f"{time_str}{original}")

    return '\n'.join(merged)


def save_lyrics(lyrics: str, output_path: str):
    """保存歌词到文件"""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(lyrics)
        return True
    except Exception as e:
        print(f"保存歌词失败: {e}")
        return False


def embed_lyrics_to_audio(audio_path: str, lyrics: str) -> bool:
    """
    将歌词嵌入音频文件
    注意：只有部分格式支持嵌入歌词
    """
    try:
        audio = MFile(audio_path)
        if audio is None:
            return False

        ext = Path(audio_path).suffix.lower()

        if ext == ".flac":
            # FLAC支持LYRICS和UNSYNCEDLYRICS标签
            audio["LYRICS"] = lyrics
            audio.save()
            return True

        elif ext == ".mp3":
            # MP3可以使用USLT帧存储歌词
            from mutagen.id3 import USLT
            if audio.tags is None:
                audio.add_tags()
            audio.tags.add(USLT(encoding=3, lang='chi', desc='', text=lyrics))
            audio.save()
            return True

        elif ext in [".m4a", ".mp4"]:
            # M4A/MP4使用©lyr标签
            audio["©lyr"] = lyrics
            audio.save()
            return True

        else:
            print(f"格式 {ext} 不支持嵌入歌词")
            return False

    except Exception as e:
        print(f"嵌入歌词失败: {e}")
        return False


def parse_filename(filename: str) -> tuple:
    """从文件名解析艺术家和标题"""
    stem = Path(filename).stem

    # 尝试分割 "艺术家 - 标题" 格式
    patterns = [
        r'^(.+?)\s*-\s*(.+)$',  # 标准格式
        r'^(.+?)\s*－\s*(.+)$',  # 全角横线
        r'^(.+?)\s*—\s*(.+)$',  # 长横线
        r'^(.+?)\s*–\s*(.+)$',  # 短横线
    ]

    for pattern in patterns:
        match = re.match(pattern, stem)
        if match:
            artist = match.group(1).strip()
            title = match.group(2).strip()
            return title, artist

    return stem, ""


def process_audio_file(audio_path: str, ncm_path: str = None,
                       save_lrc: bool = True, embed: bool = True,
                       merge_translation: bool = True) -> bool:
    """
    处理单个音频文件

    Args:
        audio_path: 音频文件路径
        ncm_path: 对应的NCM文件路径（可选）
        save_lrc: 是否保存为独立的LRC文件
        embed: 是否尝试嵌入到音频文件
        merge_translation: 是否合并翻译
    """
    filename = Path(audio_path).name
    print(f"\n处理: {filename}")

    # 获取歌曲ID
    song_id = None

    # 首先尝试从NCM文件获取
    if ncm_path and Path(ncm_path).exists():
        meta = read_ncm_meta(ncm_path)
        if meta:
            song_id = meta.get("musicId")
            if song_id:
                print(f"  从NCM获取ID: {song_id}")

    # 如果没有从NCM获取到，尝试搜索
    if not song_id:
        # 尝试从音频文件读取标签
        try:
            audio = MFile(audio_path)
            if audio:
                title = audio.get("title", [""])[0] if audio.get("title") else ""
                artist = audio.get("artist", [""])[0] if audio.get("artist") else ""

                # 如果没有标签，从文件名解析
                if not title:
                    title, artist = parse_filename(filename)

                if title:
                    print(f"  搜索: {artist} - {title}" if artist else f"  搜索: {title}")
                    song_id = search_song(title, artist)
        except:
            # 如果读取失败，从文件名解析
            title, artist = parse_filename(filename)
            if title:
                song_id = search_song(title, artist)

    if not song_id:
        print(f"  ❌ 未找到歌曲ID")
        return False

    # 获取歌词
    print(f"  获取歌词...")
    lrc, tlrc = get_lyrics(song_id)

    if not lrc:
        print(f"  ❌ 未找到歌词")
        return False

    # 合并歌词
    if merge_translation and tlrc:
        final_lyrics = merge_lyrics(lrc, tlrc)
        print(f"  ✓ 已合并翻译歌词")
    else:
        final_lyrics = lrc

    success = False

    # 保存为LRC文件
    if save_lrc:
        lrc_path = Path(audio_path).with_suffix('.lrc')
        if save_lyrics(final_lyrics, str(lrc_path)):
            print(f"  ✓ 已保存LRC: {lrc_path.name}")
            success = True

    # 嵌入到音频文件
    if embed:
        if embed_lyrics_to_audio(audio_path, final_lyrics):
            print(f"  ✓ 已嵌入歌词到音频文件")
            success = True
        else:
            print(f"  ⚠ 无法嵌入歌词（格式限制）")

    return success


def main():
    import argparse

    parser = argparse.ArgumentParser(description="歌词抓取工具")
    parser.add_argument("audio_dir", help="音频文件目录")
    parser.add_argument("--ncm_dir", help="NCM文件目录（可选）")
    parser.add_argument("--no-lrc", action="store_true", help="不保存独立的LRC文件")
    parser.add_argument("--no-embed", action="store_true", help="不嵌入到音频文件")
    parser.add_argument("--no-translation", action="store_true", help="不合并翻译")
    parser.add_argument("--limit", type=int, help="限制处理文件数量")

    args = parser.parse_args()

    audio_dir = Path(args.audio_dir)
    if not audio_dir.exists():
        print(f"目录不存在: {audio_dir}")
        sys.exit(1)

    # 收集音频文件
    audio_files = []
    for ext in [".flac", ".mp3", ".m4a", ".mp4", ".aac"]:
        audio_files.extend(audio_dir.rglob(f"*{ext}"))

    if args.limit:
        audio_files = audio_files[:args.limit]

    if not audio_files:
        print("没有找到音频文件")
        return

    print(f"找到 {len(audio_files)} 个音频文件")

    # 处理文件
    success = 0
    failed = 0

    for audio_path in tqdm(audio_files, desc="处理进度"):
        # 查找对应的NCM文件
        ncm_path = None
        if args.ncm_dir:
            ncm_dir = Path(args.ncm_dir)
            ncm_file = ncm_dir / f"{audio_path.stem}.ncm"
            if ncm_file.exists():
                ncm_path = str(ncm_file)

        # 添加延迟避免请求过快
        time.sleep(0.3)

        if process_audio_file(
                str(audio_path),
                ncm_path,
                save_lrc=not args.no_lrc,
                embed=not args.no_embed,
                merge_translation=not args.no_translation
        ):
            success += 1
        else:
            failed += 1

    print(f"\n完成: 成功 {success}, 失败 {failed}")


if __name__ == "__main__":
    main()