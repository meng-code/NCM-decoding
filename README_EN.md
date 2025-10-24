# NCM Decoder -- Import to Apple Music

NetEase Cloud Music (NCM) file processing toolkit - Decode, tag repair, cover embedding, lyrics integration for Apple Music.

[中文版](README.md) | English

## Quick Start

### Minimal Installation

```bash
# Install Python dependencies
pip install -U cryptography tqdm mutagen pillow rapidfuzz requests pycryptodome

# Decode NCM file
python3 ncm_universal.py "your_file.ncm" -o "/output_dir"

# Batch processing
python3 ncm_universal.py "/NCM_directory" -o "/output_dir"
```

### GUI Mode

```bash
# Launch graphical interface
python3 music_manager_gui.py
```

---

## Complete Workflow

Complete pipeline from NetEase Cloud Music to Apple Music:

### 1. Get Audio Source

Downloaded file types from NetEase Cloud:
- `.flac` / `.mp3` → Use directly (no processing needed)
- `.ncm` → **Must decode first** to standard format

### 2. Decode NCM Files

**Recommended: `ncm_universal.py`** (supports multiple decryption algorithms with auto fallback)

```bash
# Single file decode
python3 ncm_universal.py "song.ncm" -o "/output_dir"

# Batch decode entire directory
python3 ncm_universal.py "/netease_music_dir" -o "/decoded_dir"
```

**Features:**
- Auto-detect output format (FLAC/MP3/OGG/M4A)
- Three decryption algorithms with auto fallback
- Preserve original metadata (title, artist, album, cover)

**Notes:**
- If decoding fails, try re-downloading the original `.ncm` file
- For large batches, process in groups (few hundred at a time)

### 3. Fix Tags

#### Method 1: Offline Quick Fix (for simple cases)

**Use case:** Filename format is "Artist - Song" but lacks embedded tags, no internet required

```bash
# Preview changes (recommended)
python3 fix_flac_tags_from_filename.py "/audio_dir" --dry-run

# Write tags (only fill missing fields)
python3 fix_flac_tags_from_filename.py "/audio_dir"

# Force overwrite existing tags
python3 fix_flac_tags_from_filename.py "/audio_dir" --overwrite

# Custom default album name
python3 fix_flac_tags_from_filename.py "/audio_dir" --default-album "My Collection"
```

**Features:**
- ✅ FLAC format only
- ✅ Completely offline, fast
- ✅ Only writes basic tags (artist, title, album)
- ✅ Parses info from filename

**Supported filename separators:**
- `Artist - Song` (half-width dash)
- `Artist – Song` (en dash)
- `Artist — Song` (em dash)
- `Artist－Song` (full-width dash)

#### Method 2: Online Complete Fetch

See [6. Get Complete Album Info (Online)](#6-get-complete-album-info-online)

### 4. Embed Cover

**Auto-matching strategy:**

```bash
python3 attach_artwork.py \
  --audios "/audio_dir" \
  --meta_imgs "/meta_cover_dir" \
  --ncm_dir "/original_NCM_dir"  # Optional, for extracting musicId
```

**Matching priority:**
1. Direct match via `meta/track-{musicId}.jpg`
2. Parse NCM file to extract musicId then match
3. NetEase Cloud API online search + fuzzy matching

**Manual cover embedding:**

```bash
# FLAC
metaflac --import-picture-from="cover.jpg" "song.flac"

# MP3
eyeD3 --add-image "cover.jpg:FRONT_COVER" "song.mp3"

# M4A
AtomicParsley "song.m4a" --artwork "cover.jpg" --overWrite
```

### 5. Lyrics Processing

**Fetch and embed lyrics:**

```bash
# Fetch lyrics from NetEase Cloud API and auto-embed
python3 fetch_lyrics.py "/audio_dir" --ncm_dir "/NCM_dir"

# Download lyrics only, don't embed
python3 fetch_lyrics.py "/audio_dir" --no-embed

# Fetch lyrics without translation
python3 fetch_lyrics.py "/audio_dir" --no-translation
```

**Embed existing LRC files:**

```bash
# Embed .lrc files into corresponding audio
python3 embed_lyrics.py "/audio_dir"

# Force overwrite existing lyrics
python3 embed_lyrics.py "/audio_dir" --overwrite
```

### 6. Get Complete Album Info (Online)

**Recommended for:** Complete and accurate album information and lyrics

```bash
# Fetch complete album metadata from NetEase Cloud API
python3 fetch_album_info.py "/audio_dir" --ncm_dir "/NCM_dir"

# Force update existing tags
python3 fetch_album_info.py "/audio_dir" --force

# Don't fetch lyrics
python3 fetch_album_info.py "/audio_dir" --no-lyrics
```

**Features:**
- ✅ Supports multiple formats (FLAC/MP3/M4A/AAC)
- ✅ Fetches official data from NetEase Cloud API
- ✅ Complete tag info (album, release date, track number, etc.)
- ✅ Auto-download and save lyrics (LRC format)
- ⚠️ Requires internet connection
- ⚠️ 0.5s delay per file (avoid API rate limiting)

### 7. Convert to M4A (Optional)

**Recommended tool: XLD** (macOS GUI app)

**Conversion settings:**
- Output format: `Apple Lossless (ALAC)` or `AAC 256kbps`
- Check: Auto-add tags / Embed album artwork / Maintain unknown metadata
- Output directory: Custom folder (avoid overwriting originals)

**Steps:**
1. Drag decoded folder into XLD
2. Select output format and directory
3. Click "Convert"

### 9. Import to Apple Music

**Import steps:**
1. Open macOS Music app
2. **File → Import** (or drag folder directly)
3. Check import results in "Recently Added"

**Enable cloud matching:**
1. **Settings → General → Sync Library** (requires Apple Music subscription)
2. Ensure title + artist tags are complete (album optional)
3. Wait for auto-matching

**Important:**
> Apple Music has limited FLAC tag support. Recommend converting to M4A (ALAC/AAC) before importing for best metadata recognition and cross-device sync.

---

## Core Features

### NCM Decryption System

- **3 decryption algorithms**: Original → RC4 → Modified (auto fallback)
- **Format auto-detection**: Identify FLAC/MP3/OGG/M4A via magic bytes
- **Metadata extraction**: Parse embedded JSON metadata (musicId, title, artist, album)
- **Cover extraction**: Extract embedded album artwork from NCM files

### Smart Cover Matching

- **Local priority**: Use high-quality covers from meta directory first
- **Fuzzy matching**: Smart scoring based on filename and duration
- **Online search**: NetEase Cloud API as fallback
- **Format conversion**: Auto-convert WEBP to PNG for compatibility

### Tag Repair Engine

- **Filename parsing**: Support multiple separator formats
- **Non-destructive write**: Only fill missing fields by default
- **Batch processing**: Recursive scan entire directory tree
- **Audit report**: Generate detailed CSV reports

---

## Tool Description

### `ncm_universal.py` — Universal NCM Decoder

**Function:** Decrypt NCM files and output to standard audio format

**Parameters:**
- `source`: Input file or directory (required)
- `-o, --output`: Output directory (optional, defaults to source directory)

**Features:**
- Multi-algorithm auto fallback
- Preserve complete metadata
- Save debug info to `debug/` directory on failure

**Examples:**
```bash
# Single file
python3 ncm_universal.py "song.ncm" -o "/output"

# Batch processing
python3 ncm_universal.py "/ncm_folder" -o "/output"
```

---

### `attach_artwork.py` — Batch Cover Embedding

**Function:** Smart match and embed covers for audio files

**Parameters:**
- `--audios`: Audio file directory
- `--meta_imgs`: Meta cover directory
- `--ncm_dir`: NCM file directory (optional, for extracting musicId)

**Matching logic:**
1. Direct match via musicId to `track-{id}.jpg`
2. Parse NCM file to get musicId
3. Online search + fuzzy matching (score threshold 65-75)

**Example:**
```bash
python3 attach_artwork.py \
  --audios "/decoded" \
  --meta_imgs "/meta" \
  --ncm_dir "/ncm"
```

---

### `fetch_lyrics.py` — Lyrics Fetching

**Function:** Fetch lyrics from NetEase Cloud API and embed into audio files

**Parameters:**
- First argument: Audio directory
- `--ncm_dir`: NCM directory (for getting musicId)
- `--no-embed`: Download only, don't embed
- `--no-translation`: Exclude translation

**Example:**
```bash
# Fetch and embed
python3 fetch_lyrics.py "/audios" --ncm_dir "/ncm"

# Download LRC files only
python3 fetch_lyrics.py "/audios" --no-embed
```

---

### `embed_lyrics.py` — Lyrics Embedding

**Function:** Embed existing .lrc files into audio tags

**Parameters:**
- First argument: Audio directory
- `--overwrite`: Force overwrite existing lyrics

**Supported formats:**
- FLAC → `LYRICS` tag
- MP3 → `USLT` frame
- M4A → `©lyr` atom

**Example:**
```bash
python3 embed_lyrics.py "/audios"
python3 embed_lyrics.py "/audios" --overwrite
```

---

### `fetch_album_info.py` — Album Info Fetching (Online Complete)

**Function:** Fetch complete album metadata and lyrics from NetEase Cloud API

**Use case:** Need complete and accurate album info, supports multiple audio formats

**Parameters:**
- First argument: Audio directory
- `--ncm_dir`: NCM directory (optional, for getting musicId)
- `--force`: Force update existing tags
- `--no-lyrics`: Don't fetch lyrics

**Fields retrieved:**
- Album name, album artist, release date
- Track number, disc number
- Album description
- Lyrics (save as .lrc files)

**Supported formats:** FLAC, MP3, M4A, MP4, AAC

**Example:**
```bash
python3 fetch_album_info.py "/audios" --ncm_dir "/ncm"
python3 fetch_album_info.py "/audios" --force --no-lyrics
```

---

### `fix_flac_tags_from_filename.py` — Filename Tag Repair (Offline Quick)

**Function:** Parse and write title/artist tags from filename

**Use case:** Quick FLAC file fix, no internet needed, fast

**Parameters:**
- First argument: Audio directory
- `--dry-run`: Preview mode (don't write)
- `--overwrite`: Overwrite existing tags
- `--default-album`: Default album name

**Parsing rules:**
- Format: `Artist - Song` (supports multiple separators)
- Without separator treats as title only

**Supported format:** FLAC only

**Features:** Completely offline, only writes basic tags (artist, title, album)

**Example:**
```bash
# Preview
python3 fix_flac_tags_from_filename.py "/audios" --dry-run

# Execute
python3 fix_flac_tags_from_filename.py "/audios"

# Force overwrite
python3 fix_flac_tags_from_filename.py "/audios" --overwrite
```

---

### `music_manager_gui.py` — Graphical Interface

**Function:** Graphical interface for all functions

**Features:**
- Folder selector
- Batch operations
- Progress display
- Log output

**Launch:**
```bash
python3 music_manager_gui.py
```

---

## Dependencies

### Python Dependencies (Required)

```bash
pip install -U cryptography tqdm mutagen pillow rapidfuzz requests pycryptodome
```

**Package descriptions:**
- `cryptography` / `pycryptodome`: AES decryption
- `mutagen`: Audio tag read/write
- `pillow`: Image processing (WEBP conversion)
- `rapidfuzz`: Fuzzy text matching
- `requests`: NetEase Cloud API calls
- `tqdm`: Progress bar display

### External Tools (Optional)

**Command line tools:**

```bash
# macOS (Homebrew)
brew install ffmpeg flac eye-d3 atomicparsley

# Ubuntu/Debian
apt install ffmpeg flac eyed3 atomicparsley
```

**GUI tools:**
- **XLD**: Audio format conversion (macOS)
- **MusicBrainz Picard**: Auto tag recognition (cross-platform)

---

## FAQ

### Decoding Related

**Q: Progress bar turns red / file abnormal during decoding?**

A: Possible solutions:
1. Re-download original `.ncm` file
2. Reduce batch size (process few hundred at a time)
3. Check disk space
4. Check debug info in `debug/` directory

---

**Q: Decoded audio won't play?**

A: Check steps:
1. Verify file integrity with `ffmpeg -i file.flac`
2. Confirm NCM file is not corrupted (re-download)
3. Try other players (VLC, foobar2000)

---

### Tag Related

**Q: Only shows filename after importing to Apple Music?**

A: Missing embedded tags, solutions:
1. Run `fix_flac_tags_from_filename.py` to fix tags
2. Or use MusicBrainz Picard for auto-recognition
3. Ensure filename format is "Artist - Song"

---

**Q: Apple Music can't match cloud library?**

A: Checklist:
- ✓ Title + artist tags filled
- ✓ "Sync Library" enabled (requires subscription)
- ✓ Album name optional but helps hit rate
- ✓ File format is M4A (FLAC has limited support)

---

### Cover Related

**Q: Cover didn't embed successfully?**

A: Troubleshooting:
1. Confirm image file exists and format is correct
2. Check audio file is writable (permission issue)
3. Test with manual command:
   ```bash
   metaflac --import-picture-from="cover.jpg" "test.flac"
   ```
4. Check script output for matching logs

---

**Q: Cover quality poor / low resolution?**

A: Optimization:
1. Use high-quality covers from meta directory
2. Manually download covers from NetEase Cloud web (right-click save)
3. Use MusicBrainz Picard to get official covers

---

### Lyrics Related

**Q: Lyrics fetch failed?**

A: Possible reasons:
1. NetEase Cloud API rate limit (wait and retry)
2. Song has no lyrics or VIP only
3. Network connection issue
4. musicId extraction failed (need to provide NCM directory)

---

**Q: Lyrics don't show in Apple Music after embedding?**

A: Note:
- Apple Music has limited embedded lyrics support
- Prioritizes cloud lyrics (requires library match)
- M4A format has better support than FLAC

---

### Performance Related

**Q: Processing very slow?**

A: Optimization tips:
1. Online cover/lyrics search affected by network
2. Using local meta directory significantly speeds up
3. XLD transcoding recommended on local disk (not network drive)
4. Process large batches in groups

---

**Q: Apple Music sync slow?**

A: Normal:
- Cloud matching takes time (depends on library size)
- Network node and time affect speed
- Retry later usually recovers
- Can import small test batch first

---

### Other Issues

**Q: How to batch process large number of files?**

A: Recommended workflow:
```bash
# 1. Decode
python3 ncm_universal.py "/ncm" -o "/decoded"

# 2. Offline quick tag fix (FLAC)
python3 fix_flac_tags_from_filename.py "/decoded"

# 3. Online complete album info (optional, when complete info needed)
python3 fetch_album_info.py "/decoded" --ncm_dir "/ncm"

# 4. Embed covers
python3 attach_artwork.py --audios "/decoded" --meta_imgs "/meta"

# 5. Embed lyrics (if using step 3, .lrc files already fetched)
python3 embed_lyrics.py "/decoded"

# 6. Convert format (XLD GUI)
# 7. Import to Apple Music
```

---

**Q: How to process only some files?**

A: Methods:
1. Create subdirectories for batch processing
2. Use `--dry-run` to preview then manually filter
3. Use music management software (MusicBee, foobar2000) to view tags then target processing

---

## Technical Details

### NCM File Structure

```
+0x00: File header "CTENFDAM" (8 bytes)
+0x08: Skip 2 bytes
+0x0A: Key length (4 bytes) + encrypted key
+xxxx: Metadata length (4 bytes) + encrypted metadata (JSON)
+xxxx: CRC32 (4 bytes)
+xxxx: Unknown data (5 bytes)
+xxxx: Cover size (4 bytes) + cover data
+xxxx: Encrypted audio data
```

### Decryption Keys

```python
import binascii
CORE_KEY = binascii.a2b_hex('687A4852416D736F356B496E62617857')
META_KEY = binascii.a2b_hex('2331346C6A6B5F215C5D2630553C2728')
```

### Supported Audio Formats

| Format | Read | Write | Cover | Lyrics | Apple Music |
|--------|------|-------|-------|--------|-------------|
| FLAC   | ✓    | ✓     | ✓     | ✓      | Limited     |
| MP3    | ✓    | ✓     | ✓     | ✓      | ✓           |
| M4A    | ✓    | ✓     | ✓     | ✓      | ✓ Recommended |
| AAC    | ✓    | ✓     | ✓     | ✓      | ✓           |

---

## License

Please check the LICENSE file in project root.

---

## Contributing

Issues and Pull Requests welcome!

---

## Acknowledgments

This project builds upon open-source NCM decoding projects with improvements and feature additions. Special thanks to:

- Contributors of original NCM decryption algorithms
- All developers contributing to audio processing toolchains
- NetEase Cloud Music API reverse engineering researchers

### This Project's Improvements

- 📝 **Complete documentation**: Detailed usage instructions and FAQ
- 🎵 **Lyrics processing**: Support for fetching and embedding lyrics from NetEase Cloud API
- 🎨 **Smart cover matching**: Optimized cover matching algorithm and multiple matching strategies
- 📊 **Tag audit tools**: Generate detailed missing tag reports
- 🖥️ **GUI interface**: Graphical operation interface
- 🔧 **Enhanced toolset**: Album info fetching, metadata viewing and other utilities

Issues and Pull Requests welcome to continue improving this project!
