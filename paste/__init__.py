from flask import Blueprint

paste_bp = Blueprint("paste", __name__)
from . import routes
