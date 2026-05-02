from flask import Blueprint

douz_bp = Blueprint("douz", __name__)
from . import routes, events
