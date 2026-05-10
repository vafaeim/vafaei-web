import json
import re
from flask import request, jsonify, session, render_template, redirect, url_for
import os, imghdr, secrets
from werkzeug.utils import secure_filename
from PIL import Image
from extensions import app, socketio
from database import database
import psycopg2.extras
import psycopg2.errors
import urllib.parse
from .events import get_online_users
from . import chat_bp
import json as _json

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_VOICE_TYPES = {
    "audio/webm",
    "audio/ogg",
    "audio/mpeg",
    "audio/wav",
    "audio/mp4",
}
ALLOWED_AVATAR_TYPES = {"png", "jpg", "jpeg", "gif"}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_BASE = os.environ.get(
    "UPLOAD_BASE_PATH", os.path.join(BASE_DIR, "..", "uploads")
)

IMAGE_FOLDER = os.path.join(UPLOAD_BASE, "images")
VOICE_FOLDER = os.path.join(UPLOAD_BASE, "voice")
AVATAR_FOLDER = os.path.join(UPLOAD_BASE, "avatars")

for folder in (IMAGE_FOLDER, VOICE_FOLDER, AVATAR_FOLDER):
    if not os.path.exists(folder):
        os.makedirs(folder)


@chat_bp.route("/chat")
def chat_page():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    return render_template("chat.html")


@chat_bp.route("/api/user_status/<int:user_id>")
def user_status(user_id):
    try:
        with database() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT username, last_seen, avatar_url FROM users WHERE id = %s",
                    (user_id,),
                )
                user = cur.fetchone()
                if not user:
                    return jsonify({"error": "User not found"}), 404

                is_online = user_id in get_online_users()
                return jsonify(
                    {
                        "username": user["username"],
                        "is_online": is_online,
                        "last_seen": user["last_seen"].isoformat() + "Z"
                        if user["last_seen"]
                        else None,
                        "avatar_url": user["avatar_url"],
                    }
                )
    except RuntimeError:
        return jsonify({"error": "Database unavailable"}), 503


@chat_bp.route("/api/search_users")
def search_users():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])
    try:
        with database() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, username, avatar_url FROM users WHERE username ILIKE %s LIMIT 10",
                    (query,),
                )
                users = cur.fetchall()
    except RuntimeError:
        return jsonify({"error": "Database service unavailable"}), 503

    return jsonify(users)


@chat_bp.route("/api/start_chat", methods=["POST"])
def start_chat():
    data = request.get_json()
    other_user_id = data.get("user_id")
    if not other_user_id:
        return jsonify({"error": "user_id required"}), 400
    my_id = session.get("user_id")
    if not my_id:
        return jsonify({"error": "Not logged in"}), 401
    try:
        with database() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                SELECT id FROM chats
                WHERE (user1_id = %s AND user2_id = %s) OR (user1_id = %s AND user2_id = %s)
            """,
                    (my_id, other_user_id, other_user_id, my_id),
                )
                chat = cur.fetchone()
                if not chat:
                    cur.execute(
                        "INSERT INTO chats (user1_id, user2_id) VALUES (%s, %s) RETURNING id",
                        (my_id, other_user_id),
                    )
                    chat = cur.fetchone()
    except RuntimeError:
        return jsonify({"error": "Database service unavailable"}), 503

    return jsonify({"chat_id": chat["id"]})


@chat_bp.route("/api/chats")
def get_chats():
    my_id = session.get("user_id")
    if not my_id:
        return jsonify([])
    try:
        with database() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT c.id,
                        CASE WHEN c.user1_id = %s THEN u2.id ELSE u1.id END AS other_user_id,
                        CASE WHEN c.user1_id = %s THEN u2.username ELSE u1.username END AS other_username,
                        CASE WHEN c.user1_id = %s THEN u2.avatar_url ELSE u1.avatar_url END AS other_avatar_url,
                        (SELECT text FROM messages WHERE chat_id = c.id AND deleted = FALSE ORDER BY created_at DESC LIMIT 1) AS last_message,
                        (SELECT created_at FROM messages WHERE chat_id = c.id AND deleted = FALSE ORDER BY created_at DESC LIMIT 1) AS last_time,
                        (SELECT COUNT(*) FROM messages m WHERE m.chat_id = c.id
                            AND m.sender_id != %s
                            AND NOT (m.seen_by @> to_jsonb(%s::int))
                        ) AS unread_count
                    FROM chats c
                    JOIN users u1 ON c.user1_id = u1.id
                    JOIN users u2 ON c.user2_id = u2.id
                    WHERE c.user1_id = %s OR c.user2_id = %s
                    ORDER BY last_time DESC NULLS LAST
                """,
                    (my_id, my_id, my_id, my_id, my_id, my_id, my_id),
                )
                chats = cur.fetchall()
                for c in chats:
                    if c.get("last_time"):
                        c["other_avatar_url"] = c.get("other_avatar_url")
                        c["unread_count"] = c.get("unread_count", 0) or 0
                        c["last_time"] = (
                            c["last_time"].isoformat() + "Z"
                            if c.get("last_time")
                            else None
                        )
    except RuntimeError:
        return jsonify({"error": "Database service unavailable"}), 503

    return jsonify(chats)


@chat_bp.route("/api/messages/<int:chat_id>")
def get_messages(chat_id):
    my_id = session.get("user_id")
    if not my_id:
        return jsonify([])

    before_id = request.args.get("before_id", type=int)
    limit = min(request.args.get("limit", 50, type=int), 100)

    try:
        with database() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT user1_id, user2_id FROM chats WHERE id = %s", (chat_id,)
                )
                row = cur.fetchone()
                if not row or (row[0] != my_id and row[1] != my_id):
                    return jsonify([])

            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if before_id:
                    cur.execute(
                        """
                        SELECT m.id, m.text, m.created_at, m.reply_to_id, m.edited, m.deleted,
                              u.username AS sender_username,
                              u.avatar_url AS sender_avatar_url,
                              m.sender_id,
                              m.seen_by,
                              m.attachment,
                              m.reactions,
                              rm.text AS reply_text,
                              ru.username AS reply_sender_username,
                              rm.sender_id AS reply_sender_id
                        FROM messages m
                        JOIN users u ON m.sender_id = u.id
                        LEFT JOIN messages rm ON m.reply_to_id = rm.id
                        LEFT JOIN users ru ON rm.sender_id = ru.id
                        WHERE m.chat_id = %s AND m.id < %s
                        ORDER BY m.id DESC
                        LIMIT %s
                    """,
                        (chat_id, before_id, limit),
                    )
                else:
                    cur.execute(
                        """
                        SELECT m.id, m.text, m.created_at, m.reply_to_id, m.edited, m.deleted,
                              u.username AS sender_username,
                              u.avatar_url AS sender_avatar_url,
                              m.sender_id,
                              m.seen_by,
                              m.attachment,
                              m.reactions,
                              rm.text AS reply_text,
                              ru.username AS reply_sender_username,
                              rm.sender_id AS reply_sender_id
                        FROM messages m
                        JOIN users u ON m.sender_id = u.id
                        LEFT JOIN messages rm ON m.reply_to_id = rm.id
                        LEFT JOIN users ru ON rm.sender_id = ru.id
                        WHERE m.chat_id = %s
                        ORDER BY m.id DESC
                        LIMIT %s
                    """,
                        (chat_id, limit),
                    )
                messages = cur.fetchall()
                messages.reverse()
    except RuntimeError:
        return jsonify({"error": "Database service unavailable"}), 503

    result = []
    for m in messages:
        m["created_at"] = m["created_at"].isoformat() + "Z"
        att = m.get("attachment")
        if att is None:
            attachment_data = None
        elif isinstance(att, dict):
            attachment_data = att
        else:
            attachment_data = _json.loads(att)
        msg_dict = {
            "id": m["id"],
            "sender_id": m["sender_id"],
            "text": m["text"],
            "edited": m["edited"],
            "deleted": m["deleted"],
            "created_at": m["created_at"],
            "sender_username": m["sender_username"],
            "sender_avatar_url": m["sender_avatar_url"],
            "seen_by": m["seen_by"] or [],
            "attachment": attachment_data,
            "reactions": m["reactions"] or {},
        }
        if m["reply_to_id"] and m["reply_text"]:
            msg_dict["reply_to"] = {
                "id": m["reply_to_id"],
                "text": m["reply_text"],
                "sender_username": m["reply_sender_username"],
                "sender_id": m["reply_sender_id"],
            }
        result.append(msg_dict)
    return jsonify(result)


@chat_bp.route("/api/whoami")
def whoami():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"user_id": None, "username": None, "avatar_url": None})

    try:
        with database() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT avatar_url FROM users WHERE id = %s", (user_id,))
                user = cur.fetchone()
                avatar = user["avatar_url"] if user else None
    except RuntimeError:
        avatar = None

    return jsonify(
        {
            "user_id": user_id,
            "username": session.get("username", "unknown"),
            "avatar_url": avatar,
        }
    )


@chat_bp.route("/api/change_username", methods=["POST"])
def change_username():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json()
    new_username = data.get("username", "").strip()
    if not new_username:
        return jsonify({"error": "Username required"}), 400

    if not re.match(r"^[a-zA-Z0-9_]{3,20}$", new_username):
        return jsonify(
            {
                "error": "Username must be 3-20 characters, letters, numbers or underscore."
            }
        ), 400

    try:
        with database() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET username = %s WHERE id = %s",
                    (new_username, session["user_id"]),
                )
            session["username"] = new_username
            return jsonify({"success": True})
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "Username already taken"}), 409
    except RuntimeError:
        return jsonify({"error": "Database service unavailable"}), 503


@chat_bp.route("/api/messages/<int:message_id>", methods=["PUT"])
def edit_message(message_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json()
    new_text = data.get("text", "").strip()
    if not new_text:
        return jsonify({"error": "Text cannot be empty"}), 400

    try:
        with database() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM messages WHERE id = %s", (message_id,))
                msg = cur.fetchone()
                if not msg:
                    return jsonify({"error": "Message not found"}), 404
                if msg["sender_id"] != user_id:
                    return jsonify({"error": "Not authorized"}), 403
                if msg["deleted"]:
                    return jsonify({"error": "Cannot edit deleted message"}), 400

                cur.execute(
                    """
                    UPDATE messages
                    SET text = %s, edited = TRUE
                    WHERE id = %s
                """,
                    (new_text, message_id),
                )

        socketio.emit(
            "message_edited",
            {"message_id": message_id, "text": new_text, "chat_id": msg["chat_id"]},
            room=f"chat_{msg['chat_id']}",
        )

        return jsonify({"success": True})
    except RuntimeError:
        return jsonify({"error": "Database unavailable"}), 503


@chat_bp.route("/api/messages/<int:message_id>", methods=["DELETE"])
def delete_message(message_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    try:
        with database() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM messages WHERE id = %s", (message_id,))
                msg = cur.fetchone()
                if not msg:
                    return jsonify({"error": "Message not found"}), 404
                if msg["sender_id"] != user_id:
                    return jsonify({"error": "Not authorized"}), 403

                cur.execute(
                    """
                    UPDATE messages
                    SET deleted = TRUE, text = ''
                    WHERE id = %s
                """,
                    (message_id,),
                )

        socketio.emit(
            "message_deleted",
            {"message_id": message_id, "chat_id": msg["chat_id"]},
            room=f"chat_{msg['chat_id']}",
        )

        return jsonify({"success": True})
    except RuntimeError:
        return jsonify({"error": "Database unavailable"}), 503


@chat_bp.route("/api/sessions")
def get_sessions():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    try:
        with database() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT token, ip, user_agent, created_at,
                           (token = %s) AS is_current
                    FROM sessions
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                """,
                    (session.get("session_token"), user_id),
                )
                sessions_list = cur.fetchall()
        for s in sessions_list:
            s["created_at"] = s["created_at"].isoformat()
            s["is_current"] = bool(s["is_current"])
        return jsonify(sessions_list)
    except RuntimeError:
        return jsonify({"error": "Database unavailable"}), 503


@chat_bp.route("/api/sessions/<token>", methods=["DELETE"])
def terminate_session(token):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    try:
        with database() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM sessions WHERE token = %s AND user_id = %s",
                    (token, user_id),
                )
                if cur.rowcount == 0:
                    return jsonify(
                        {"error": "Session not found or not authorized"}
                    ), 404
        return jsonify({"success": True})
    except RuntimeError:
        return jsonify({"error": "Database unavailable"}), 503


@chat_bp.route("/api/create_group", methods=["POST"])
def create_group():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json()
    name = data.get("name", "").strip()
    member_ids = data.get("members", [])

    if not name:
        return jsonify({"error": "Group name required"}), 400

    try:
        with database() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "INSERT INTO groups_chat (name, creator_id) VALUES (%s, %s) RETURNING id",
                    (name, user_id),
                )
                group = cur.fetchone()
                group_id = group["id"]

                cur.execute(
                    "INSERT INTO group_members (group_id, user_id, is_admin) VALUES (%s, %s, TRUE)",
                    (group_id, user_id),
                )

                for member_id in member_ids:
                    if member_id != user_id:
                        cur.execute(
                            "INSERT INTO group_members (group_id, user_id) VALUES (%s, %s)",
                            (group_id, member_id),
                        )

        socketio.emit(
            "new_group", {"group_id": group_id, "name": name}, room=f"user_{user_id}"
        )
        for mid in member_ids:
            socketio.emit(
                "new_group", {"group_id": group_id, "name": name}, room=f"user_{mid}"
            )

        return jsonify({"success": True, "group_id": group_id})
    except RuntimeError:
        return jsonify({"error": "Database unavailable"}), 503


@chat_bp.route("/api/groups")
def get_groups():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify([])

    try:
        with database() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT g.id, g.name, g.avatar_url,
                           (SELECT text FROM group_messages gm WHERE gm.group_id = g.id AND deleted = FALSE ORDER BY created_at DESC LIMIT 1) AS last_message,
                           (SELECT created_at FROM group_messages gm WHERE gm.group_id = g.id AND deleted = FALSE ORDER BY created_at DESC LIMIT 1) AS last_time,
                           (SELECT COUNT(*) FROM group_messages gm WHERE gm.group_id = g.id AND gm.sender_id != %s AND NOT (gm.seen_by @> to_jsonb(%s::int))) AS unread_count
                    FROM groups_chat g
                    JOIN group_members gm ON g.id = gm.group_id
                    WHERE gm.user_id = %s
                    ORDER BY last_time DESC NULLS LAST
                """,
                    (user_id, user_id, user_id),
                )
                groups = cur.fetchall()
                for g in groups:
                    if g.get("last_time"):
                        g["last_time"] = g["last_time"].isoformat() + "Z"
        return jsonify(groups)
    except RuntimeError:
        return jsonify({"error": "Database unavailable"}), 503


@chat_bp.route("/api/group_messages/<int:group_id>")
def get_group_messages(group_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify([])

    before_id = request.args.get("before_id", type=int)
    limit = min(request.args.get("limit", 50, type=int), 100)

    try:
        with database() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM group_members WHERE group_id = %s AND user_id = %s",
                    (group_id, user_id),
                )
                if not cur.fetchone():
                    return jsonify([])

            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if before_id:
                    cur.execute(
                        """
                        SELECT gm.id, gm.text, gm.created_at, gm.reply_to_id,
                               u.username AS sender_username,
                               u.avatar_url AS sender_avatar_url,
                               gm.sender_id, gm.seen_by, gm.attachment, gm.edited, gm.deleted,
                               rm.text AS reply_text,
                               ru.username AS reply_sender_username,
                               rm.sender_id AS reply_sender_id
                        FROM group_messages gm
                        JOIN users u ON gm.sender_id = u.id
                        LEFT JOIN group_messages rm ON gm.reply_to_id = rm.id
                        LEFT JOIN users ru ON rm.sender_id = ru.id
                        WHERE gm.group_id = %s AND gm.id < %s
                        ORDER BY gm.id DESC LIMIT %s
                    """,
                        (group_id, before_id, limit),
                    )
                else:
                    cur.execute(
                        """
                        SELECT gm.id, gm.text, gm.created_at, gm.reply_to_id,
                               u.username AS sender_username,
                               u.avatar_url AS sender_avatar_url,
                               gm.sender_id, gm.seen_by, gm.attachment, gm.edited, gm.deleted,
                               rm.text AS reply_text,
                               ru.username AS reply_sender_username,
                               rm.sender_id AS reply_sender_id
                        FROM group_messages gm
                        JOIN users u ON gm.sender_id = u.id
                        LEFT JOIN group_messages rm ON gm.reply_to_id = rm.id
                        LEFT JOIN users ru ON rm.sender_id = ru.id
                        WHERE gm.group_id = %s
                        ORDER BY gm.id DESC LIMIT %s
                    """,
                        (group_id, limit),
                    )
                messages = cur.fetchall()
                messages.reverse()

        result = []
        for m in messages:
            m["created_at"] = m["created_at"].isoformat() + "Z"
            att = m.get("attachment")
            if att is None:
                attachment_data = None
            elif isinstance(att, dict):
                attachment_data = att
            else:
                attachment_data = _json.loads(att)
            msg_dict = {
                "id": m["id"],
                "sender_id": m["sender_id"],
                "text": m["text"],
                "created_at": m["created_at"],
                "sender_username": m["sender_username"],
                "sender_avatar_url": m["sender_avatar_url"],
                "seen_by": m["seen_by"] or [],
                "edited": m["edited"],
                "deleted": m["deleted"],
                "attachment": attachment_data,
            }
            if m["reply_to_id"] and m["reply_text"]:
                msg_dict["reply_to"] = {
                    "id": m["reply_to_id"],
                    "text": m["reply_text"],
                    "sender_username": m["reply_sender_username"],
                    "sender_id": m["reply_sender_id"],
                }
            result.append(msg_dict)
        return jsonify(result)
    except RuntimeError:
        return jsonify({"error": "Database unavailable"}), 503


@chat_bp.route("/api/group_info/<int:group_id>")
def group_info(group_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    try:
        with database() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT g.id, g.name, g.avatar_url, g.creator_id,
                           (SELECT COUNT(*) FROM group_members WHERE group_id = g.id) AS member_count
                    FROM groups_chat g
                    JOIN group_members gm ON g.id = gm.group_id
                    WHERE g.id = %s AND gm.user_id = %s
                """,
                    (group_id, user_id),
                )
                group = cur.fetchone()
                if not group:
                    return jsonify({"error": "Group not found"}), 404

                cur.execute(
                    """
                    SELECT u.id, u.username, u.avatar_url
                    FROM users u
                    JOIN group_members gm ON u.id = gm.user_id
                    WHERE gm.group_id = %s
                """,
                    (group_id,),
                )
                members = cur.fetchall()
                group["members"] = members
        return jsonify(group)
    except RuntimeError:
        return jsonify({"error": "Database unavailable"}), 503


@chat_bp.route("/api/rename_group/<int:group_id>", methods=["PUT"])
def rename_group(group_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json()
    new_name = data.get("name", "").strip()
    if not new_name:
        return jsonify({"error": "New name required"}), 400

    try:
        with database() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT is_admin FROM group_members WHERE group_id = %s AND user_id = %s",
                    (group_id, user_id),
                )
                member = cur.fetchone()
                if not member or not member["is_admin"]:
                    cur.execute(
                        "SELECT creator_id FROM groups_chat WHERE id = %s", (group_id,)
                    )
                    group = cur.fetchone()
                    if not group or group["creator_id"] != user_id:
                        return jsonify({"error": "Not authorized"}), 403

                cur.execute(
                    "UPDATE groups_chat SET name = %s WHERE id = %s",
                    (new_name, group_id),
                )
        socketio.emit(
            "group_renamed",
            {"group_id": group_id, "name": new_name},
            room=f"group_{group_id}",
        )
        return jsonify({"success": True})
    except RuntimeError:
        return jsonify({"error": "Database unavailable"}), 503


@chat_bp.route("/api/group_invite/<int:group_id>", methods=["GET"])
def get_group_invite(group_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    try:
        with database() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT 1 FROM group_members WHERE group_id = %s AND user_id = %s",
                    (group_id, user_id),
                )
                if not cur.fetchone():
                    return jsonify({"error": "Not a member"}), 403

                cur.execute(
                    "SELECT invite_code FROM groups_chat WHERE id = %s", (group_id,)
                )
                group = cur.fetchone()
                code = group["invite_code"]
                if not code:
                    import secrets, string

                    code = "".join(
                        secrets.choice(string.ascii_letters + string.digits)
                        for _ in range(10)
                    )
                    cur.execute(
                        "UPDATE groups_chat SET invite_code = %s WHERE id = %s",
                        (code, group_id),
                    )

                return jsonify(
                    {
                        "invite_code": code,
                        "link": f"{request.host_url}join?code={urllib.parse.quote(code)}",
                    }
                )
    except RuntimeError:
        return jsonify({"error": "Database unavailable"}), 503


@chat_bp.route("/api/join_group_by_code", methods=["POST"])
def join_group_by_code():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    code = request.json.get("code", "").strip()
    if not code:
        return jsonify({"error": "Code required"}), 400

    try:
        with database() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT id FROM groups_chat WHERE invite_code = %s", (code,)
                )
                group = cur.fetchone()
                if not group:
                    return jsonify({"error": "Invalid invite code"}), 404

                group_id = group["id"]
                cur.execute(
                    "SELECT 1 FROM group_members WHERE group_id = %s AND user_id = %s",
                    (group_id, user_id),
                )
                if cur.fetchone():
                    return jsonify({"error": "Already a member"}), 400

                cur.execute(
                    "INSERT INTO group_members (group_id, user_id) VALUES (%s, %s)",
                    (group_id, user_id),
                )
        socketio.emit(
            "new_group", {"group_id": group_id, "name": ""}, room=f"user_{user_id}"
        )
        return jsonify({"success": True, "group_id": group_id})
    except RuntimeError:
        return jsonify({"error": "Database unavailable"}), 503


import base64
from io import BytesIO


@chat_bp.route("/api/avatar", methods=["POST"])
def upload_avatar():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    file = request.files.get("avatar")
    if not file:
        return jsonify({"error": "No file"}), 400

    try:
        img = Image.open(file.stream)
        img = img.convert("RGB")
        img.thumbnail((128, 128))

        filename = secrets.token_hex(8) + ".jpg"
        filepath = os.path.join(AVATAR_FOLDER, filename)
        img.save(filepath, format="JPEG", quality=80)

        avatar_url = f"/media/avatars/{filename}"

        old_avatar = None
        with database() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT avatar_url FROM users WHERE id = %s", (user_id,))
                row = cur.fetchone()
                if row:
                    old_avatar = row[0]

        if old_avatar and old_avatar.startswith("/media/avatars/"):
            old_filename = os.path.basename(old_avatar)
            old_path = os.path.join(AVATAR_FOLDER, old_filename)
            if os.path.exists(old_path):
                os.remove(old_path)

        with database() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET avatar_url = %s WHERE id = %s",
                    (avatar_url, user_id),
                )

        return jsonify({"success": True, "avatar_url": avatar_url})

    except Exception as e:
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500


@chat_bp.route("/api/avatar/remove", methods=["POST"])
def remove_avatar():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    try:
        old_avatar = None
        with database() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT avatar_url FROM users WHERE id = %s", (user_id,))
                row = cur.fetchone()
                if row:
                    old_avatar = row[0]

        if old_avatar and old_avatar.startswith("/media/avatars/"):
            old_filename = os.path.basename(old_avatar)
            old_path = os.path.join(AVATAR_FOLDER, old_filename)
            if os.path.exists(old_path):
                os.remove(old_path)

        with database() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET avatar_url = NULL WHERE id = %s", (user_id,)
                )

        return jsonify({"success": True})
    except RuntimeError:
        return jsonify({"error": "Database unavailable"}), 503


@chat_bp.route("/api/upload", methods=["POST"])
def upload_file():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file provided"}), 400

    mime = file.mimetype.lower() if file.mimetype else ""
    if not mime:
        return jsonify({"error": "Cannot determine file type"}), 400

    if mime in ALLOWED_IMAGE_TYPES:
        file_type = "image"
        folder = IMAGE_FOLDER
        ext = "jpg"
    elif mime in ALLOWED_VOICE_TYPES:
        file_type = "voice"
        folder = VOICE_FOLDER
        if "mp4" in mime or "aac" in mime:
            ext = "m4a"
        elif "ogg" in mime:
            ext = "ogg"
        else:
            ext = "webm"
    else:
        return jsonify({"error": f"Unsupported file type: {mime}"}), 400

    ext = "jpg" if file_type == "image" else "ogg"
    filename = secrets.token_hex(12) + "." + ext
    filepath = os.path.join(folder, filename)
    folder_name = "images" if file_type == "image" else "voice"

    attachment = {"type": file_type, "url": f"/media/uploads/{folder_name}/{filename}"}

    try:
        if file_type == "image":
            img = Image.open(file.stream)
            img = img.convert("RGB")
            img.thumbnail((1200, 1200))
            img.save(filepath, format="JPEG", quality=85)
            attachment["width"] = img.width
            attachment["height"] = img.height
        else:
            file.save(filepath)
    except Exception as e:
        return jsonify({"error": f"Upload processing failed: {str(e)}"}), 500

    return jsonify({"success": True, "attachment": attachment})


from flask import send_from_directory


@chat_bp.route("/media/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_BASE, filename)


@chat_bp.route("/api/messages/<int:message_id>/reaction", methods=["POST"])
def toggle_reaction(message_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json()
    emoji = data.get("reaction", "").strip()
    if not emoji:
        return jsonify({"error": "Reaction emoji required"}), 400

    try:
        with database() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, chat_id, reactions FROM messages WHERE id = %s",
                    (message_id,),
                )
                msg = cur.fetchone()
                if not msg:
                    return jsonify({"error": "Message not found"}), 404

                reactions = msg["reactions"] or {}
                if emoji in reactions:
                    user_list = reactions[emoji]
                    if user_id in user_list:
                        user_list.remove(user_id)
                    else:
                        user_list.append(user_id)
                    if not user_list:
                        del reactions[emoji]
                    else:
                        reactions[emoji] = user_list
                else:
                    reactions[emoji] = [user_id]

                cur.execute(
                    "UPDATE messages SET reactions = %s WHERE id = %s",
                    (json.dumps(reactions), message_id),
                )

                socketio.emit(
                    "message_reaction",
                    {
                        "message_id": message_id,
                        "reactions": reactions,
                        "chat_id": msg["chat_id"],
                    },
                    room=f"chat_{msg['chat_id']}",
                )

        return jsonify({"success": True, "reactions": reactions})
    except RuntimeError:
        return jsonify({"error": "Database unavailable"}), 503
