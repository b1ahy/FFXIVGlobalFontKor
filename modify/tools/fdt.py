"""FFXIV font data (.fdt) reader/writer.

Glyph entry: [utf8, shift_jis, texture_index, x, y, width, height, next_offset_x, offset_y]
  texture_index = texture file number * 4 + plane; advance = width + next_offset_x.
Kerning entry: [left_utf8, right_utf8, left_sjis, right_sjis, offset]
"""
import struct


def utf8_to_char(v):
    b = v.to_bytes(4, 'big').lstrip(b'\0')
    try:
        return b.decode('utf-8')
    except UnicodeDecodeError:
        return None


def char_to_utf8(c):
    return int.from_bytes(c.encode('utf-8'), 'big')


class Fdt:
    def __init__(self, d):
        assert d[:8] == b'fcsv0100', d[:8]
        self.raw = d
        fthd_off, knhd_off = struct.unpack_from('<II', d, 8)
        assert d[fthd_off:fthd_off + 4] == b'fthd'
        (self.glyph_count, self.kern_count, self.pad, self.tex_w, self.tex_h,
         self.size, self.line_height, self.ascent) = struct.unpack_from('<IIIHHfII', d, fthd_off + 4)
        p = fthd_off + 32
        self.glyphs = [list(struct.unpack_from('<IHHHHBBbb', d, p + i * 16)) for i in range(self.glyph_count)]
        assert d[knhd_off:knhd_off + 4] == b'knhd'
        self.knhd_raw = d[knhd_off:knhd_off + 16]
        n = struct.unpack_from('<I', d, knhd_off + 4)[0]
        self.kerns = [list(struct.unpack_from('<IIHHi', d, knhd_off + 16 + i * 16)) for i in range(n)]
        self.tail = d[knhd_off + 16 + n * 16:]

    def build(self):
        out = bytearray(b'fcsv0100')
        fthd_off = 0x20
        knhd_off = fthd_off + 32 + 16 * len(self.glyphs)
        out += struct.pack('<II', fthd_off, knhd_off)
        out += self.raw[16:0x20]
        out += b'fthd' + struct.pack('<IIIHHfII', len(self.glyphs), len(self.kerns), self.pad, self.tex_w, self.tex_h,
                                      self.size, self.line_height, self.ascent)
        for g in self.glyphs:
            out += struct.pack('<IHHHHBBbb', *g)
        out += b'knhd' + struct.pack('<I', len(self.kerns)) + self.knhd_raw[8:16]
        for k in self.kerns:
            out += struct.pack('<IIHHi', *k)
        out += self.tail
        return bytes(out)
