#!/usr/bin/env python3
import os, json, base64, struct, binascii
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


def check_ncm(filepath):
    CORE_KEY = binascii.a2b_hex('687A4852416D736F356B496E62617857')
    META_KEY = binascii.a2b_hex('2331346C6A6B5F215C5D2630553C2728')

    with open(filepath, 'rb') as f:
        header = f.read(8)
        f.seek(2, 1)

        # 解密密钥
        key_length = struct.unpack('<I', f.read(4))[0]
        key_data = bytearray(f.read(key_length))
        for i in range(len(key_data)):
            key_data[i] ^= 0x64

        # 跳过密钥解密部分，直接到元数据
        cryptor = Cipher(algorithms.AES(CORE_KEY), modes.ECB(), backend=default_backend()).decryptor()
        key_data = cryptor.update(bytes(key_data)) + cryptor.finalize()

        # 读取元数据
        meta_length = struct.unpack('<I', f.read(4))[0]
        meta_data = bytearray(f.read(meta_length))
        for i in range(len(meta_data)):
            meta_data[i] ^= 0x63

        meta_data = base64.b64decode(bytes(meta_data)[22:])
        cryptor = Cipher(algorithms.AES(META_KEY), modes.ECB(), backend=default_backend()).decryptor()
        meta_data = cryptor.update(meta_data) + cryptor.finalize()

        # 去除填充
        pad = meta_data[-1]
        meta_data = meta_data[:-pad]

        meta_json = json.loads(meta_data.decode('utf-8')[6:])

        print(f"文件: {os.path.basename(filepath)}")
        print(f"元数据格式: {meta_json.get('format')}")
        print(f"比特率: {meta_json.get('bitrate')}")
        print(f"音乐名: {meta_json.get('musicName')}")
        print("-" * 40)


# 测试几个文件
import sys

if len(sys.argv) > 1:
    for f in sys.argv[1:]:
        if f.endswith('.ncm'):
            check_ncm(f)