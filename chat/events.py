import json
from flask import session
from extensions import socketio, database
import psycopg2.extras
from datetime import datetime
from flask_socketio import join_room
from database import update_last_seen

online_users = set()


def get_online_users():
    return online_users


def emit_status(user_id, online, last_seen=None):
    try:
        with database() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM chats WHERE user1_id = %s OR user2_id = %s",
                    (user_id, user_id),
                )
                chat_ids = [row[0] for row in cur.fetchall()]
                payload = {"user_id": user_id, "online": online}
                if not online and last_seen:
                    payload["last_seen"] = last_seen
                for chat_id in chat_ids:
                    socketio.emit(
                        "user_status_changed",
                        payload,
                        room=f"chat_{chat_id}",
                    )
    except Exception:
        pass


@socketio.on("connect")
def handle_connect():
    user_id = session.get("user_id")
    if user_id:
        update_last_seen(user_id)
        online_users.add(user_id)
        emit_status(user_id, online=True)


@socketio.on("disconnect")
def handle_disconnect():
    user_id = session.get("user_id")
    if user_id:
        update_last_seen(user_id)
        online_users.discard(user_id)
        now_utc = datetime.utcnow().isoformat() + "Z"
        emit_status(user_id, online=False, last_seen=now_utc)


@socketio.on("join_chat_room")
def handle_join_chat_room(data):
    user_id = session.get("user_id")
    if user_id:
        update_last_seen(user_id)
    chat_id = data.get("chat_id")
    if chat_id:
        join_room(f"chat_{chat_id}")


@socketio.on("send_chat_message")
def handle_chat_message(data):
    sender_id = session.get("user_id")
    if not sender_id:
        return
    chat_id = data.get("chat_id")
    text = data.get("text", "").strip()
    reply_to = data.get("reply_to_message_id")
    if not text and not reply_to:
        return
    if not chat_id:
        return

    try:
        with database() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """INSERT INTO messages (chat_id, sender_id, text, reply_to_id)
                    VALUES (%s, %s, %s, %s) RETURNING id, created_at, seen_by""",
                    (chat_id, sender_id, text, reply_to),
                )
                msg = cur.fetchone()
                msg["text"] = text or ""
                msg["chat_id"] = chat_id
                msg["created_at"] = msg["created_at"].isoformat() + "Z"
                msg["seen_by"] = msg["seen_by"] or []

                cur.execute("SELECT username FROM users WHERE id = %s", (sender_id,))
                user = cur.fetchone()
                msg["sender_username"] = user["username"]

                if reply_to:
                    cur.execute(
                        """SELECT m.text, u.username AS sender_username
                        FROM messages m JOIN users u ON m.sender_id = u.id
                        WHERE m.id = %s""",
                        (reply_to,),
                    )
                    reply_msg = cur.fetchone()
                    if reply_msg:
                        msg["reply_to"] = {
                            "text": reply_msg["text"],
                            "sender_username": reply_msg["sender_username"],
                        }

                cur.execute(
                    "SELECT user1_id, user2_id FROM chats WHERE id = %s", (chat_id,)
                )
                row = cur.fetchone()
                other = None
                if row:
                    other = (
                        row["user1_id"]
                        if row["user1_id"] != sender_id
                        else row["user2_id"]
                    )

        emit("new_message", msg, room=f"chat_{chat_id}")

        if other:
            emit(
                "new_message_notification",
                {
                    "chat_id": chat_id,
                    "sender_username": user["username"],
                    "text": (text or "📎 replied")[:30]
                    + ("..." if len(text or "") > 30 else ""),
                },
                room=f"user_{other}",
            )
    except RuntimeError:
        emit("error", {"msg": "Database temporarily unavailable"})


@socketio.on("join_chat")
def handle_join_chat(data=None):
    user_id = session.get("user_id")
    if user_id:
        update_last_seen(user_id)
        join_room(f"user_{user_id}")


@socketio.on("typing")
def handle_typing(data):
    chat_id = data.get("chat_id")
    if chat_id:
        emit(
            "user_typing",
            {"user": session.get("username")},
            room=f"chat_{chat_id}",
            include_self=False,
        )


@socketio.on("stop_typing")
def handle_stop_typing(data):
    chat_id = data.get("chat_id")
    if chat_id:
        emit("user_stop_typing", room=f"chat_{chat_id}", include_self=False)


@socketio.on("seen")
def handle_seen(data):
    chat_id = data.get("chat_id")
    user_id = session.get("user_id")
    if not chat_id or not user_id:
        return
    try:
        with database() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE messages
                    SET seen_by = seen_by || %s::jsonb
                    WHERE chat_id = %s
                      AND sender_id != %s
                      AND NOT seen_by @> %s::jsonb
                """,
                    (json.dumps([user_id]), chat_id, user_id, json.dumps([user_id])),
                )
                updated = cur.rowcount
        if updated > 0:
            emit(
                "message_seen",
                {"user_id": user_id, "chat_id": chat_id},
                room=f"chat_{chat_id}",
                include_self=False,
            )
    except RuntimeError:
        pass
