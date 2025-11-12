#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NCM 工具模块
提供 NCM 文件解析和解密的通用功能
"""

import json
import base64
import struct
import binascii
from typing import Optional
from Crypto.Cipher import AES


# NCM 文件加密使用的固定密钥
CORE_KEY = binascii.a2b_hex('687A4852416D736F356B496E62617857')
META_KEY = binascii.a2b_hex('2331346C6A6B5F215C5D2630553C2728')


def unpad(s: bytes) -> bytes:
    """
    移除 PKCS7 填充

    Args:
        s: 需要去除填充的字节串

    Returns:
        去除填充后的字节串
    """
    if not s:
        return s
    pad = s[-1] if isinstance(s[-1], int) else ord(s[-1])
    if pad > len(s) or pad == 0:
        return s
    return s[:-pad]


def read_ncm_meta(ncm_path: str) -> Optional[dict]:
    """
    读取 NCM 文件的元数据

    Args:
        ncm_path: NCM 文件路径

    Returns:
        包含元数据的字典，如果读取失败返回 None
        元数据字典包含：
        - musicId: 网易云音乐 ID
        - musicName: 歌曲名称
        - artist: 艺术家列表 [[名称, ID], ...]
        - album: 专辑名称
        - format: 音频格式 (mp3/flac/等)
    """
    try:
        with open(ncm_path, 'rb') as f:
            # 验证文件头 "CTENFDAM"
            header = f.read(8)
            if binascii.b2a_hex(header) != b'4354454e4644414d':
                return None

            # 跳过 2 字节
            f.seek(2, 1)

            # 读取并解密密钥数据
            key_len = struct.unpack('<I', f.read(4))[0]
            key_data = bytearray(f.read(key_len))
            for i in range(len(key_data)):
                key_data[i] ^= 0x64

            cipher = AES.new(CORE_KEY, AES.MODE_ECB)
            key_data = unpad(cipher.decrypt(bytes(key_data)))[17:]

            # 读取元数据区域
            meta_len = struct.unpack('<I', f.read(4))[0]
            if meta_len == 0:
                return None

            meta_data = bytearray(f.read(meta_len))
            for i in range(len(meta_data)):
                meta_data[i] ^= 0x63

            # 解码 base64 并解密
            meta_data = base64.b64decode(bytes(meta_data)[22:])
            cipher = AES.new(META_KEY, AES.MODE_ECB)
            meta_data = unpad(cipher.decrypt(meta_data))

            # 解析 JSON（跳过前6个字符 "music:"）
            meta = json.loads(meta_data.decode('utf-8')[6:])
            return meta

    except Exception as e:
        # 静默失败，让调用者处理
        return None


def get_music_id_from_ncm(ncm_path: str) -> Optional[str]:
    """
    从 NCM 文件中提取音乐 ID

    Args:
        ncm_path: NCM 文件路径

    Returns:
        音乐 ID 字符串，失败返回 None
    """
    meta = read_ncm_meta(ncm_path)
    if meta:
        music_id = meta.get("musicId") or meta.get("musicid")
        return str(music_id) if music_id else None
    return None
