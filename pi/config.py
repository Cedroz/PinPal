from dotenv import load_dotenv

load_dotenv()

CAMERA_INDEX = 0
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720

VISION_POLL_INTERVAL_S = 2.0
VISION_CONFIRM_COUNT = 2    # consecutive matching reads required
VISION_MAX_FAILS_BEFORE_HINT = 5

REFERENCE_DIR = "reference"
RUNS_DIR = "runs"

# ST7789 SPI display (BLK->3V3 always on, DC->GPIO24, RST->GPIO25, CS->CE0)
DISPLAY_ENABLED   = True
DISPLAY_PORT      = 0          # SPI0
DISPLAY_CS        = 0          # CE0
DISPLAY_DC        = 24
DISPLAY_RST       = 25
DISPLAY_WIDTH     = 240
DISPLAY_HEIGHT    = 240        # set 320 for the taller ST7789 variant
DISPLAY_ROTATION  = 0          # rotate 90/180/270 if orientation is wrong
DISPLAY_SPI_HZ    = 4_000_000  # conservative for breadboard jumpers; raise for smoother anim
DISPLAY_FPS       = 12
DISPLAY_FONT      = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
