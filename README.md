# NCM解码器--导入Apple Music

网易云音乐（NCM）文件处理工具集 —— 解码、标签修复、封面嵌入、歌词集成，完美导入 Apple Music。

> **注意：** 本项目在原始开源项目的基础上进行了功能扩展和文档改进。感谢原作者的贡献。

中文版 | [Eglish](README_EN.md)
## 目录

- [快速开始](#快速开始)
- [完整工作流程](#完整工作流程)
- [核心功能](#核心功能)
- [工具说明](#工具说明)
- [依赖安装](#依赖安装)
- [常见问题](#常见问题)

---

## 快速开始

### 最小化安装

```bash
# 安装 Python 依赖
pip install -U cryptography tqdm mutagen pillow rapidfuzz requests pycryptodome

# 解码 NCM 文件
python3 ncm_universal.py "your_file.ncm" -o "/输出目录"

# 批量处理
python3 ncm_universal.py "/NCM文件目录" -o "/输出目录"
```

### GUI 模式

```bash
# 启动图形界面（包含所有功能）
python3 music_manager_gui.py
```

---

## 完整工作流程

从网易云音乐到 Apple Music 的完整流水线：

### 1. 获取音源

从网易云下载的文件类型：
- `.flac` / `.mp3` → 直接使用（无需处理）
- `.ncm` → **必须先解码**为标准格式

### 2. 解码 NCM 文件

**推荐使用：`ncm_universal.py`**（支持多种解密算法，自动降级重试）

```bash
# 单文件解码
python3 ncm_universal.py "歌曲.ncm" -o "/输出目录"

# 批量解码整个目录
python3 ncm_universal.py "/网易云音乐目录" -o "/解码后目录"
```

**特性：**
- 自动检测输出格式（FLAC/MP3/OGG/M4A）
- 三种解密算法自动回退
- 保留原始元数据（标题、艺人、专辑、封面）

**注意事项：**
- 首次解码出错时，尝试重新下载原 `.ncm` 文件
- 大批量处理建议分批进行（每次几百首）

### 3. 修复标签

#### 方式一：离线快速修复（推荐用于简单场景）

**场景：** 文件名格式为"艺人 - 歌名"但缺少内嵌标签，无需联网

```bash
# 预览修改（推荐先运行）
python3 fix_flac_tags_from_filename.py "/音频目录" --dry-run

# 写入标签（仅填充缺失字段）
python3 fix_flac_tags_from_filename.py "/音频目录"

# 强制覆盖现有标签
python3 fix_flac_tags_from_filename.py "/音频目录" --overwrite

# 自定义默认专辑名
python3 fix_flac_tags_from_filename.py "/音频目录" --default-album "我的精选集"
```

**特点：**
- ✅ 仅支持 FLAC 格式
- ✅ 完全离线操作，速度快
- ✅ 仅写入基础标签（艺人、标题、专辑）
- ✅ 从文件名解析信息

**支持的文件名分隔符：**
- `艺人 - 歌名`（半角横线）
- `艺人 – 歌名`（短横线）
- `艺人 — 歌名`（长横线）
- `艺人－歌名`（全角横线）

#### 方式二：在线完整获取（推荐用于完整专辑信息）

参见下方 [6. 获取完整专辑信息（在线）](#6-获取完整专辑信息在线)

### 4. 嵌入封面

**自动匹配策略：**

```bash
python3 attach_artwork.py \
  --audios "/音频目录" \
  --meta_imgs "/meta封面目录" \
  --ncm_dir "/原始NCM目录"  # 可选，用于提取 musicId
```

**匹配优先级：**
1. 通过 `meta/track-{musicId}.jpg` 直接匹配
2. 解析 NCM 文件提取 musicId 后匹配
3. 网易云 API 在线搜索 + 模糊匹配

**手动嵌入封面：**

```bash
# FLAC
metaflac --import-picture-from="封面.jpg" "歌曲.flac"

# MP3
eyeD3 --add-image "封面.jpg:FRONT_COVER" "歌曲.mp3"

# M4A
AtomicParsley "歌曲.m4a" --artwork "封面.jpg" --overWrite
```

### 5. 歌词处理

**获取并嵌入歌词：**

```bash
# 从网易云 API 获取歌词并自动嵌入
python3 fetch_lyrics.py "/音频目录" --ncm_dir "/NCM目录"

# 仅下载歌词文件，不嵌入
python3 fetch_lyrics.py "/音频目录" --no-embed

# 获取歌词但不包含翻译
python3 fetch_lyrics.py "/音频目录" --no-translation
```

**嵌入已有的 LRC 文件：**

```bash
# 将目录中的 .lrc 文件嵌入到对应音频
python3 embed_lyrics.py "/音频目录"

# 强制覆盖已有歌词
python3 embed_lyrics.py "/音频目录" --overwrite
```

### 6. 获取完整专辑信息（在线）

**推荐用于：** 需要完整、准确的专辑信息和歌词

```bash
# 从网易云 API 获取专辑完整元数据
python3 fetch_album_info.py "/音频目录" --ncm_dir "/NCM目录"

# 强制更新已有标签
python3 fetch_album_info.py "/音频目录" --force

# 不获取歌词
python3 fetch_album_info.py "/音频目录" --no-lyrics
```

**特点：**
- ✅ 支持多种格式（FLAC/MP3/M4A/AAC）
- ✅ 从网易云 API 获取官方数据
- ✅ 完整的标签信息（专辑、发行日期、曲目号等）
- ✅ 自动下载并保存歌词（LRC格式）
- ⚠️ 需要网络连接
- ⚠️ 每个文件间隔0.5秒（避免API限流）

### 7. 转换为 M4A（可选）

**推荐工具：XLD**（macOS GUI 应用）

**转换设置：**
- 输出格式：`Apple Lossless (ALAC)` 或 `AAC 256kbps`
- 勾选：自动添加标签 / 嵌入专辑封面 / 维持未知元数据
- 输出目录：自定义文件夹（避免覆盖原文件）

**操作步骤：**
1. 将解码后的文件夹拖入 XLD
2. 选择输出格式和目录
3. 点击"转换"

### 9. 导入 Apple Music

**导入步骤：**
1. 打开 macOS 音乐 App
2. **文件 → 导入**（或直接拖拽文件夹）
3. 在"最近添加"中查看导入结果

**启用云匹配：**
1. **设置 → 通用 → 同步资料库**（需 Apple Music 订阅）
2. 确保标题 + 艺人标签完整（专辑可选）
3. 等待自动匹配完成

**重要提示：**
> Apple Music 对 FLAC 的标签支持有限，建议转换为 M4A（ALAC/AAC）后再导入，以获得最佳元数据识别和跨设备同步体验。

---

## 核心功能

### NCM 解密系统

- **3 种解密算法**：原始算法 → RC4 算法 → 修改算法（自动降级）
- **格式自动检测**：通过魔术字节识别 FLAC/MP3/OGG/M4A
- **元数据提取**：解析 NCM 内嵌的 JSON 元数据（musicId, title, artist, album）
- **封面提取**：从 NCM 文件中提取嵌入的专辑封面

### 智能封面匹配

- **本地优先**：优先使用 meta 目录中的高质量封面
- **模糊匹配**：基于文件名和时长的智能评分系统
- **在线搜索**：网易云 API 作为后备方案
- **格式转换**：自动将 WEBP 转换为 PNG 保证兼容性

### 标签修复引擎

- **文件名解析**：支持多种分隔符格式
- **非破坏性写入**：默认仅填充缺失字段
- **批量处理**：递归扫描整个目录树
- **审计报告**：生成详细的 CSV 报告

---

## 工具说明

### `ncm_universal.py` — 通用 NCM 解码器

**功能：** 解密 NCM 文件并输出为标准音频格式

**参数：**
- `source`：输入文件或目录（必填）
- `-o, --output`：输出目录（可选，默认为源目录）

**特性：**
- 多算法自动降级
- 保留完整元数据
- 解密失败时保存调试信息到 `debug/` 目录

**示例：**
```bash
# 单文件
python3 ncm_universal.py "song.ncm" -o "/output"

# 批量处理
python3 ncm_universal.py "/ncm_folder" -o "/output"
```

---

### `attach_artwork.py` — 批量封面嵌入

**功能：** 为音频文件智能匹配并嵌入封面

**参数：**
- `--audios`：音频文件目录
- `--meta_imgs`：meta 封面目录
- `--ncm_dir`：NCM 文件目录（可选，用于提取 musicId）

**匹配逻辑：**
1. 通过 musicId 直接匹配 `track-{id}.jpg`
2. 解析 NCM 文件获取 musicId
3. 在线搜索 + 模糊匹配（评分阈值 65-75）

**示例：**
```bash
python3 attach_artwork.py \
  --audios "/decoded" \
  --meta_imgs "/meta" \
  --ncm_dir "/ncm"
```

---

### `fetch_lyrics.py` — 歌词获取

**功能：** 从网易云 API 获取歌词并嵌入到音频文件

**参数：**
- 第一个参数：音频目录
- `--ncm_dir`：NCM 目录（用于获取 musicId）
- `--no-embed`：仅下载不嵌入
- `--no-translation`：不包含翻译

**示例：**
```bash
# 获取并嵌入
python3 fetch_lyrics.py "/audios" --ncm_dir "/ncm"

# 仅下载 LRC 文件
python3 fetch_lyrics.py "/audios" --no-embed
```

---

### `embed_lyrics.py` — 歌词嵌入

**功能：** 将已有的 .lrc 文件嵌入到音频标签

**参数：**
- 第一个参数：音频目录
- `--overwrite`：强制覆盖已有歌词

**支持格式：**
- FLAC → `LYRICS` 标签
- MP3 → `USLT` 帧
- M4A → `©lyr` 原子

**示例：**
```bash
python3 embed_lyrics.py "/audios"
python3 embed_lyrics.py "/audios" --overwrite
```

---

### `fetch_album_info.py` — 专辑信息获取（在线完整）

**功能：** 从网易云 API 获取完整专辑元数据和歌词

**适用场景：** 需要完整准确的专辑信息，支持多种音频格式

**参数：**
- 第一个参数：音频目录
- `--ncm_dir`：NCM 目录（可选，用于获取 musicId）
- `--force`：强制更新已有标签
- `--no-lyrics`：不获取歌词文件

**获取字段：**
- 专辑名称、专辑艺人、发行日期
- 曲目编号、碟片号
- 专辑描述
- 歌词（保存为 .lrc 文件）

**支持格式：** FLAC, MP3, M4A, MP4, AAC

**示例：**
```bash
python3 fetch_album_info.py "/audios" --ncm_dir "/ncm"
python3 fetch_album_info.py "/audios" --force --no-lyrics
```

---

### `fix_flac_tags_from_filename.py` — 文件名标签修复（离线快速）

**功能：** 从文件名解析并写入标题/艺人标签

**适用场景：** FLAC 文件快速修复，无需网络，速度快

**参数：**
- 第一个参数：音频目录
- `--dry-run`：预览模式（不写入）
- `--overwrite`：覆盖已有标签
- `--default-album`：默认专辑名

**解析规则：**
- 格式：`艺人 - 歌名`（支持多种分隔符）
- 无分隔符时视为仅标题

**支持格式：** 仅 FLAC

**特点：** 完全离线，仅写入基础标签（artist, title, album）

**示例：**
```bash
# 预览
python3 fix_flac_tags_from_filename.py "/audios" --dry-run

# 执行
python3 fix_flac_tags_from_filename.py "/audios"

# 强制覆盖
python3 fix_flac_tags_from_filename.py "/audios" --overwrite
```

---

### `music_manager_gui.py` — 图形界面

**功能：** 提供所有功能的图形化操作界面

**特性：**
- 文件夹选择器
- 批量操作
- 进度显示
- 日志输出

**启动：**
```bash
python3 music_manager_gui.py
```

---

## 依赖安装

### Python 依赖（必需）

```bash
pip install -U cryptography tqdm mutagen pillow rapidfuzz requests pycryptodome
```

**包说明：**
- `cryptography` / `pycryptodome`：AES 解密
- `mutagen`：音频标签读写
- `pillow`：图片处理（WEBP 转换）
- `rapidfuzz`：模糊文本匹配
- `requests`：网易云 API 调用
- `tqdm`：进度条显示

### 外部工具（可选）

**命令行工具：**

```bash
# macOS (Homebrew)
brew install ffmpeg flac eye-d3 atomicparsley

# Ubuntu/Debian
apt install ffmpeg flac eyed3 atomicparsley
```

**GUI 工具：**
- **XLD**：音频格式转换（macOS）
- **MusicBrainz Picard**：自动标签识别（跨平台）

---

## 常见问题

### 解码相关

**Q: 解码时进度条变红 / 文件异常？**

A: 可能的解决方案：
1. 重新下载原始 `.ncm` 文件
2. 减少批处理数量（每次处理几百首）
3. 检查磁盘空间是否充足
4. 查看 `debug/` 目录中的调试信息

---

**Q: 解码后的音频无法播放？**

A: 检查步骤：
1. 使用 `ffmpeg -i file.flac` 验证文件完整性
2. 确认 NCM 文件未损坏（重新下载）
3. 尝试其他播放器（VLC, foobar2000）

---

### 标签相关

**Q: 导入 Apple Music 后只显示文件名？**

A: 原因是缺少内嵌标签，解决方法：
1. 运行 `fix_flac_tags_from_filename.py` 修复标签
2. 或使用 MusicBrainz Picard 自动识别
3. 确保文件名格式为"艺人 - 歌名"

---

**Q: Apple Music 无法匹配云曲库？**

A: 检查清单：
- ✓ 标题 + 艺人标签已填写
- ✓ 已开启"同步资料库"（需订阅）
- ✓ 专辑名可选但有助提高命中率
- ✓ 文件格式为 M4A（FLAC 支持有限）

---

### 封面相关

**Q: 封面没有成功嵌入？**

A: 排查步骤：
1. 确认图片文件存在且格式正确
2. 检查音频文件是否可写（权限问题）
3. 使用手动命令测试：
   ```bash
   metaflac --import-picture-from="cover.jpg" "test.flac"
   ```
4. 查看脚本输出的匹配日志

---

**Q: 封面质量不佳 / 分辨率低？**

A: 优化方案：
1. 使用 meta 目录中的高质量封面
2. 手动从网易云网页版下载封面（右键保存）
3. 使用 MusicBrainz Picard 获取官方封面

---

### 歌词相关

**Q: 获取歌词失败？**

A: 可能原因：
1. 网易云 API 速率限制（等待后重试）
2. 歌曲无歌词或仅 VIP 可用
3. 网络连接问题
4. musicId 提取失败（需提供 NCM 目录）

---

**Q: 歌词嵌入后 Apple Music 不显示？**

A: 说明：
- Apple Music 对嵌入式歌词支持有限
- 优先使用云端歌词（需匹配曲库）
- M4A 格式支持比 FLAC 更好

---

### 性能相关

**Q: 处理速度很慢？**

A: 优化建议：
1. 在线搜索封面/歌词时会受网络影响
2. 使用本地 meta 目录可显著提速
3. XLD 转码建议在本地磁盘（非网络驱动器）
4. 分批处理大量文件

---

**Q: Apple Music 同步很慢？**

A: 正常现象：
- 云匹配需要时间（取决于曲库大小）
- 网络节点和时段影响速度
- 稍后重试通常可恢复
- 可以先导入少量测试

---

### 其他问题

**Q: 如何批量处理大量文件？**

A: 推荐流程：
```bash
# 1. 解码
python3 ncm_universal.py "/ncm" -o "/decoded"

# 2. 离线快速修复标签（FLAC）
python3 fix_flac_tags_from_filename.py "/decoded"

# 3. 在线获取完整专辑信息（可选，需要完整信息时使用）
python3 fetch_album_info.py "/decoded" --ncm_dir "/ncm"

# 4. 嵌入封面
python3 attach_artwork.py --audios "/decoded" --meta_imgs "/meta"

# 5. 嵌入歌词（如果使用了步骤3，已自动获取.lrc文件）
python3 embed_lyrics.py "/decoded"

# 6. 转换格式（XLD GUI）
# 7. 导入 Apple Music
```

---

**Q: 如何只处理部分文件？**

A: 方法：
1. 创建子目录分批处理
2. 使用 `--dry-run` 预览后手动筛选
3. 使用音乐管理软件（如MusicBee、foobar2000）查看标签后针对性处理

---

## 技术细节

### NCM 文件结构

```
+0x00: 文件头 "CTENFDAM" (8 字节)
+0x08: 跳过 2 字节
+0x0A: 密钥长度 (4 字节) + 加密密钥
+xxxx: 元数据长度 (4 字节) + 加密元数据 (JSON)
+xxxx: CRC32 (4 字节)
+xxxx: 未知数据 (5 字节)
+xxxx: 封面大小 (4 字节) + 封面数据
+xxxx: 加密音频数据
```

### 解密密钥

```python
import binascii
CORE_KEY = binascii.a2b_hex('687A4852416D736F356B496E62617857')
META_KEY = binascii.a2b_hex('2331346C6A6B5F215C5D2630553C2728')
```

### 支持的音频格式

| 格式 | 读取 | 写入 | 封面 | 歌词 | Apple Music |
|------|------|------|------|------|-------------|
| FLAC | ✓    | ✓    | ✓    | ✓    | 有限支持    |
| MP3  | ✓    | ✓    | ✓    | ✓    | ✓           |
| M4A  | ✓    | ✓    | ✓    | ✓    | ✓ 推荐      |
| AAC  | ✓    | ✓    | ✓    | ✓    | ✓           |

---

## 许可证

请查看项目根目录中的 LICENSE 文件。

---

## 贡献

欢迎提交 Issue 和 Pull Request！

---

## 致谢

本项目基于开源社区的 NCM 解码项目进行改进和功能扩展，特别感谢：

- 原始 NCM 解密算法的贡献者
- 所有为音频处理工具链做出贡献的开发者
- 网易云音乐 API 逆向工程的研究者

### 本项目的改进

- 📝 **完善的中文文档**：详细的使用说明和常见问题解答
- 🎵 **歌词处理功能**：支持从网易云 API 获取和嵌入歌词
- 🎨 **智能封面匹配**：优化的封面匹配算法和多种匹配策略
- 📊 **标签审计工具**：生成详细的缺失标签报告
- 🖥️ **GUI 界面**：提供图形化操作界面
- 🔧 **增强的工具集**：专辑信息获取、元数据查看等实用工具

欢迎提交 Issue 和 Pull Request 继续改进本项目！