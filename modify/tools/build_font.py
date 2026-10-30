"""Builds FFXIV global-client fonts with native-resolution Hangul glyphs.

Reads the game's current fonts (font1..7.tex and every FDT that uses them), enlarges the
textures, keeps every vanilla glyph exactly where it was, and adds Hangul at the real size of
each AXIS font (9.6/12/14/18/36). AXIS_36 keeps its own high-resolution glyphs instead of being
replaced with AXIS_18 like the old patch did.

Hangul comes from the Korean client's own glyphs (KrnAXIS_120/140/180/360) where a source has
them, so the text looks like it does on the Korean servers; any size without them is rendered
from Source Han Sans K, fitted to the Korean client's glyph proportions.

Output: <out>/common/font/*.fdt and font1..7.tex (raw game files).
"""
import argparse
import os
import sys

import numpy as np

from fdt import Fdt, char_to_utf8, utf8_to_char
from render import Renderer, place_in_cell
from sqpack import DEFAULT_GAME_DIR, Index
from tex import decode_planes, encode_b4g4r4a4, encode_b8g8r8a8

TEXTURE_COUNT = 7  # the game loads font1..font7.tex for the main fonts
VANILLA_SIDE = 1024

# Every FDT drawn from font%d.tex. All of them get the new texture size in their header.
MAIN_FONTS = (
    ['AXIS_96', 'AXIS_12', 'AXIS_14', 'AXIS_18', 'AXIS_36']
    + [f'Jupiter_{s}' for s in (16, 20, 23, 45, 46, 90)]
    + [f'Meidinger_{s}' for s in (16, 20, 40)]
    + [f'MiedingerMid_{s}' for s in (10, 12, 14, 18, 36)]
    + [f'TrumpGothic_{s}' for s in (184, 23, 34, 68)]
)

# AXIS font -> (Source Han Sans K weight, horizontal scale, x shift px, y shift px (up)).
# Source Han Sans Hangul is narrower than the Korean client's and sits further left. The scale and
# shifts make the average ink box match the Korean client's KrnAXIS_120/140/180 glyphs (the ones
# the old patch shipped). AXIS_96 uses the 12px fit scaled down; AXIS_36 is drawn in place of
# AXIS_18 in high-resolution UI, so it uses the 18px fit doubled.
KOREAN_FONTS = {
    'AXIS_96': ('Medium', 1.113, 0.42, -0.06),
    'AXIS_12': ('Medium', 1.113, 0.52, -0.07),
    'AXIS_14': ('Medium', 1.107, 0.92, 0.68),
    'AXIS_18': ('Medium', 1.038, 2.46, 0.04),
    'AXIS_36': ('Medium', 1.038, 4.92, 0.08),
}

# AXIS font -> the Korean client's font of the same size. Its line height matches the AXIS font's,
# so its glyph cells (including the vertical offset from the line top) are copied unchanged.
KRN_FONTS = {
    'AXIS_12': 'KrnAXIS_120',
    'AXIS_14': 'KrnAXIS_140',
    'AXIS_18': 'KrnAXIS_180',
    'AXIS_36': 'KrnAXIS_360',
}

# Hangul Compatibility Jamo (what the IME shows while composing) + all Hangul Syllables.
KOREAN_CHARS = [chr(c) for c in range(0x3131, 0x318F)] + [chr(c) for c in range(0xAC00, 0xD7A4)]

# Glyph whose cell geometry (size, advance, vertical offset) every Hangul glyph copies.
REFERENCE_GLYPH = '漢'
GAP = 1  # empty pixels between glyph cells, as in the vanilla textures


class PlaneAllocator:
    """Shelf packer over the area of each texture plane that vanilla glyphs don't use."""

    def __init__(self, used_rows, side):
        self.side = side
        self.used_rows = used_rows  # per plane: rows [0, used_rows) are vanilla in x < VANILLA_SIDE
        self.plane = 0
        self.x = self.y = self.shelf_h = 0
        self._start_plane()

    def _start_plane(self):
        self.y = 0
        self.x = self._row_start(0)
        self.shelf_h = 0

    def _row_start(self, y):
        # a shelf starting inside the vanilla rows stays right of the vanilla 1024x1024 area
        return VANILLA_SIDE if y < self.used_rows[self.plane] else 0

    def alloc(self, w, h):
        while True:
            if self.y + h > self.side:
                self.plane += 1
                if self.plane >= len(self.used_rows):
                    raise RuntimeError('out of texture space; increase --side')
                self._start_plane()
                continue
            if self.x + w > self.side:
                self.y += self.shelf_h + GAP
                self.x = self._row_start(self.y)
                self.shelf_h = 0
                continue
            pos = (self.plane, self.x, self.y)
            self.x += w + GAP
            self.shelf_h = max(self.shelf_h, h)
            return pos


class KrnSource:
    """The Korean client's KrnAXIS fonts, from loose files or from a Korean client's sqpack."""

    def __init__(self, read, label):
        self._read = read  # file name -> bytes, or None when missing/empty
        self.label = label
        self._planes = {}

    @classmethod
    def from_dir(cls, d):
        def read(name):
            p = os.path.join(d, name)
            return open(p, 'rb').read() if os.path.isfile(p) else None
        return cls(read, d)

    @classmethod
    def from_game(cls, game_dir):
        idx = Index(game_dir)

        def read(name):
            try:
                return idx.read(f'common/font/{name}') or None  # the global client has empty placeholders
            except FileNotFoundError:
                return None
        return cls(read, game_dir)

    def font(self, name):
        d = self._read(f'{name}.fdt')
        return Fdt(d) if d else None

    def cell(self, glyph):
        _, _, ti, x, y, w, h, _, _ = glyph
        f = ti // 4
        if f not in self._planes:
            d = self._read(f'font_krn_{f + 1}.tex')
            if not d:
                raise RuntimeError(f'{self.label}: font_krn_{f + 1}.tex is missing')
            self._planes[f] = decode_planes(d)
        return self._planes[f][ti % 4, y:y + h, x:x + w]


def load_game(game_dir):
    idx = Index(game_dir)
    fdts = {n: Fdt(idx.read(f'common/font/{n}.fdt')) for n in MAIN_FONTS}
    planes = np.concatenate([decode_planes(idx.read(f'common/font/font{i}.tex')) for i in range(1, TEXTURE_COUNT + 1)])
    return fdts, planes


def used_rows_per_plane(fdts, nplanes):
    rows = [0] * nplanes
    for F in fdts.values():
        for _, _, ti, x, y, w, h, _, _ in F.glyphs:
            if w and h:
                rows[ti] = max(rows[ti], y + h + GAP)
    return rows


def build(game_dir, font_dir, out_dir, side, fmt, styles, krn=None):
    fdts, vanilla = load_game(game_dir)
    for n, F in fdts.items():
        assert (F.tex_w, F.tex_h) == (VANILLA_SIDE, VANILLA_SIDE), f'{n}: unexpected texture size {F.tex_w}x{F.tex_h}'
    nplanes = vanilla.shape[0]
    planes = np.zeros((nplanes, side, side), np.uint8)
    planes[:, :VANILLA_SIDE, :VANILLA_SIDE] = vanilla
    alloc = PlaneAllocator(used_rows_per_plane(fdts, nplanes), side)

    # AXIS_18 and AXIS_36 must list the same characters in the same order: the game lays out
    # high-resolution text with AXIS_18 and draws it with AXIS_36 glyphs of the same index.
    assert [g[0] for g in fdts['AXIS_18'].glyphs] == [g[0] for g in fdts['AXIS_36'].glyphs]

    for name, (weight, scale_x, dx, dy) in styles.items():
        F = fdts[name]
        existing = {g[0] for g in F.glyphs}
        ref = next(g for g in F.glyphs if utf8_to_char(g[0]) == REFERENCE_GLYPH)
        _, _, _, _, _, cw, chh, nxt, oy = ref
        r = Renderer(os.path.join(font_dir, f'SourceHanSansK-{weight}.otf'), F.size, scale_x, dx, dy)
        baseline = F.ascent - oy
        K = krn.font(KRN_FONTS[name]) if krn and name in KRN_FONTS else None
        if K and K.line_height != F.line_height:
            raise RuntimeError(f'{KRN_FONTS[name]}: line height {K.line_height} differs from {name} ({F.line_height})')
        kmap = {g[0]: g for g in K.glyphs} if K else {}
        copied = rendered = clipped = 0
        for ch in KOREAN_CHARS:
            code = char_to_utf8(ch)
            if code in existing:
                continue
            if code in kmap:
                _, _, _, _, _, w, h, gnxt, goy = kmap[code]
                cell = krn.cell(kmap[code])
                copied += 1
            else:
                if not r.has(ch):
                    raise RuntimeError(f'{weight} has no glyph for U+{ord(ch):04X}')
                bm, left, top = r.glyph(ch)
                cell, was_clipped = place_in_cell(bm, left, top, cw, chh, baseline)
                clipped += was_clipped
                w, h, gnxt, goy = cw, chh, nxt, oy
                rendered += 1
            p, x, y = alloc.alloc(w, h)
            planes[p, y:y + h, x:x + w] = cell
            F.glyphs.append([code, 0, p, x, y, w, h, gnxt, goy])
        F.glyphs.sort(key=lambda g: g[0])
        print(f'{name}: +{copied} from {KRN_FONTS[name] if K else "-"}, '
              f'+{rendered} rendered ({weight} x{scale_x}, {F.size:g}px, cell {cw}x{chh}, clipped {clipped})')

    assert [g[0] for g in fdts['AXIS_18'].glyphs] == [g[0] for g in fdts['AXIS_36'].glyphs]
    print(f'texture use: up to plane {alloc.plane} of {nplanes} (font{alloc.plane // 4 + 1}.tex)')

    font_out = os.path.join(out_dir, 'common', 'font')
    os.makedirs(font_out, exist_ok=True)
    for name, F in fdts.items():
        F.tex_w = F.tex_h = side
        with open(os.path.join(font_out, f'{name}.fdt'), 'wb') as f:
            f.write(F.build())
    encode = encode_b8g8r8a8 if fmt == 'b8g8r8a8' else encode_b4g4r4a4
    for i in range(TEXTURE_COUNT):
        with open(os.path.join(font_out, f'font{i + 1}.tex'), 'wb') as f:
            f.write(encode(planes[i * 4:i * 4 + 4]))
    return fdts, planes


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--game', default=DEFAULT_GAME_DIR, help='FFXIV "game" folder')
    ap.add_argument('--fonts', default=os.path.join(root, 'font', 'OTF', 'Korean'), help='folder with SourceHanSansK-*.otf')
    ap.add_argument('--out', default=os.path.join(os.path.dirname(here), 'build'), help='output folder')
    ap.add_argument('--side', type=int, default=2048, choices=(2048, 4096), help='texture width/height')
    ap.add_argument('--format', default='b8g8r8a8', choices=('b8g8r8a8', 'b4g4r4a4'),
                    help='texture format: 8-bit (smoother Hangul) or the vanilla 4-bit format (half the VRAM)')
    ap.add_argument('--weight', action='append', default=[], metavar='FONT=WEIGHT',
                    help='override a weight, e.g. AXIS_36=Regular (Regular, Normal, Medium, Bold, ...)')
    add_krn_args(ap, root)
    args = ap.parse_args()
    styles = dict(KOREAN_FONTS)
    for w in args.weight:
        k, v = w.split('=')
        if k not in styles:
            sys.exit(f'unknown font {k}')
        styles[k] = (v,) + styles[k][1:]
    build(args.game, args.fonts, args.out, args.side, args.format, styles, krn_source(args))


def add_krn_args(ap, root):
    defaults = [os.path.join(root, 'modify', 'krn'),  # what export_krn.py writes
                os.path.join(root, 'original', 'fk', 'data', 'common', 'font')]  # the old patch: 120/140/180 only
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--krn-game', metavar='DIR', help='Korean client "game" folder: Hangul from all of KrnAXIS_120/140/180/360')
    g.add_argument('--krn-dir', metavar='DIR',
                   help='folder with KrnAXIS_*.fdt and font_krn_*.tex (default: the first of %s that exists)' % ', '.join(defaults))
    g.add_argument('--no-krn', action='store_true', help='render every size from Source Han Sans K')
    ap.set_defaults(krn_defaults=defaults)


def krn_source(args):
    if args.no_krn:
        return None
    if args.krn_game:
        return KrnSource.from_game(args.krn_game)
    dirs = [args.krn_dir] if args.krn_dir else args.krn_defaults
    for d in dirs:
        if os.path.isdir(d):
            print(f'Korean client fonts: {d}')
            return KrnSource.from_dir(d)
    print(f'note: no Korean client fonts at {", ".join(dirs)}; rendering every size from Source Han Sans K')
    return None


if __name__ == '__main__':
    main()
