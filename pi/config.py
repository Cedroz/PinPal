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
