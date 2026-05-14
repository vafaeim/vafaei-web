from flask import render_template
from extensions import app, init_pool
from database import init_db, database
from scheduler import start_scheduler
from config import Config
from flask import (
    request,
    redirect,
    url_for,
    session,
    render_template,
    send_from_directory,
    make_response,
    jsonify,
)


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


@app.route("/manifest.json")
def serve_manifest():
    response = make_response(send_from_directory(app.static_folder, "manifest.json"))
    response.headers["Content-Type"] = "application/manifest+json"
    return response


@app.route("/admin/users", methods=["GET", "POST"])
def admin_users():
    key = request.args.get("key") or (
        request.form.get("key") if request.method == "POST" else ""
    )
    if key != Config.WHISPER_SECRET_KEY:
        return "Access denied. Add ?key=YOUR_SECRET_KEY to the URL.", 403

    if request.method == "POST" and request.form.get("action") == "delete":
        user_id = request.form.get("user_id")
        if user_id:
            with database() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
            return redirect(url_for("admin_users", key=key))
        return redirect(url_for("admin_users", key=key))

    search = request.args.get("search", "").strip()
    sort_by = request.args.get("sort", "id")
    order = request.args.get("order", "asc")

    allowed_sorts = [
        "id",
        "username",
        "created_at",
        "last_seen",
        "private_msgs",
        "group_msgs",
        "session_count",
    ]
    if sort_by not in allowed_sorts:
        sort_by = "id"
    if order not in ("asc", "desc"):
        order = "asc"

    from chat.events import get_online_users

    online = get_online_users()

    with database() as conn:
        with conn.cursor() as cur:
            where_clause = ""
            params = []
            if search:
                where_clause = " WHERE u.username ILIKE %s"
                params.append(f"%{search}%")

            cur.execute(
                f"""
                SELECT u.id, u.username, u.rubika_chat_id, u.created_at, u.last_seen,
                       u.avatar_url,
                       u.password_hash IS NOT NULL AS has_password,
                       (SELECT COUNT(*) FROM messages WHERE sender_id = u.id) AS private_msgs,
                       (SELECT COUNT(*) FROM group_messages WHERE sender_id = u.id) AS group_msgs,
                       (SELECT COUNT(*) FROM sessions WHERE user_id = u.id) AS session_count
                FROM users u
                {where_clause}
                ORDER BY {sort_by} {order}
            """,
                params,
            )
            rows = cur.fetchall()

    users = []
    for row in rows:
        uid = row[0]
        users.append(
            {
                "id": uid,
                "username": row[1],
                "rubika_chat_id": row[2],
                "created_at": row[3],
                "last_seen": row[4],
                "avatar_url": row[5],
                "has_password": row[6],
                "private_msgs": row[7],
                "group_msgs": row[8],
                "session_count": row[9],
                "is_online": uid in online,
            }
        )

    return render_template(
        "admin_users.html",
        users=users,
        count=len(users),
        search=search,
        sort_by=sort_by,
        order=order,
        key=key,
    )
    key = request.args.get("key", "")
    if key != Config.WHISPER_SECRET_KEY:
        return "Access denied. Add ?key=YOUR_SECRET_KEY to the URL.", 403

    from chat.events import get_online_users

    online = get_online_users()

    with database() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT u.id, u.username, u.rubika_chat_id, u.created_at, u.last_seen,
                       u.avatar_url,
                       u.password_hash IS NOT NULL AS has_password,
                       (SELECT COUNT(*) FROM messages WHERE sender_id = u.id) AS private_msgs,
                       (SELECT COUNT(*) FROM group_messages WHERE sender_id = u.id) AS group_msgs,
                       (SELECT COUNT(*) FROM sessions WHERE user_id = u.id) AS session_count
                FROM users u
                ORDER BY u.id
            """)
            rows = cur.fetchall()

    users = []
    for row in rows:
        uid = row[0]
        users.append(
            {
                "id": uid,
                "username": row[1],
                "rubika_chat_id": row[2],
                "created_at": row[3],
                "last_seen": row[4],
                "avatar_url": row[5],
                "has_password": row[6],
                "private_msgs": row[7],
                "group_msgs": row[8],
                "session_count": row[9],
                "is_online": uid in online,
            }
        )

    return render_template("admin_users.html", users=users, count=len(users))


with app.app_context():
    init_pool()
    init_db()
    start_scheduler()
