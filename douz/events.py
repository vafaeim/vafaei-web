import random
import string
from extensions import socketio
from flask import request
from flask_socketio import join_room, leave_room, emit

dous_rooms = {}


def generate_room_code():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def check_winner(board):
    wins = [
        (0, 1, 2),
        (3, 4, 5),
        (6, 7, 8),
        (0, 3, 6),
        (1, 4, 7),
        (2, 5, 8),
        (0, 4, 8),
        (2, 4, 6),
    ]
    for a, b, c in wins:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    return None


def _emit_game_over(room, board, winner_symbol):
    room_data = dous_rooms[room]
    room_data["replay_votes"].clear()
    players = room_data["players"]
    scores = room_data["scores"]
    for sid in players:
        my_wins = scores["wins"].get(sid, 0)
        opponent_sid = players[0] if players[1] == sid else players[1]
        opp_wins = scores["wins"].get(opponent_sid, 0)
        draw_count = scores["draws"]
        emit(
            "game_over",
            {
                "board": board,
                "winner": None if winner_symbol is None else winner_symbol,
                "scores": {
                    "my_wins": my_wins,
                    "opponent_wins": opp_wins,
                    "draws": draw_count,
                },
            },
            to=sid,
        )


@socketio.on("create_room")
def handle_create_room():
    room = generate_room_code()
    while room in dous_rooms:
        room = generate_room_code()
    dous_rooms[room] = {
        "board": ["", "", "", "", "", "", "", "", ""],
        "turn": "X",
        "players": [request.sid],
        "symbols": {"X": request.sid},
        "replay_votes": set(),
        "scores": {
            "wins": {request.sid: 0},
            "draws": 0,
        },
    }
    join_room(room)
    emit("room_created", {"room": room})


@socketio.on("join_room")
def handle_join_room(data):
    room = data.get("room")
    if room not in dous_rooms:
        emit("error", {"msg": "Room not found"})
        return

    room_data = dous_rooms[room]
    if len(room_data["players"]) >= 2:
        emit("error", {"msg": "Room full"})
        return

    if len(room_data["players"]) == 0:
        symbol = "X"
    else:
        symbol = "O"

    room_data["players"].append(request.sid)
    room_data["symbols"][symbol] = request.sid
    room_data["scores"]["wins"][request.sid] = 0
    room_data["replay_votes"].clear()
    join_room(room)
    emit("room_joined", {"room": room})

    if len(room_data["players"]) == 2:
        player_x = room_data["symbols"]["X"]
        player_o = room_data["symbols"]["O"]
        emit(
            "game_start",
            {
                "symbol": "X",
                "board": room_data["board"],
                "scores": {"my_wins": 0, "opponent_wins": 0, "draws": 0},
            },
            to=player_x,
        )
        emit(
            "game_start",
            {
                "symbol": "O",
                "board": room_data["board"],
                "scores": {"my_wins": 0, "opponent_wins": 0, "draws": 0},
            },
            to=player_o,
        )


@socketio.on("make_move")
def handle_make_move(data):
    room = data.get("room")
    index = int(data.get("index"))
    if room not in dous_rooms:
        return
    room_data = dous_rooms[room]
    board = room_data["board"]
    if board[index] != "":
        return
    symbol = "X" if request.sid == room_data["symbols"]["X"] else "O"
    if symbol != room_data["turn"]:
        return
    board[index] = symbol
    winner = check_winner(board)
    if winner:
        room_data["turn"] = None
        winner_sid = room_data["symbols"][winner]
        room_data["scores"]["wins"][winner_sid] += 1
        _emit_game_over(room, board, winner)
    elif "" not in board:
        room_data["turn"] = None
        room_data["scores"]["draws"] += 1
        _emit_game_over(room, board, None)
    else:
        room_data["turn"] = "O" if symbol == "X" else "X"
        emit("board_update", {"board": board, "turn": room_data["turn"]}, room=room)


@socketio.on("request_replay")
def handle_request_replay(data):
    room = data.get("room")
    if room not in dous_rooms:
        return
    room_data = dous_rooms[room]
    if "replay_votes" not in room_data:
        room_data["replay_votes"] = set()
    room_data["replay_votes"].add(request.sid)

    if len(room_data["replay_votes"]) >= 2:
        syms = room_data["symbols"]
        if syms["X"] == room_data["players"][0]:
            syms["X"] = room_data["players"][1]
            syms["O"] = room_data["players"][0]
        else:
            syms["X"] = room_data["players"][0]
            syms["O"] = room_data["players"][1]

        room_data["board"] = ["", "", "", "", "", "", "", "", ""]
        room_data["turn"] = "X"
        room_data["replay_votes"].clear()

        players = room_data["players"]
        scores = room_data["scores"]
        for symbol, sid in syms.items():
            my_wins = scores["wins"].get(sid, 0)
            opponent_sid = players[0] if players[1] == sid else players[1]
            opp_wins = scores["wins"].get(opponent_sid, 0)
            draw_count = scores["draws"]
            emit(
                "replay_accepted",
                {
                    "symbol": symbol,
                    "board": room_data["board"],
                    "scores": {
                        "my_wins": my_wins,
                        "opponent_wins": opp_wins,
                        "draws": draw_count,
                    },
                },
                to=sid,
            )
    else:
        emit(
            "replay_waiting",
            {"msg": "Waiting for opponent to accept replay..."},
            to=request.sid,
        )


@socketio.on("leave_room")
def handle_leave_room(data):
    room = data.get("room")
    if room in dous_rooms:
        emit("opponent_left", room=room, skip_sid=request.sid)
        leave_room(room)
        dous_rooms[room]["players"] = [
            p for p in dous_rooms[room]["players"] if p != request.sid
        ]
        if len(dous_rooms[room]["players"]) == 0:
            del dous_rooms[room]
        else:
            dous_rooms[room]["replay_votes"].clear()
