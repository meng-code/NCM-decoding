#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
专辑信息抓取脚本
从网易云API获取完整的专辑信息并写入音频文件标签
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from typing import Dict, Optional, List
from tqdm import tqdm
import unicodedata
import re

# 音频标签库
from mutagen.flac import FLAC
from mutagen.mp3 import MP3, EasyMP3
from mutagen.mp4 import MP4
from mutagen.easyid3 import EasyID3
from mutagen import File as MFile


def get_lyrics(song_id: int) -> Optional[str]:
    """获取歌词（带时间轴的LRC格式）"""
    if not song_id:
        return None

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

        # 获取翻译歌词（如果有）
        tlrc = None
        if "tlyric" in result:
            tlrc = result["tlyric"].get("lyric", None)

        # 如果有翻译，合并到原歌词中
        if lrc and tlrc:
            # 简单合并：在原歌词后添加翻译标记
            return f"{lrc}\n\n[翻译歌词]\n{tlrc}"

        return lrc

    except Exception:
        return None


# NCM元数据读取（如果需要）
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


def search_song_info(title: str, artist: str = "") -> Optional[Dict]:
    """搜索歌曲获取详细信息"""
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://music.163.com",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    # 构建搜索关键词
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
            "limit": 10
        }

        resp = requests.post(url, data=data, headers=headers, timeout=10)
        resp.raise_for_status()
        result = resp.json()

        songs = result.get("result", {}).get("songs", [])
        if not songs:
            return None

        # 返回第一个匹配的结果
        song = songs[0]

        # 获取更详细的歌曲信息
        song_id = song.get("id")
        if song_id:
            detail = get_song_detail(song_id)
            if detail:
                return detail

        # 如果获取详情失败，返回基础信息
        return {
            "title": song.get("name", ""),
            "artist": " / ".join([a.get("name", "") for a in song.get("artists", [])]),
            "album": song.get("album", {}).get("name", ""),
            "albumartist": " / ".join([a.get("name", "") for a in song.get("album", {}).get("artists", [])]),
            "date": "",
            "genre": "",
            "tracknumber": str(song.get("position", "")),
            "discnumber": str(song.get("disc", ""))
        }

    except Exception as e:
        print(f"搜索失败: {e}")
        return None


def get_song_detail(song_id: int) -> Optional[Dict]:
    """获取歌曲详细信息"""
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://music.163.com"
    }

    try:
        # 使用详情API
        url = "https://music.163.com/api/song/detail"
        params = {
            "id": song_id,
            "ids": f"[{song_id}]"
        }

        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        result = resp.json()

        songs = result.get("songs", [])
        if not songs:
            return None

        song = songs[0]
        album = song.get("album", {})

        # 提取发行日期
        publish_time = album.get("publishTime", 0)
        if publish_time:
            date = time.strftime("%Y-%m-%d", time.localtime(publish_time / 1000))
        else:
            date = ""

        return {
            "title": song.get("name", ""),
            "artist": " / ".join([a.get("name", "") for a in song.get("artists", [])]),
            "album": album.get("name", ""),
            "albumartist": " / ".join([a.get("name", "") for a in album.get("artists", [])]),
            "date": date,
            "genre": "",  # 网易云API不提供流派信息
            "tracknumber": str(song.get("position", "")),
            "discnumber": str(song.get("disc", "")),
            "comment": album.get("description", "")[:500] if album.get("description") else "",
            "song_id": song_id  # 保存ID用于获取歌词
        }

    except Exception as e:
        print(f"获取详情失败: {e}")
        return None


def update_audio_tags(audio_path: str, info: Dict) -> bool:
    """更新音频文件标签"""
    try:
        audio = MFile(audio_path)
        if audio is None:
            print(f"无法读取文件: {audio_path}")
            return False

        ext = Path(audio_path).suffix.lower()

        if ext == ".flac":
            # FLAC文件
            if isinstance(audio, FLAC):
                for key, value in info.items():
                    if value:
                        audio[key.upper()] = value
                audio.save()

        elif ext == ".mp3":
            # MP3文件
            try:
                # 尝试使用EasyID3
                easy = EasyID3(audio_path)
                for key, value in info.items():
                    if value and key in ["title", "artist", "album", "date", "genre", "tracknumber", "albumartist"]:
                        easy[key] = value
                easy.save()
            except Exception as e:
                print(f"更新MP3标签失败: {e}")
                return False

        elif ext in [".m4a", ".mp4", ".aac"]:
            # MP4/M4A文件
            if isinstance(audio, MP4):
                tag_mapping = {
                    "title": "\xa9nam",
                    "artist": "\xa9ART",
                    "album": "\xa9alb",
                    "albumartist": "aART",
                    "date": "\xa9day",
                    "genre": "\xa9gen",
                    "comment": "\xa9cmt"
                }

                for key, value in info.items():
                    if value:
                        if key in tag_mapping:
                            audio[tag_mapping[key]] = value
                        elif key == "tracknumber":
                            try:
                                track_num = int(value.split("/")[0])
                                audio["trkn"] = [(track_num, 0)]
                            except:
                                pass
                        elif key == "discnumber":
                            try:
                                disc_num = int(value.split("/")[0])
                                audio["disk"] = [(disc_num, 0)]
                            except:
                                pass
                audio.save()
        else:
            print(f"不支持的文件格式: {ext}")
            return False

        return True

    except Exception as e:
        print(f"更新标签失败: {e}")
        return False


def parse_filename(filename: str) -> tuple:
    """从文件名解析艺术家和标题"""
    # 去掉扩展名
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

    # 如果没有匹配，返回整个文件名作为标题
    return stem, ""


def process_audio_file(audio_path: str, ncm_path: str = None, force_update: bool = False,
                       save_lyrics: bool = True) -> bool:
    """处理单个音频文件"""
    filename = Path(audio_path).name

    # 检查是否已有完整标签
    if not force_update:
        try:
            audio = MFile(audio_path)
            if audio and audio.get("album") and audio.get("artist"):
                print(f"跳过 {filename} (已有完整标签)")
                return True
        except:
            pass

    # 首先尝试从对应的NCM文件获取信息
    song_info = None

    if ncm_path and Path(ncm_path).exists():
        meta = read_ncm_meta(ncm_path)
        if meta:
            # 从NCM元数据构建信息
            song_info = {
                "title": meta.get("musicName", ""),
                "artist": " / ".join([a[0] for a in meta.get("artist", [])]),
                "album": meta.get("album", ""),
                "albumartist": " / ".join([a[0] for a in meta.get("artist", [])]),
                "date": "",
                "genre": "",
                "tracknumber": "",
                "discnumber": "",
                "song_id": meta.get("musicId")  # 保存音乐ID
            }

            # 如果有musicId，尝试获取更详细信息
            music_id = meta.get("musicId")
            if music_id:
                detail = get_song_detail(music_id)
                if detail:
                    song_info.update(detail)

    # 如果没有从NCM获取到信息，从文件名解析并搜索
    if not song_info:
        title, artist = parse_filename(filename)
        song_info = search_song_info(title, artist)

    if song_info:
        print(f"更新 {filename}")
        print(f"  标题: {song_info.get('title', '')}")
        print(f"  艺术家: {song_info.get('artist', '')}")
        print(f"  专辑: {song_info.get('album', '')}")
        print(f"  日期: {song_info.get('date', '')}")

        # 获取并保存歌词
        if save_lyrics and song_info.get('song_id'):
            lyrics = get_lyrics(song_info.get('song_id'))
            if lyrics:
                # 保存为独立的LRC文件
                lrc_path = Path(audio_path).with_suffix('.lrc')
                try:
                    with open(lrc_path, 'w', encoding='utf-8') as f:
                        f.write(lyrics)
                    print(f"  ✓ 已保存歌词: {lrc_path.name}")
                except:
                    print(f"  ⚠ 保存歌词失败")

        # 移除song_id（不需要写入标签）
        song_info.pop('song_id', None)

        if update_audio_tags(audio_path, song_info):
            print(f"  ✅ 成功")
            return True
        else:
            print(f"  ❌ 失败")
            return False
    else:
        print(f"❌ 未找到 {filename} 的信息")
        return False


def main():
    import argparse

    parser = argparse.ArgumentParser(description="专辑信息抓取工具")
    parser.add_argument("audio_dir", help="音频文件目录")
    parser.add_argument("--ncm_dir", help="NCM文件目录（可选）")
    parser.add_argument("--force", action="store_true", help="强制更新已有标签的文件")
    parser.add_argument("--no-lyrics", action="store_true", help="不获取歌词")
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
        time.sleep(0.5)

        if process_audio_file(str(audio_path), ncm_path, args.force, save_lyrics=not args.no_lyrics):
            success += 1
        else:
            failed += 1

    print(f"\n完成: 成功 {success}, 失败 {failed}")


if __name__ == "__main__":
    main()