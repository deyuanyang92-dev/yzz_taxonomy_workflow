"""Conservative clean-up of scanned literature pages (no AI redrawing: only pixels already present are re-weighted).

  text   : grey page -> remove uneven/yellow background (divide by blurred background), stretch levels,
           light unsharp mask; optional --binary = Sauvola threshold (pure black text on white)
  figure : same background flattening, gentler levels, no threshold (keeps stipple, hatching, halftone)

Rendering uses the scan's native resolution (capped), not a fixed 300 dpi.
usage (module): from 87_enhance_scan import render_page, enhance
usage (CLI)   : python 03_脚本/87_enhance_scan.py <pdf> <page 1-based> [text|figure] [--binary] -> PNG next to scratch
"""
import io, sys
import cv2
import fitz
import numpy as np
from PIL import Image


def native_dpi(page):
    """highest resolution of the scan images on the page (dpi), 0 if the page is vector/text only"""
    best = 0
    for info in page.get_image_info():
        bw = info['bbox'][2] - info['bbox'][0]
        if bw > 0 and info.get('width'): best = max(best, info['width'] / (bw / 72))
    return best


def render_page(page, max_px=6000, min_dpi=300, clip=None):
    """render at native scan resolution (>= 300 dpi), long side capped at max_px; returns grey uint8 array"""
    rect = clip or page.rect
    dpi = max(min_dpi, min(native_dpi(page) or min_dpi, 1200))
    dpi = min(dpi, max_px * 72 / max(rect.width, rect.height))
    pix = page.get_pixmap(dpi=int(dpi), clip=clip, colorspace=fitz.csGRAY)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width).copy(), int(dpi)


def flatten(g):
    """divide by the estimated paper background (large-scale) -> uniform white paper"""
    k = max(31, (min(g.shape) // 40) | 1)
    bg = cv2.morphologyEx(g, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k // 3 | 1, k // 3 | 1)))
    bg = cv2.medianBlur(bg, min(k, 255) if k % 2 else k + 1)
    out = cv2.divide(g.astype(np.float32), np.maximum(bg.astype(np.float32), 1), scale=255.0)
    return np.clip(out, 0, 255).astype(np.uint8)


def levels(g, lo_pct, hi_pct, gamma=1.0):
    lo, hi = np.percentile(g, lo_pct), np.percentile(g, hi_pct)
    x = np.clip((g.astype(np.float32) - lo) / max(hi - lo, 1), 0, 1) ** gamma
    return (x * 255).astype(np.uint8)


def unsharp(g, sigma, amount):
    blur = cv2.GaussianBlur(g, (0, 0), sigma)
    return cv2.addWeighted(g, 1 + amount, blur, -amount, 0)


def enhance(g, mode='text', binary=False, dpi=300):
    s = dpi / 300
    f = flatten(g) if mode == 'text' else None  # scale filters with resolution
    if mode == 'text':
        out = levels(f, 0.5, 60, gamma=1.25)       # paper -> white, ink -> near black
        out = unsharp(out, 0.8 * s, 0.6)
        if binary:
            from skimage.filters import threshold_sauvola
            w = int(25 * s) | 1
            out = np.where(f > threshold_sauvola(f, window_size=w, k=0.15), 255, 0).astype(np.uint8)
            out = cv2.medianBlur(out, 3)
    else:   # figures: photographs (dark fields) and drawings -> no background division, only local contrast
        photo = (g < 100).mean() > 0.20              # large dark fields = photographic plate
        out = levels(g, 0.3, 99.5) if photo else levels(g, 0.3, 90, gamma=1.1)   # drawings: paper -> white
        if photo: out = cv2.createCLAHE(clipLimit=1.3, tileGridSize=(4, 4)).apply(out)
        out = unsharp(out, 1.0 * s, 0.35)
    return out


def to_png_bytes(a):
    b = io.BytesIO(); Image.fromarray(a).save(b, 'PNG', optimize=True); return b.getvalue()


if __name__ == '__main__':
    pdf, pno = sys.argv[1], int(sys.argv[2]); mode = sys.argv[3] if len(sys.argv) > 3 else 'text'
    page = fitz.open(pdf)[pno - 1]; g, dpi = render_page(page)
    out = enhance(g, mode, '--binary' in sys.argv, dpi)
    o = f'/tmp/enh_p{pno}_{mode}.png'; Image.fromarray(out).save(o); print(o, g.shape, dpi)
