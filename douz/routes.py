from flask import session, render_template, jsonify
from extensions import app
from . import douz_bp
from .events import dous_rooms, generate_room_code


@douz_bp.route("/douz/")
def douz_page():
    return render_template("douz.html")


@douz_bp.route("/api/create_douz_room", methods=["POST"])
def create_douz_room_api():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    room = generate_room_code()
    while room in dous_rooms:
        room = generate_room_code()

    dous_rooms[room] = {
        "board": ["", "", "", "", "", "", "", "", ""],
        "turn": "X",
        "players": [],
        "symbols": {},
        "replay_votes": set(),
        "scores": {
            "wins": {},
            "draws": 0,
        },
    }
    return jsonify({"room": room})
