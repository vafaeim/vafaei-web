from flask import render_template
from extensions import app
from . import douz_bp


@douz_bp.route("/douz/")
def douz_page():
    return render_template("douz.html")
