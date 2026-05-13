import os
from extensions import app, socketio, init_pool
from database import init_db
from scheduler import start_scheduler
from flask import request, redirect, url_for, session, render_template

from auth import auth_bp
from chat import chat_bp
from whisper import whisper_bp
from douz import douz_bp
from paste import paste_bp

app.register_blueprint(auth_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(whisper_bp)
app.register_blueprint(douz_bp)
app.register_blueprint(paste_bp)


@app.route("/")
def index():
    return render_template("main.html")


@app.route("/join")
def join_via_invite():
    code = request.args.get("code", "")
    if not code:
        return "Missing invite code", 400
    if "user_id" not in session:
        return redirect(url_for("auth.login", next=request.url))
    return redirect(url_for("chat.chat_page") + f"?code={code}")


with app.app_context():
    init_pool()
    init_db()
    start_scheduler()

if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    socketio.run(
        app, host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=debug_mode
    )
