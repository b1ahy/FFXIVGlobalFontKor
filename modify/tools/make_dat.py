"""Packs built font files into a standalone SqPack .dat that the dinput8.dll loader serves to the game.

Writes <out>/000000.win32.dat and <out>/files.txt. Each files.txt line is
    <index1 hash, 16 hex> <index2 hash, 8 hex> <offset in the .dat> <game path>
and the loader points those index entries at the .dat.
"""
import argparse
import hashlib
import os
import struct
import time

from build_font import MAIN_FONTS, TEXTURE_COUNT
from sqpack import full_hash, pack_standard, pack_texture, path_hash

DAT_MAX_SIZE = 2000000000


def sqpack_header(file_type):
    h = bytearray(0x400)
    h[0:6] = b'SqPack'
    t = time.gmtime()
    struct.pack_into('<IIIIII', h, 0xC, 0x400, 1, file_type,
                     t.tm_year * 10000 + t.tm_mon * 100 + t.tm_mday,
                     t.tm_hour * 1000000 + t.tm_min * 10000 + t.tm_sec * 100, 0xFFFFFFFF)
    h[0x3C0:0x3D4] = hashlib.sha1(h[:0x3C0]).digest()
    return bytes(h)


def dat_header(data):
    h = bytearray(0x400)
    struct.pack_into('<IIIIIIQ', h, 0, 0x400, 0, 0x10, len(data) // 128, 1, 0, DAT_MAX_SIZE)
    h[0x20:0x34] = hashlib.sha1(data).digest()
    h[0x3C0:0x3D4] = hashlib.sha1(h[:0x3C0]).digest()
    return bytes(h)


def make_dat(font_dir, out_dir):
    files = [(f'common/font/{n}.fdt', pack_standard) for n in MAIN_FONTS]
    files += [(f'common/font/font{i}.tex', pack_texture) for i in range(1, TEXTURE_COUNT + 1)]
    body = bytearray()
    manifest = []
    for path, pack in files:
        with open(os.path.join(font_dir, os.path.basename(path)), 'rb') as f:
            entry = pack(f.read())
        assert len(entry) % 128 == 0
        manifest.append(f'{path_hash(path):016x} {full_hash(path):08x} {0x800 + len(body)} {path}')
        body += entry
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, '000000.win32.dat'), 'wb') as f:
        f.write(sqpack_header(1))
        f.write(dat_header(bytes(body)))
        f.write(body)
    with open(os.path.join(out_dir, 'files.txt'), 'w', newline='\n') as f:
        f.write('\n'.join(manifest) + '\n')
    print(f'{len(files)} files, {(0x800 + len(body)) / 1048576:.1f} MiB')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('fonts', help='folder with the built common/font files')
    ap.add_argument('out', help='output folder (the loader\'s data folder)')
    a = ap.parse_args()
    make_dat(a.fonts, a.out)
