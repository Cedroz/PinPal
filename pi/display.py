"""
display.py — drives the ST7789 SPI TFT as a status face for the MCP server.

Two states, owned by a background render thread:
  - idle : the orange Claude pixel-creature does a looping dance (bob + leg tap)
  - busy : a verb ("Capturing…") in animated gradient-shimmer text, with a small
           creature/logo and a pulsing sparkle beside it.

The MCP server flips state via set_busy(verb)/set_idle(); rendering never blocks
the server, and a missing library / unplugged panel degrades to a no-op so the
tools keep working headless.

Standalone preview (no MCP, iterate art on the Pi):
  python -m pi.display --demo
"""

import math
import threading
import time

try:
    from . import config as cfg
except ImportError:  # run as a plain script from the pi/ dir
    import config as cfg


# --- palette --------------------------------------------------------------
BG        = (16, 16, 20)
ORANGE    = (217, 119, 87)     # Claude clay
EYE       = BG                 # eyes match the background
GOLD      = (235, 180, 90)     # shimmer base
WHITE     = (255, 255, 255)


# --- creature sprite ------------------------------------------------------
# Body only (legs are animated separately). '1' = orange, 'W' = eye, '.' = clear.
# 16 wide. Side tabs reach the full width at the mid rows.
BODY = [
    "................",
    ".11111111111111.",
    ".11111111111111.",
    ".11WW111111WW11.",
    ".11WW111111WW11.",
    ".11WW111111WW11.",
    "1111111111111111",
    "1111111111111111",
    ".11111111111111.",
    ".11111111111111.",
]
SPRITE_W = 16
BODY_H = len(BODY)
# (col_start, col_end) of each leg, in sprite columns; legs hang below the body.
LEG_COLS = [(2, 3), (5, 6), (10, 11), (13, 14)]
LEG_LEN = 3        # base leg length in sprite pixels


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Display:
    def __init__(self):
        self._lock = threading.Lock()
        self._depth = 0          # >0 == busy; counts overlapping tool calls
        self._verb = ""
        self._enabled = False
        self._disp = None
        self._stop = threading.Event()
        self._thread = None
        self._fonts = {}         # size -> ImageFont, lazily built

    # --- public API -------------------------------------------------------
    def start(self):
        if not cfg.DISPLAY_ENABLED:
            print("[display] disabled in config — skipping")
            return
        self._disp = self._init_hw()
        if self._disp is None:
            return
        self._enabled = True
        self._thread = threading.Thread(target=self._loop, name="display", daemon=True)
        self._thread.start()

    def set_busy(self, verb):
        with self._lock:
            self._depth += 1
            self._verb = verb

    def set_idle(self):
        with self._lock:
            if self._depth > 0:
                self._depth -= 1

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    # --- hardware ---------------------------------------------------------
    def _init_hw(self):
        try:
            import st7789
            disp = st7789.ST7789(
                port=cfg.DISPLAY_PORT, cs=cfg.DISPLAY_CS, dc=cfg.DISPLAY_DC,
                rst=cfg.DISPLAY_RST, backlight=None,        # BLK hard-wired to 3V3
                width=cfg.DISPLAY_WIDTH, height=cfg.DISPLAY_HEIGHT,
                rotation=cfg.DISPLAY_ROTATION, spi_speed_hz=cfg.DISPLAY_SPI_HZ,
            )
            # GOTCHA: the st7789 PyPI constructor leaves the hardware RST pin held
            # low and fires its init commands while the chip is in reset, so they
            # are silently ignored (backlight on, screen blank white). .begin() is
            # a documented no-op. Re-run reset + init by hand to actually wake it.
            disp.reset()
            disp._init()
            return disp
        except Exception as e:
            print(f"[display] init failed ({e}) — running headless, no display")
            return None

    def _font(self, size):
        if size not in self._fonts:
            from PIL import ImageFont
            try:
                self._fonts[size] = ImageFont.truetype(cfg.DISPLAY_FONT, size)
            except Exception:
                self._fonts[size] = ImageFont.load_default()
        return self._fonts[size]

    def _fit_font(self, text, max_w, max_size=34, min_size=12):
        """Largest font (<= max_size) whose rendered text fits within max_w px."""
        for size in range(max_size, min_size - 1, -2):
            f = self._font(size)
            x0, _, x1, _ = f.getbbox(text)
            if x1 - x0 <= max_w:
                return f
        return self._font(min_size)

    # --- render loop ------------------------------------------------------
    def _loop(self):
        from PIL import Image
        W, H = cfg.DISPLAY_WIDTH, cfg.DISPLAY_HEIGHT
        period = 1.0 / max(1, cfg.DISPLAY_FPS)
        frame = 0
        while not self._stop.is_set():
            t0 = time.monotonic()
            with self._lock:
                busy = self._depth > 0
                verb = self._verb
            img = Image.new("RGB", (W, H), BG)
            if busy:
                self._draw_busy(img, verb, frame)
            else:
                self._draw_idle(img, frame)
            try:
                self._disp.display(img)
            except Exception as e:
                print(f"[display] push failed ({e}) — stopping render thread")
                return
            frame += 1
            time.sleep(max(0, period - (time.monotonic() - t0)))

    # --- drawing primitives ----------------------------------------------
    def _blit_body(self, draw, ox, oy, scale):
        for ry, row in enumerate(BODY):
            for cx, ch in enumerate(row):
                if ch == ".":
                    continue
                color = EYE if ch == "W" else ORANGE
                x = ox + cx * scale
                y = oy + ry * scale
                draw.rectangle([x, y, x + scale - 1, y + scale - 1], fill=color)

    def _draw_creature(self, draw, ox, oy, scale, frame, dance=True):
        """Body at (ox, oy); legs tap below it with a phase ripple when dancing."""
        self._blit_body(draw, ox, oy, scale)
        leg_top = oy + BODY_H * scale
        for i, (c0, c1) in enumerate(LEG_COLS):
            wob = 0
            if dance:
                wob = round((math.sin(frame * 0.5 + i * (math.pi / 2)) + 1) * scale)
            x0 = ox + c0 * scale
            x1 = ox + (c1 + 1) * scale - 1
            draw.rectangle([x0, leg_top, x1, leg_top + LEG_LEN * scale + wob], fill=ORANGE)

    def _draw_idle(self, img, frame):
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        W, H = img.size
        scale = max(4, W // 24)
        sprite_w = SPRITE_W * scale
        sprite_h = (BODY_H + LEG_LEN) * scale
        # bob + gentle sway
        dy = round(scale * 0.8 * math.sin(frame * 0.25))
        dx = round(scale * 0.5 * math.sin(frame * 0.25 + math.pi / 2))
        ox = (W - sprite_w) // 2 + dx
        oy = (H - sprite_h) // 2 + dy
        self._draw_creature(draw, ox, oy, scale, frame, dance=True)

    def _draw_busy(self, img, verb, frame):
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        W, H = img.size
        # small logo creature at the left
        scale = max(2, W // 60)
        logo_w = SPRITE_W * scale
        logo_h = (BODY_H + LEG_LEN) * scale
        ox = max(6, W // 20)
        oy = (H - logo_h) // 2
        self._draw_creature(draw, ox, oy, scale, frame, dance=False)
        self._draw_sparkle(draw, ox + logo_w, oy + scale * 2, scale, frame)
        # shimmering verb to the right of the logo
        text_x = ox + logo_w + scale * 4
        self._shimmer_text(img, f"{verb}…", text_x, frame)

    def _draw_sparkle(self, draw, cx, cy, scale, frame):
        s = scale * (2.0 + 1.2 * (math.sin(frame * 0.6) + 1) / 2)  # pulsing size
        v = round(150 + 105 * (math.sin(frame * 0.6) + 1) / 2)     # pulsing brightness
        a = s * 0.28
        pts = [
            (cx, cy - s), (cx + a, cy - a), (cx + s, cy), (cx + a, cy + a),
            (cx, cy + s), (cx - a, cy + a), (cx - s, cy), (cx - a, cy - a),
        ]
        draw.polygon(pts, fill=(v, v, v))

    def _shimmer_text(self, img, text, px, frame):
        from PIL import Image, ImageDraw
        font = self._fit_font(text, img.size[0] - px - 6)
        x0, y0, x1, y1 = font.getbbox(text)
        tw, th = x1 - x0, y1 - y0
        if tw <= 0 or th <= 0:
            return
        # glyph alpha mask
        mask = Image.new("L", (tw, th), 0)
        ImageDraw.Draw(mask).text((-x0, -y0), text, font=font, fill=255)
        # gradient with a moving highlight band sweeping across the word
        grad = Image.new("RGB", (tw, th), GOLD)
        gd = ImageDraw.Draw(grad)
        band = max(8, tw // 4)
        hc = (frame * 6) % (tw + band) - band     # highlight center, sweeps in
        for x in range(tw):
            h = max(0.0, 1.0 - abs(x - hc) / band)
            gd.line([(x, 0), (x, th)], fill=_lerp(GOLD, WHITE, h))
        py = (img.size[1] - th) // 2
        img.paste(grad, (px, py), mask)


# --- standalone preview ---------------------------------------------------
if __name__ == "__main__":
    import sys

    if "--demo" in sys.argv:
        d = Display()
        d.start()
        if not d._enabled:
            print("[display] demo: no panel — nothing to show")
            sys.exit(1)
        try:
            script = [("idle", None, 4), ("busy", "Capturing", 4),
                      ("busy", "Scanning", 4), ("busy", "Flashing", 4)]
            while True:
                for state, verb, secs in script:
                    if state == "busy":
                        d.set_busy(verb)
                    print(f"[display] demo -> {state} {verb or ''}")
                    time.sleep(secs)
                    if state == "busy":
                        d.set_idle()
        except KeyboardInterrupt:
            d.stop()
