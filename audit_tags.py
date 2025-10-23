#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys, os, csv, time
from pathlib import Path
from typing import Tuple, Dict, Any, Optional

from mutagen import File as MuFile
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC
from mutagen.easymp4 import EasyMP4
from mutagen.mp4 import MP4

AUDIO_EXTS = {".flac", ".mp3", ".m4a", ".alac", ".aac"}

def has_cover(audio) -> bool:
    """Return whether embedded artwork exists."""
    try:
        if isinstance(audio, FLAC):
            return bool(getattr(audio, "pictures", []))
        if isinstance(audio, MP3):
            # Any APIC frame
            if hasattr(audio, "tags") and isinstance(audio.tags, ID3):
                return any(k.startswith("APIC") for k in audio.tags.keys())
            return False
        if isinstance(audio, MP4):
            # MP4 cover atom 'covr'
            return "covr" in audio
        # Fallback for EasyMP4 or others
        if isinstance(audio, EasyMP4):
            return "covr" in audio.tags if audio.tags else False
    except Exception:
        pass
    return False

def get_basic_tags(audio) -> Dict[str, Optional[str]]:
    """Return a normalized tag dict for title/artist/album/year/track."""
    tags = {"title": None, "artist": None, "album": None, "date": None, "tracknumber": None}
    try:
        if isinstance(audio, FLAC):
            for k in tags.keys():
                v = audio.tags.get(k.upper()) or audio.tags.get(k)
                if v: tags[k] = v[0]
        elif isinstance(audio, MP3):
            ea = audio.tags  # ID3
            # Use easy keys if present, else ID3 frames
            from mutagen.easyid3 import EasyID3
            try:
                easy = EasyID3(audio.filename)
                for k in ("title","artist","album","date","tracknumber"):
                    v = easy.get(k)
                    tags[k] = v[0] if v else None
            except Exception:
                pass
        elif isinstance(audio, (EasyMP4, MP4)):
            def first(key_list):
                for k in key_list:
                    if k in audio.tags:
                        v = audio.tags[k]
                        if isinstance(v, list) and v: return str(v[0])
                        return str(v)
                return None
            tags["title"]  = first(["\xa9nam","title"])
            tags["artist"] = first(["\xa9ART","artist"])
            tags["album"]  = first(["\xa9alb","album"])
            tags["date"]   = first(["\xa9day","date"])
            # track number is usually tuple like (n, total)
            tn = audio.tags.get("trkn")
            if tn and isinstance(tn, list) and tn and isinstance(tn[0], tuple):
                tags["tracknumber"] = str(tn[0][0])
    except Exception:
        pass
    return tags

def audit_file(path: Path) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "path": str(path),
        "ext": path.suffix.lower(),
        "title": None, "artist": None, "album": None, "date": None, "tracknumber": None,
        "duration_sec": None, "samplerate": None, "channels": None,
        "has_cover": False,
        "problems": []
    }
    try:
        audio = MuFile(path)
        if audio is None:
            info["problems"].append("无法读取（不是受支持的音频）")
            return info

        # duration / sample rate / channels
        try:
            info["duration_sec"] = round(float(getattr(audio.info, "length", 0)), 2)
            info["samplerate"] = getattr(audio.info, "sample_rate", None) or getattr(audio.info, "samplerate", None)
            info["channels"] = getattr(audio.info, "channels", None)
        except Exception:
            pass

        # tags
        tags = get_basic_tags(audio)
        info.update(tags)

        # cover
        info["has_cover"] = has_cover(audio)

        # problems detection
        if not info["title"]:  info["problems"].append("缺少标题")
        if not info["artist"]: info["problems"].append("缺少艺人")
        if not info["album"]:  info["problems"].append("缺少专辑")
        if not info["has_cover"]: info["problems"].append("无嵌入封面")

    except Exception as e:
        info["problems"].append(f"读取异常: {e!r}")

    return info

def iter_audio_files(root: Path):
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
            yield p

def main():
    if len(sys.argv) < 2:
        print("用法：python3 audit_tags.py \"/path/to/你的音频根目录\"")
        sys.exit(1)

    root = Path(sys.argv[1]).expanduser().resolve()
    if not root.exists():
        print(f"路径不存在：{root}")
        sys.exit(1)

    rows = []
    total = ok = warn = 0

    print(f"\n🔎 正在扫描目录：{root}\n")
    for f in iter_audio_files(root):
        total += 1
        r = audit_file(f)
        rows.append(r)
        if r["problems"]:
            warn += 1
            short = "、".join(r["problems"])
            print(f"⚠ {f.name}  →  {short}")
        else:
            ok += 1

    # summary
    print("\n—— 总结 —————————————————")
    print(f"文件总数：{total}")
    print(f"标签完整：{ok}")
    print(f"需修复：  {warn}")

    # export CSV
    out = Path.cwd() / f"tag_report_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "path","ext","title","artist","album","date","tracknumber",
                "duration_sec","samplerate","channels","has_cover","problems"
            ]
        )
        writer.writeheader()
        for r in rows:
            r = r.copy()
            r["problems"] = " | ".join(r["problems"])
            writer.writerow(r)

    print(f"\n✅ 已导出报告：{out}\n（用 Excel/Numbers 打开可筛选「缺少艺人/专辑/封面」等）")

if __name__ == "__main__":
    main()