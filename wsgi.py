from flask import render_template
from extensions import app, init_pool
from database import init_db
from scheduler import start_scheduler

from auth import auth_bp
from chat import chat_bp
from whisper import whisper_bp
from douz import douz_bp

app.register_blueprint(auth_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(whisper_bp)
app.register_blueprint(douz_bp)

@app.route("/")
def index():
    return render_template("main.html")

with app.app_context():
    init_pool()
    init_db()
    start_scheduler()
