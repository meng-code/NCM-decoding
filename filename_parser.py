#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件名解析工具模块
统一处理 "艺人 - 歌名" 格式的文件名
"""

import re
import unicodedata
from pathlib import Path
from typing import Optional, Tuple, List, Dict


# 带空格的分隔符：明确的"艺人 - 标题"边界。
# 注意：全角横线 "－"(U+FF0D) 经 NFKC 会先归一成 "-"，故无需单列。
SPACED_SEPARATORS = [" - ", " – ", " — "]

# 已知的音频文件扩展名（仅剥离这些，避免误伤含点的歌名/艺人名）
KNOWN_AUDIO_EXTS = {
    ".ncm", ".flac", ".mp3", ".m4a", ".mp4", ".aac", ".alac",
    ".ogg", ".wav", ".ape", ".wma",
}


def strip_ext(filename: str) -> str:
    """
    去除文件名的扩展名，但只剥离已知的音频扩展名。

    不能直接用 Path().stem，因为像 "Mr. Children - Tomorrow"、
    "a.b.c - song" 这类含点的名称会被错误地从点处截断。

    Args:
        filename: 文件名（带或不带扩展名）

    Returns:
        去除已知扩展名后的名称
    """
    p = Path(filename)
    if p.suffix.lower() in KNOWN_AUDIO_EXTS:
        return p.stem
    return filename


def _split_two(stem: str) -> Optional[Tuple[str, str]]:
    """
    把 "艺人 - 标题" 切成 (左, 右) 两段。切不出来返回 None。

    策略：
    1. 优先匹配带空格分隔符 " - "/" – "/" — "（明确边界）。
    2. 回退到裸连字符 "-"，但仅当整串无空格、恰好一个连字符、且两侧非纯数字时，
       以避免把 "2024-01-01 backup"（日期）、"Jay-Z 歌"（缺正规分隔符）等误切成错误标签。
    """
    # 1) 带空格分隔符
    for sep in SPACED_SEPARATORS:
        if sep in stem:
            left, right = stem.split(sep, 1)
            left, right = left.strip(), right.strip()
            if left and right:
                return left, right

    # 2) 受限的裸连字符回退（如 "周杰伦-七里香"、"will.i.am-song"）
    if " " not in stem and stem.count("-") == 1:
        left, right = stem.split("-", 1)
        left, right = left.strip(), right.strip()
        if left and right and not (left.isdigit() and right.isdigit()):
            return left, right

    return None


def parse_filename(filename: str) -> Optional[Tuple[str, str]]:
    """
    从文件名解析艺人和标题
    假设格式为 "艺人 - 标题"

    Args:
        filename: 文件名（带或不带扩展名）

    Returns:
        (artist, title) 元组，失败返回 None
    """
    stem = strip_ext(filename)
    stem = unicodedata.normalize("NFKC", stem).strip()
    return _split_two(stem)


def parse_filename_as_title_artist(filename: str) -> Tuple[str, str]:
    """
    从文件名解析，返回 (title, artist)
    与 parse_filename 不同：调换返回顺序，并且解析失败时返回 (整个文件名, "")

    用于 fetch_album_info.py 和 fetch_lyrics.py 的调用模式

    Args:
        filename: 文件名

    Returns:
        (title, artist) 元组
    """
    result = parse_filename(filename)
    if result:
        artist, title = result
        return title, artist

    # 解析失败：将整个文件名作为标题
    stem = strip_ext(filename)
    return stem, ""


def clean_text_for_search(s: str) -> str:
    """
    清理文本用于模糊搜索匹配
    去除括号内容、feat. 标记、特殊字符

    Args:
        s: 原始文本

    Returns:
        清理后的文本（小写、规范化）
    """
    s = unicodedata.normalize("NFKC", s or "")
    # 去除括号内容（中英文）
    s = re.sub(r"[（(].*?[)）]", " ", s)
    # 去除 feat./with 等
    s = re.sub(r"\b(feat\.?|with|＆|&)\b.*$", " ", s, flags=re.I)
    # 去除特殊字符
    s = re.sub(r"[~!@#$%^&*=_+\-|\\/:;,.?·，。、《》""\"'！【】\[\]\{\}]+", " ", s)
    # 合并多余空格
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def make_title_artist_candidates(filename: str) -> List[Dict[str, str]]:
    """
    生成标题/艺人候选列表
    由于无法确定文件名是 "艺人 - 标题" 还是 "标题 - 艺人"，生成两种候选

    Args:
        filename: 文件名

    Returns:
        候选列表，每项包含 title, artist, title_c (清理后), artist_c (清理后)
    """
    stem = strip_ext(filename)
    stem = unicodedata.normalize("NFKC", stem).strip()

    candidates = []

    # 复用统一的分隔逻辑（支持带空格分隔符 + 受限裸连字符），
    # 而非只认 " - "，以覆盖全角/破折号等命名
    split = _split_two(stem)

    if split:
        left, right = split
        # 候选1：左边是标题，右边是艺人
        candidates.append({
            "title": left,
            "artist": right,
            "title_c": clean_text_for_search(left),
            "artist_c": clean_text_for_search(right),
        })
        # 候选2：左边是艺人，右边是标题
        candidates.append({
            "title": right,
            "artist": left,
            "title_c": clean_text_for_search(right),
            "artist_c": clean_text_for_search(left),
        })
    else:
        # 没有分隔符，整个作为标题
        candidates.append({
            "title": stem,
            "artist": "",
            "title_c": clean_text_for_search(stem),
            "artist_c": "",
        })

    return candidates


def guess_title_artist(filename: str) -> Tuple[str, str]:
    """
    猜测文件名中的标题和艺人（保留括号外内容作为标题）
    假设格式为 "艺人 - 标题"，但会清理标题中的括号

    Args:
        filename: 文件名

    Returns:
        (title, artist) 元组
    """
    stem = unicodedata.normalize("NFKC", strip_ext(filename)).strip()

    split = _split_two(stem)
    if split:
        artist, title = split
    else:
        artist, title = "", stem

    # 清理标题中的括号内容
    title = re.sub(r"[（(].*?[)）]", "", title).strip()
    artist = artist.strip()

    # 规范化
    title = unicodedata.normalize("NFKC", title).strip()
    artist = unicodedata.normalize("NFKC", artist).strip()

    return title, artist
