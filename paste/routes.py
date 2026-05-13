import secrets
from flask import render_template, request, redirect, url_for, session, Response
from extensions import database
from . import paste_bp


@paste_bp.route("/paste", methods=["GET", "POST"])
def paste_create():
    if request.method == "POST":
        content = request.form.get("content", "").strip()
        if not content:
            return redirect(url_for("paste.paste_create"))

        slug = secrets.token_hex(4)
        with database() as conn:
            with conn.cursor() as cur:
                while True:
                    cur.execute("SELECT 1 FROM pastebins WHERE slug = %s", (slug,))
                    if cur.fetchone() is None:
                        break
                    slug = secrets.token_hex(4)
                cur.execute(
                    "INSERT INTO pastebins (content, slug) VALUES (%s, %s)",
                    (content, slug),
                )
        return redirect(url_for("paste.paste_view", slug=slug))

    return render_template("paste_create.html")


@paste_bp.route("/paste/<slug>")
def paste_view(slug):
    with database() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT content FROM pastebins WHERE slug = %s", (slug,))
            row = cur.fetchone()
            if not row:
                return "Paste not found", 404
            content = row[0]
    return render_template("paste_view.html", content=content, slug=slug)


@paste_bp.route("/paste/<slug>/raw")
def paste_raw(slug):
    with database() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT content FROM pastebins WHERE slug = %s", (slug,))
            row = cur.fetchone()
            if not row:
                return "Paste not found", 404
            content = row[0]
    return Response(content, mimetype="text/plain")
