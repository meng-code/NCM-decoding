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


# 支持的分隔符（顺序很重要：长的在前，避免短分隔符提前匹配）
SEPARATORS = [" - ", " – ", " — ", "－", "—", "–", "-"]


def parse_filename(filename: str) -> Optional[Tuple[str, str]]:
    """
    从文件名解析艺人和标题
    假设格式为 "艺人 - 标题"

    Args:
        filename: 文件名（带或不带扩展名）

    Returns:
        (artist, title) 元组，失败返回 None
    """
    stem = Path(filename).stem if "." in filename else filename
    stem = unicodedata.normalize("NFKC", stem).strip()

    for sep in SEPARATORS:
        if sep in stem:
            artist, title = stem.split(sep, 1)
            artist, title = artist.strip(), title.strip()
            if artist and title:
                return artist, title

    return None


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
    stem = Path(filename).stem if "." in filename else filename
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
    stem = Path(filename).stem if "." in filename else filename
    stem = unicodedata.normalize("NFKC", stem).strip()

    candidates = []

    # 尝试用 " - " 分割（标准分隔符）
    parts = [p.strip() for p in stem.split(" - ", 1)]

    if len(parts) == 2:
        left, right = parts
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
    stem = Path(filename).stem if "." in filename else filename

    parts = stem.split(" - ", 1)
    if len(parts) == 2:
        artist, title = parts
    else:
        artist, title = "", stem

    # 清理标题中的括号内容
    title = re.sub(r"[（(].*?[)）]", "", title).strip()
    artist = artist.strip()

    # 规范化
    title = unicodedata.normalize("NFKC", title).strip()
    artist = unicodedata.normalize("NFKC", artist).strip()

    return title, artist
