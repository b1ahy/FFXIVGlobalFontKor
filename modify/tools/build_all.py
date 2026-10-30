"""Builds the fonts from the installed game, verifies them, and packs them into ../FFXIVGlobalKr/koreanfont."""
import argparse
import os
import tempfile

from build_font import KOREAN_FONTS, add_krn_args, build, krn_source
from make_dat import make_dat
from sqpack import DEFAULT_GAME_DIR
from verify_build import check, preview

HERE = os.path.dirname(os.path.abspath(__file__))
MODIFY = os.path.dirname(HERE)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--game', default=DEFAULT_GAME_DIR, help='FFXIV "game" folder')
    ap.add_argument('--fonts', default=os.path.join(os.path.dirname(MODIFY), 'font', 'OTF', 'Korean'))
    ap.add_argument('--out', default=os.path.join(MODIFY, 'FFXIVGlobalKr', 'koreanfont'))
    ap.add_argument('--side', type=int, default=2048, choices=(2048, 4096))
    ap.add_argument('--format', default='b8g8r8a8', choices=('b8g8r8a8', 'b4g4r4a4'))
    add_krn_args(ap, os.path.dirname(MODIFY))
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        build(a.game, a.fonts, tmp, a.side, a.format, dict(KOREAN_FONTS), krn_source(a))
        font_dir = os.path.join(tmp, 'common', 'font')
        fdts, planes = check(a.game, font_dir)
        preview(fdts, planes, os.path.join(MODIFY, 'preview.png'))
        make_dat(font_dir, a.out)


if __name__ == '__main__':
    main()
