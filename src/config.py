import os
import logging
import mimetypes

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("WatchWithMe")

# Path configs
DB_PATH = "data/movies.db"
MEDIA_DIR = "data/media"
TEMP_DIR = "data/temp"

# Ensure directories exist
os.makedirs("data", exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(os.path.join(MEDIA_DIR, "thumbnails"), exist_ok=True)
os.makedirs(os.path.join(MEDIA_DIR, "subtitles"), exist_ok=True)
os.makedirs(os.path.join(MEDIA_DIR, "videos"), exist_ok=True)

# Register HLS MIME types to fix Windows mappings
mimetypes.add_type("application/vnd.apple.mpegurl", ".m3u8")
mimetypes.add_type("video/mp2t", ".ts")
mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("video/mp4", ".m4s")
