import os
import psycopg2
from extensions import database


def init_db():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("WARNING: Database not available, skipping initialization.")
        return

    target_db = db_url.rsplit("/", 1)[-1]
    if target_db != "postgres":
        try:
            default_url = db_url.rsplit("/", 1)[0] + "/postgres"
            conn_default = psycopg2.connect(default_url)
            conn_default.autocommit = True
            with conn_default.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s", (target_db,)
                )
                if not cur.fetchone():
                    cur.execute(f"CREATE DATABASE {target_db}")
            conn_default.close()
        except Exception as e:
            print(f"WARNING: Could not ensure database exists: {e}")

    try:
        with database() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(50) UNIQUE NOT NULL,
                        rubika_chat_id VARCHAR UNIQUE,
                        created_at TIMESTAMP DEFAULT NOW()
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS chats (
                        id SERIAL PRIMARY KEY,
                        user1_id INT REFERENCES users(id),
                        user2_id INT REFERENCES users(id),
                        created_at TIMESTAMP DEFAULT NOW()
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id SERIAL PRIMARY KEY,
                        chat_id INT REFERENCES chats(id),
                        sender_id INT REFERENCES users(id),
                        text TEXT NOT NULL,
                        reply_to_id INT REFERENCES messages(id),
                        created_at TIMESTAMP DEFAULT NOW()
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS otps (
                        id SERIAL PRIMARY KEY,
                        code VARCHAR(10) NOT NULL,
                        session_token VARCHAR(64) UNIQUE NOT NULL,
                        rubika_chat_id VARCHAR,
                        created_at_unix BIGINT NOT NULL,
                        expires_at_unix BIGINT NOT NULL,
                        used BOOLEAN DEFAULT FALSE
                    );
                """)
                cur.execute("ALTER TABLE otps ALTER COLUMN code TYPE VARCHAR(10)")
                cur.execute(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS rubika_chat_id VARCHAR UNIQUE"
                )
                cur.execute(
                    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS reply_to_id INT REFERENCES messages(id)"
                )
                cur.execute("""
                    ALTER TABLE messages ADD COLUMN IF NOT EXISTS seen_by JSONB DEFAULT '[]'::jsonb
                """)
                cur.execute(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR"
                )
                cur.execute(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen TIMESTAMP"
                )
                cur.execute(
                    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS edited BOOLEAN DEFAULT FALSE"
                )
                cur.execute(
                    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS deleted BOOLEAN DEFAULT FALSE"
                )
        print("INFO: Database initialized successfully.")
    except RuntimeError:
        print("WARNING: Could not initialize database – pool not available.")
    except Exception as e:
        print(f"ERROR during database init: {e}")


def update_last_seen(user_id):
    try:
        with database() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET last_seen = NOW() WHERE id = %s", (user_id,)
                )
    except Exception:
        pass
