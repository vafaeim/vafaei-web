from flask import Blueprint

whisper_bp = Blueprint("whisper", __name__)
from . import routes
