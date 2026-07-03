import os, re, json, base64, struct, binascii, logging
from glob import glob
from typing import Dict, Optional
from tqdm import tqdm

from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3, APIC, error as ID3Error
from mutagen.mp3 import EasyMP3
from mutagen.mp4 import MP4, MP4Cover
from rapidfuzz import fuzz
from rapidfuzz import process as rf_process
import unicodedata, time
from mutagen import File as MFile
try:
    from PIL import Image
except Exception:
    Image = None
import requests

# 导入共享模块
from ncm_utils import read_ncm_meta
from filename_parser import (
    clean_text_for_search as _clean_text,
    make_title_artist_candidates,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("artwork")

def build_img_index(meta_img_dir: str) -> Dict[str, str]:
    """索引meta目录中的track-<id>图片，有重复时选择较大文件"""
    idx: Dict[str, str] = {}
    patterns = ["track-*.jpg", "track-*.jpeg", "track-*.png", "track-*.webp"]
    for pat in patterns:
        for p in glob(os.path.join(meta_img_dir, pat)):
            fn = os.path.basename(p)
            fn = re.sub(r"\s*\(\d+\)(?=\.(jpe?g|png|webp)$)", "", fn, flags=re.I)
            m = re.match(r"track-(\d+)\.(jpe?g|png|webp)$", fn, flags=re.I)
            if not m:
                continue
            tid = m.group(1)
            if tid not in idx or os.path.getsize(p) > os.path.getsize(idx[tid]):
                idx[tid] = p
    log.info(f"封面索引：{len(idx)} 张")
    return idx


_AUDIO_EXTS = (".flac", ".mp3", ".m4a", ".alac", ".aac")

def find_matching_audio(decoded_dir: str, stem: str):
    """匹配音频文件"""
    for ext in _AUDIO_EXTS:
        p = os.path.join(decoded_dir, f"{stem}{ext}")
        if os.path.exists(p):
            return p
    # 回退：忽略空白差异模糊匹配，但只接受音频扩展名，避免返回同名 .lrc/.jpg
    norm = re.sub(r"\s+", "", stem).lower()
    for p in glob(os.path.join(decoded_dir, "*")):
        if os.path.splitext(p)[1].lower() not in _AUDIO_EXTS:
            continue
        s = re.sub(r"\s+", "", os.path.splitext(os.path.basename(p))[0]).lower()
        if s == norm:
            return p
    return None

def _infer_mime(img_path: str) -> str:
    ext = os.path.splitext(img_path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".png":
        return "image/png"
    if ext == ".webp":
        return "image/webp"
    return "application/octet-stream"

def embed_cover(audio_path: str, img_path: str):
    ext = os.path.splitext(audio_path)[1].lower()
    img_mime = _infer_mime(img_path)
    with open(img_path, "rb") as f:
        img_bytes = f.read()
    if img_mime == "image/webp":
        # webp 需转成 png 才能安全内嵌；否则数据与声明的 mime 不符会导致播放器显示破图
        if Image is None:
            raise RuntimeError("封面为 webp 但未安装 Pillow，无法转换（跳过以免写入错误 mime）")
        try:
            from io import BytesIO
            im = Image.open(img_path).convert("RGB")
            buf = BytesIO()
            im.save(buf, format="PNG")
            img_bytes = buf.getvalue()
            img_mime = "image/png"
        except Exception as e:
            raise RuntimeError(f"webp 封面转换失败: {e}")

    if ext == ".flac":
        audio = FLAC(audio_path)
        pic = Picture()
        pic.type = 3
        pic.mime = "image/jpeg" if img_mime == "image/jpeg" else "image/png"
        pic.desc = "cover"
        pic.data = img_bytes
        audio.clear_pictures()
        audio.add_picture(pic)
        audio.save()
    elif ext == ".mp3":
        try:
            tags = ID3(audio_path)
        except ID3Error:
            tags = ID3()
        tags.delall("APIC")
        mime = "image/jpeg" if img_mime == "image/jpeg" else "image/png"
        tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=img_bytes))
        tags.save(audio_path)
    elif ext in (".m4a", ".alac", ".aac"):
        mp4 = MP4(audio_path)
        if img_mime == "image/jpeg":
            mp4["covr"] = [MP4Cover(img_bytes, imageformat=MP4Cover.FORMAT_JPEG)]
        else:
            mp4["covr"] = [MP4Cover(img_bytes, imageformat=MP4Cover.FORMAT_PNG)]
        mp4.save()
    else:
        raise RuntimeError(f"不支持的音频格式：{ext}")


def _req_json(url: str, data: dict, retries: int = 2) -> Optional[dict]:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://music.163.com",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    for i in range(retries + 1):
        try:
            r = requests.post(url, data=data, headers=headers, timeout=8)
            r.raise_for_status()
            return r.json()
        except Exception:
            if i < retries:
                time.sleep(0.6)
            else:
                return None


def _extract_songs(js):
    """安全地从网易云 API 响应中提取歌曲列表

    API 在某些情况下会让 result 字段返回字符串（错误信息）而非字典，
    需要逐层做类型检查防御。
    """
    if not isinstance(js, dict):
        return []
    result = js.get("result")
    if not isinstance(result, dict):
        return []
    songs = result.get("songs", [])
    return songs if isinstance(songs, list) else []

def search_netease_track_id(title: str, artist: str, want_seconds: Optional[float]) -> Optional[str]:
    """搜索网易云音乐track ID"""
    title_c = _clean_text(title)
    artist_c = _clean_text(artist)
    q_base = (title_c + " " + artist_c).strip()
    queries = [q for q in {q_base, title_c, f"{artist_c} {title_c}"} if q]

    best_id, best_score = None, -1

    def score_candidate(name: str, artists: str, dur_ms) -> int:
        text_hit = _clean_text(name + " " + artists)
        sim = rf_process.extractOne(text_hit, [q_base] + queries, scorer=fuzz.token_set_ratio)
        s = (sim[1] if sim else 0)
        if want_seconds and isinstance(dur_ms, (int, float)):
            dur_s = dur_ms / 1000.0
            if abs(dur_s - want_seconds) <= 2:
                s += 12
            elif abs(dur_s - want_seconds) <= 5:
                s += 6
            else:
                s -= 10
        return int(s)

    for q in queries:
        js1 = _req_json("https://music.163.com/api/cloudsearch/pc",
                        {"type": 1, "s": q, "offset": 0, "total": "true", "limit": 15})
        songs = _extract_songs(js1)
        if not songs:
            js2 = _req_json("https://music.163.com/api/search/get/web",
                            {"csrf_token": "", "type": 1, "s": q, "offset": 0, "total": "true", "limit": 10})
            songs = _extract_songs(js2)

        for s in songs:
            name = s.get("name", "")
            arts = s.get("ar") or s.get("artists") or []
            artists = " & ".join(a.get("name", "") for a in arts)
            dur = s.get("dt", s.get("duration", 0))
            sc = score_candidate(name, artists, dur)
            if sc > best_score:
                best_score, best_id = sc, str(s.get("id"))
        if best_score >= 90:
            break

    cutoff = 65 if want_seconds else 75
    return best_id if best_score >= cutoff else None

def main(decoded_dir: str, meta_img_dir: str, ncm_dir: Optional[str] = None):
    img_idx = build_img_index(meta_img_dir)
    done, miss = 0, []

    if ncm_dir and os.path.isdir(ncm_dir):
        for ncm in tqdm(glob(os.path.join(ncm_dir, "*.ncm")), desc="处理含 NCM 的文件"):
            try:
                stem = os.path.splitext(os.path.basename(ncm))[0]
                meta = read_ncm_meta(ncm)
                if not meta:
                    continue
                tid = str(meta.get("musicId") or meta.get("musicId".lower(), ""))
                if not tid:
                    continue
                img = img_idx.get(tid)
                audio = find_matching_audio(decoded_dir, stem)
                if img and audio:
                    try:
                        embed_cover(audio, img)
                        done += 1
                    except Exception as e:
                        miss.append((audio, f"写封面失败: {e}"))
                else:
                    miss.append((stem, "找不到图片或音频"))
            except Exception as e:
                # 单首歌处理异常不影响整批继续
                log.warning(f"处理 {os.path.basename(ncm)} 时出错: {e}")
                miss.append((ncm, f"处理异常: {e}"))

    for audio in tqdm([p for p in glob(os.path.join(decoded_dir,"*")) if os.path.splitext(p)[1].lower() in (".flac",".mp3",".m4a",".alac",".aac")],
                      desc="处理无 NCM 的音频"):
        try:
            stem = os.path.splitext(os.path.basename(audio))[0]
            if os.path.splitext(audio)[1].lower()==".flac":
                try:
                    if FLAC(audio).pictures:
                        continue
                except Exception:
                    pass
            cands = make_title_artist_candidates(stem)

            length = None
            try:
                length = MFile(audio).info.length
            except Exception:
                pass

            matched = False
            for c in cands:
                try:
                    tid = search_netease_track_id(c["title"], c["artist"], length)
                except Exception as e:
                    log.warning(f"搜索 {stem} 失败: {e}")
                    tid = None
                if tid and tid in img_idx:
                    try:
                        embed_cover(audio, img_idx[tid])
                        done += 1
                    except Exception as e:
                        miss.append((audio, f"写封面失败: {e}"))
                    matched = True
                    break

            if not matched:
                miss.append((audio, "未能匹配到 trackId 或 meta 无此封面"))
        except Exception as e:
            # 单首歌处理异常不影响整批继续
            log.warning(f"处理 {os.path.basename(audio)} 时出错: {e}")
            miss.append((audio, f"处理异常: {e}"))

    log.info(f"✅ 已写入封面：{done} 首")
    if miss:
        log.info("⚠️ 以下文件未完成：")
        for a, why in miss[:50]:
            log.info(f"- {a} | {why}")
        if len(miss) > 50:
            log.info(f"... 还有 {len(miss)-50} 条省略")
    log.info("完成。")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--audios", required=True, help="已解码音频所在文件夹（你的 flac 和 mp3 文件夹）")
    ap.add_argument("--meta_imgs", required=True, help="meta 里的封面图文件夹（含 track-*.jpg）")
    ap.add_argument("--ncm_dir", default=None, help="仍然保留的 .ncm 文件夹（可选）")
    args = ap.parse_args()
    main(args.audios, args.meta_imgs, args.ncm_dir)