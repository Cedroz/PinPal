import os
from dotenv import load_dotenv

load_dotenv()

DEEPGRAM_API_KEY = os.environ["DEEPGRAM_API_KEY"]
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
ARIZE_API_KEY = os.getenv("ARIZE_API_KEY", "")
ARIZE_SPACE_KEY = os.getenv("ARIZE_SPACE_KEY", "")

CAMERA_INDEX = 0
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720

VISION_POLL_INTERVAL_S = 2.0
VISION_CONFIRM_COUNT = 2    # consecutive matching reads required
VISION_MAX_FAILS_BEFORE_HINT = 5

REFERENCE_DIR = "reference"
RUNS_DIR = "runs"
