import os
from flask import Flask
from flask_socketio import SocketIO
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config.from_object("config.Config")

socketio = SocketIO(
    app,
    async_mode="eventlet",
    cors_allowed_origins=[
        "https://vafaei.runflare.run",
        "http://vafaei.runflare.run",
        "http://127.0.0.1:5000",
        "http://localhost:5000",
    ],
    max_http_buffer_size=10 * 1024 * 1024,
    ping_interval=10,
    ping_timeout=5,
)

db_pool = None


def get_db():
    global db_pool
    if db_pool is None:
        return None

    for _ in range(2):
        try:
            conn = db_pool.getconn()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            return conn
        except Exception:
            continue
    return None


def return_db(conn):
    global db_pool
    if db_pool and conn is not None:
        try:
            db_pool.putconn(conn)
        except Exception:
            pass


@contextmanager
def database():
    conn = get_db()
    if conn is None:
        raise RuntimeError("Database unavailable")
    try:
        yield conn
        conn.commit()
    except Exception as e:
        if not conn.closed:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if not conn.closed:
            return_db(conn)
        else:
            pass


def init_pool():
    global db_pool
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("WARNING: DATABASE_URL not set.")
        return
    try:
        db_pool = ThreadedConnectionPool(1, 10, db_url)
        print("INFO: Database pool created.")
    except Exception as e:
        print(f"ERROR creating pool: {e}")
        db_pool = None
