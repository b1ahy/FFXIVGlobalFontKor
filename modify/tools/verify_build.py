"""Checks a build against the game's vanilla fonts and renders a preview image."""
import argparse
import os

import numpy as np
from PIL import Image

from build_font import MAIN_FONTS, TEXTURE_COUNT, VANILLA_SIDE
from fdt import Fdt, utf8_to_char
from sqpack import DEFAULT_GAME_DIR, Index
from tex import decode_planes

SAMPLE = '파이널 판타지14 한글 채팅 테스트 漢字かな Hello ㄱㅏ 뷁똠햏'


def load_built(d):
    fdts = {n: Fdt(open(os.path.join(d, f'{n}.fdt'), 'rb').read()) for n in MAIN_FONTS}
    planes = np.concatenate([decode_planes(open(os.path.join(d, f'font{i}.tex'), 'rb').read())
                             for i in range(1, TEXTURE_COUNT + 1)])
    return fdts, planes


def check(game_dir, built_dir):
    idx = Index(game_dir)
    vanilla = {n: Fdt(idx.read(f'common/font/{n}.fdt')) for n in MAIN_FONTS}
    vplanes = np.concatenate([decode_planes(idx.read(f'common/font/font{i}.tex')) for i in range(1, TEXTURE_COUNT + 1)])
    fdts, planes = load_built(built_dir)

    vmask = np.zeros(vplanes.shape, bool)  # texels inside any vanilla glyph cell
    for V in vanilla.values():
        for _, _, ti, x, y, w, h, _, _ in V.glyphs:
            vmask[ti, y:y + h, x:x + w] = True
    region = planes[:, :VANILLA_SIDE, :VANILLA_SIDE]
    assert np.array_equal(region[vmask], vplanes[vmask]), 'vanilla glyph pixels changed'
    owner = np.zeros(planes.shape, np.int32)  # how many new glyph cells cover each texel
    for n, F in fdts.items():
        V = vanilla[n]
        codes = [g[0] for g in F.glyphs]
        assert codes == sorted(codes), f'{n}: glyph table not sorted'
        assert len(F.glyphs) == F.glyph_count and len(F.kerns) == F.kern_count
        assert F.kerns == V.kerns, f'{n}: kerning changed'
        assert (F.line_height, F.ascent, F.size) == (V.line_height, V.ascent, V.size)
        built = {}
        for g in F.glyphs:
            built.setdefault(g[0], []).append(g)
        for g in V.glyphs:
            assert g in built[g[0]], f'{n}: vanilla glyph {utf8_to_char(g[0])!r} changed'
        vset = {tuple(g) for g in V.glyphs}
        for g in F.glyphs:
            if tuple(g) in vset:
                continue
            _, _, ti, x, y, w, h, _, _ = g
            assert ti < TEXTURE_COUNT * 4 and x + w <= F.tex_w and y + h <= F.tex_h
            assert not vmask[ti, y:y + h, x:x + w].any(), f'{n}: new glyph overlaps a vanilla glyph cell'
            owner[ti, y:y + h, x:x + w] += 1
    assert owner.max() <= 1, 'new glyph cells overlap each other'
    a18 = [g[0] for g in fdts['AXIS_18'].glyphs]
    assert a18 == [g[0] for g in fdts['AXIS_36'].glyphs], 'AXIS_18/AXIS_36 glyph lists differ'
    print('OK: vanilla glyphs/kerning untouched, no overlaps, tables sorted, AXIS_18/36 linked')
    return fdts, planes


def draw(F, planes, text):
    gm = {}
    for g in F.glyphs:
        gm.setdefault(utf8_to_char(g[0]), g)
    canvas = np.zeros((F.line_height + 4, len(text) * F.line_height + 8), np.uint8)
    pen = 2
    for ch in text:
        _, _, ti, x, y, w, h, nxt, oy = gm[ch]
        region = canvas[2 + oy:2 + oy + h, pen:pen + w]
        np.maximum(region, planes[ti, y:y + h, x:x + w][:region.shape[0], :region.shape[1]], out=region)
        pen += w + nxt
    return canvas[:, :pen + 2]


def preview(fdts, planes, path, scale=2):
    rows = [draw(fdts[n], planes, SAMPLE) for n in ('AXIS_96', 'AXIS_12', 'AXIS_14', 'AXIS_18', 'AXIS_36')]
    W = max(r.shape[1] for r in rows) * scale
    img = Image.new('L', (W, sum(r.shape[0] * scale + 4 for r in rows)), 40)
    y = 0
    for r in rows:
        img.paste(Image.fromarray(r).resize((r.shape[1] * scale, r.shape[0] * scale), Image.NEAREST), (0, y))
        y += r.shape[0] * scale + 4
    img.save(path)
    print('preview:', path)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('built', help='folder with the built common/font files')
    ap.add_argument('--game', default=DEFAULT_GAME_DIR)
    ap.add_argument('--preview', help='write a preview PNG here')
    a = ap.parse_args()
    fdts, planes = check(a.game, a.built)
    if a.preview:
        preview(fdts, planes, a.preview)
