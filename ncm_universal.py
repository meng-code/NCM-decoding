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
        if padding > len(s):
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

        try:
            with open(ncm_path, 'rb') as f:
                header = f.read(8)
                if binascii.b2a_hex(header) != b'4354454e4644414d':
                    print(f"❌ 无效的NCM文件头")
                    return False

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
                    print(f"  ❌ 所有方法都失败了")
                    print(f"  调试信息:")
                    print(f"    原始前16字节: {binascii.b2a_hex(test_data[:16])}")

                    debug_file = debug_dir / f"{ncm_path.stem}.debug"
                    with open(debug_file, 'wb') as df:
                        df.write(test_data)
                    print(f"    已保存调试文件: {debug_file}")
                    return False

                output_file = output_dir / f"{ncm_path.stem}.{output_format}"

                with open(output_file, 'wb') as out:
                    out.write(decrypted_test)

                    f.seek(audio_start + 1024)
                    key_box_copy = bytearray(key_box_original)

                    total_size = len(decrypted_test)
                    while True:
                        chunk = f.read(0x8000)
                        if not chunk:
                            break

                        decrypted_chunk = successful_method(key_box_copy, chunk)
                        out.write(decrypted_chunk)
                        total_size += len(decrypted_chunk)

                        if total_size % (1024 * 1024 * 10) == 0:
                            print(f"    已处理: {total_size / 1024 / 1024:.1f} MB")

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
    failed_files = []

    for ncm_file in ncm_files:
        if decoder.decode(ncm_file, output_dir):
            success_count += 1
        else:
            failed_files.append(ncm_file.name)
        print()

    print("=" * 60)
    print(f"完成: {success_count}/{len(ncm_files)} 成功")

    if failed_files:
        print(f"\n失败的文件:")
        for name in failed_files[:10]:
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