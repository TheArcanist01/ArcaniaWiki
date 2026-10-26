"""
Cut Borderlands 2 inspect-screen screenshots into transparent PNGs.

Every item needs two screenshots of the same inspect screen:

    <Name>-look.jpg    item zoomed in (it may overlap the stats card)
    <Name>-stats.jpg   item zoomed out, stats card fully visible

and produces:

    <name>-look.png    the item alone, background removed  (from -look)
    <name>-stats.png   the stats card with flavor text      (from -stats)

Usage:
    python tools/extract_item_images.py pictures
    python tools/extract_item_images.py pictures/Titus-look.jpg pictures/Titus-stats.jpg
    python tools/extract_item_images.py pictures --out media/items --debug

Relics and other items without a black outline use one screenshot each:

    python tools/extract_item_images.py --single pictures-relics
    (<Name>.jpg -> <name>-look.png and <name>-stats.png)

Folders are searched for <Name>-look / <Name>-stats pairs (jpg, jpeg, png, bmp).
Results go to an "extracted" folder next to the screenshots unless --out is given.
Requires numpy and scipy (pip install -r requirements.txt).

How it works
------------
Card (from -stats): the card is the only large, strongly blue area of the
screen and always sits in the top-left corner. Its blue pixels are grouped,
holes are filled and the edge is softened so the cyan glow fades out.

Item (from -look): the game draws items with a near-black outline. Pixels
darker than OUTLINE_MAX form a wall; flood-filling the background from the
image border cannot cross it, so whatever it does not reach is the item.
Where the item overlaps the card, the two screenshots are compared: both show
the same card in the same place, so pixels that differ there belong to the item.
Openings in the item (stocks, trigger guards) that show background are removed
by comparing their colour with the background around the item.

Single screenshot (--single, relics): relics have no outline and are surrounded
by floating, glowing shards. The inspect screen's background is a smooth dark
gradient, so a low-order 2D polynomial is fitted to the pixels that look like
background (refitted a few times, each time dropping pixels that don't fit).
Everything that differs clearly from that surface is the item; the alpha is
soft, following the colour difference, so glows fade out instead of being cut.
Gaps inside the relic's main body are made opaque unless they look like
background (hollow shards in front of the stone stay see-through). The card
and the controls hint at the bottom are left out.
"""

import argparse
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

OUTLINE_MAX = 14          # luminance (0-255) at or below this counts as item outline
OUTLINE_CLOSE = 2         # px: closes small gaps in the outline before flood filling
CARD_MIN_SATURATION = 0.35
CARD_HUE_RANGE = (170, 250)  # degrees: cyan to blue
CARD_DIFF_MIN = 30        # colour difference (0-441) that marks the item over the card
SPECKLE_MAX = 80          # px: smaller isolated differences are JPEG noise, not the item
POCKET_TOLERANCE = (12, 30)  # allowed colour distance from the background (min, max)
POCKET_MAX_SHARE = 0.25   # an opening can't be more than this share of the item
CARD_SAME_MAX = 15        # colour difference below which a pixel still shows the card
CARD_HOLE_MIN = 200       # px: openings in the item this big that show the card are cut out
RELIC_BACKGROUND_DEGREE = 4  # polynomial degree of the fitted background
RELIC_DIFF_SOLID = 45     # colour difference from the background that is surely item
RELIC_DIFF_COLOURED = 25  # ...or this much for clearly coloured (saturated) pixels
RELIC_ALPHA_RAMP = (12, 45)  # difference range over which alpha rises from 0 to 1
RELIC_MIN_PIECE = 60      # px: smaller isolated pieces are noise
HINT_LINE_TOP = 0.865     # share of the height where the controls hint line starts
PADDING = 8               # px of transparent margin around each cut-out
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}


# --------------------------------------------------------------------------- helpers

def luminance(rgb):
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def hue_saturation(rgb):
    r, g, b = (rgb[..., i] / 255.0 for i in range(3))
    mx, mn = np.maximum(np.maximum(r, g), b), np.minimum(np.minimum(r, g), b)
    delta = mx - mn
    sat = np.where(mx > 0, delta / np.maximum(mx, 1e-6), 0)
    hue = np.zeros_like(mx)
    nz = delta > 1e-6
    rmax = nz & (mx == r)
    gmax = nz & (mx == g) & ~rmax
    bmax = nz & ~rmax & ~gmax
    hue[rmax] = (60 * ((g - b)[rmax] / delta[rmax])) % 360
    hue[gmax] = 60 * ((b - r)[gmax] / delta[gmax]) + 120
    hue[bmax] = 60 * ((r - g)[bmax] / delta[bmax]) + 240
    return hue, sat


def largest_component(mask):
    labels, count = ndimage.label(mask)
    if count == 0:
        return np.zeros_like(mask)
    sizes = ndimage.sum(mask, labels, range(1, count + 1))
    return labels == (int(np.argmax(sizes)) + 1)


def to_rgba(rgb, alpha):
    ys, xs = np.nonzero(alpha > 0.02)
    if len(ys) == 0:
        raise ValueError("nothing was detected")
    y0, y1 = max(ys.min() - PADDING, 0), min(ys.max() + PADDING + 1, rgb.shape[0])
    x0, x1 = max(xs.min() - PADDING, 0), min(xs.max() + PADDING + 1, rgb.shape[1])
    rgba = np.dstack([rgb, (np.clip(alpha, 0, 1) * 255).astype(np.uint8)])[y0:y1, x0:x1]
    return Image.fromarray(rgba, "RGBA")


# --------------------------------------------------------------------------- card

def card_mask(rgb):
    """The stats card: the large blue area in the top-left corner."""
    height, width = rgb.shape[:2]
    hue, sat = hue_saturation(rgb)
    blue = (
        (sat >= CARD_MIN_SATURATION)
        & (hue >= CARD_HUE_RANGE[0]) & (hue <= CARD_HUE_RANGE[1])
        & (luminance(rgb) > 40)
    )
    blue = ndimage.binary_closing(blue, iterations=3)
    labels, count = ndimage.label(blue)
    if count == 0:
        raise ValueError("no stats card found")
    # The card is the biggest blue blob whose centre lies in the top-left quarter.
    best, best_size = 0, 0
    for label, (sl_y, sl_x) in enumerate(ndimage.find_objects(labels), start=1):
        cy, cx = (sl_y.start + sl_y.stop) / 2, (sl_x.start + sl_x.stop) / 2
        size = int((labels[sl_y, sl_x] == label).sum())
        if cy < height / 2 and cx < width / 2 and size > best_size:
            best, best_size = label, size
    if not best:
        raise ValueError("no stats card found in the top-left corner")
    return ndimage.binary_fill_holes(labels == best)


def extract_stats(rgb):
    card = ndimage.binary_dilation(card_mask(rgb), iterations=4)
    alpha = ndimage.gaussian_filter(card.astype(np.float32), 3)
    alpha = np.clip(alpha * 1.5, 0, 1) * ndimage.binary_dilation(card, iterations=9)
    # Gaps left inside the card (e.g. the insides of the price digits) become opaque;
    # the soft outer edge is left as it is.
    solid = alpha > 0.5
    inside = ndimage.binary_fill_holes(solid)
    holes = ndimage.binary_dilation(inside & ~solid, iterations=4)
    alpha[holes & ndimage.binary_erosion(inside, iterations=3)] = 1
    return to_rgba(rgb, alpha), card


# --------------------------------------------------------------------------- item

def background_flood(rgb):
    """Labels of open space and the labels that touch the border (= background)."""
    outline = luminance(rgb) <= OUTLINE_MAX
    walls = ndimage.binary_dilation(outline, iterations=OUTLINE_CLOSE)
    labels, _ = ndimage.label(~walls)
    border = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    border = border[border > 0]
    return outline, labels, border


def background_pockets(rgb, item, labels, border, outline, card_area, card_seen):
    """Enclosed openings whose colour matches the background around the item."""
    ring = ndimage.binary_dilation(item, iterations=30) & ~ndimage.binary_dilation(item, iterations=10)
    ring &= ~card_area  # the card is not background
    bg_pixels = rgb[ring].astype(np.float32)
    bg_mean = bg_pixels.mean(axis=0)
    spread = np.percentile(np.linalg.norm(bg_pixels - bg_mean, axis=1), 95)
    tolerance = float(np.clip(spread, *POCKET_TOLERANCE))
    max_size = item.sum() * POCKET_MAX_SHARE

    pockets = np.zeros_like(item)
    inside = np.unique(labels[item])
    for label in inside[(inside > 0) & ~np.isin(inside, border)]:
        region = labels == label
        on_card = region & card_area
        if on_card.any() and (on_card & card_seen).sum() >= 0.6 * on_card.sum():
            # An opening that shows the card: card_holes() cuts that part, and only
            # the rest is judged against the background colour here.
            region &= ~card_area
        size = region.sum()
        if size < 150 or size > max_size:
            continue
        distance = np.linalg.norm(rgb[region].astype(np.float32) - bg_mean, axis=1)
        if np.median(distance) <= tolerance and np.percentile(distance, 90) <= tolerance * 1.5:
            pockets |= region
    return ndimage.binary_dilation(pockets, iterations=OUTLINE_CLOSE) & ~outline


def changed_over_card(look_rgb, stats_rgb):
    difference = np.linalg.norm(look_rgb.astype(np.float32) - stats_rgb.astype(np.float32), axis=2)
    changed = difference > CARD_DIFF_MIN
    # Drop small isolated specks (JPEG noise around the card's text) without
    # eroding thin parts of the item the way a morphological opening would.
    labels, count = ndimage.label(changed)
    if count:
        sizes = ndimage.sum(changed, labels, range(1, count + 1))
        changed = np.isin(labels, np.nonzero(sizes > SPECKLE_MAX)[0] + 1)
    changed = ndimage.binary_closing(changed, iterations=2)
    return ndimage.binary_fill_holes(changed)


def card_holes(look_rgb, stats_rgb, item, card):
    """Openings in the item through which the stats card is visible."""
    difference = np.linalg.norm(look_rgb.astype(np.float32) - stats_rgb.astype(np.float32), axis=2)
    same = (difference < CARD_SAME_MAX) & item & ndimage.binary_dilation(card, iterations=12)
    same = ndimage.binary_opening(same, iterations=2)  # ignore thin coincidental matches
    labels, count = ndimage.label(same)
    if not count:
        return same
    sizes = ndimage.sum(same, labels, range(1, count + 1))
    holes = np.isin(labels, np.nonzero(sizes >= CARD_HOLE_MIN)[0] + 1)
    return ndimage.binary_dilation(holes, iterations=2) & item


def extract_look(look_rgb, stats_rgb, card):
    outline, labels, border = background_flood(look_rgb)
    foreground = ~np.isin(labels, border)
    # Undo the wall growth so the item keeps its real outline, not a thicker one.
    foreground = ndimage.binary_erosion(foreground, iterations=OUTLINE_CLOSE) | (outline & foreground)

    # Over the card, the item is whatever differs from the -stats screenshot
    # (both show the same card in the same place).
    card_area = ndimage.binary_dilation(card, iterations=12)
    foreground = (foreground & ~card_area) | (changed_over_card(look_rgb, stats_rgb) & card_area)

    item = ndimage.binary_fill_holes(largest_component(foreground))
    holes = card_holes(look_rgb, stats_rgb, item, card)
    item &= ~background_pockets(look_rgb, item, labels, border, outline, card_area, holes)
    item &= ~holes
    item = largest_component(item)
    return to_rgba(look_rgb, item.astype(np.float32)), item


# --------------------------------------------------------------------------- single screenshot (relics)

def _poly_terms(x, y, degree):
    return [x ** i * y ** j for i in range(degree + 1) for j in range(degree + 1 - i)]


def fitted_background(rgb, card, degree=RELIC_BACKGROUND_DEGREE, scale=8):
    """The smooth inspect-screen background, without the item."""
    height, width = rgb.shape[:2]
    small = np.asarray(Image.fromarray(rgb).resize((width // scale, height // scale), Image.BILINEAR))
    small = small.astype(np.float32)
    sh, sw = small.shape[:2]
    card_small = np.asarray(Image.fromarray(card.astype(np.uint8) * 255).resize((sw, sh))) > 0

    yy, xx = np.mgrid[0:sh, 0:sw]
    design = np.stack([t.ravel() for t in _poly_terms(xx / sw * 2 - 1, yy / sh * 2 - 1, degree)], axis=1)
    _, sat = hue_saturation(small.astype(np.uint8))
    usable = ~ndimage.binary_dilation(card_small, iterations=3) & (sat < 0.3)
    usable[int(sh * HINT_LINE_TOP):] = False
    usable = usable.ravel()
    for _ in range(6):
        coefs = [np.linalg.lstsq(design[usable], small[..., c].ravel()[usable], rcond=None)[0] for c in range(3)]
        fit = np.stack([(design @ coef).reshape(sh, sw) for coef in coefs], axis=2)
        misfit = ndimage.binary_dilation(np.linalg.norm(small - fit, axis=2) > 8, iterations=2)
        usable &= ~misfit.ravel()

    yy, xx = np.mgrid[0:height, 0:width]
    terms = _poly_terms(xx / width * 2 - 1, yy / height * 2 - 1, degree)
    return np.stack([sum(c * t for c, t in zip(coef, terms)) for coef in coefs], axis=2).astype(np.float32)


def extract_single_look(rgb, card):
    height = rgb.shape[0]
    background = fitted_background(rgb, card)
    difference = np.linalg.norm(rgb.astype(np.float32) - background, axis=2)
    _, sat = hue_saturation(rgb)

    sure = (difference > RELIC_DIFF_SOLID) | ((sat > 0.4) & (difference > RELIC_DIFF_COLOURED))
    excluded = ndimage.binary_dilation(card, iterations=20)
    excluded[int(height * HINT_LINE_TOP):] = True
    sure &= ~excluded
    labels, count = ndimage.label(sure)
    if not count:
        raise ValueError("no item found")
    sizes = ndimage.sum(sure, labels, range(1, count + 1))
    pieces = np.isin(labels, np.nonzero(sizes >= RELIC_MIN_PIECE)[0] + 1)

    low, high = RELIC_ALPHA_RAMP
    alpha = np.clip((difference - low) / (high - low), 0, 1)
    alpha *= ndimage.binary_dilation(pieces, iterations=3) & ~excluded
    body = ndimage.binary_fill_holes(largest_component(pieces))
    alpha = np.maximum(alpha, ndimage.binary_erosion(body, iterations=2) & (difference > 15))
    return to_rgba(rgb, alpha.astype(np.float32)), alpha > 0.5


def process_single(name, path, out_dir, debug=False):
    rgb = np.asarray(Image.open(path).convert("RGB"))
    stats_image, card = extract_stats(rgb)
    look_image, item = extract_single_look(rgb, card)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = output_name(name)
    look_image.save(out_dir / f"{base}-look.png", optimize=True)
    stats_image.save(out_dir / f"{base}-stats.png", optimize=True)
    if debug:
        overlay = rgb.copy()
        overlay[item] = (overlay[item] * 0.4 + np.array([255, 0, 160]) * 0.6).astype(np.uint8)
        Image.fromarray(overlay).save(out_dir / f"{base}-debug.jpg", quality=85)
    return base


def find_singles(paths):
    """{item name: screenshot} for --single mode."""
    files = []
    for path in map(Path, paths):
        if path.is_dir():
            files += [p for p in sorted(path.iterdir()) if p.suffix.lower() in IMAGE_EXTENSIONS]
        elif path.is_file():
            files.append(path)
        else:
            print(f"skipped: {path} does not exist", file=sys.stderr)
    return {file.stem: file for file in files}


# --------------------------------------------------------------------------- driver

def output_name(name):
    """Same rules as the wiki's URL slugs (Django's slugify), so the files match
    their items: "Jörmungandr" -> "jormungandr", "Hellskream'r" -> "hellskreamr"."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r"[^\w\s-]", "", ascii_name.lower())
    return re.sub(r"[-\s]+", "-", ascii_name).strip("-_")


def find_pairs(paths):
    """{item name: (look path, stats path)} from files and folders."""
    files = []
    for path in map(Path, paths):
        if path.is_dir():
            files += [p for p in sorted(path.iterdir()) if p.suffix.lower() in IMAGE_EXTENSIONS]
        elif path.is_file():
            files.append(path)
        else:
            print(f"skipped: {path} does not exist", file=sys.stderr)
    pairs = {}
    for file in files:
        match = re.fullmatch(r"(.+)-(look|stats)", file.stem, re.IGNORECASE)
        if match:
            pairs.setdefault(match.group(1), {})[match.group(2).lower()] = file
    complete = {}
    for name, found in sorted(pairs.items()):
        if "look" in found and "stats" in found:
            complete[name] = (found["look"], found["stats"])
        else:
            missing = "stats" if "look" in found else "look"
            print(f"skipped: {name} has no -{missing} screenshot", file=sys.stderr)
    return complete


def process(name, look_path, stats_path, out_dir, debug=False):
    look_rgb = np.asarray(Image.open(look_path).convert("RGB"))
    stats_rgb = np.asarray(Image.open(stats_path).convert("RGB"))
    if look_rgb.shape != stats_rgb.shape:
        raise ValueError(f"screenshots have different sizes: {look_rgb.shape[:2]} vs {stats_rgb.shape[:2]}")

    stats_image, card = extract_stats(stats_rgb)
    look_image, item = extract_look(look_rgb, stats_rgb, card)

    out_dir.mkdir(parents=True, exist_ok=True)
    base = output_name(name)
    look_image.save(out_dir / f"{base}-look.png", optimize=True)
    stats_image.save(out_dir / f"{base}-stats.png", optimize=True)

    if debug:
        overlay = look_rgb.copy()
        overlay[item] = (overlay[item] * 0.4 + np.array([255, 0, 160]) * 0.6).astype(np.uint8)
        edge = card ^ ndimage.binary_erosion(card, iterations=3)
        overlay[edge] = (0, 255, 0)
        Image.fromarray(overlay).save(out_dir / f"{base}-debug.jpg", quality=85)
    return base


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", help="Screenshot files and/or folders containing them.")
    parser.add_argument("--out", help='Output folder (default: "extracted" next to the screenshots).')
    parser.add_argument("--debug", action="store_true", help="Also save an overlay of what was detected.")
    parser.add_argument("--single", action="store_true",
                        help="One screenshot per item (relics): <Name>.jpg gives both images.")
    args = parser.parse_args()

    if args.single:
        singles = find_singles(args.paths)
        if not singles:
            sys.exit("No screenshots found.")
        failed = 0
        for name, path in singles.items():
            out_dir = Path(args.out) if args.out else path.parent / "extracted"
            try:
                base = process_single(name, path, out_dir, args.debug)
                print(f"{name}: {out_dir / (base + '-look.png')}, {out_dir / (base + '-stats.png')}")
            except Exception as error:
                failed += 1
                print(f"{name}: FAILED - {error}", file=sys.stderr)
        sys.exit(1 if failed else 0)

    pairs = find_pairs(args.paths)
    if not pairs:
        sys.exit("No <Name>-look / <Name>-stats screenshot pairs found.")
    failed = 0
    for name, (look_path, stats_path) in pairs.items():
        out_dir = Path(args.out) if args.out else look_path.parent / "extracted"
        try:
            base = process(name, look_path, stats_path, out_dir, args.debug)
            print(f"{name}: {out_dir / (base + '-look.png')}, {out_dir / (base + '-stats.png')}")
        except Exception as error:  # keep going with the other items
            failed += 1
            print(f"{name}: FAILED - {error}", file=sys.stderr)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
