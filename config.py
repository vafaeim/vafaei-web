import os
from datetime import timedelta


class Config:
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    SECRET_KEY = os.environ.get("SECRET_KEY", "")
    VERIFY_BOT_TOKEN = os.environ.get("VERIFY_BOT_TOKEN", "")
    WHISPER_CONFIG_FILE = "whisper_config.json"
    WHISPER_SECRET_KEY = os.environ.get("WHISPER_SECRET_KEY", "")
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 5242880))
