"""Minimal SqPack reader/writer for FFXIV (index1/index2/dat)."""
import os
import struct
import zlib

DEFAULT_GAME_DIR = r"C:\Program Files (x86)\SquareEnix\FINAL FANTASY XIV - A Realm Reborn\game"

BLOCK_SIZE = 16000  # max uncompressed bytes per block
UNCOMPRESSED_MARK = 32000


def crc(s):
    return (~zlib.crc32(s.lower().encode())) & 0xFFFFFFFF


def path_hash(path):
    """index1 key: (folder crc << 32) | filename crc."""
    folder, _, name = path.rpartition('/')
    return (crc(folder) << 32) | crc(name)


def full_hash(path):
    """index2 key: crc of the whole path."""
    return crc(path)


class Index:
    def __init__(self, game_dir=DEFAULT_GAME_DIR, cat='000000'):
        self.dir = os.path.join(game_dir, 'sqpack', 'ffxiv')
        self.cat = cat
        d = open(os.path.join(self.dir, cat + '.win32.index'), 'rb').read()
        hdr = struct.unpack_from('<I', d, 0xC)[0]
        off, size = struct.unpack_from('<II', d, hdr + 8)
        self.entries = {}
        for i in range(off, off + size, 16):
            h, data, _ = struct.unpack_from('<QII', d, i)
            self.entries[h] = data

    def locate(self, path):
        data = self.entries.get(path_hash(path))
        if data is None:
            return None
        return (data >> 1) & 7, (data & ~0xF) * 8

    def read(self, path):
        loc = self.locate(path)
        if loc is None:
            raise FileNotFoundError(path)
        dat, off = loc
        with open(os.path.join(self.dir, f'{self.cat}.win32.dat{dat}'), 'rb') as f:
            return read_file(f, off)


def _read_block(f, off):
    f.seek(off)
    _, _, csz, dsz = struct.unpack('<IIII', f.read(16))
    if csz == UNCOMPRESSED_MARK:
        return f.read(dsz)
    return zlib.decompress(f.read(csz), -15)


def read_file(f, off):
    f.seek(off)
    hsz, typ, usz, _, _, nblk = struct.unpack('<IIIIII', f.read(24))
    if typ == 2:
        blocks = [struct.unpack('<IHH', f.read(8)) for _ in range(nblk)]
        return b''.join(_read_block(f, off + hsz + bo) for bo, _, _ in blocks)
    if typ == 4:
        lods = [struct.unpack('<IIIII', f.read(20)) for _ in range(nblk)]
        nsub = sum(l[4] for l in lods)
        subs = struct.unpack(f'<{nsub}H', f.read(2 * nsub))
        f.seek(off + hsz)
        out = f.read(lods[0][0])
        for coff, _, _, bstart, bcount in lods:
            p = off + hsz + coff
            for i in range(bstart, bstart + bcount):
                out += _read_block(f, p)
                p += subs[i]
        return out
    raise ValueError(f'unsupported sqpack entry type {typ}')


# ---------------------------------------------------------------- packing

def _pad(b, align=128):
    return b + b'\0' * (-len(b) % align)


def _pack_block(raw):
    comp = zlib.compressobj(9, zlib.DEFLATED, -15)
    c = comp.compress(raw) + comp.flush()
    if len(c) >= len(raw):
        body = struct.pack('<IIII', 16, 0, UNCOMPRESSED_MARK, len(raw)) + raw
    else:
        body = struct.pack('<IIII', 16, 0, len(c), len(raw)) + c
    return _pad(body)


def pack_standard(data):
    """Pack a file as a type 2 (standard) sqpack entry."""
    blocks = [_pack_block(data[i:i + BLOCK_SIZE]) for i in range(0, max(len(data), 1), BLOCK_SIZE)]
    table = b''
    off = 0
    for i, b in enumerate(blocks):
        dsz = min(BLOCK_SIZE, len(data) - i * BLOCK_SIZE)
        table += struct.pack('<IHH', off, len(b), dsz)
        off += len(b)
    hsz = (24 + len(table) + 127) // 128 * 128
    hdr = struct.pack('<IIIIII', hsz, 2, len(data), off // 128, off // 128, len(blocks)) + table
    return hdr.ljust(hsz, b'\0') + b''.join(blocks)


def pack_texture(data):
    """Pack a .tex (single mip, 0x50 header) as a type 4 sqpack entry."""
    tex_hdr, body = data[:0x50], data[0x50:]
    blocks = [_pack_block(body[i:i + BLOCK_SIZE]) for i in range(0, len(body), BLOCK_SIZE)]
    comp_size = sum(len(b) for b in blocks)
    lod = struct.pack('<IIIII', 0x50, comp_size, len(body), 0, len(blocks))
    subs = struct.pack(f'<{len(blocks)}H', *[len(b) for b in blocks])
    hsz = (24 + len(lod) + len(subs) + 127) // 128 * 128
    total = (0x50 + comp_size + 127) // 128
    hdr = struct.pack('<IIIIII', hsz, 4, len(data), total, total, 1) + lod + subs
    return hdr.ljust(hsz, b'\0') + _pad(tex_hdr + b''.join(blocks))
