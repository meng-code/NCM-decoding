#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import sys
from pathlib import Path
from typing import Tuple, Optional

from mutagen.flac import FLAC

SEPARATORS = [
    " - ", " – ", " — ", "－", "—", "–", "-"
]

def split_artist_title(stem: str) -> Optional[Tuple[str, str]]:
    """从文件名解析艺人和标题"""
    s = stem.strip()
    for sep in SEPARATORS:
        if sep in s:
            a, t = s.split(sep, 1)
            a, t = a.strip(), t.strip()
            if a and t:
                return a, t
    m = re.match(r"(.+?)\s*-\s*(.+)", s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None

def needs_update(value) -> bool:
    if value is None:
        return True
    if isinstance(value, list):
        return all((not str(v).strip()) for v in value)
    return not str(value).strip()

def fix_one(path: Path, overwrite: bool, default_album: Optional[str]) -> Tuple[bool, str]:
    stem = path.stem
    parsed = split_artist_title(stem)
    if not parsed:
        return (False, "无法从文件名解析“艺人 - 歌名”")

    artist_from_name, title_from_name = parsed

    try:
        audio = FLAC(path)
    except Exception as e:
        return (False, f"读取失败: {e}")

    changed = False
    if overwrite or needs_update(audio.get("title")):
        audio["title"] = title_from_name
        changed = True
    if overwrite or needs_update(audio.get("artist")):
        audio["artist"] = artist_from_name
        changed = True
    if default_album and (overwrite or needs_update(audio.get("album"))):
        audio["album"] = default_album
        changed = True

    if changed:
        try:
            audio.save()
        except Exception as e:
            return (False, f"保存失败: {e}")
        return (True, f'写入：artist="{artist_from_name}", title="{title_from_name}"'
                + (f', album="{default_album}"' if default_album else ""))
    else:
        return (False, "无需修改（已有完整标签）")

def main():
    import argparse
    ap = argparse.ArgumentParser(description="从文件名修复 FLAC 标签（仅 FLAC）")
    ap.add_argument("music_dir", help="包含音频文件的目录（会递归）")
    ap.add_argument("--overwrite", action="store_true",
                    help="若提供，则覆盖已有的 title/artist/album")
    ap.add_argument("--default-album", default="未知专辑",
                    help="缺失时写入的专辑名（设为空串可不写入）")
    ap.add_argument("--dry-run", action="store_true",
                    help="试运行，仅打印不落盘")
    args = ap.parse_args()

    root = Path(args.music_dir).expanduser().resolve()
    if not root.exists():
        print(f"目录不存在：{root}")
        sys.exit(1)

    total = ok = skip = err = 0

    for p in root.rglob("*.flac"):
        total += 1
        parsed = split_artist_title(p.stem)
        if not parsed:
            err += 1
            print(f"❌ {p.name} → 无法解析“艺人 - 歌名”")
            continue

        if args.dry_run:
            artist_from_name, title_from_name = parsed
            print(f"📝 试运行 {p.name} → artist='{artist_from_name}', title='{title_from_name}'"
                  + (f", album='{args.default_album}'" if args.default_album else ""))
            ok += 1
            continue

        changed, msg = fix_one(p, overwrite=args.overwrite,
                               default_album=(args.default_album or None))
        if changed:
            ok += 1
            print(f"✅ {p.name} → {msg}")
        else:
            # 可能是已有标签完整或者保存失败
            if msg.startswith("无需修改"):
                skip += 1
                print(f"↪️  {p.name} → {msg}")
            else:
                err += 1
                print(f"⚠️ {p.name} → {msg}")

    print("\n—— 完成 ——")
    print(f"总计：{total}  | 写入：{ok}  | 跳过：{skip}  | 出错：{err}")

if __name__ == "__main__":
    main()