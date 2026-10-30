import struct
import numpy as np

FMT_B4G4R4A4 = 0x1440
FMT_B8G8R8A8 = 0x1450

# glyph plane index (TextureIndex & 3) -> byte index in B8G8R8A8 pixel (B=0, G=1, R=2, A=3)
PLANE_TO_BYTE = (2, 1, 0, 3)


def decode_planes(d):
    """Return array [4, h, w] of uint8 (0..255) in glyph-plane order."""
    attr, fmt, w, h = struct.unpack_from('<IIHH', d, 0)
    hdr = 0x50
    if fmt == FMT_B4G4R4A4:
        px = np.frombuffer(d, '<u2', w * h, hdr).reshape(h, w)
        nib = [(px >> (4 * i)) & 0xF for i in range(4)]  # B, G, R, A
        return np.stack([(nib[PLANE_TO_BYTE[p]] * 17).astype(np.uint8) for p in range(4)])
    if fmt == FMT_B8G8R8A8:
        px = np.frombuffer(d, np.uint8, w * h * 4, hdr).reshape(h, w, 4)
        return np.stack([px[:, :, PLANE_TO_BYTE[p]] for p in range(4)])
    raise ValueError(hex(fmt))


def encode_b8g8r8a8(planes):
    _, h, w = planes.shape
    px = np.zeros((h, w, 4), np.uint8)
    for p in range(4):
        px[:, :, PLANE_TO_BYTE[p]] = planes[p]
    hdr = bytearray(0x50)
    # attribute 0x800000 (TextureType2D), format, width, height, depth 1, mip levels 1;
    # 0x10: three LoD offsets (0), 0x1C: offset of the first surface
    struct.pack_into('<IIHHHH', hdr, 0, 0x800000, FMT_B8G8R8A8, w, h, 1, 1)
    struct.pack_into('<I', hdr, 0x1C, 0x50)
    return bytes(hdr) + px.tobytes()


def encode_b4g4r4a4(planes):
    _, h, w = planes.shape
    q = [((planes[p].astype(np.uint16) + 8) // 17) for p in range(4)]
    nib = [None] * 4
    for p in range(4):
        nib[PLANE_TO_BYTE[p]] = q[p]
    px = nib[0] | (nib[1] << 4) | (nib[2] << 8) | (nib[3] << 12)
    hdr = bytearray(0x50)
    struct.pack_into('<IIHHHH', hdr, 0, 0x800000, FMT_B4G4R4A4, w, h, 1, 1)
    struct.pack_into('<I', hdr, 0x1C, 0x50)
    return bytes(hdr) + px.astype('<u2').tobytes()
