import os, re, json, base64, struct, binascii, logging
from glob import glob
from typing import Dict, Optional
from tqdm import tqdm

# —— 写标签用 ——
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
# —— (可选) 在线搜索 ——
import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("artwork")

def build_img_index(meta_img_dir: str) -> Dict[str, str]:
    """
    把 meta 目录里 'track-<id>.<ext>' 形式的图片建索引；若有重复(如 (1))，取文件体积更大的那张。
    支持 jpg/jpeg/png/webp。
    """
    idx: Dict[str, str] = {}
    patterns = ["track-*.jpg", "track-*.jpeg", "track-*.png", "track-*.webp"]
    for pat in patterns:
        for p in glob(os.path.join(meta_img_dir, pat)):
            fn = os.path.basename(p)
            fn = re.sub(r"\s*\(\d+\)(?=\.(jpe?g|png|webp)$)", "", fn, flags=re.I)  # 去掉(1)
            m = re.match(r"track-(\d+)\.(jpe?g|png|webp)$", fn, flags=re.I)
            if not m:
                continue
            tid = m.group(1)
            if tid not in idx or os.path.getsize(p) > os.path.getsize(idx[tid]):
                idx[tid] = p
    log.info(f"封面索引：{len(idx)} 张")
    return idx

# —— 从 .ncm 取 trackId ——
CORE_KEY = binascii.a2b_hex('687A4852416D736F356B496E62617857')
META_KEY = binascii.a2b_hex('2331346C6A6B5F215C5D2630553C2728')
def aes_ecb_decrypt(data: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend
    decryptor = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend()).decryptor()
    return decryptor.update(data) + decryptor.finalize()

def unpad(bs: bytes) -> bytes:
    pad = bs[-1] if isinstance(bs[-1], int) else ord(bs[-1])
    return bs[:-pad]

def read_ncm_meta(ncm_path: str) -> Optional[dict]:
    with open(ncm_path, "rb") as f:
        if binascii.b2a_hex(f.read(8)) != b'4354454e4644414d':
            return None
        f.seek(2, 1)
        key_len = struct.unpack('<I', f.read(4))[0]
        key_data = bytearray(f.read(key_len))
        for i in range(len(key_data)):
            key_data[i] ^= 0x64
        key_data = unpad(aes_ecb_decrypt(bytes(key_data), CORE_KEY))[17:]

        # 跳到 meta 区
        meta_len = struct.unpack('<I', f.read(4))[0]
        meta_data = bytearray(f.read(meta_len))
        for i in range(len(meta_data)):
            meta_data[i] ^= 0x63
        meta_data = base64.b64decode(bytes(meta_data)[22:])
        meta = json.loads(unpad(aes_ecb_decrypt(meta_data, META_KEY)).decode("utf-8")[6:])
        # 常见字段：musicId / musicName / artist / album 等
        return meta

def find_matching_audio(decoded_dir: str, stem: str):
    """用文件名主干匹配音频（优先 flac 其次 mp3 / m4a）"""
    for ext in (".flac", ".mp3", ".m4a", ".alac", ".aac"):
        p = os.path.join(decoded_dir, f"{stem}{ext}")
        if os.path.exists(p):
            return p
    # 宽松匹配：去掉空格与大小写
    norm = re.sub(r"\s+", "", stem).lower()
    for p in glob(os.path.join(decoded_dir, "*")):
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
    # WEBP → PNG（若装了 Pillow）
    if img_mime == "image/webp" and Image is not None:
        try:
            from io import BytesIO
            im = Image.open(img_path).convert("RGB")
            buf = BytesIO()
            im.save(buf, format="PNG")
            img_bytes = buf.getvalue()
            img_mime = "image/png"
        except Exception:
            pass

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

def _clean_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"[（(].*?[)）]", " ", s)  # 去括号内容
    s = re.sub(r"\b(feat\.?|with|＆|&)\b.*$", " ", s, flags=re.I)  # 去 feat 之后
    s = re.sub(r"[~!@#$%^&*=_+\-|\\/:;,.?·，。、《》“”\"'！【】\[\]\{\}]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s

def make_title_artist_candidates(stem: str):
    """
    从文件名生成 (title, artist) 候选：
    同时尝试 “左=歌名/右=艺人” 和 “左=艺人/右=歌名”，并做基础清洗。
    """
    s = unicodedata.normalize("NFKC", stem or "").strip()
    parts = [p.strip() for p in s.split(" - ", 1)]
    cands = []

    def _clean(s):
        return _clean_text(s)

    if len(parts) == 2:
        left, right = parts
        # 假设1：左是“歌名”、右是“艺人”
        cands.append({"title": left,  "artist": right,
                      "title_c": _clean(left),  "artist_c": _clean(right)})
        # 假设2：左是“艺人”、右是“歌名”
        cands.append({"title": right, "artist": left,
                      "title_c": _clean(right), "artist_c": _clean(left)})
    else:
        cands.append({"title": s, "artist": "", "title_c": _clean(s), "artist_c": ""})

    return cands

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

def search_netease_track_id(title: str, artist: str, want_seconds: Optional[float]) -> Optional[str]:
    """
    先 cloudsearch 再 web 接口；生成若干候选查询串；用 rapidfuzz 对文本 + 时长评分，返回最佳 id。
    """
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
        songs = (js1 or {}).get("result", {}).get("songs", []) or []
        if not songs:
            js2 = _req_json("https://music.163.com/api/search/get/web",
                            {"csrf_token": "", "type": 1, "s": q, "offset": 0, "total": "true", "limit": 10})
            songs = (js2 or {}).get("result", {}).get("songs", []) or []

        for s in songs:
            name = s.get("name", "")
            arts = s.get("ar") or s.get("artists") or []
            artists = " & ".join(a.get("name", "") for a in arts)
            dur = s.get("dt", s.get("duration", 0))
            sc = score_candidate(name, artists, dur)
            if sc > best_score:
                best_score, best_id = sc, str(s.get("id"))
        if best_score >= 90:  # 够高就早停
            break

    cutoff = 65 if want_seconds else 75
    return best_id if best_score >= cutoff else None

def guess_title_artist(stem: str):
    # 你的文件名多为 “艺术家 - 歌名”，先粗切一刀
    parts = stem.split(" - ", 1)
    if len(parts) == 2:
        artist, title = parts
    else:
        artist, title = "", stem
    # 去掉括号内附加信息
    title = re.sub(r"[（(].*?[)）]", "", title).strip()
    artist = artist.strip()
    title = unicodedata.normalize("NFKC", title).strip()
    artist = unicodedata.normalize("NFKC", artist).strip()
    return title, artist

def main(decoded_dir: str, meta_img_dir: str, ncm_dir: Optional[str] = None):
    img_idx = build_img_index(meta_img_dir)
    done, miss = 0, []

    # —— 1) 先处理有 .ncm 的 ——
    if ncm_dir and os.path.isdir(ncm_dir):
        for ncm in tqdm(glob(os.path.join(ncm_dir, "*.ncm")), desc="处理含 NCM 的文件"):
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

    # —— 2) 再处理没有 .ncm 的：尝试在线查 ID ——
    for audio in tqdm([p for p in glob(os.path.join(decoded_dir,"*")) if os.path.splitext(p)[1].lower() in (".flac",".mp3",".m4a",".alac",".aac")],
                      desc="处理无 NCM 的音频"):
        stem = os.path.splitext(os.path.basename(audio))[0]
        # 已经贴过封面就跳过（简单判断）
        if os.path.splitext(audio)[1].lower()==".flac":
            try:
                if FLAC(audio).pictures:
                    continue
            except: pass
        # 同时尝试“左=歌名/右=艺人”和“左=艺人/右=歌名”的两种顺序
        cands = make_title_artist_candidates(stem)

        length = None
        try:
            length = MFile(audio).info.length  # 秒
        except Exception:
            pass

        matched = False
        for c in cands:
            tid = search_netease_track_id(c["title"], c["artist"], length)
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