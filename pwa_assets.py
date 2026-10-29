"""PWA Assets Generator for Ad Vandi.
Ensures crisp PNG and SVG icons exist in static/icons/ on startup.
Zero hard dependencies: Uses PIL if available, with a pure Python (zlib + struct) fallback.
"""
import os
import struct
import zlib

ICONS_DIR = os.path.join(os.path.dirname(__file__), "static", "icons")
LOGO_PATH = os.path.join(os.path.dirname(__file__), "static", "ad-vandi-logo.png")


def _write_png(width, height, rgba_data, filepath):
    """Write raw RGBA pixel data to a valid PNG file using pure Python."""
    # PNG signature
    signature = b"\x89PNG\r\n\x1a\n"

    # IHDR chunk
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
    ihdr_chunk = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)

    # Scanlines with filter byte 0 (None)
    raw_scanlines = bytearray()
    row_bytes = width * 4
    for y in range(height):
        raw_scanlines.append(0)  # filter type 0
        raw_scanlines.extend(rgba_data[y * row_bytes : (y + 1) * row_bytes])

    compressed = zlib.compress(bytes(raw_scanlines), level=9)
    idat_crc = zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF
    idat_chunk = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", idat_crc)

    # IEND chunk
    iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
    iend_chunk = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "wb") as f:
        f.write(signature + ihdr_chunk + idat_chunk + iend_chunk)


def _draw_icon(size, is_maskable=False):
    """Generate RGBA pixels for Ad Vandi truck icon at given square size."""
    w = h = size
    buf = bytearray(w * h * 4)

    # Scale factor
    s = size / 512.0

    # Colors
    bg_r, bg_g, bg_b = 8, 12, 22          # #080c16
    gold_top = (250, 227, 157)             # #fae39d
    gold_mid = (232, 202, 120)             # #e8ca78
    gold_bot = (184, 147, 59)              # #b8933b
    truck_c = (21, 18, 12)                 # #15120c dark ink
    white_trans = (255, 255, 255, 40)

    # Badge bounding box (centered)
    badge_size = int(size * (0.68 if not is_maskable else 0.58))
    badge_x = (size - badge_size) // 2
    badge_y = (size - badge_size) // 2
    corner_r = int(badge_size * 0.22)

    def in_rounded_rect(px, py, rx, ry, rw, rh, rad):
        if px < rx or px >= rx + rw or py < ry or py >= ry + rh:
            return False
        # corners
        cx = rx + rad if px < rx + rad else (rx + rw - rad - 1 if px >= rx + rw - rad else None)
        cy = ry + rad if py < ry + rad else (ry + rh - rad - 1 if py >= ry + rh - rad else None)
        if cx is not None and cy is not None:
            return ((px - cx) ** 2 + (py - cy) ** 2) <= (rad ** 2)
        return True

    # Truck coordinates normalized to badge interior
    # Badge has width/height `badge_size`, origin (badge_x, badge_y)
    bw = badge_size
    bx = badge_x
    by = badge_y

    for y in range(h):
        for x in range(w):
            idx = (y * w + x) * 4

            # Default: background
            r, g, b, a = bg_r, bg_g, bg_b, 255

            # Subtle radial background glow
            dx = (x - w / 2) / (w / 2)
            dy = (y - h / 2) / (h / 2)
            dist_sq = dx * dx + dy * dy
            if dist_sq < 1.0:
                glow = (1.0 - dist_sq) * 0.14
                r = int(min(255, r + 232 * glow))
                g = int(min(255, g + 202 * glow))
                b = int(min(255, b + 120 * glow))

            # Is pixel inside golden badge?
            if in_rounded_rect(x, y, bx, by, bw, bw, corner_r):
                # Gradient from top to bottom
                t = (y - by) / float(bw)
                if t < 0.5:
                    sub_t = t * 2.0
                    gr = int(gold_top[0] * (1 - sub_t) + gold_mid[0] * sub_t)
                    gg = int(gold_top[1] * (1 - sub_t) + gold_mid[1] * sub_t)
                    gb = int(gold_top[2] * (1 - sub_t) + gold_mid[2] * sub_t)
                else:
                    sub_t = (t - 0.5) * 2.0
                    gr = int(gold_mid[0] * (1 - sub_t) + gold_bot[0] * sub_t)
                    gg = int(gold_mid[1] * (1 - sub_t) + gold_bot[1] * sub_t)
                    gb = int(gold_mid[2] * (1 - sub_t) + gold_bot[2] * sub_t)

                r, g, b = gr, gg, gb

                # Truck drawing inside badge
                nx = (x - bx) / float(bw)
                ny = (y - by) / float(bw)

                # Truck Box: nx in [0.20, 0.56], ny in [0.32, 0.64]
                is_truck_box_border = (
                    (0.20 <= nx <= 0.56 and 0.32 <= ny <= 0.64) and
                    (nx <= 0.24 or nx >= 0.52 or ny <= 0.36 or ny >= 0.60)
                )

                # Truck Cab: nx in [0.56, 0.78], ny in [0.42, 0.64]
                is_cab_body = (
                    (0.56 <= nx <= 0.78 and 0.42 <= ny <= 0.64) and
                    (nx >= 0.74 or ny <= 0.46 or ny >= 0.60)
                )

                # Cab Window: nx in [0.60, 0.72], ny in [0.45, 0.53]
                is_window = (0.59 <= nx <= 0.73 and 0.45 <= ny <= 0.53)

                # Wheels: center1=(0.33, 0.68), center2=(0.67, 0.68), radius=0.08
                w1_d = ((nx - 0.33) ** 2 + (ny - 0.68) ** 2) ** 0.5
                w2_d = ((nx - 0.67) ** 2 + (ny - 0.68) ** 2) ** 0.5
                is_wheel = (w1_d <= 0.08 or w2_d <= 0.08)
                is_wheel_hub = (w1_d <= 0.035 or w2_d <= 0.035)

                # Chassis beam: ny in [0.61, 0.65], nx in [0.22, 0.76]
                is_chassis = (0.22 <= nx <= 0.76 and 0.61 <= ny <= 0.65)

                if is_wheel_hub:
                    r, g, b = gold_top
                elif is_wheel or is_truck_box_border or is_cab_body or is_chassis:
                    r, g, b = truck_c
                elif is_window:
                    r, g, b = (242, 216, 140)

            buf[idx] = r
            buf[idx + 1] = g
            buf[idx + 2] = b
            buf[idx + 3] = a

    return bytes(buf)


def _generate_with_pil():
    """If PIL is installed, render using PIL for maximum anti-aliasing quality."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False

    os.makedirs(ICONS_DIR, exist_ok=True)

    # We can create base 512x512
    for size, name, is_maskable in [
        (512, "icon-512.png", False),
        (512, "icon-maskable-512.png", True),
        (192, "icon-192.png", False),
        (180, "apple-touch-icon.png", False),
        (32, "favicon.png", False),
    ]:
        out_file = os.path.join(ICONS_DIR, name)
        # Check if already exists
        if os.path.exists(out_file) and os.path.getsize(out_file) > 100:
            continue

        scale = size / 512.0
        im = Image.new("RGBA", (size, size), (8, 12, 22, 255))
        draw = ImageDraw.Draw(im)

        # Badge
        badge_ratio = 0.58 if is_maskable else 0.68
        b_size = int(size * badge_ratio)
        bx = (size - b_size) // 2
        by = (size - b_size) // 2
        corner_r = int(b_size * 0.22)

        # Draw rounded badge
        draw.rounded_rectangle(
            [bx, by, bx + b_size, by + b_size],
            radius=corner_r,
            fill=(232, 202, 120, 255),
            outline=(255, 240, 190, 180),
            width=max(1, int(2 * scale)),
        )

        # Truck inside badge
        truck_color = (21, 18, 12, 255)
        # Cargo box
        box_x1 = bx + int(b_size * 0.18)
        box_y1 = by + int(b_size * 0.28)
        box_x2 = bx + int(b_size * 0.56)
        box_y2 = by + int(b_size * 0.64)
        box_stroke = max(2, int(12 * scale))

        draw.rounded_rectangle(
            [box_x1, box_y1, box_x2, box_y2],
            radius=int(10 * scale),
            outline=truck_color,
            width=box_stroke,
            fill=(21, 18, 12, 20),
        )

        # Cab
        cab_x1 = box_x2
        cab_y1 = by + int(b_size * 0.40)
        cab_x2 = bx + int(b_size * 0.80)
        cab_y2 = box_y2
        draw.polygon(
            [
                (cab_x1, cab_y1),
                (bx + int(b_size * 0.70), cab_y1),
                (cab_x2, by + int(b_size * 0.50)),
                (cab_x2, cab_y2),
                (cab_x1, cab_y2),
            ],
            outline=truck_color,
            fill=(21, 18, 12, 20),
        )
        draw.line(
            [(cab_x1, cab_y1), (bx + int(b_size * 0.70), cab_y1), (cab_x2, by + int(b_size * 0.50)), (cab_x2, cab_y2)],
            fill=truck_color,
            width=box_stroke,
        )

        # Window
        win_x1 = bx + int(b_size * 0.60)
        win_y1 = by + int(b_size * 0.44)
        win_x2 = bx + int(b_size * 0.73)
        win_y2 = by + int(b_size * 0.52)
        draw.rectangle([win_x1, win_y1, win_x2, win_y2], fill=(250, 227, 157, 255), outline=truck_color, width=max(1, int(3 * scale)))

        # Wheels
        wheel_r = int(b_size * 0.08)
        for wx in [bx + int(b_size * 0.33), bx + int(b_size * 0.67)]:
            wy = by + int(b_size * 0.68)
            draw.ellipse([wx - wheel_r, wy - wheel_r, wx + wheel_r, wy + wheel_r], fill=truck_color, outline=(250, 227, 157, 255), width=max(1, int(4 * scale)))

        im.save(out_file, "PNG", optimize=True)

    return True


def ensure_pwa_icons():
    """Ensure all required PWA icons exist. Safe to call multiple times."""
    os.makedirs(ICONS_DIR, exist_ok=True)

    targets = [
        (512, "icon-512.png", False),
        (512, "icon-maskable-512.png", True),
        (192, "icon-192.png", False),
        (180, "apple-touch-icon.png", False),
        (32, "favicon.png", False),
    ]

    all_exist = all(
        os.path.exists(os.path.join(ICONS_DIR, name)) and os.path.getsize(os.path.join(ICONS_DIR, name)) > 100
        for _, name, _ in targets
    )
    if all_exist:
        return

    # Try PIL first
    if _generate_with_pil():
        return

    # Pure Python fallback
    for size, name, is_maskable in targets:
        filepath = os.path.join(ICONS_DIR, name)
        if not (os.path.exists(filepath) and os.path.getsize(filepath) > 100):
            pixels = _draw_icon(size, is_maskable)
            _write_png(size, size, pixels, filepath)


# Auto-run when module is loaded
ensure_pwa_icons()
