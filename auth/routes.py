import re
import requests
import secrets
import string
from datetime import datetime

from werkzeug.security import generate_password_hash, check_password_hash
from flask import request, jsonify, render_template, session, redirect, url_for

from extensions import app, socketio
from database import database, update_last_seen
from config import Config
import psycopg2.extras
import psycopg2.errors
from . import auth_bp


def rubika_get_updates(token, max_pages=5):
    url = f"https://botapi.rubika.ir/v3/{token}/getUpdates"
    offset_id = None
    all_updates = []

    for _ in range(max_pages):
        payload = {"limit": "100"}
        if offset_id:
            payload["offset_id"] = offset_id

        try:
            resp = requests.post(url, json=payload, timeout=10)
            if not resp.ok:
                break
            data = resp.json()
            if data.get("status") != "OK":
                break

            updates = data.get("data", {}).get("updates", [])
            if not updates:
                break
            all_updates.extend(updates)

            next_offset = data.get("data", {}).get("next_offset_id")
            if next_offset:
                offset_id = next_offset
            else:
                break
        except:
            break

    return {"status": "OK", "data": {"updates": all_updates}} if all_updates else None


def rubika_get_chat(token, chat_id):
    url = f"https://botapi.rubika.ir/v3/{token}/getChat"
    try:
        resp = requests.post(url, json={"chat_id": chat_id}, timeout=10)
        if resp.ok:
            return resp.json()
    except:
        pass
    return None


@auth_bp.route("/login", methods=["GET"])
def login():
    if "user_id" in session:
        return redirect(url_for("chat.chat_page"))

    code = "".join(
        secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8)
    )
    otp_token = secrets.token_hex(32)
    now_unix = int(datetime.utcnow().timestamp())
    expires_unix = now_unix + 90

    try:
        with database() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO otps (code, session_token, created_at_unix, expires_at_unix) VALUES (%s, %s, %s, %s)",
                    (code, otp_token, now_unix, expires_unix),
                )
    except RuntimeError:
        return jsonify({"error": "Database service unavailable"}), 503

    return render_template("login.html", code=code, otp_token=otp_token)


@auth_bp.route("/api/verify_otp")
def verify_otp():
    code = request.args.get("code", "").strip()
    otp_token = request.args.get("otp_token", "").strip()
    if not code or not otp_token:
        return jsonify({"success": False, "error": "پارامترها ناقص هستند."})
    try:
        with database() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM otps WHERE session_token = %s AND used = FALSE AND expires_at_unix > %s",
                    (otp_token, int(datetime.utcnow().timestamp())),
                )
                otp_record = cur.fetchone()
                if not otp_record:
                    return jsonify({"success": False, "error": "کد منقضی یا نامعتبر."})

                token = Config.VERIFY_BOT_TOKEN
                if not token:
                    return jsonify(
                        {"success": False, "error": "ربات تأیید هویت تنظیم نشده است."}
                    )

                updates_data = rubika_get_updates(token, max_pages=2)
                if not updates_data or updates_data.get("status") != "OK":
                    return jsonify(
                        {"success": False, "error": "خطا در دریافت پیام‌های ربات."}
                    )

                updates = updates_data.get("data", {}).get("updates", [])
                verified_chat_id = None
                for update in updates:
                    if update.get("type") == "NewMessage":
                        new_msg = update.get("new_message", {})
                        if new_msg.get("text") == code and new_msg.get("time"):
                            msg_time = int(new_msg["time"])
                            otp_created = int(otp_record["created_at_unix"])
                            if msg_time >= otp_created:
                                verified_chat_id = update.get("chat_id")
                                break

                if not verified_chat_id:
                    return jsonify(
                        {"success": False, "error": "هنوز پیامی با این کد دریافت نشده."}
                    )

                cur.execute(
                    "UPDATE otps SET used = TRUE, rubika_chat_id = %s WHERE id = %s",
                    (verified_chat_id, otp_record["id"]),
                )

                chat_data = rubika_get_chat(token, verified_chat_id)
                if not chat_data or chat_data.get("status") != "OK":
                    return jsonify(
                        {"success": False, "error": "خطا در دریافت اطلاعات کاربر."}
                    )

                user_info = chat_data["data"]["chat"]
                rubika_first_name = (
                    user_info.get("first_name", "")
                    or user_info.get("username", "")
                    or "کاربر"
                )

                cur.execute(
                    "SELECT id, username FROM users WHERE rubika_chat_id = %s",
                    (verified_chat_id,),
                )
                existing_user = cur.fetchone()

                if existing_user:
                    user_id = existing_user["id"]
                    display_name = existing_user["username"] or rubika_first_name
                    session["user_id"] = user_id
                    session["username"] = display_name
                    update_last_seen(session["user_id"])
                    return jsonify({"success": True, "new_user": False})
                else:
                    session["temp_rubika_chat_id"] = verified_chat_id
                    return jsonify({"success": True, "new_user": True})
    except RuntimeError:
        return jsonify({"error": "Database service unavailable"}), 503


@auth_bp.route("/api/set_username", methods=["POST"])
def set_username():
    if "temp_rubika_chat_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    username = data.get("username", "").strip()
    if not username:
        return jsonify({"error": "Username cannot be empty."}), 400
    if not re.match(r"^[a-zA-Z0-9_]{3,20}$", username):
        return jsonify(
            {
                "error": "Username must be 3-20 characters, letters, numbers or underscore."
            }
        ), 400

    try:
        with database() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "INSERT INTO users (username, rubika_chat_id) VALUES (%s, %s) RETURNING id",
                    (username, session["temp_rubika_chat_id"]),
                )
                user = cur.fetchone()
            session.pop("temp_rubika_chat_id", None)
            session["user_id"] = user["id"]
            session["username"] = username
            return jsonify({"success": True})
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "Username already taken"}), 409
    except RuntimeError:
        return jsonify({"error": "Database service unavailable"}), 503


@auth_bp.route("/api/set_password", methods=["POST"])
def set_password():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json()
    password = data.get("password", "")
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    password_hash = generate_password_hash(password)
    try:
        with database() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET password_hash = %s WHERE id = %s",
                    (password_hash, session["user_id"]),
                )
        return jsonify({"success": True})
    except RuntimeError:
        return jsonify({"error": "Database unavailable"}), 503


@auth_bp.route("/api/login_password", methods=["POST"])
def login_password():
    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "")

    try:
        with database() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, username, password_hash FROM users WHERE username = %s",
                    (username,),
                )
                user = cur.fetchone()
                if user and user["password_hash"]:
                    if check_password_hash(user["password_hash"], password):
                        session["user_id"] = user["id"]
                        session["username"] = user["username"]
                        update_last_seen(session["user_id"])
                        return jsonify({"success": True})

                return jsonify(
                    {"success": False, "error": "Invalid username or password"}
                ), 401
    except RuntimeError:
        return jsonify({"error": "Database unavailable"}), 503


@auth_bp.route("/set-username")
def set_username_page():
    if "temp_rubika_chat_id" not in session:
        return redirect(url_for("auth.login"))
    return render_template("set_username.html")


@auth_bp.route("/set-password")
def set_password_page():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    return render_template("set_password.html")
