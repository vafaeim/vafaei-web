import json
import re
from flask import request, jsonify, session, redirect, render_template
from extensions import app
from database import database
import psycopg2.extras
import psycopg2.errors
from .events import get_online_users
from . import chat_bp


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
                    "SELECT username, last_seen FROM users WHERE id = %s", (user_id,)
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
                    "SELECT id, username FROM users WHERE username ILIKE %s LIMIT 10",
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
                       (SELECT text FROM messages WHERE chat_id = c.id ORDER BY created_at DESC LIMIT 1) AS last_message,
                       (SELECT created_at FROM messages WHERE chat_id = c.id ORDER BY created_at DESC LIMIT 1) AS last_time
                FROM chats c
                JOIN users u1 ON c.user1_id = u1.id
                JOIN users u2 ON c.user2_id = u2.id
                WHERE c.user1_id = %s OR c.user2_id = %s
                ORDER BY last_time DESC NULLS LAST
            """,
                    (my_id, my_id, my_id, my_id),
                )
                chats = cur.fetchall()
                for c in chats:
                    if c.get("last_time"):
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
                        SELECT m.id, m.text, m.created_at, m.reply_to_id,
                              u.username AS sender_username,
                              m.sender_id,
                              m.seen_by,
                              rm.text AS reply_text,
                              ru.username AS reply_sender_username
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
                        SELECT m.id, m.text, m.created_at, m.reply_to_id,
                              u.username AS sender_username,
                              m.sender_id,
                              m.seen_by,
                              rm.text AS reply_text,
                              ru.username AS reply_sender_username
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
        msg_dict = {
            "id": m["id"],
            "sender_id": m["sender_id"],
            "text": m["text"],
            "created_at": m["created_at"],
            "sender_username": m["sender_username"],
            "seen_by": m["seen_by"] or [],
        }
        if m["reply_to_id"] and m["reply_text"]:
            msg_dict["reply_to"] = {
                "text": m["reply_text"],
                "sender_username": m["reply_sender_username"],
            }
        result.append(msg_dict)
    return jsonify(result)


@chat_bp.route("/api/whoami")
def whoami():
    return jsonify(
        {
            "user_id": session.get("user_id"),
            "username": session.get("username", "unknown"),
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
