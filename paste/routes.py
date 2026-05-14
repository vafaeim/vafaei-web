import secrets
from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, Response
from extensions import database
from config import Config
from . import paste_bp


EXPIRATION_OPTIONS = {
    "0": 0,
    "600": 600,
    "3600": 3600,
    "21600": 21600,
    "86400": 86400,
    "172800": 172800,
    "259200": 259200,
}


def format_timedelta(td):
    """تبدیل timedelta به رشته‌ی فارسی یا انگلیسی با روز/ساعت/دقیقه"""
    total_seconds = int(td.total_seconds())
    if total_seconds <= 0:
        return "expired"
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days > 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours > 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes > 1 else ''}")
    if not parts:
        parts.append("less than a minute")
    return ", ".join(parts)


@paste_bp.route("/paste", methods=["GET", "POST"])
def paste_create():
    if request.method == "POST":
        content = request.form.get("content", "").strip()
        if not content:
            return redirect(url_for("paste.paste_create"))

        # دریافت زمان انقضا از فرم (پیش‌فرض: ۰ = هرگز)
        expires_choice = request.form.get("expires", "0")
        expires_seconds = EXPIRATION_OPTIONS.get(expires_choice, 0)

        slug = secrets.token_hex(4)
        with database() as conn:
            with conn.cursor() as cur:
                while True:
                    cur.execute("SELECT 1 FROM pastebins WHERE slug = %s", (slug,))
                    if cur.fetchone() is None:
                        break
                    slug = secrets.token_hex(4)

                expires_at = None
                if expires_seconds > 0:
                    expires_at = datetime.utcnow() + timedelta(seconds=expires_seconds)

                cur.execute(
                    "INSERT INTO pastebins (content, slug, expires_at) VALUES (%s, %s, %s)",
                    (content, slug, expires_at),
                )
        return redirect(url_for("paste.paste_view", slug=slug))

    return render_template("paste_create.html")


@paste_bp.route("/paste/<slug>")
def paste_view(slug):
    with database() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT content, expires_at FROM pastebins WHERE slug = %s", (slug,)
            )
            row = cur.fetchone()
            if not row:
                return "Paste not found", 404
            content, expires_at = row

            if expires_at:
                now = datetime.utcnow()
                if now > expires_at:
                    cur.execute("DELETE FROM pastebins WHERE slug = %s", (slug,))
                    return "Paste expired and has been deleted", 410
                time_left = format_timedelta(expires_at - now)
            else:
                time_left = None

    paste_url = url_for("paste.paste_view", slug=slug, _external=True)
    raw_url = url_for("paste.paste_raw", slug=slug, _external=True)

    return render_template(
        "paste_view.html",
        content=content,
        slug=slug,
        paste_url=paste_url,
        raw_url=raw_url,
        expires_at=expires_at,
        time_left=time_left,
    )
    with database() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT content, expires_at FROM pastebins WHERE slug = %s", (slug,)
            )
            row = cur.fetchone()
            if not row:
                return "Paste not found", 404

            content = row[0]
            expires_at = row[1]

            # بررسی انقضا
            if expires_at and datetime.utcnow() > expires_at:
                # حذف paste منقضی شده
                cur.execute("DELETE FROM pastebins WHERE slug = %s", (slug,))
                return "Paste expired and has been deleted", 410

    paste_url = url_for("paste.paste_view", slug=slug, _external=True)
    raw_url = url_for("paste.paste_raw", slug=slug, _external=True)

    return render_template(
        "paste_view.html",
        content=content,
        slug=slug,
        paste_url=paste_url,
        raw_url=raw_url,
        expires_at=expires_at,
        now=datetime.utcnow(),
    )


@paste_bp.route("/paste/<slug>/raw")
def paste_raw(slug):
    with database() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT content, expires_at FROM pastebins WHERE slug = %s", (slug,)
            )
            row = cur.fetchone()
            if not row:
                return "Paste not found", 404
            if row[1] and datetime.utcnow() > row[1]:
                cur.execute("DELETE FROM pastebins WHERE slug = %s", (slug,))
                return "Paste expired", 410
            content = row[0]
    return Response(content, mimetype="text/plain")


@paste_bp.route("/paste/admin", methods=["GET", "POST"])
def paste_admin():
    # بررسی کلید امنیتی
    key = request.args.get("key") or (
        request.form.get("key") if request.method == "POST" else ""
    )
    if key != Config.WHISPER_SECRET_KEY:
        return "Access denied. Add ?key=YOUR_SECRET_KEY to the URL.", 403

    # درخواست حذف
    if request.method == "POST":
        action = request.form.get("action")
        slug = request.form.get("slug")
        if action == "delete" and slug:
            with database() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM pastebins WHERE slug = %s", (slug,))
            return redirect(url_for("paste.paste_admin", key=key))  # بازگشت به لیست

    # دریافت همه pasteها (حتی منقضی‌ها)
    with database() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT slug, content, created_at, expires_at FROM pastebins ORDER BY created_at DESC"
            )
            rows = cur.fetchall()

    now = datetime.utcnow()
    pastes = []
    for row in rows:
        slug, _, created_at, expires_at = row
        expired = expires_at is not None and expires_at < now
        pastes.append(
            {
                "slug": slug,
                "created_at": created_at,
                "expires_at": expires_at,
                "expired": expired,
            }
        )

    return render_template("paste_admin.html", pastes=pastes, key=key)
