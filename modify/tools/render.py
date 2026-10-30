"""FreeType glyph rendering into FFXIV-style fixed glyph cells."""
import freetype
import numpy as np


class Renderer:
    def __init__(self, font_path, px, scale_x=1.0, dx=0.0, dy=0.0):
        """scale_x widens the glyphs; dx/dy (pixels, y up) shift them. Vertical hinting is kept."""
        self.face = freetype.Face(font_path)
        self.face.set_char_size(int(round(px * 64)), 0, 72, 72)
        # light hinting: vertical-only snapping keeps strokes crisp without distorting Hangul shapes
        self.flags = freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_LIGHT
        matrix = freetype.Matrix(int(round(scale_x * 0x10000)), 0, 0, 0x10000)
        self.face.set_transform(matrix, freetype.Vector(int(round(dx * 64)), int(round(dy * 64))))

    def has(self, ch):
        return self.face.get_char_index(ch) != 0

    def glyph(self, ch):
        """Return (bitmap uint8 [h, w], left, top)."""
        self.face.load_char(ch, self.flags)
        slot = self.face.glyph
        bm = slot.bitmap
        if not bm.rows:
            return np.zeros((0, 0), np.uint8), 0, 0
        a = np.array(bm.buffer, np.uint8).reshape(bm.rows, bm.pitch)[:, :bm.width]
        return a, slot.bitmap_left, slot.bitmap_top


def place_in_cell(bitmap, left, top, cell_w, cell_h, baseline_y, pen_x=0):
    """Blit a glyph bitmap into a cell whose pen origin is (pen_x, baseline_y). Returns (cell, clipped)."""
    cell = np.zeros((cell_h, cell_w), np.uint8)
    h, w = bitmap.shape
    x0, y0 = pen_x + left, baseline_y - top
    sx0, sy0 = max(0, -x0), max(0, -y0)
    dx0, dy0 = max(0, x0), max(0, y0)
    dx1, dy1 = min(cell_w, x0 + w), min(cell_h, y0 + h)
    if dx1 > dx0 and dy1 > dy0:
        cell[dy0:dy1, dx0:dx1] = bitmap[sy0:sy0 + dy1 - dy0, sx0:sx0 + dx1 - dx0]
    clipped = w > 0 and (x0 < 0 or y0 < 0 or x0 + w > cell_w or y0 + h > cell_h)
    return cell, clipped
