"""Exports the Korean client's fonts (KrnAXIS_120/140/180/360.fdt and font_krn_*.tex) to a folder.

Run it on a PC with the Korean client installed; only the Python standard library is needed.
The build then takes the Hangul from these files (build_all.py reads ../krn by default), so
people using the patch don't need the Korean client.

    python export_krn.py "<Korean client folder>"
"""
import argparse
import os
import struct
import sys

from sqpack import Index

FONTS = ['KrnAXIS_120', 'KrnAXIS_140', 'KrnAXIS_180', 'KrnAXIS_360']


def find_game_dir(path):
    """Accepts the install folder, its game folder, or anything inside; returns the game folder."""
    p = os.path.abspath(path)
    for _ in range(4):
        for cand in (p, os.path.join(p, 'game')):
            if os.path.isfile(os.path.join(cand, 'sqpack', 'ffxiv', '000000.win32.index')):
                return cand
        p = os.path.dirname(p)
    return None


def texture_files(fdt):
    """Numbers of the font_krn_N.tex files the glyphs of an .fdt use."""
    fthd = struct.unpack_from('<I', fdt, 8)[0]
    count = struct.unpack_from('<I', fdt, fthd + 4)[0]
    return {struct.unpack_from('<H', fdt, fthd + 32 + i * 16 + 6)[0] // 4 + 1 for i in range(count)}


def export(game_dir, out_dir):
    idx = Index(game_dir)
    fdts = {}
    for name in FONTS:
        try:
            data = idx.read(f'common/font/{name}.fdt')
        except FileNotFoundError:
            data = b''
        if not data:
            # the global client lists these files too, but as empty placeholders
            raise SystemExit(f'{name}.fdt is missing or empty in {game_dir}. Is this the Korean client?')
        if data[:8] != b'fcsv0100':
            raise SystemExit(f'{name}.fdt is not font data')
        fdts[name] = data
    textures = sorted(set().union(*(texture_files(d) for d in fdts.values())))

    os.makedirs(out_dir, exist_ok=True)
    for name, data in fdts.items():
        with open(os.path.join(out_dir, f'{name}.fdt'), 'wb') as f:
            f.write(data)
    for n in textures:
        data = idx.read(f'common/font/font_krn_{n}.tex')
        if not data:
            raise SystemExit(f'font_krn_{n}.tex is empty')
        with open(os.path.join(out_dir, f'font_krn_{n}.tex'), 'wb') as f:
            f.write(data)
    print(f'{len(fdts)} fonts and textures font_krn_{{{",".join(map(str, textures))}}}.tex -> {out_dir}')


def main():
    default_out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'krn')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('client', help='Korean client install folder (or its "game" folder)')
    ap.add_argument('--out', default=default_out, help=f'output folder (default: {default_out})')
    a = ap.parse_args()
    game_dir = find_game_dir(a.client)
    if not game_dir:
        sys.exit(f'no FFXIV game data (game\\sqpack\\ffxiv) found at {a.client}')
    export(game_dir, a.out)


if __name__ == '__main__':
    main()
