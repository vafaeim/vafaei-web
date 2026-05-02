import json
import os
from datetime import datetime
from flask import request, jsonify, render_template
from extensions import app
from config import Config
import requests
from . import whisper_bp


def load_whisper_config():
    if os.path.exists(Config.WHISPER_CONFIG_FILE):
        try:
            with open(Config.WHISPER_CONFIG_FILE, "r") as f:
                config = json.load(f)
            if config.get("token") and config.get("chat_id"):
                return config
        except:
            pass

    token = os.environ.get("WHISPER_TOKEN", "")
    chat_id = os.environ.get("WHISPER_CHAT_ID", "")
    if token and chat_id:
        return {"token": token, "chat_id": chat_id}

    return {"token": "", "chat_id": ""}


def save_whisper_config(token, chat_id):
    with open(Config.WHISPER_CONFIG_FILE, "w") as f:
        json.dump({"token": token, "chat_id": chat_id}, f)


@whisper_bp.route("/whisper/")
def whisper_home():
    return render_template("whisper.html")


@whisper_bp.route("/whisper/settings", methods=["GET", "POST"])
def whisper_settings():
    if request.method == "GET":
        key = request.args.get("key", "")
        if key != Config.WHISPER_SECRET_KEY:
            return "Access denied. Add ?key=YOUR_SECRET_KEY to the URL.", 403
        config = load_whisper_config()
        return render_template(
            "whisper_settings.html",
            token=config.get("token", ""),
            chat_id=config.get("chat_id", ""),
        )
    if request.method == "POST":
        data = request.get_json()
        if not data or data.get("key") != Config.WHISPER_SECRET_KEY:
            return jsonify({"success": False, "error": "Invalid security key."}), 403
        token = data.get("token", "").strip()
        chat_id = data.get("chat_id", "").strip()
        if not token or not chat_id:
            return jsonify(
                {"success": False, "error": "Both fields are required."}
            ), 400
        save_whisper_config(token, chat_id)
        return jsonify({"success": True})


@whisper_bp.route("/whisper/send", methods=["POST"])
def whisper_send():
    config = load_whisper_config()
    token = config.get("token")
    chat_id = config.get("chat_id")
    if not token or not chat_id:
        return jsonify({"success": False, "error": "Bot not configured."}), 500
    data = request.get_json()
    if not data or "text" not in data:
        return jsonify({"success": False, "error": "No text provided"}), 400
    text = data["text"].strip()
    if not text:
        return jsonify({"success": False, "error": "Empty message"}), 400
    raw_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    ip = raw_ip.split(",")[0].strip() if raw_ip else "Unknown"
    user_agent = request.headers.get("User-Agent", "Unknown")
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    full_text = (
        f"📩 New message:\n{text}\n\n"
        f"──────────────────\n"
        f"🕵️ Sender info:\n"
        f"IP: {ip}\n"
        f"Device: {user_agent}\n"
        f"Time: {timestamp}"
    )
    api_url = f"https://botapi.rubika.ir/v3/{token}/sendMessage"
    try:
        resp = requests.post(
            api_url,
            json={"chat_id": chat_id, "text": full_text},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if resp.ok:
            return jsonify({"success": True})
        else:
            return jsonify(
                {"success": False, "error": f"API error: {resp.text}"}
            ), resp.status_code
    except requests.exceptions.RequestException as e:
        return jsonify({"success": False, "error": str(e)}), 500


@whisper_bp.route("/whisper/send_file", methods=["POST"])
def whisper_send_file():
    config = load_whisper_config()
    token = config.get("token")
    chat_id = config.get("chat_id")
    if not token or not chat_id:
        return jsonify({"success": False, "error": "Bot not configured."}), 500

    file = request.files.get("file")
    if not file:
        return jsonify({"success": False, "error": "No file provided."}), 400

    caption = request.form.get("text", "").strip()
    mime = file.mimetype.lower() if file.mimetype else ""

    if mime.startswith("image/"):
        rubika_type = "Image"
    elif mime.startswith("audio/") or mime.startswith("video/webm"):
        rubika_type = "File"
    else:
        rubika_type = "File"

    try:
        resp = requests.post(
            f"https://botapi.rubika.ir/v3/{token}/requestSendFile",
            json={"type": rubika_type},
            timeout=10,
        )
        if not resp.ok:
            return jsonify(
                {"success": False, "error": f"API error ({resp.status_code})"}
            ), 500

        resp_data = resp.json()
        upload_url = resp_data.get("data", {}).get("upload_url")
        if not upload_url:
            app.logger.error(f"No upload_url: {resp.text}")
            return jsonify({"success": False, "error": "No upload_url"}), 500

        files = {"file": (file.filename, file.stream, file.mimetype)}
        upload_resp = requests.post(upload_url, files=files, timeout=30)
        if not upload_resp.ok:
            app.logger.error(f"Upload failed: {upload_resp.text}")
            return jsonify({"success": False, "error": "Upload failed"}), 500

        upload_json = upload_resp.json()
        file_id = upload_json.get("data", {}).get("file_id")
        if not file_id:
            app.logger.error(f"No file_id after upload: {upload_resp.text}")
            return jsonify({"success": False, "error": "No file_id"}), 500

        send_data = {"chat_id": chat_id, "file_id": file_id}
        if caption:
            send_data["text"] = caption

        send_resp = requests.post(
            f"https://botapi.rubika.ir/v3/{token}/sendFile", json=send_data, timeout=10
        )
        if send_resp.ok:
            return jsonify({"success": True})
        else:
            app.logger.error(f"sendFile failed: {send_resp.text}")
            return jsonify({"success": False, "error": "sendFile failed"}), 500

    except Exception as e:
        app.logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500
