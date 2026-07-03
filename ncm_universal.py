#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import base64
import struct
import binascii
from pathlib import Path
from Crypto.Cipher import AES


class NCMUniversalDecoder:
    CORE_KEY = binascii.a2b_hex('687A4852416D736F356B496E62617857')
    META_KEY = binascii.a2b_hex('2331346C6A6B5F215C5D2630553C2728')

    @staticmethod
    def unpad(s):
        if not s:
            return s
        padding = s[-1] if isinstance(s[-1], int) else ord(s[-1])
        # padding==0 时 s[:-0] 会退化成空串，需与 padding>len 一样原样返回
        if padding > len(s) or padding == 0:
            return s
        return s[:-padding]

    def detect_format(self, data):
        if len(data) < 4:
            return None

        if data[:4] == b'fLaC':
            return 'flac'
        elif data[:3] == b'ID3':
            return 'mp3'
        elif data[0:1] == b'\xff' and (data[1:2][0] & 0xe0) == 0xe0:
            return 'mp3'
        elif data[:4] == b'OggS':
            return 'ogg'
        elif data[:4] == b'RIFF':
            return 'wav'
        elif len(data) > 8 and data[4:8] == b'ftyp':
            return 'm4a'

        return None

    def try_decode_method1(self, key_box, data):
        result = bytearray(data)
        for i in range(len(result)):
            j = (i + 1) & 0xff
            result[i] ^= key_box[(key_box[j] + key_box[(key_box[j] + j) & 0xff]) & 0xff]
        return bytes(result)

    def try_decode_method2(self, key_box, data, offset=0):
        result = bytearray(data)
        i = 0
        j = 0

        for k in range(len(result)):
            i = (i + 1) & 0xff
            j = (j + key_box[i]) & 0xff
            key_box[i], key_box[j] = key_box[j], key_box[i]
            result[k] ^= key_box[(key_box[i] + key_box[j]) & 0xff]

        return bytes(result)

    def try_decode_method3(self, key_box, data):
        result = bytearray(data)

        for i in range(len(result)):
            idx = i & 0xff
            k = key_box[idx]
            j = (k + idx) & 0xff
            result[i] ^= key_box[j]

        return bytes(result)

    def _has_audio_signature_loose(self, data):
        """宽松验证：粗扫描用，只检查魔术字节"""
        if len(data) < 4:
            return False
        if data[:4] == b'fLaC':
            return True
        if data[:3] == b'ID3':
            return True
        if data[0] == 0xff and (data[1] & 0xe0) == 0xe0:
            return True
        if len(data) >= 8 and data[4:8] == b'ftyp':
            return True
        if data[:4] == b'OggS':
            return True
        return False

    def _has_audio_signature_strict(self, data):
        """严格验证：精细搜索用，验证完整的格式头结构"""
        if len(data) < 16:
            return False

        # FLAC: fLaC + 合法 STREAMINFO (block_type=0, size=34)
        if data[:4] == b'fLaC':
            block_type = data[4] & 0x7f
            block_size = (data[5] << 16) | (data[6] << 8) | data[7]
            return block_type == 0 and block_size == 34

        # MP3 ID3v2 标签
        if data[:3] == b'ID3':
            return data[3] < 5  # 合法版本号

        # MP3 同步帧
        if data[0] == 0xff and (data[1] & 0xe0) == 0xe0:
            version = (data[1] >> 3) & 0x03
            layer = (data[1] >> 1) & 0x03
            return layer != 0 and version != 1

        # M4A
        if len(data) >= 8 and data[4:8] == b'ftyp':
            return True

        # OGG
        if data[:4] == b'OggS' and data[4] == 0:
            return True

        return False

    # 各格式的魔术签名：(magic 字节, magic 在音频起点内的偏移)
    # 大多数格式魔术在音频第 0 字节；M4A 的 'ftyp' 在第 4 字节（前 4 字节是 box 长度）
    _AUDIO_SIGNATURES = [
        (b'fLaC\x00\x00\x00\x22', 0),  # FLAC + STREAMINFO 块头（block_type=0, size=34），最强
        (b'fLaC', 0),                  # FLAC 回退
        (b'OggS', 0),                  # OGG
        (b'ID3', 0),                   # MP3 (ID3v2)
        (b'ftyp', 4),                  # M4A/MP4（'ftyp' 位于第 4 字节）
    ]

    def _keystream(self, method_func, key_box_original, n):
        """
        取某解密方法从音频起点(keystream 索引 0)开始的前 n 字节 keystream。
        原理：对全零字节解密，result[i] = 0 ^ keystream[i] = keystream[i]。
        对 method1/method3（无状态）与 method2（RC4，前 n 字节确定）均成立。
        """
        return method_func(bytearray(key_box_original), bytes(n))

    def find_audio_start_recovery(self, ncm_path, key_box_original):
        """
        恢复模式：当文件结构损坏（如音频起始偏移被错误读取）时，
        在整个文件中搜索正确的音频起始位置。

        做法：利用 keystream 只依赖字节索引这一特性，反向计算"密文指纹"
        （魔术字节 XOR keystream），用 bytes.find() 在全文件做 C 级快速搜索。
        相比逐字节试解密，这能覆盖任意（非对齐）起点且快得多。

        Args:
            ncm_path: NCM 文件路径
            key_box_original: 已解密的原始 key_box

        Returns:
            (audio_start, method_func, detected_format) 或 (None, None, None)
        """
        file_size = os.path.getsize(ncm_path)

        methods = [
            ("方法1 (原始)", self.try_decode_method1),
            ("方法2 (RC4)", self.try_decode_method2),
            ("方法3 (新版)", self.try_decode_method3),
        ]

        print(f"  🔧 进入恢复模式：全文件搜索正确的音频起始位置")
        print(f"     （文件大小 {file_size / 1024:.1f} KB）")

        with open(ncm_path, 'rb') as f:
            data = f.read()

        # 音频通常不会紧贴文件头；限定一个合理的下限避免误命中头部结构
        min_start = 10

        for method_name, method_func in methods:
            # 预计算该方法的 keystream（够长即可覆盖所有签名 + 偏移）
            ks = self._keystream(method_func, key_box_original, 32)

            for magic, magic_off in self._AUDIO_SIGNATURES:
                # 指纹 = 魔术字节 XOR 对应位置的 keystream
                fingerprint = bytes(
                    magic[i] ^ ks[magic_off + i] for i in range(len(magic))
                )

                # 全文件搜索该指纹的所有出现位置（短指纹可能有假阳性，逐个严格验证）
                search_from = 0
                while True:
                    hit = data.find(fingerprint, search_from)
                    if hit < 0:
                        break
                    search_from = hit + 1

                    audio_start = hit - magic_off
                    if audio_start < min_start or audio_start >= file_size:
                        continue

                    # 严格验证：从候选起点实际解密 64 字节，确认是合法音频头
                    seg = data[audio_start:audio_start + 64]
                    if len(seg) < 16:
                        continue
                    decrypted = method_func(bytearray(key_box_original), seg)
                    if self._has_audio_signature_strict(decrypted):
                        detected = self.detect_format(decrypted)
                        print(f"  ✅ 恢复成功！正确起始: 0x{audio_start:x}, "
                              f"格式: {detected} ({method_name})")
                        return audio_start, method_func, detected

        print(f"  ❌ 恢复模式失败：未能定位有效的音频起始位置")
        return None, None, None

    def preflight_check(self, ncm_path):
        """
        文件完整性预检查
        返回 (是否通过, 失败原因)
        失败原因可能是：
          - 'too_small'         文件太小，疑似下载不完整
          - 'bad_header'        文件头损坏，疑似下载错误或文件类型错误
          - 'truncated'         文件被截断
          - 'invalid_struct'    结构损坏（key/meta/image 长度异常）
          - 'corrupt_offset'    音频偏移异常（中间段损坏，需要重下）
        """
        try:
            file_size = os.path.getsize(ncm_path)

            # NCM 文件最小约 50KB（包含头、密钥、元数据、封面、少量音频）
            if file_size < 1024:
                return False, 'too_small'

            with open(ncm_path, 'rb') as f:
                # 检查文件头
                header = f.read(8)
                if binascii.b2a_hex(header) != b'4354454e4644414d':
                    return False, 'bad_header'

                # 检查关键结构是否完整
                f.seek(2, 1)
                try:
                    key_length = struct.unpack('<I', f.read(4))[0]
                except struct.error:
                    return False, 'truncated'

                # 密钥长度异常（正常范围约 100-300 字节）
                if key_length == 0 or key_length > 10000:
                    return False, 'invalid_struct'

                # 检查文件是否包含完整的密钥数据
                if 14 + key_length > file_size:
                    return False, 'truncated'

                f.seek(key_length, 1)
                try:
                    meta_length = struct.unpack('<I', f.read(4))[0]
                except struct.error:
                    return False, 'truncated'

                # 元数据长度异常（正常范围约 0-10000 字节）
                if meta_length > 100000:
                    return False, 'invalid_struct'

                # 检查文件是否包含完整的元数据
                if 18 + key_length + meta_length > file_size:
                    return False, 'truncated'

                # 跳过元数据 + CRC(4) + 保留(5) 后读取封面长度
                f.seek(meta_length + 4 + 5, 1)
                try:
                    image_size = struct.unpack('<I', f.read(4))[0]
                except struct.error:
                    return False, 'truncated'

                # 封面长度异常（正常 50KB-2MB，单图最大也很少超过 50MB）
                if image_size > 50 * 1024 * 1024:
                    return False, 'invalid_struct'

                # 计算音频起始位置：8(header) + 2(gap) + 4(keylen) + key_length
                #   + 4(metalen) + meta_length + 4(CRC) + 5(gap) + 4(imglen) + image_size
                #   = 31 + key_length + meta_length + image_size
                audio_start = 31 + key_length + meta_length + image_size

                # 检查音频起始位置是否在文件范围内
                if audio_start >= file_size:
                    return False, 'truncated'

                # 检查音频数据剩余大小是否合理
                # FLAC 文件至少要有几 KB 才算正常的音乐
                audio_size = file_size - audio_start
                if audio_size < 10 * 1024:
                    return False, 'corrupt_offset'

                # 关键：检测"结构异常但大小正常"的情况
                # 如果元数据声明了格式（说明前段是好的），但封面/音频偏移不合理：
                # 正常 NCM 文件应该带封面，封面通常 50KB-2MB
                # 如果封面 < 1KB 但文件 > 1MB，说明中间段数据错乱
                if file_size > 1024 * 1024 and image_size < 1024 and audio_start < 10240:
                    return False, 'corrupt_offset'

            return True, None

        except Exception as e:
            return False, f'check_error: {e}'

    def decode(self, ncm_path, output_dir=None):
        ncm_path = Path(ncm_path)
        if not ncm_path.exists() or not ncm_path.suffix == '.ncm':
            print(f"❌ 无效的NCM文件: {ncm_path}")
            return False

        if output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            debug_dir = output_dir / 'debug'
            debug_dir.mkdir(exist_ok=True)
        else:
            output_dir = ncm_path.parent
            debug_dir = output_dir / 'debug'
            debug_dir.mkdir(exist_ok=True)

        # 文件完整性预检查
        ok, reason = self.preflight_check(ncm_path)
        # corrupt_offset 是可恢复的错误，发出警告但继续解码
        # 后续如果三种算法都失败，会自动启用恢复模式
        if not ok and reason != 'corrupt_offset':
            file_size = os.path.getsize(ncm_path) if ncm_path.exists() else 0
            print(f"❌ 文件完整性检查失败: {ncm_path.name}")
            print(f"   文件大小: {file_size / 1024:.1f} KB")
            if reason == 'too_small':
                print(f"   原因: 文件太小（< 1KB），疑似下载未完成")
                print(f"   💡 建议: 删除此文件并重新下载")
            elif reason == 'bad_header':
                print(f"   原因: 文件头损坏或不是 NCM 格式")
                print(f"   💡 建议: 确认文件是 .ncm 格式，或重新下载")
            elif reason == 'truncated':
                print(f"   原因: 文件被截断（下载不完整）")
                print(f"   💡 建议: 删除此文件并重新下载（这是常见问题）")
            elif reason == 'invalid_struct':
                print(f"   原因: 文件结构异常（长度字段不合理）")
                print(f"   💡 建议: 重新下载，如果多次失败请联系开发者")
            else:
                print(f"   原因: {reason}")
            return False

        if not ok and reason == 'corrupt_offset':
            print(f"⚠️ 检测到文件结构异常（封面/音频偏移损坏），将启用自动恢复模式...")

        try:
            with open(ncm_path, 'rb') as f:
                # 跳过头部和保留字节（已在 preflight 中验证）
                f.read(8)

                print(f"处理文件: {ncm_path.name}")

                f.seek(2, 1)

                key_length = struct.unpack('<I', f.read(4))[0]
                print(f"  密钥长度: {key_length} 字节")

                key_data = bytearray(f.read(key_length))
                for i in range(len(key_data)):
                    key_data[i] ^= 0x64

                cipher = AES.new(self.CORE_KEY, AES.MODE_ECB)
                key_data = self.unpad(cipher.decrypt(bytes(key_data)))
                key_data = key_data[17:]

                key_box_original = bytearray(range(256))
                c = 0
                last_byte = 0
                key_offset = 0

                for i in range(256):
                    swap = key_box_original[i]
                    c = (swap + last_byte + key_data[key_offset]) & 0xff
                    key_offset += 1
                    if key_offset >= len(key_data):
                        key_offset = 0
                    key_box_original[i] = key_box_original[c]
                    key_box_original[c] = swap
                    last_byte = c

                meta_length = struct.unpack('<I', f.read(4))[0]
                output_format = 'mp3'

                if meta_length > 0:
                    meta_data = bytearray(f.read(meta_length))
                    for i in range(len(meta_data)):
                        meta_data[i] ^= 0x63

                    try:
                        meta_data = base64.b64decode(bytes(meta_data)[22:])
                        cipher = AES.new(self.META_KEY, AES.MODE_ECB)
                        meta_data = self.unpad(cipher.decrypt(meta_data))
                        meta_json = json.loads(meta_data.decode('utf-8')[6:])
                        output_format = meta_json.get('format', 'mp3')
                        print(f"  元数据格式: {output_format}")
                    except:
                        print(f"  ⚠️ 无法解析元数据，使用默认格式")

                f.seek(4, 1)
                f.seek(5, 1)
                image_size = struct.unpack('<I', f.read(4))[0]
                if image_size > 0:
                    f.seek(image_size, 1)

                audio_start = f.tell()
                print(f"  音频起始: 0x{audio_start:x}")

                test_data = f.read(1024)
                if not test_data:
                    print(f"  ❌ 没有音频数据")
                    return False

                print(f"  尝试解密方法...")

                methods = [
                    ("方法1 (原始)", self.try_decode_method1),
                    ("方法2 (RC4)", self.try_decode_method2),
                    ("方法3 (新版)", self.try_decode_method3)
                ]

                successful_method = None
                decrypted_test = None

                for method_name, method_func in methods:
                    key_box_copy = bytearray(key_box_original)
                    decrypted = method_func(key_box_copy, test_data)

                    detected_format = self.detect_format(decrypted)
                    if detected_format:
                        print(f"    ✅ {method_name} 成功！检测到 {detected_format}")
                        successful_method = method_func
                        decrypted_test = decrypted
                        output_format = detected_format
                        break
                    else:
                        print(f"    ❌ {method_name} 失败")

                if not successful_method:
                    print(f"  ⚠️ 标准起始位置 0x{audio_start:x} 解密失败，启动恢复模式...")

                    # 启动恢复模式：搜索正确的音频起始位置
                    rec_offset, rec_method, rec_format = self.find_audio_start_recovery(
                        ncm_path, key_box_original)

                    if rec_offset is None:
                        # 恢复模式也失败
                        print(f"  ❌ 恢复模式无法找到有效的音频起始位置")
                        print(f"  💡 可能原因：")
                        print(f"     1. 文件下载严重损坏（建议重新下载）")
                        print(f"     2. 网易云使用了新的加密版本（请反馈给开发者）")
                        print(f"  调试信息:")
                        print(f"    文件大小: {os.path.getsize(ncm_path) / 1024:.1f} KB")
                        print(f"    标准起始位置: 0x{audio_start:x}")
                        print(f"    原始前16字节: {binascii.b2a_hex(test_data[:16]).decode()}")

                        debug_file = debug_dir / f"{ncm_path.stem}.debug"
                        with open(debug_file, 'wb') as df:
                            df.write(test_data)
                        print(f"    已保存调试文件: {debug_file}")
                        return False

                    # 恢复模式成功：用新参数继续解码
                    audio_start = rec_offset
                    successful_method = rec_method
                    output_format = rec_format
                    print(f"  ✅ 恢复成功，继续解码...")

                output_file = output_dir / f"{ncm_path.stem}.{output_format}"

                # 从正确的音频起点开始解密整段音频
                f.seek(audio_start)

                with open(output_file, 'wb') as out:
                    if successful_method is self.try_decode_method2:
                        # method2 是有状态 RC4，且本实现每次调用重置 i/j 指针，
                        # 无法正确分块——必须整段一次性解密。
                        audio_data = f.read()
                        out.write(successful_method(bytearray(key_box_original), audio_data))
                        total_size = len(audio_data)
                    else:
                        # method1/method3 无状态、keystream 周期 256，
                        # chunk(0x8000) 是 256 的整数倍，分块解密与整段等价。
                        key_box_copy = bytearray(key_box_original)
                        total_size = 0
                        next_report = 10 * 1024 * 1024  # 每 10MB 报告一次进度
                        while True:
                            chunk = f.read(0x8000)
                            if not chunk:
                                break
                            out.write(successful_method(key_box_copy, chunk))
                            total_size += len(chunk)
                            if total_size >= next_report:
                                print(f"    已处理: {total_size / 1024 / 1024:.1f} MB")
                                next_report += 10 * 1024 * 1024

                print(f"  ✅ 成功！输出: {output_file}")
                print(f"     大小: {total_size / 1024 / 1024:.2f} MB")
                return True

        except Exception as e:
            print(f"❌ 解码失败: {e}")
            import traceback
            traceback.print_exc()
            return False


def decode_directory(input_dir, output_dir=None):
    input_dir = Path(input_dir)

    if not input_dir.exists():
        print(f"❌ 输入目录不存在: {input_dir}")
        return

    ncm_files = list(input_dir.glob('*.ncm'))
    if not ncm_files:
        ncm_files = list(input_dir.rglob('*.ncm'))

    if not ncm_files:
        print("没有找到NCM文件")
        return

    print(f"找到 {len(ncm_files)} 个NCM文件")

    decoder = NCMUniversalDecoder()
    success_count = 0
    # 按失败原因分类，方便用户定位问题
    failed_by_reason = {
        'incomplete': [],   # 文件不完整（建议重下）
        'bad_header': [],   # 文件头损坏
        'algo_failed': [],  # 加密算法不匹配
        'other': [],        # 其他错误
    }

    for ncm_file in ncm_files:
        ok, reason = decoder.preflight_check(ncm_file)
        # corrupt_offset 让 decode 自己尝试恢复，不预先跳过
        if not ok and reason != 'corrupt_offset':
            if reason in ('too_small', 'truncated'):
                failed_by_reason['incomplete'].append(ncm_file.name)
            elif reason == 'bad_header':
                failed_by_reason['bad_header'].append(ncm_file.name)
            else:
                failed_by_reason['other'].append(f"{ncm_file.name} ({reason})")
            print(f"⚠️ 跳过损坏文件: {ncm_file.name} ({reason})")
            print()
            continue

        if decoder.decode(ncm_file, output_dir):
            success_count += 1
        else:
            failed_by_reason['algo_failed'].append(ncm_file.name)
        print()

    total = len(ncm_files)
    failed_total = sum(len(v) for v in failed_by_reason.values())

    print("=" * 60)
    print(f"完成: {success_count}/{total} 成功，{failed_total} 失败")

    if failed_by_reason['incomplete']:
        print(f"\n📥 下载不完整的文件（{len(failed_by_reason['incomplete'])} 个，建议重新下载）:")
        for name in failed_by_reason['incomplete'][:10]:
            print(f"  • {name}")
        if len(failed_by_reason['incomplete']) > 10:
            print(f"  ... 还有 {len(failed_by_reason['incomplete']) - 10} 个")

    if failed_by_reason['bad_header']:
        print(f"\n🔧 文件头损坏（{len(failed_by_reason['bad_header'])} 个）:")
        for name in failed_by_reason['bad_header'][:10]:
            print(f"  • {name}")

    if failed_by_reason['algo_failed']:
        print(f"\n🔐 加密算法不匹配（{len(failed_by_reason['algo_failed'])} 个，重下也可能解决）:")
        for name in failed_by_reason['algo_failed'][:10]:
            print(f"  • {name}")

    if failed_by_reason['other']:
        print(f"\n❓ 其他错误（{len(failed_by_reason['other'])} 个）:")
        for name in failed_by_reason['other'][:10]:
            print(f"  • {name}")


def main():
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="NCM 通用解码器 v2.0")
    parser.add_argument('input', help='NCM文件或包含NCM文件的目录')
    parser.add_argument('-o', '--output', help='输出目录（可选）', default=None)

    args = parser.parse_args()

    source = Path(args.input)

    if not source.exists():
        print(f"❌ 路径不存在: {source}")
        sys.exit(1)

    if source.is_file():
        decoder = NCMUniversalDecoder()
        decoder.decode(source, args.output)
    else:
        decode_directory(source, args.output)


if __name__ == '__main__':
    main()