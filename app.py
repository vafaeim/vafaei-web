import os
import re
import json
import string
import random
import secrets
import requests
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from flask_socketio import SocketIO, emit, join_room, leave_room
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from psycopg2.pool import ThreadedConnectionPool
from flask import session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__, static_folder="static", static_url_path="/static")

db_pool = None


def init_pool():
    global db_pool
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("WARNING: DATABASE_URL not set. Database features disabled.")
        return
    try:
        db_pool = ThreadedConnectionPool(1, 10, db_url)
        print("INFO: Database connection pool created.")
    except Exception as e:
        print(f"ERROR: Could not create connection pool: {e}")
        db_pool = None


app.config["SECRET_KEY"] = "amirrrr-secret-douz"
VERIFY_BOT_TOKEN = os.environ.get("VERIFY_BOT_TOKEN", "")

socketio = SocketIO(
    app,
    async_mode="eventlet",
    cors_allowed_origins=[
        "https://vafaei.runflare.run",
        "http://vafaei.runflare.run",
        "http://127.0.0.1:5000",
        "http://localhost:5000",
    ],
)


def get_db():
    if db_pool is None:
        return None
    try:
        return db_pool.getconn()
    except Exception:
        return None


def return_db(conn):
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
    except Exception:
        conn.rollback()
        raise
    finally:
        return_db(conn)


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

        print("INFO: Database initialized successfully.")
    except RuntimeError:
        print("WARNING: Could not initialize database – pool not available.")
    except Exception as e:
        print(f"ERROR during database init: {e}")


with app.app_context():
    init_pool()
    init_db()
    from scheduler import start_scheduler

    start_scheduler()


WHISPER_CONFIG_FILE = "whisper_config.json"
SECRET_KEY = "kavan2026"


def load_whisper_config():
    if os.path.exists(WHISPER_CONFIG_FILE):
        try:
            with open(WHISPER_CONFIG_FILE, "r") as f:
                config = json.load(f)
            if config.get("token") and config.get("chat_id"):
                return config
        except:
            pass

    token = os.environ.get("WHISPER_TOKEN", "")
    chat_id = os.environ.get("WHISPER_CHAT_ID", "")
    if token and chat_id:
        return {"token": token, "chat_id": chat_id}

    return {"token": "", "chat_id": ""}


def save_whisper_config(token, chat_id):
    with open(WHISPER_CONFIG_FILE, "w") as f:
        json.dump({"token": token, "chat_id": chat_id}, f)


MAIN_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>amirrrr</title>
  <style>
    :root {
      --bg: #000;
      --card-bg: rgba(10, 10, 10, 0.85);
      --text: #e8e8e8;
      --text-secondary: #999;
      --border: rgba(255, 255, 255, 0.08);
      --link-hover-bg: rgba(255, 255, 255, 0.03);
      --link-hover-border: rgba(255, 255, 255, 0.2);
      --rule-color: rgba(255, 255, 255, 0.3);
      --footer-color: #333;
      --game-prompt: #555;
      --bird-color: #e0e0e0;
      --pipe-color: #555;
      --game-bg: #0a0a0a;
      --game-border: rgba(255,255,255,0.07);
      --particle-color: rgba(255, 255, 255, 0.1);
      --toggle-color: #999;
    }
    body.light-mode {
      --bg: #f5f5f5;
      --card-bg: rgba(255, 255, 255, 0.9);
      --text: #111;
      --text-secondary: #333;
      --border: rgba(0, 0, 0, 0.08);
      --link-hover-bg: rgba(0, 0, 0, 0.03);
      --link-hover-border: rgba(0, 0, 0, 0.2);
      --rule-color: rgba(0, 0, 0, 0.2);
      --footer-color: #aaa;
      --game-prompt: #888;
      --bird-color: #111;
      --pipe-color: #aaa;
      --game-bg: #f0f0f0;
      --game-border: rgba(0,0,0,0.07);
      --particle-color: rgba(0, 0, 0, 0.1);
      --toggle-color: #333;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Segoe UI', system-ui, -apple-system, BlinkMacSystemFont, Roboto, 'Helvetica Neue', sans-serif;
      background: var(--bg);
      min-height: 100vh;
      overflow-y: auto;
      position: relative;
      transition: background 0.4s;
    }
    #particles {
      position: fixed; top: 0; left: 0; width: 100%; height: 100%;
      z-index: 0; pointer-events: none;
    }
    .page {
      position: relative; z-index: 1;
      display: flex; flex-direction: column; align-items: center;
      padding: 3rem 1.5rem 6rem;
    }
    .card {
      background: var(--card-bg);
      backdrop-filter: blur(15px); -webkit-backdrop-filter: blur(15px);
      border: 1px solid var(--border);
      border-radius: 0; padding: 3rem 2.5rem;
      max-width: 420px; width: 100%; text-align: center;
      transition: background 0.4s, border-color 0.4s;
      position: relative;
    }
    .theme-toggle {
      position: absolute; top: 1rem; left: 1rem;
      background: none; border: 1px solid transparent;
      color: var(--toggle-color); font-size: 1.2rem; cursor: pointer;
      width: 36px; height: 36px; display: flex; align-items: center; justify-content: center;
      border-radius: 50%; transition: all 0.3s;
    }
    .theme-toggle:hover { border-color: var(--border); background: var(--link-hover-bg); }
    .rule {
      width: 40px; height: 1px; background: var(--rule-color);
      margin: 0 auto 2rem; transition: background 0.4s;
    }
    h1 {
      font-family: 'Georgia', 'Times New Roman', serif;
      font-size: 2rem; font-weight: 400; color: var(--text);
      letter-spacing: 0.15em; margin-bottom: 2.5rem; text-transform: lowercase;
      transition: color 0.4s;
    }
    .links { display: flex; flex-direction: column; gap: 0.75rem; }
    a {
      display: block; padding: 0.75rem 1rem;
      color: var(--text-secondary); text-decoration: none;
      font-size: 0.9rem; font-weight: 400; letter-spacing: 0.05em;
      border: 1px solid var(--border);
      transition: all 0.3s ease; text-align: center;
    }
    a:hover {
      color: var(--text); border-color: var(--link-hover-border);
      background: var(--link-hover-bg);
    }
    .footer {
      margin-top: 2.5rem; font-size: 0.65rem;
      color: var(--footer-color); letter-spacing: 0.1em; transition: color 0.4s;
    }
    .game-section {
      margin-top: 4rem;
      display: flex; flex-direction: column; align-items: center;
    }
    .game-prompt { color: var(--game-prompt); font-size: 0.7rem; margin-bottom: 0.5rem; }
    canvas#flappyCanvas {
      display: block;
      border: 1px solid var(--game-border);
      background: var(--game-bg);
      transition: background 0.4s, border-color 0.4s;
    }
    .reset-btn {
      margin-top: 1rem;
      background: var(--button-bg);
      border: 1px solid var(--button-border);
      color: var(--button-text);
      font-size: 0.8rem;
      padding: 0.4rem 1.2rem;
      cursor: pointer;
      transition: all 0.2s;
      text-transform: lowercase;
      display: none;
    }
    .reset-btn:hover {
      color: var(--text);
      border-color: var(--link-hover-border);
      background: var(--link-hover-bg);
    }
    .reset-btn.show { display: inline-block; }
    :root {
      --button-bg: rgba(255,255,255,0.03);
      --button-border: rgba(255,255,255,0.1);
      --button-text: #aaa;
    }
    body.light-mode {
      --button-bg: rgba(0,0,0,0.03);
      --button-border: rgba(0,0,0,0.1);
      --button-text: #333;
    }
  </style>
</head>
<body>
  <canvas id="particles"></canvas>
  <div class="page">
    <div class="card">
      <button class="theme-toggle" onclick="toggleTheme()" title="switch theme">◑</button>
      <div class="rule"></div>
      <h1>amirrrr</h1>
      <div class="links">
        <a href="/chat">Messenger</a>
        <a href="/whisper/">Anonymous Message</a>
        <a href="/douz/">Tic-Tac-Toe</a>
        <a href="https://github.com/vafaeim" target="_blank">GitHub</a>
        <a href="https://kaggle.com/vafaeii" target="_blank">Kaggle</a>
        <a href="https://t.me/amirvafaeim" target="_blank">Telegram</a>
        <a href="https://rubika.ir/amir__kavan" target="_blank">Rubika</a>
      </div>
      <div class="footer">
        —<br>
        <span style="font-size:0.65rem;">scroll for a game (;</span>
      </div>
    </div>
    <div class="game-section">
      <p class="game-prompt">press space or click to fly</p>
      <canvas id="flappyCanvas" width="360" height="480"></canvas>
      <button id="resetButton" class="reset-btn">↻ retry</button>
    </div>
  </div>

  <script>
    const body = document.body;
    const themeToggleBtn = document.querySelector('.theme-toggle');
    function setTheme(isLight) {
      if (isLight) { body.classList.add('light-mode'); themeToggleBtn.textContent = '◐'; }
      else { body.classList.remove('light-mode'); themeToggleBtn.textContent = '◑'; }
      localStorage.setItem('theme', isLight ? 'light' : 'dark');
    }
    function toggleTheme() { setTheme(!body.classList.contains('light-mode')); }
    (localStorage.getItem('theme') === 'light') ? setTheme(true) : setTheme(false);

    const canvasP = document.getElementById('particles');
    const ctxP = canvasP.getContext('2d');
    canvasP.width = window.innerWidth; canvasP.height = window.innerHeight;
    const particles = []; const particleCount = 50;
    class Particle {
      constructor() {
        this.x = Math.random() * canvasP.width; this.y = Math.random() * canvasP.height;
        this.size = Math.random() * 1.5 + 0.3;
        this.speedX = (Math.random() - 0.5) * 0.3; this.speedY = (Math.random() - 0.5) * 0.3;
      }
      update() { this.x += this.speedX; this.y += this.speedY; if (this.x<0||this.x>canvasP.width) this.speedX*=-1; if (this.y<0||this.y>canvasP.height) this.speedY*=-1; }
      draw() {
        const color = getComputedStyle(document.documentElement).getPropertyValue('--particle-color').trim();
        ctxP.fillStyle = color; ctxP.beginPath(); ctxP.arc(this.x, this.y, this.size, 0, Math.PI*2); ctxP.fill();
      }
    }
    for (let i=0; i<particleCount; i++) particles.push(new Particle());
    function animateParticles() { ctxP.clearRect(0,0,canvasP.width,canvasP.height); particles.forEach(p=>{p.update();p.draw();}); requestAnimationFrame(animateParticles); }
    animateParticles();
    window.addEventListener('resize', () => { canvasP.width = window.innerWidth; canvasP.height = window.innerHeight; });

    const canvas = document.getElementById('flappyCanvas');
    const ctx = canvas.getContext('2d');
    const resetBtn = document.getElementById('resetButton');

    function getStyleVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

    const bird = { x:60, y:canvas.height/2, w:16, h:16, gravity:0.5, lift:-8, vel:0 };
    let pipes = [];
    const PW = 18, GAP = 110;
    let frame = 0, score = 0, best = parseInt(localStorage.getItem('flappyBest')||'0');
    let started = false, over = false;
    let animId;

    function resetGame() {
      bird.y = canvas.height/2; bird.vel = 0;
      pipes = []; frame = 0; score = 0;
      over = false; started = true;
      resetBtn.classList.remove('show');
    }

    function drawBird() {
      ctx.fillStyle = getStyleVar('--bird-color');
      ctx.fillRect(bird.x, bird.y, bird.w, bird.h);
    }

    function drawPipes() {
      ctx.fillStyle = getStyleVar('--pipe-color');
      for (let p of pipes) {
        ctx.fillRect(p.x, 0, PW, p.top);
        ctx.fillRect(p.x, p.top+GAP, PW, canvas.height-p.top-GAP);
      }
    }

    function updatePipes() {
      if (frame % 90 === 0) {
        let top = Math.random()*(canvas.height-GAP-60)+30;
        pipes.push({ x:canvas.width, top, scored:false });
      }
      for (let p of pipes) p.x -= 2;
      pipes = pipes.filter(p => p.x > -PW);
    }

    function checkCollision() {
      for (let p of pipes) {
        if (bird.x+bird.w > p.x && bird.x < p.x+PW) {
          if (bird.y < p.top || bird.y+bird.h > p.top+GAP) return true;
        }
      }
      return bird.y < 0 || bird.y+bird.h > canvas.height;
    }

    function updateScore() {
      for (let p of pipes) {
        if (!p.scored && p.x+PW < bird.x) { score++; p.scored = true; if (score > best) { best = score; localStorage.setItem('flappyBest', best); } }
      }
    }

    function drawIdle() {
      ctx.clearRect(0,0,canvas.width,canvas.height);
      let bob = Math.sin(Date.now()*0.008)*6;
      ctx.fillStyle = getStyleVar('--bird-color');
      ctx.fillRect(bird.x, bird.y+bob, bird.w, bird.h);
      ctx.fillStyle = getStyleVar('--text-secondary');
      ctx.font = '18px "Segoe UI"';
      ctx.textAlign = 'center';
      ctx.fillText('press space or click to start', canvas.width/2, canvas.height/2-20);
      ctx.font = '13px "Segoe UI"';
      ctx.textAlign = 'right';
      ctx.fillText('best: '+best, canvas.width-15, 25);
    }

    function drawPlaying() {
      ctx.clearRect(0,0,canvas.width,canvas.height);
      drawPipes();
      drawBird();
      ctx.fillStyle = getStyleVar('--text-secondary');
      ctx.font = 'bold 16px "Segoe UI"';
      ctx.textAlign = 'left';
      ctx.fillText(score, 15, 30);
      ctx.font = '13px "Segoe UI"';
      ctx.textAlign = 'right';
      ctx.fillText('best: '+best, canvas.width-15, 25);
    }

    function drawGameOver() {
      ctx.fillStyle = getStyleVar('--text-secondary');
      ctx.textAlign = 'center';
      let cy = canvas.height/2 - 30;
      ctx.font = '22px "Georgia"';
      ctx.fillText('game over', canvas.width/2, cy);
      cy += 35;
      ctx.font = '16px "Segoe UI"';
      ctx.fillText('score: ' + score, canvas.width/2, cy);
      cy += 25;
      ctx.fillText('best: ' + best, canvas.width/2, cy);
    }

    function gameLoop() {
      if (!started && !over) {
        drawIdle();
        animId = requestAnimationFrame(gameLoop);
        return;
      }
      if (over) {
        animId = requestAnimationFrame(gameLoop);
        return;
      }
      bird.vel += bird.gravity;
      bird.y += bird.vel;
      updatePipes();
      updateScore();
      drawPlaying();
      if (checkCollision()) {
        over = true; started = false;
        drawGameOver();
        resetBtn.classList.add('show');
      }
      frame++;
      animId = requestAnimationFrame(gameLoop);
    }

    function jump() {
      if (over) return;
      if (!started) { resetGame(); }
      else { bird.vel = bird.lift; }
    }

    document.addEventListener('keydown', function(e) {
      if (e.code === 'Space') {
        if (document.activeElement && (document.activeElement.tagName === 'BUTTON' || document.activeElement.tagName === 'INPUT')) return;
        e.preventDefault();
        jump();
      }
    });
    canvas.addEventListener('click', jump);
    resetBtn.addEventListener('click', () => { if (over) resetGame(); });
    animId = requestAnimationFrame(gameLoop);
  </script>
</body>
</html>
"""

WHISPER_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>whisper</title>
  <style>
    :root {
      --bg: #17212b;
      --chat-bg: #0e1621;
      --bubble-sent: #2b5278;
      --text-primary: #fff;
      --text-secondary: #aab2bb;
      --input-bg: #212e3c;
      --input-border: #2b3a4a;
      --btn-color: #8ea2b8;
      --btn-hover-bg: #2b5278;
      --status-bar-bg: #212e3c;
      --shadow: 0 2px 10px rgba(0,0,0,0.3);
    }
    body.light-mode {
      --bg: #f5f5f5;
      --chat-bg: #ffffff;
      --bubble-sent: #e3ffd8;
      --text-primary: #000;
      --text-secondary: #707579;
      --input-bg: #fff;
      --input-border: #d3d9de;
      --btn-color: #707579;
      --btn-hover-bg: #e8ecef;
      --status-bar-bg: #f5f5f5;
      --shadow: 0 2px 10px rgba(0,0,0,0.05);
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Segoe UI', system-ui, -apple-system, BlinkMacSystemFont, 'Helvetica Neue', sans-serif;
      background: var(--bg);
      height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background 0.4s;
    }
    .phone-frame {
      width: 100%;
      max-width: 400px;
      height: 85vh;
      max-height: 700px;
      background: var(--chat-bg);
      border-radius: 20px;
      box-shadow: var(--shadow);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      position: relative;
    }
    .status-bar {
      background: var(--status-bar-bg);
      padding: 0.8rem 1rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid var(--input-border);
    }
    .status-bar .title {
      font-size: 1.1rem;
      font-weight: 600;
      color: var(--text-primary);
      letter-spacing: 0.5px;
    }
    .theme-toggle {
      background: none;
      border: none;
      color: var(--btn-color);
      font-size: 1.3rem;
      cursor: pointer;
      width: 34px; height: 34px;
      display: flex; align-items: center; justify-content: center;
      border-radius: 50%;
    }
    .theme-toggle:hover { background: var(--btn-hover-bg); }
    .messages {
      flex: 1;
      padding: 1rem 0.8rem;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }
    .message {
      display: flex;
      justify-content: flex-end;
    }
    .bubble {
      max-width: 80%;
      padding: 0.6rem 0.9rem;
      border-radius: 18px 4px 18px 18px;
      background: var(--bubble-sent);
      color: var(--text-primary);
      font-size: 0.95rem;
      word-wrap: break-word;
      position: relative;
      box-shadow: 0 1px 2px rgba(0,0,0,0.1);
    }
    .bubble.emoji-only {
      font-size: 2.5rem;
      background: transparent;
      box-shadow: none;
      padding: 0.2rem;
    }
    .bubble .time {
      font-size: 0.65rem;
      color: var(--text-secondary);
      float: right;
      margin-left: 0.5rem;
      margin-top: 0.3rem;
    }
    .input-bar {
      background: var(--input-bg);
      padding: 0.6rem 0.8rem;
      border-top: 1px solid var(--input-border);
      display: flex;
      align-items: flex-end;
      gap: 0.5rem;
    }
    .attach-btn, .voice-btn, .emoji-toggle-btn {
      background: none;
      border: none;
      color: var(--btn-color);
      font-size: 1.5rem;
      cursor: pointer;
      padding: 0.3rem;
      line-height: 1;
      transition: color 0.2s;
    }
    .attach-btn:hover, .voice-btn:hover, .emoji-toggle-btn:hover { color: #2b9cff; }
    .voice-btn.recording {
      color: #ff4d4d;
    }
    .text-input {
      flex: 1;
      background: transparent;
      border: none;
      outline: none;
      color: var(--text-primary);
      font-size: 16px;
      resize: none;
      max-height: 100px;
      padding: 0.4rem 0;
      font-family: inherit;
    }
    .send-btn {
      background: none;
      border: none;
      color: #2b9cff;
      font-size: 1.5rem;
      cursor: pointer;
      padding: 0.3rem;
      line-height: 1;
      display: none;
      position: relative;
    }
    .send-btn.visible { display: block; }
    .send-btn:disabled { opacity: 0.5; cursor: default; }
    .send-spinner {
      display: none;
      width: 20px; height: 20px;
      border: 2px solid rgba(43,156,255,0.3);
      border-top: 2px solid #2b9cff;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
      position: absolute;
      top: 50%; left: 50%;
      transform: translate(-50%, -50%);
    }
    @keyframes spin { 0% { transform: translate(-50%, -50%) rotate(0deg); } 100% { transform: translate(-50%, -50%) rotate(360deg); } }
    .emoji-panel {
      display: none;
      background: var(--input-bg);
      border-top: 1px solid var(--input-border);
      padding: 0.5rem 0.3rem;
      justify-content: center;
      gap: 0.5rem;
      flex-wrap: wrap;
    }
    .emoji-panel.open { display: flex; }
    .emoji-panel .emoji-btn {
      background: none;
      border: none;
      font-size: 1.6rem;
      cursor: pointer;
      padding: 0.3rem;
    }
    .preview-area {
      padding: 0.3rem 0.8rem;
      background: var(--input-bg);
      border-top: 1px solid var(--input-border);
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.85rem;
      color: var(--text-secondary);
    }
    .preview-area .remove-preview {
      color: #ff4d4d;
      cursor: pointer;
    }
    #photoInput { display: none; }
    .messages::-webkit-scrollbar { width: 4px; }
    .messages::-webkit-scrollbar-thumb { background: var(--input-border); border-radius: 4px; }
  </style>
</head>
<body>
  <div class="phone-frame">
    <div class="status-bar">
      <button class="theme-toggle" onclick="toggleTheme()" title="switch theme">◑</button>
      <span class="title">whisper</span>
      <div style="width:34px;"></div>
    </div>

    <div class="messages" id="messagesContainer"></div>

    <div class="preview-area" id="previewArea" style="display:none;">
      <span id="previewText"></span>
      <span class="remove-preview" onclick="removeAttachment()">✕</span>
    </div>

    <div class="emoji-panel" id="emojiPanel">
      <button class="emoji-btn" onclick="sendEmoji('👍')">👍</button>
      <button class="emoji-btn" onclick="sendEmoji('❤️')">❤️</button>
      <button class="emoji-btn" onclick="sendEmoji('😂')">😂</button>
      <button class="emoji-btn" onclick="sendEmoji('😢')">😢</button>
      <button class="emoji-btn" onclick="sendEmoji('😡')">😡</button>
      <button class="emoji-btn" onclick="sendEmoji('👋')">👋</button>
    </div>

    <div class="input-bar">
      <button class="emoji-toggle-btn" id="emojiToggleBtn" onclick="toggleEmojiPanel()">😊</button>
      <label for="photoInput" class="attach-btn">📎</label>
      <input type="file" id="photoInput" accept="image/*" onchange="handlePhotoSelect(this)">
      <button class="voice-btn" id="voiceBtn" onclick="toggleRecording()">🎤</button>
      <textarea class="text-input" id="messageInput" placeholder="پیامت رو اینجا بنویس..." dir="auto" rows="1" oninput="toggleSendButton()"></textarea>
      <button class="send-btn" id="sendBtn" onclick="sendMessage()">
        <span class="send-text">➤</span>
        <span class="send-spinner" id="sendSpinner"></span>
      </button>
    </div>
  </div>

  <script>
    const body = document.body;
    const themeToggleBtn = document.querySelector('.theme-toggle');
    function setTheme(isLight) {
      if (isLight) { body.classList.add('light-mode'); themeToggleBtn.textContent = '◐'; }
      else { body.classList.remove('light-mode'); themeToggleBtn.textContent = '◑'; }
      localStorage.setItem('theme', isLight ? 'light' : 'dark');
    }
    function toggleTheme() { setTheme(!body.classList.contains('light-mode')); }
    (localStorage.getItem('theme') === 'light') ? setTheme(true) : setTheme(false);

    const messagesContainer = document.getElementById('messagesContainer');
    const messageInput = document.getElementById('messageInput');
    const sendButton = document.getElementById('sendBtn');
    const sendText = document.querySelector('.send-text');
    const sendSpinner = document.getElementById('sendSpinner');
    const photoInput = document.getElementById('photoInput');
    const voiceBtn = document.getElementById('voiceBtn');
    const previewArea = document.getElementById('previewArea');
    const previewText = document.getElementById('previewText');
    const emojiPanel = document.getElementById('emojiPanel');

    let selectedFile = null;
    let mediaRecorder = null;
    let audioChunks = [];
    let recording = false;
    let isSending = false;

    function addMessage(text, isEmojiOnly = false) {
      const msgDiv = document.createElement('div');
      msgDiv.className = 'message';
      const bubble = document.createElement('div');
      bubble.className = 'bubble' + (isEmojiOnly ? ' emoji-only' : '');
      bubble.textContent = text;
      const timeSpan = document.createElement('span');
      timeSpan.className = 'time';
      const now = new Date();
      timeSpan.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      bubble.appendChild(timeSpan);
      msgDiv.appendChild(bubble);
      messagesContainer.appendChild(msgDiv);
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function toggleSendButton() {
      if (messageInput.value.trim() || selectedFile) {
        sendButton.classList.add('visible');
      } else {
        sendButton.classList.remove('visible');
      }
    }

    function toggleEmojiPanel() {
      emojiPanel.classList.toggle('open');
    }

    function sendEmoji(emoji) {
      addMessage(emoji, true);
      sendToServer({ text: emoji });
      emojiPanel.classList.remove('open');
    }

    function setSendingState(sending) {
      isSending = sending;
      if (sending) {
        sendButton.disabled = true;
        sendText.style.display = 'none';
        sendSpinner.style.display = 'inline-block';
      } else {
        sendButton.disabled = false;
        sendText.style.display = 'inline';
        sendSpinner.style.display = 'none';
      }
    }

    function handlePhotoSelect(input) {
      if (input.files.length > 0) {
        selectedFile = input.files[0];
        previewText.textContent = '📷 ' + selectedFile.name;
        previewArea.style.display = 'flex';
        toggleSendButton();
        if (mediaRecorder && mediaRecorder.state === 'recording') {
          mediaRecorder.stop();
        }
      }
    }

    function removeAttachment() {
      selectedFile = null;
      photoInput.value = '';
      previewArea.style.display = 'none';
      toggleSendButton();
    }

    async function toggleRecording() {
      if (recording) {
        mediaRecorder.stop();
        recording = false;
        voiceBtn.classList.remove('recording');
        voiceBtn.textContent = '🎤';
      } else {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          try {
            mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/ogg' });
          } catch (e) {
            mediaRecorder = new MediaRecorder(stream);
          }
          audioChunks = [];
          mediaRecorder.ondataavailable = (event) => {
            audioChunks.push(event.data);
          };
          mediaRecorder.onstop = () => {
            const blob = new Blob(audioChunks, { type: 'audio/ogg' });
            selectedFile = new File([blob], 'voice_message.ogg', { type: 'audio/ogg' });
            previewText.textContent = '🎙️ Voice message';
            previewArea.style.display = 'flex';
            toggleSendButton();
            stream.getTracks().forEach(track => track.stop());
            recording = false;
            voiceBtn.classList.remove('recording');
            voiceBtn.textContent = '🎤';
          };
          mediaRecorder.start();
          recording = true;
          voiceBtn.classList.add('recording');
          voiceBtn.textContent = '⏹️';
          removeAttachment();
        } catch (err) {
          alert('Microphone access denied.');
        }
      }
    }

    const PROXY_URL = '/whisper/send';
    const FILE_PROXY_URL = '/whisper/send_file';

    async function sendToServer(payload) {
      try {
        let response;
        if (selectedFile) {
          const formData = new FormData();
          formData.append('file', selectedFile);
          if (payload.text) formData.append('text', payload.text);
          response = await fetch(FILE_PROXY_URL, { method: 'POST', body: formData });
        } else {
          response = await fetch(PROXY_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          });
        }
        const result = await response.json();
        if (!result.success) {
          console.error('Send failed:', result.error);
        }
      } catch (err) {
        console.error('Connection error:', err);
      }
    }

    async function sendMessage() {
      const text = messageInput.value.trim();
      if (!text && !selectedFile) return;
      if (isSending) return;

      if (selectedFile) {
        if (text) addMessage(text);
        addMessage('📎 ' + (selectedFile.type.startsWith('image/') ? 'Photo' : 'Voice message'));
      } else if (text) {
        addMessage(text);
      }

      emojiPanel.classList.remove('open');

      setSendingState(true);

      await sendToServer({ text: text });

      messageInput.value = '';
      removeAttachment();
      sendButton.classList.remove('visible');
      setSendingState(false);
    }

    messageInput.addEventListener('input', function() {
      this.style.height = 'auto';
      this.style.height = Math.min(this.scrollHeight, 100) + 'px';
      toggleSendButton();
    });

    window.addEventListener('load', () => {
      messageInput.focus();
    });
  </script>
</body>
</html>
"""

WHISPER_SETTINGS_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>settings</title>
  <style>
    body {
      font-family: 'Segoe UI', system-ui, sans-serif; background: #000; color: #e2e8f0;
      display: flex; align-items: center; justify-content: center; min-height: 100vh; padding: 1.5rem;
    }
    .settings-card {
      background: rgba(10,10,10,0.85); backdrop-filter: blur(15px); border: 1px solid rgba(255,255,255,0.08);
      border-radius: 0; padding: 2rem; max-width: 400px; width: 100%;
    }
    h2 {
      text-align: center; font-family: 'Georgia', serif; font-size: 1.5rem; font-weight: 400;
      color: #ccc; margin-bottom: 2rem; letter-spacing: 0.1em;
    }
    label { display: block; margin-top: 1rem; font-size: 0.8rem; color: #666; letter-spacing: 0.05em; }
    input {
      width: 100%; padding: 0.8rem; margin-top: 0.3rem;
      background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08);
      border-radius: 0; color: white; font-size: 0.9rem; outline: none;
    }
    input:focus { border-color: rgba(255,255,255,0.2); }
    button {
      margin-top: 1.8rem; width: 100%; padding: 0.8rem;
      border: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.03);
      color: #aaa; font-weight: 400; letter-spacing: 0.08em; cursor: pointer; transition: all 0.2s;
    }
    button:hover { color: #fff; border-color: rgba(255,255,255,0.3); background: rgba(255,255,255,0.05); }
    #msg { margin-top: 1rem; font-size: 0.8rem; text-align: center; }
    .success { color: #5f9; } .error { color: #f66; }
    .note { margin-top: 1.5rem; font-size: 0.65rem; color: #333; text-align: center; }
  </style>
</head>
<body>
  <div class="settings-card">
    <h2>settings</h2>
    <form id="settingsForm">
      <label for="token">Rubika bot token</label>
      <input type="text" id="token" placeholder="BCCG..." value="{{ token }}">
      <label for="chat_id">chat id</label>
      <input type="text" id="chat_id" placeholder="chat_id" value="{{ chat_id }}">
      <button type="submit">save</button>
    </form>
    <div id="msg"></div>
    <div class="note">?key=kavan2026</div>
  </div>
  <script>
    const form = document.getElementById('settingsForm');
    const msgDiv = document.getElementById('msg');
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const token = document.getElementById('token').value.trim();
      const chat_id = document.getElementById('chat_id').value.trim();
      if (!token || !chat_id) { msgDiv.textContent = 'both fields required'; msgDiv.className = 'error'; return; }
      try {
        const response = await fetch('/whisper/settings', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token, chat_id, key: new URLSearchParams(window.location.search).get('key') })
        });
        const result = await response.json();
        if (result.success) { msgDiv.textContent = 'saved'; msgDiv.className = 'success'; }
        else { msgDiv.textContent = result.error; msgDiv.className = 'error'; }
      } catch (err) { msgDiv.textContent = 'connection error'; msgDiv.className = 'error'; }
    });
  </script>
</body>
</html>
"""

DOUZ_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>dous</title>
  <style>
    :root {
      --bg: #000;
      --text: #e8e8e8;
      --text-secondary: #999;
      --border: rgba(255,255,255,0.08);
      --cell-bg: rgba(255,255,255,0.03);
      --cell-hover: rgba(255,255,255,0.06);
      --x-color: #c084fc;
      --o-color: #60a5fa;
      --container-bg: rgba(20,20,30,0.8);
      --button-bg: rgba(255,255,255,0.03);
      --button-border: rgba(255,255,255,0.1);
      --button-text: #aaa;
      --input-bg: rgba(255,255,255,0.03);
    }
    body.light-mode {
      --bg: #f5f5f5;
      --text: #111;
      --text-secondary: #333;
      --border: rgba(0,0,0,0.08);
      --cell-bg: rgba(0,0,0,0.02);
      --cell-hover: rgba(0,0,0,0.05);
      --x-color: #7c3aed;
      --o-color: #2563eb;
      --container-bg: rgba(255,255,255,0.85);
      --button-bg: rgba(0,0,0,0.03);
      --button-border: rgba(0,0,0,0.1);
      --button-text: #333;
      --input-bg: rgba(0,0,0,0.03);
    }
    * { margin:0; padding:0; box-sizing:border-box; }
    body {
      font-family: 'Segoe UI', system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: flex; align-items: center; justify-content: center;
      padding: 1.5rem;
      transition: background 0.4s;
      position: relative;
    }
    .container {
      background: var(--container-bg);
      backdrop-filter: blur(15px);
      border: 1px solid var(--border);
      border-radius: 0;
      padding: 2.5rem;
      max-width: 400px;
      width: 100%;
      text-align: center;
      position: relative;
      transition: background 0.4s, border-color 0.4s;
    }
    .theme-toggle {
      position: absolute; top: 1rem; left: 1rem;
      background: none; border: 1px solid transparent;
      color: var(--text-secondary); font-size: 1.2rem; cursor: pointer;
      width: 36px; height: 36px; display: flex; align-items: center; justify-content: center;
      border-radius: 50%;
      transition: all 0.3s;
    }
    .theme-toggle:hover { border-color: var(--border); background: var(--cell-hover); }
    h1 {
      font-family: 'Georgia', serif;
      font-size: 2rem; font-weight: 400; letter-spacing: 0.1em;
      margin-bottom: 1.5rem;
      color: var(--text);
    }
    .board {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 6px;
      margin: 1.5rem 0;
    }
    .cell {
      background: var(--cell-bg);
      border: 1px solid var(--border);
      aspect-ratio: 1;
      display: flex; align-items: center; justify-content: center;
      font-size: 2.2rem;
      font-weight: 300;
      cursor: pointer;
      transition: background 0.2s;
      color: var(--text);
    }
    .cell:hover { background: var(--cell-hover); }
    .cell.x { color: var(--x-color); }
    .cell.o { color: var(--o-color); }
    .status {
      font-size: 0.9rem;
      color: var(--text-secondary);
      margin: 1rem 0;
    }
    .room-info {
      font-size: 0.8rem;
      color: var(--text-secondary);
      margin-bottom: 1rem;
    }
    .scoreboard {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1rem;
      padding: 0.5rem;
      border: 1px solid var(--border);
      font-size: 1.1rem;
      background: var(--cell-bg);
      color: var(--text);
    }
    .score-item {
      text-align: center;
      flex: 1;
    }
    .score-label {
      display: block;
      font-size: 0.7rem;
      color: var(--text-secondary);
      text-transform: lowercase;
    }
    button {
      background: var(--button-bg);
      border: 1px solid var(--button-border);
      color: var(--button-text);
      padding: 0.6rem 1.5rem;
      font-size: 0.85rem;
      cursor: pointer;
      transition: all 0.2s;
      margin: 0.3rem;
    }
    button:hover {
      color: var(--text);
      border-color: var(--link-hover-border, rgba(255,255,255,0.2));
      background: var(--cell-hover);
    }
    input {
      background: var(--input-bg);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 0.5rem;
      font-size: 0.9rem;
      text-transform: uppercase;
      text-align: center;
      width: 120px;
    }
    .hidden { display: none; }
  </style>
</head>
<body>
  <button class="theme-toggle" onclick="toggleTheme()">◑</button>
  <div class="container">
    <h1>dous</h1>
    <div id="lobby">
      <button id="createRoomBtn">create room</button>
      <div style="margin: 1rem 0; color: var(--text-secondary);">or</div>
      <input type="text" id="roomInput" placeholder="room code" maxlength="6">
      <button id="joinRoomBtn">join room</button>
    </div>
    <div id="gameArea" class="hidden">
      <div class="room-info">room: <span id="roomCode"></span></div>
      <div class="scoreboard" id="scoreboard">
        <div class="score-item">
          <span class="score-label">you</span>
          <span id="myWins">0</span>
        </div>
        <div class="score-item">
          <span class="score-label">draws</span>
          <span id="draws">0</span>
        </div>
        <div class="score-item">
          <span class="score-label">opponent</span>
          <span id="oppWins">0</span>
        </div>
      </div>
      <div class="status" id="status">waiting for opponent...</div>
      <div class="board" id="board">
        <div class="cell" data-idx="0"></div>
        <div class="cell" data-idx="1"></div>
        <div class="cell" data-idx="2"></div>
        <div class="cell" data-idx="3"></div>
        <div class="cell" data-idx="4"></div>
        <div class="cell" data-idx="5"></div>
        <div class="cell" data-idx="6"></div>
        <div class="cell" data-idx="7"></div>
        <div class="cell" data-idx="8"></div>
      </div>
      <button id="leaveBtn">leave room</button>
      <button id="replayBtn" class="hidden">replay</button>
    </div>
  </div>
  <script src="/static/socket.io.min.js"></script>
  <script>
    const body = document.body;
    function toggleTheme() {
      body.classList.toggle('light-mode');
      localStorage.setItem('theme', body.classList.contains('light-mode') ? 'light' : 'dark');
    }
    (localStorage.getItem('theme') === 'light') ? body.classList.add('light-mode') : body.classList.remove('light-mode');

    const socket = io();

    let myRoom = null;
    let mySymbol = null;
    let currentTurn = null;

    const lobby = document.getElementById('lobby');
    const gameArea = document.getElementById('gameArea');
    const statusDiv = document.getElementById('status');
    const roomCodeSpan = document.getElementById('roomCode');
    const cells = document.querySelectorAll('.cell');
    const replayBtn = document.getElementById('replayBtn');
    const leaveBtn = document.getElementById('leaveBtn');
    const myWinsSpan = document.getElementById('myWins');
    const oppWinsSpan = document.getElementById('oppWins');
    const drawsSpan = document.getElementById('draws');

    document.getElementById('createRoomBtn').addEventListener('click', () => {
      socket.emit('create_room');
    });

    document.getElementById('joinRoomBtn').addEventListener('click', () => {
      const code = document.getElementById('roomInput').value.trim().toUpperCase();
      if (code) socket.emit('join_room', {room: code});
    });

    cells.forEach(cell => {
      cell.addEventListener('click', () => {
        if (!mySymbol || currentTurn !== mySymbol) return;
        const idx = cell.dataset.idx;
        socket.emit('make_move', {room: myRoom, index: idx});
      });
    });

    socket.on('room_created', (data) => {
      myRoom = data.room;
      joinGameRoom(data.room);
      roomCodeSpan.textContent = data.room;
      statusDiv.textContent = 'waiting for opponent...';
      updateScores({my_wins: 0, opponent_wins: 0, draws: 0});
    });

    socket.on('room_joined', (data) => {
      myRoom = data.room;
      joinGameRoom(data.room);
      roomCodeSpan.textContent = data.room;
    });

    socket.on('game_start', (data) => {
      mySymbol = data.symbol;
      currentTurn = 'X';
      statusDiv.textContent = data.symbol === 'X' ? 'your turn' : 'opponent turn';
      updateBoard(data.board);
      updateScores(data.scores);
      replayBtn.classList.add('hidden');
    });

    socket.on('board_update', (data) => {
      updateBoard(data.board);
      currentTurn = data.turn;
      statusDiv.textContent = data.turn === mySymbol ? 'your turn' : 'opponent turn';
    });

    socket.on('game_over', (data) => {
      updateBoard(data.board);
      if (data.winner) {
        const winText = data.winner === mySymbol ? 'you won!' : 'you lost';
        statusDiv.textContent = winText;
      } else {
        statusDiv.textContent = 'draw';
      }
      currentTurn = null;
      updateScores(data.scores);
      replayBtn.classList.remove('hidden');
      replayBtn.textContent = 'replay';
      replayBtn.disabled = false;
    });

    socket.on('opponent_left', () => {
      statusDiv.textContent = 'opponent left the room';
      currentTurn = null;
      replayBtn.classList.add('hidden');
    });

    replayBtn.addEventListener('click', () => {
      socket.emit('request_replay', {room: myRoom});
      replayBtn.textContent = 'waiting...';
      replayBtn.disabled = true;
    });

    socket.on('replay_waiting', (data) => {
      statusDiv.textContent = data.msg;
    });

    socket.on('replay_accepted', (data) => {
      mySymbol = data.symbol;
      currentTurn = 'X';
      updateBoard(data.board);
      updateScores(data.scores);
      statusDiv.textContent = data.symbol === 'X' ? 'your turn' : 'opponent turn';
      replayBtn.classList.add('hidden');
    });

    leaveBtn.addEventListener('click', () => {
      socket.emit('leave_room', {room: myRoom});
      myRoom = null;
      mySymbol = null;
      gameArea.classList.add('hidden');
      lobby.classList.remove('hidden');
    });

    function joinGameRoom(room) {
      lobby.classList.add('hidden');
      gameArea.classList.remove('hidden');
    }

    function updateBoard(board) {
      cells.forEach((cell, i) => {
        cell.textContent = board[i];
        cell.className = 'cell';
        if (board[i] === 'X') cell.classList.add('x');
        if (board[i] === 'O') cell.classList.add('o');
      });
    }

    function updateScores(scores) {
      myWinsSpan.textContent = scores.my_wins;
      oppWinsSpan.textContent = scores.opponent_wins;
      drawsSpan.textContent = scores.draws;
    }
  </script>
</body>
</html>
"""

LOGIN_HTML = r"""
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>ورود</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Vazirmatn', Tahoma, sans-serif;
      background: #17212b;
      color: #fff;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
      padding: 1rem;
    }
    .card {
      background: #0e1621;
      padding: 2rem;
      border-radius: 1.5rem;
      text-align: center;
      max-width: 420px;
      width: 100%;
      box-shadow: 0 10px 30px rgba(0,0,0,0.5);
    }
    .tab-container {
      display: flex;
      background: #212e3c;
      border-radius: 1rem;
      margin-bottom: 1.5rem;
      overflow: hidden;
      gap: 0;
    }
    .tab {
      flex: 1;
      padding: 0.6rem;
      font-size: 0.9rem;
      cursor: pointer;
      color: #8ea2b8;
      border-bottom: 2px solid transparent;
      transition: 0.2s;
      background: none;
      border: none;
      font-family: inherit;
    }
    .tab.active {
      color: #fff;
      border-bottom-color: #2b9cff;
    }
    h2 { margin-bottom: 0.25rem; font-size: 1.5rem; }
    .subtitle {
      font-size: 0.85rem;
      color: #aab2bb;
      margin-bottom: 1.5rem;
    }
    .form-group {
      margin: 1rem 0;
      display: none;
    }
    .form-group.active {
      display: block;
    }
    input {
      width: 100%;
      padding: 0.8rem;
      font-size: 1rem;
      background: #212e3c;
      border: 1px solid #2b3a4a;
      border-radius: 0.8rem;
      color: #fff;
      margin: 0.5rem 0;
      outline: none;
      font-family: inherit;
    }
    .btn {
      background: #2b5278;
      color: #fff;
      border: none;
      padding: 0.8rem 2rem;
      border-radius: 0.8rem;
      font-size: 1rem;
      cursor: pointer;
      transition: background 0.2s;
      margin-top: 1rem;
      width: 100%;
      font-family: inherit;
    }
    .btn:hover { background: #3a6a99; }
    .error { color: #ff4d4d; margin-top: 1rem; font-size: 0.9rem; }
    .success { color: #34d399; margin-top: 1rem; font-size: 0.9rem; }
    .timer {
      font-size: 0.9rem;
      color: #ffb300;
      margin: 1rem 0;
    }
    .hidden { display: none; }
    .token-box {
    background: #212e3c;
    border-radius: 1rem;
    padding: 1rem;
    margin: 1rem 0;
    }
    .token {
    font-size: 1.8rem;
    font-weight: 700;
    letter-spacing: 0.3rem;
    color: #2b9cff;
    user-select: all;
    word-break: break-all;
    font-family: 'Courier New', monospace;
    margin-bottom: 0.5rem;
    }
    .copy-hint {
    font-size: 0.75rem;
    color: #8ea2b8;
    }
    .bot-box {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.6rem;
    background: #212e3c;
    border-radius: 1rem;
    padding: 0.8rem;
    margin: 1.2rem 0;
    text-decoration: none;
    color: #fff;
    transition: background 0.2s;
    }
    .bot-box:hover { background: #2b5278; }
    .bot-icon {
    width: 44px;
    height: 44px;
    border-radius: 50%;
    background-image: url('/static/assets/images/verifymebot.png');
    background-size: cover;
    background-position: center;
    }
    .bot-name {
    font-weight: 600;
    font-size: 1rem;
    }
    .bot-link {
    font-size: 0.75rem;
    color: #aab2bb;
    }
    .btn-secondary {
    background: transparent;
    color: #8ea2b8;
    border: 1px solid #2b3a4a;
    padding: 0.8rem 1.5rem;
    border-radius: 0.8rem;
    font-size: 1rem;
    cursor: pointer;
    transition: background 0.2s;
    font-family: inherit;
    margin-top: 0.5rem;
    }
    .btn-secondary:hover { background: #212e3c; }
    .status {
    margin: 1rem 0;
    min-height: 1.5rem;
    }
    .animate-pulse {
    animation: pulse 1.5s ease-in-out infinite;
    }
    @keyframes pulse {
    0% { opacity: 1; }
    50% { opacity: 0.5; }
    100% { opacity: 1; }
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="tab-container">
      <button class="tab active" id="tabOtp" onclick="switchTab('otp')">🤖 ورود با ربات</button>
      <button class="tab" id="tabPass" onclick="switchTab('password')">🔑 رمز عبور</button>
    </div>

    <!-- OTP Form -->
    <div id="otpForm" class="form-group active">
      <h2>🔐 ورود امن</h2>
      <p class="subtitle">با ربات VerifymeBot احراز هویت کنید</p>
      <div class="token-box">
        <div class="token" id="otpCode">{{ code }}</div>
        <div class="copy-hint">توکن را کپی کرده و برای ربات ارسال کنید</div>
      </div>
      <a class="bot-box" href="https://rubika.ir/verifymebot" target="_blank">
        <div class="bot-icon"></div>
        <div>
          <div class="bot-name">VerifymeBot</div>
          <div class="bot-link">@verifymebot</div>
        </div>
      </a>
      <div class="timer" id="timer">
        <span>⏳</span> <span id="timerText">زمان باقی‌مانده: ۹۰ ثانیه</span>
      </div>
      <div id="statusOtp" class="status"></div>
      <button class="btn-secondary" onclick="window.location.reload()">دریافت توکن جدید</button>
    </div>

    <!-- Password Form -->
    <div id="passwordForm" class="form-group">
      <h2>🔑 ورود با رمز عبور</h2>
      <input type="text" id="usernameInput" placeholder="نام کاربری">
      <input type="password" id="passwordInputLogin" placeholder="رمز عبور">
      <button class="btn" onclick="loginWithPassword()">ورود</button>
      <div id="errorPass" class="error"></div>
    </div>
  </div>

  <script>
    let activeTab = 'otp';
    const code = "{{ code }}";
    const otpToken = "{{ otp_token }}";

    let timeLeft = 90;
    let expired = false;
    let checking = false;

    const timerEl = document.getElementById('timerText');
    const statusEl = document.getElementById('statusOtp');

    function updateTimer() {
      if (expired) return;
      timeLeft--;
      if (timeLeft <= 0) {
        expired = true;
        timerEl.textContent = 'زمان به پایان رسید';
        statusEl.innerHTML = '<div class="error">کد منقضی شد. لطفاً توکن جدید دریافت کنید.</div>';
        return;
      }
      const mins = Math.floor(timeLeft / 60);
      const secs = timeLeft % 60;
      timerEl.textContent = `زمان باقی‌مانده: ${mins}:${secs.toString().padStart(2, '0')}`;
    }
    setInterval(updateTimer, 1000);

    async function checkVerification() {
      if (expired || checking) return;
      checking = true;
      statusEl.innerHTML = '<div class="info animate-pulse">در حال بررسی...</div>';
      try {
        const resp = await fetch(`/api/verify_otp?code=${encodeURIComponent(code)}&otp_token=${encodeURIComponent(otpToken)}`);
        const data = await resp.json();
        if (data.success) {
          statusEl.innerHTML = '<div class="success">تأیید شد! در حال انتقال...</div>';
          setTimeout(() => {
            window.location.href = data.new_user ? '/set-username' : '/chat';
          }, 800);
        } else {
          checking = false;
        }
      } catch (err) {
        checking = false;
      }
    }

    checkVerification();
    setInterval(() => {
      if (!expired && !checking) checkVerification();
    }, 2000);

    async function loginWithPassword() {
      const username = document.getElementById('usernameInput').value.trim();
      const password = document.getElementById('passwordInputLogin').value;
      if (!username || !password) {
        document.getElementById('errorPass').textContent = 'لطفاً نام کاربری و رمز عبور را وارد کنید.';
        return;
      }
      try {
        const resp = await fetch('/api/login_password', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ username, password })
        });
        const data = await resp.json();
        if (data.success) {
          window.location.href = '/chat';
        } else {
          document.getElementById('errorPass').textContent = data.error || 'نام کاربری یا رمز عبور اشتباه است.';
        }
      } catch (err) {
        document.getElementById('errorPass').textContent = 'خطای شبکه.';
      }
    }

    function switchTab(tab) {
      activeTab = tab;
      document.getElementById('tabOtp').classList.toggle('active', tab === 'otp');
      document.getElementById('tabPass').classList.toggle('active', tab === 'password');
      document.getElementById('otpForm').classList.toggle('active', tab === 'otp');
      document.getElementById('passwordForm').classList.toggle('active', tab === 'password');
    }
  </script>
</body>
</html>
"""

CHAT_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <title>Chat</title>
  <link href="/static/assets/styles/Vazirmatn-font-face.css" rel="stylesheet">
  <style>
    :root {
      --bg: #17212b;
      --sidebar-bg: #17212b;
      --chat-bg: #0e1621;
      --text-primary: #fff;
      --text-secondary: #aab2bb;
      --border-color: #2a3a4a;
      --hover-bg: #212e3c;
      --bubble-sent: #2b5278;
      --bubble-received: #182533;
      --input-bg: #212e3c;
      --input-border: #2b3a4a;
      --btn-color: #8ea2b8;
      --btn-hover-bg: #2b5278;
      --status-bar-bg: #212e3c;
      --shadow: 0 2px 10px rgba(0,0,0,0.3);
      --transition: 0.3s ease;
    }
    body.light-mode {
      --bg: #f5f5f5;
      --sidebar-bg: #ffffff;
      --chat-bg: #f8f9fa;
      --text-primary: #000;
      --text-secondary: #707579;
      --border-color: #d3d9de;
      --hover-bg: #e8ecef;
      --bubble-sent: #e3ffd8;
      --bubble-received: #ffffff;
      --input-bg: #fff;
      --input-border: #d3d9de;
      --btn-color: #707579;
      --btn-hover-bg: #e8ecef;
      --status-bar-bg: #ffffff;
      --shadow: 0 2px 10px rgba(0,0,0,0.05);
    }
    html, body {
      height: 100%;
      margin: 0;
      padding: 0;
      overflow: hidden;
      font-family: 'Vazirmatn', Tahoma, sans-serif;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: var(--bg);
      display: flex;
      justify-content: center;
      align-items: stretch;
      transition: background var(--transition);
    }
    .app-container {
      width: 100%;
      max-width: 1000px;
      height: 100%;
      display: flex;
      background: var(--sidebar-bg);
      overflow: hidden;
      box-shadow: var(--shadow);
      transition: background var(--transition);
      border-radius: 1.5rem;
    }
    .sidebar {
      width: 320px;
      background: var(--sidebar-bg);
      border-right: 1px solid var(--border-color);
      display: flex;
      flex-direction: column;
      transition: all var(--transition);
    }
    .sidebar-header {
      padding: 1rem;
      border-bottom: 1px solid var(--border-color);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .sidebar-header .title {
      font-size: 1.2rem;
      font-weight: 600;
      color: var(--text-primary);
    }
    .search-box {
      padding: 0.6rem 1rem;
    }
    .search-box input {
      width: 100%;
      padding: 0.6rem 1rem;
      border-radius: 1.5rem;
      border: 1px solid var(--border-color);
      background: var(--input-bg);
      color: var(--text-primary);
      outline: none;
      font-size: 0.9rem;
      transition: background var(--transition);
      font-family: inherit;
    }
    .search-results {
      max-height: 200px;
      overflow-y: auto;
      border-bottom: 1px solid var(--border-color);
      display: none;
    }
    .search-result-item {
      padding: 0.7rem 1rem;
      cursor: pointer;
      color: var(--text-primary);
      border-bottom: 1px solid var(--border-color);
    }
    .search-result-item:hover {
      background: var(--hover-bg);
    }
    .chat-list {
      flex: 1;
      overflow-y: auto;
    }
    .chat-item {
      display: flex;
      align-items: center;
      padding: 0.8rem 1rem;
      cursor: pointer;
      border-bottom: 1px solid var(--border-color);
      transition: background 0.2s;
    }
    .chat-item:hover, .chat-item.active {
      background: var(--hover-bg);
    }
    .chat-item .avatar {
      width: 48px; height: 48px;
      border-radius: 50%;
      background: var(--bubble-sent);
      display: flex; align-items: center; justify-content: center;
      margin-right: 0.8rem;
      color: #fff;
      font-weight: 600;
      font-size: 1.2rem;
    }
    .chat-item .chat-info {
      flex: 1;
    }
    .chat-item .chat-name {
      font-size: 1rem;
      font-weight: 600;
      color: var(--text-primary);
    }
    .chat-item .last-message {
      font-size: 0.8rem;
      color: var(--text-secondary);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .chat-item .chat-time {
      font-size: 0.7rem;
      color: var(--text-secondary);
    }

    .main-chat {
      flex: 1;
      display: flex;
      flex-direction: column;
      background: var(--chat-bg);
      transition: background var(--transition);
      position: relative;
    }
    .chat-header {
      padding: 0.8rem 1rem;
      border-bottom: 1px solid var(--border-color);
      background: var(--status-bar-bg);
      color: var(--text-primary);
      font-weight: 600;
      font-size: 1.1rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      flex-shrink: 0;
    }
    .back-btn {
      display: none;
      background: none;
      border: none;
      color: var(--btn-color);
      font-size: 1.5rem;
      cursor: pointer;
      padding: 0.2rem;
    }
    .back-btn:hover { color: #2b9cff; }

    .messages-container {
      flex: 1;
      padding: 1rem;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }
    .message-row {
      display: flex;
      position: relative;
    }
    .message-row.sent {
      justify-content: flex-end;
    }
    .message-row.received {
      justify-content: flex-start;
    }
    .bubble {
      max-width: 70%;
      padding: 0.6rem 0.9rem;
      border-radius: 1.2rem;
      font-size: 0.95rem;
      color: var(--text-primary);
      position: relative;
      word-wrap: break-word;
      box-shadow: 0 1px 2px rgba(0,0,0,0.1);
      cursor: pointer;
      transition: background 0.15s;
      direction: auto;
      text-align: start;
    }
    .bubble:active {
      background: rgba(255,255,255,0.1);
    }
    .bubble.sent {
      background: var(--bubble-sent);
      border-bottom-right-radius: 0.3rem;
    }
    .bubble.received {
      background: var(--bubble-received);
      border-bottom-left-radius: 0.3rem;
    }
    .bubble.emoji-only {
      background: transparent !important;
      box-shadow: none;
      font-size: 2.5rem;
      padding: 0.2rem;
      line-height: 1.2;
    }
    .bubble .message-time {
      font-size: 0.65rem;
      color: var(--text-secondary);
      float: right;
      margin-left: 0.5rem;
      margin-top: 0.2rem;
      direction: ltr;
      text-align: right;
    }
    .no-chat-message {
      color: var(--text-secondary);
      text-align: center;
      margin-top: 3rem;
      font-size: 1rem;
    }

    .reply-preview {
      background: var(--input-bg);
      border-top: 1px solid var(--border-color);
      padding: 0.5rem 1rem;
      display: none;
      align-items: center;
      gap: 0.5rem;
      color: var(--text-secondary);
      font-size: 0.85rem;
      flex-shrink: 0;
    }
    .reply-preview.active {
      display: flex;
    }
    .reply-preview .reply-text {
      flex: 1;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 60%;
    }
    .reply-preview .cancel-reply {
      color: #ff4d4d;
      cursor: pointer;
      font-weight: bold;
    }

    .reply-quote {
      border-left: 3px solid #2b9cff;
      padding-left: 0.6rem;
      margin-bottom: 0.3rem;
      font-size: 0.85rem;
      color: var(--text-secondary);
      direction: auto;
      text-align: start;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .reply-quote .reply-sender {
      font-weight: 600;
      color: #2b9cff;
      margin-bottom: 0.1rem;
    }

    .input-area {
      padding: 0.8rem 1rem;
      border-top: 1px solid var(--border-color);
      background: var(--input-bg);
      display: flex;
      align-items: flex-end;
      gap: 0.5rem;
      flex-shrink: 0;
    }
    .input-area textarea {
      flex: 1;
      background: transparent;
      border: none;
      outline: none;
      color: var(--text-primary);
      font-size: 16px;
      resize: none;
      padding: 0.4rem 0;
      font-family: inherit;
      max-height: 100px;
      direction: auto;
      white-space: pre-wrap;
      word-break: break-word;
      overflow-wrap: break-word;
    }
    .input-area .send-chat-btn {
      background: none;
      border: none;
      color: #2b9cff;
      font-size: 1.5rem;
      cursor: pointer;
      padding: 0.3rem;
    }
    .input-area .send-chat-btn:disabled {
      opacity: 0.4;
      cursor: default;
    }

    .theme-toggle {
      background: none;
      border: none;
      color: var(--btn-color);
      font-size: 1.2rem;
      cursor: pointer;
      width: 34px; height: 34px;
      display: flex; align-items: center; justify-content: center;
      border-radius: 50%;
    }
    .theme-toggle:hover { background: var(--hover-bg); }

    .error-toast {
        position: fixed;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        background: #ff4d4d;
        color: #fff;
        padding: 0.6rem 1.2rem;
        border-radius: 0.5rem;
        z-index: 999;
        font-size: 0.9rem;
        white-space: nowrap;
    }

    .typing-indicator {
        font-size: 0.8rem;
        color: var(--text-secondary);
        margin: 0.3rem 0;
        font-style: italic;
    }

    .msg-ticks {
        font-size: 0.65rem;
        color: var(--text-secondary);
        margin-left: 4px;
        float: right;
        direction: ltr;
    }
    .msg-ticks.seen {
        color: #4fc3f7;
    }

    @media (max-width: 700px) {
      .app-container {
        border-radius: 0;
      }
      .sidebar {
        width: 100%;
      }
      .main-chat {
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        z-index: 10;
        transform: translateX(100%);
        display: flex;
      }
      .main-chat.active {
        transform: translateX(0);
      }
      .back-btn {
        display: block;
      }
    }
  </style>
</head>
<body>
  <div class="app-container">
    <div class="sidebar" id="sidebar">
      <div class="sidebar-header">
        <span class="title">Chats</span>
        <div style="display:flex;align-items:center;gap:0.3rem;">
          <button id="changeUsernameSidebarBtn" class="theme-toggle" style="font-size:1rem;" title="Change Username">✏️</button>
          <button id="changePasswordSidebarBtn" class="theme-toggle" style="font-size:1rem;" title="Change Password">🔑</button>
          <button class="theme-toggle" onclick="toggleTheme()">◑</button>
        </div>
      </div>
      <div class="search-box">
        <input type="text" id="searchUserInput" placeholder="Search user..." oninput="searchUsers()">
      </div>
      <div class="search-results" id="searchResults"></div>
      <div class="chat-list" id="chatList"></div>
    </div>

    <div class="main-chat" id="mainChat">
      <div class="chat-header">
        <button class="back-btn" onclick="backToChats()">←</button>
        <span id="chatHeader"></span>
      </div>
      <div class="reply-preview" id="replyPreview">
        <span class="reply-text" id="replyText"></span>
        <span class="cancel-reply" onclick="cancelReply()">✕</span>
      </div>
      <div class="messages-container" id="messagesContainer">
        <div class="no-chat-message">Select a chat to start messaging</div>
      </div>
      <div class="input-area" id="inputArea" style="display:none;">
        <textarea id="chatInput" placeholder="Message..." dir="auto" rows="1" oninput="autoResize(this)"></textarea>
        <button class="send-chat-btn" id="sendChatBtn" onclick="sendChatMessage()">➤</button>
      </div>
    </div>
  </div>

  <div id="usernameModal" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;
    background:rgba(0,0,0,0.6);z-index:200;justify-content:center;align-items:center;">
    <div style="background:var(--chat-bg);padding:2rem;border-radius:1.5rem;max-width:320px;width:100%;text-align:center;
      border:1px solid var(--border-color);">
      <h3 style="color:var(--text-primary);margin-bottom:1rem;">Change Username</h3>
      <input type="text" id="newUsernameInput" placeholder="New username"
        style="width:100%;padding:0.6rem;background:var(--input-bg);border:1px solid var(--border-color);
        border-radius:0.8rem;color:var(--text-primary);margin-bottom:1rem;font-size:16px;">
      <div>
        <button id="saveUsernameBtn" style="background:#2b5278;color:#fff;border:none;padding:0.5rem 1.5rem;
          border-radius:0.8rem;cursor:pointer;font-size:0.9rem;">Save</button>
        <button id="cancelUsernameBtn" style="background:transparent;color:var(--btn-color);
          border:1px solid var(--border-color);padding:0.5rem 1.5rem;border-radius:0.8rem;cursor:pointer;
          margin-left:0.5rem;font-size:0.9rem;">Cancel</button>
      </div>
      <div id="usernameMsg" style="margin-top:1rem;font-size:0.9rem;"></div>
    </div>
  </div>
  <script src="/static/socket.io.min.js"></script>
  <script>
    const body = document.body;
    function toggleTheme() {
      body.classList.toggle('light-mode');
      localStorage.setItem('theme', body.classList.contains('light-mode') ? 'light' : 'dark');
    }
    (localStorage.getItem('theme') === 'light') ? body.classList.add('light-mode') : body.classList.remove('light-mode');

    function escapeHtml(unsafe) {
        if (!unsafe) return '';
        return String(unsafe)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    const socket = io();
    let activeChatId = null;
    let oldestMessageId = null;
    let isLoadingMore = false;
    const MESSAGE_LIMIT = 50;
    let currentUsername = null;
    let currentUserId = null;
    let otherUserId = null;
    let replyToMessage = null;
    let typingTimeout;
    let typingIndicator = document.getElementById('typingIndicator');

    socket.on('user_typing', (data) => {
        if (!typingIndicator) {
            typingIndicator = document.createElement('div');
            typingIndicator.id = 'typingIndicator';
            typingIndicator.className = 'typing-indicator';
            typingIndicator.textContent = data.user + ' is typing...';
            document.getElementById('messagesContainer').appendChild(typingIndicator);
        }
    });

    socket.on('user_stop_typing', () => {
        if (typingIndicator) {
            typingIndicator.remove();
            typingIndicator = null;
        }
    });

    document.getElementById('chatInput').addEventListener('input', function() {
        socket.emit('typing', { chat_id: activeChatId });
        clearTimeout(typingTimeout);
        typingTimeout = setTimeout(() => {
            socket.emit('stop_typing', { chat_id: activeChatId });
        }, 1000);
    });

    socket.on('connect', () => {
      socket.emit('join_chat');
    });

    socket.on('new_message', (msg) => {
      const chatId = Number(msg.chat_id);
      if (activeChatId === chatId) {
        appendMessage(msg, msg.sender_username === currentUsername);
        socket.emit('seen', { chat_id: chatId });
      }
      loadChats();
    });

    socket.on('new_message_notification', () => {
      loadChats();
    });

    socket.on('error', (data) => {
        showToast('⚠️ ' + (data.msg || 'An error occurred'));
    });

    socket.on('message_seen', (data) => {
        if (data.chat_id === activeChatId) {
            document.querySelectorAll('.message-row.sent .msg-ticks').forEach(tick => {
                tick.textContent = '✓✓';
                tick.classList.add('seen');
            });
        }
    });

    function showToast(message) {
        const toast = document.createElement('div');
        toast.className = 'error-toast';
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }

    fetch('/api/whoami').then(r => r.json()).then(d => {
        currentUserId = d.user_id;
        currentUsername = d.username;
    });

    function isEmojiOnly(text) {
      if (!text) return false;
      const segmenter = new Intl.Segmenter('en', { granularity: 'grapheme' });
      const graphemes = [...segmenter.segment(text)].map(s => s.segment);
      const emojiRegex = /\p{Emoji}/u;
      const allEmoji = graphemes.every(g => emojiRegex.test(g));
      return allEmoji && graphemes.length >= 1 && graphemes.length <= 3;
    }

    function searchUsers() {
      const q = document.getElementById('searchUserInput').value.trim();
      const resultsDiv = document.getElementById('searchResults');
      if (!q) { resultsDiv.style.display = 'none'; return; }
      fetch(`/api/search_users?q=${encodeURIComponent(q)}`)
        .then(r => r.json())
        .then(users => {
          resultsDiv.innerHTML = '';
          users.forEach(u => {
              const div = document.createElement('div');
              div.className = 'search-result-item';
              div.textContent = u.username;
              div.onclick = () => startChat(u.id);
              resultsDiv.appendChild(div);
          });
          resultsDiv.style.display = users.length ? 'block' : 'none';
        });
    }

    function startChat(userId) {
      fetch('/api/start_chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId })
      })
      .then(r => r.json())
      .then(data => {
        if (data.chat_id) {
          openChat(data.chat_id);
          document.getElementById('searchResults').style.display = 'none';
          document.getElementById('searchUserInput').value = '';
        }
      });
    }

    function loadChats() {
      fetch('/api/chats')
        .then(r => r.json())
        .then(chats => {
          const chatList = document.getElementById('chatList');
          chatList.innerHTML = '';
          chats.forEach(c => {
              const item = document.createElement('div');
              item.className = 'chat-item' + (activeChatId === c.id ? ' active' : '');
              item.onclick = () => openChat(c.id);

              const avatar = document.createElement('div');
              avatar.className = 'avatar';
              avatar.textContent = c.other_username[0].toUpperCase();
              item.appendChild(avatar);

              const infoDiv = document.createElement('div');
              infoDiv.className = 'chat-info';

              const nameDiv = document.createElement('div');
              nameDiv.className = 'chat-name';
              nameDiv.textContent = c.other_username;
              infoDiv.appendChild(nameDiv);

              const lastMsg = document.createElement('div');
              lastMsg.className = 'last-message';
              lastMsg.textContent = c.last_message || '';
              infoDiv.appendChild(lastMsg);

              item.appendChild(infoDiv);

              const timeDiv = document.createElement('div');
              timeDiv.className = 'chat-time';
              timeDiv.textContent = c.last_time
                  ? new Date(c.last_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                  : '';
              item.appendChild(timeDiv);

              chatList.appendChild(item);
          });
        });
    }

    function openChat(chatId) {
        activeChatId = chatId;
        socket.emit('join_chat_room', { chat_id: chatId });
        cancelReply();

        const mainChat = document.getElementById('mainChat');
        mainChat.classList.add('active');
        document.getElementById('inputArea').style.display = 'flex';
        const msgContainer = document.getElementById('messagesContainer');
        msgContainer.innerHTML = '';
        oldestMessageId = null;

        fetch('/api/chats').then(r => r.json()).then(chats => {
            const chat = chats.find(c => c.id == chatId);
            if (chat) {
                document.getElementById('chatHeader').textContent = chat.other_username;
                otherUserId = chat.other_user_id;
            }

            fetch(`/api/messages/${chatId}?limit=${MESSAGE_LIMIT}`)
                .then(r => r.json())
                .then(messages => {
                    if (messages.length > 0) {
                        oldestMessageId = messages[0].id;
                    }
                    messages.forEach(msg => appendMessage(msg, msg.sender_username === currentUsername));
                    msgContainer.scrollTop = msgContainer.scrollHeight;
                });
        });

        socket.emit('seen', { chat_id: chatId });

        if (window.innerWidth < 700) {
            document.getElementById('sidebar').classList.add('hidden');
        }
    }

    function createMessageElement(msg, isSent) {
        const row = document.createElement('div');
        row.className = 'message-row ' + (isSent ? 'sent' : 'received');

        const bubble = document.createElement('div');
        bubble.className = 'bubble ' + (isSent ? 'sent' : 'received');
        bubble.setAttribute('dir', 'auto');

        if (isEmojiOnly(msg.text)) {
            bubble.classList.add('emoji-only');
            bubble.textContent = msg.text;
            row.appendChild(bubble);
            return row;
        }

        if (msg.reply_to) {
            const quoteDiv = document.createElement('div');
            quoteDiv.className = 'reply-quote';
            quoteDiv.setAttribute('dir', 'auto');

            const senderSpan = document.createElement('div');
            senderSpan.className = 'reply-sender';
            senderSpan.textContent = msg.reply_to.sender_username;
            quoteDiv.appendChild(senderSpan);

            const previewSpan = document.createElement('div');
            const previewText = msg.reply_to.text.length > 60 ? msg.reply_to.text.substring(0, 60) + '...' : msg.reply_to.text;
            previewSpan.textContent = previewText;
            quoteDiv.appendChild(previewSpan);

            bubble.appendChild(quoteDiv);
        }

        const textNode = document.createTextNode(msg.text || '');
        bubble.appendChild(textNode);

        const time = document.createElement('span');
        time.className = 'message-time';
        time.textContent = new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        bubble.appendChild(time);

        bubble.addEventListener('click', () => {
            replyToMessage = msg;
            const previewText = msg.text.length > 40 ? msg.text.substring(0, 40) + '...' : msg.text;
            document.getElementById('replyText').textContent = '↩ ' + previewText;
            document.getElementById('replyPreview').classList.add('active');
            document.getElementById('chatInput').focus();
        });

        if (isSent) {
            const ticks = document.createElement('span');
            ticks.className = 'msg-ticks';
            const seenBy = msg.seen_by || [];
            const seen = seenBy.includes(otherUserId);
            ticks.textContent = seen ? '✓✓' : '✓';
            if (seen) ticks.classList.add('seen');
            bubble.appendChild(ticks);
        }

        row.appendChild(bubble);
        return row;
    }

    function appendMessage(msg, isSent) {
        const container = document.getElementById('messagesContainer');
        const row = createMessageElement(msg, isSent);
        container.appendChild(row);
        container.scrollTop = container.scrollHeight;
    }

    function cancelReply() {
      replyToMessage = null;
      document.getElementById('replyPreview').classList.remove('active');
    }

    function sendChatMessage() {
      const input = document.getElementById('chatInput');
      const text = input.value.trim();
      if (!text && !replyToMessage) return;
      if (!activeChatId) return;

      const payload = { chat_id: activeChatId, text: text };
      if (replyToMessage) {
        payload.reply_to_message_id = replyToMessage.id;
        cancelReply();
      }

      socket.emit('send_chat_message', payload);
      input.value = '';
      autoResize(input);
    }

    function autoResize(textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = Math.min(textarea.scrollHeight, 100) + 'px';
    }

    function backToChats() {
      document.getElementById('mainChat').classList.remove('active');
      document.getElementById('sidebar').classList.remove('hidden');
      activeChatId = null;
      cancelReply();
    }

    loadChats();
    window.addEventListener('load', () => {
      document.getElementById('searchUserInput').focus();
    });
    const usernameModal = document.getElementById('usernameModal');
    const newUsernameInput = document.getElementById('newUsernameInput');
    const saveUsernameBtn = document.getElementById('saveUsernameBtn');
    const cancelUsernameBtn = document.getElementById('cancelUsernameBtn');
    const usernameMsg = document.getElementById('usernameMsg');

    const changeUsernameSidebarBtn = document.getElementById('changeUsernameSidebarBtn');
    if (changeUsernameSidebarBtn) {
      changeUsernameSidebarBtn.addEventListener('click', () => {
        usernameModal.style.display = 'flex';
        newUsernameInput.value = currentUsername || '';
        newUsernameInput.focus();
      });
    }

    const changePasswordSidebarBtn = document.getElementById('changePasswordSidebarBtn');
    if (changePasswordSidebarBtn) {
    changePasswordSidebarBtn.addEventListener('click', () => {
        window.location.href = '/set-password';
    });
    }

    cancelUsernameBtn.addEventListener('click', () => {
      usernameModal.style.display = 'none';
      newUsernameInput.value = '';
      usernameMsg.textContent = '';
    });

    saveUsernameBtn.addEventListener('click', async () => {
      const newName = newUsernameInput.value.trim();
      if (!newName) {
        usernameMsg.textContent = 'Username cannot be empty.';
        usernameMsg.style.color = '#ff4d4d';
        return;
      }

      try {
        const resp = await fetch('/api/change_username', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: newName })
        });
        const data = await resp.json();
        if (data.success) {
          currentUsername = newName;
          usernameMsg.textContent = 'Username updated successfully!';
          usernameMsg.style.color = '#34d399';
          setTimeout(() => {
            usernameModal.style.display = 'none';
          }, 1000);
          loadChats();
        } else {
          usernameMsg.textContent = data.error || 'Failed to update.';
          usernameMsg.style.color = '#ff4d4d';
        }
      } catch (err) {
        usernameMsg.textContent = 'Network error.';
        usernameMsg.style.color = '#ff4d4d';
      }
    });
    const messagesContainerEl = document.getElementById('messagesContainer');
    messagesContainerEl.addEventListener('scroll', function() {
        if (isLoadingMore) return;
        if (messagesContainerEl.scrollTop < 30 && oldestMessageId && activeChatId) {
            isLoadingMore = true;

            const prevScrollHeight = messagesContainerEl.scrollHeight;
            const prevScrollTop = messagesContainerEl.scrollTop;

            fetch(`/api/messages/${activeChatId}?limit=${MESSAGE_LIMIT}&before_id=${oldestMessageId}`)
                .then(r => r.json())
                .then(olderMessages => {
                    if (!olderMessages.length) {
                        oldestMessageId = null;
                        return;
                    }

                    const fragment = document.createDocumentFragment();
                    olderMessages.forEach(msg => {
                        const isSent = msg.sender_username === currentUsername;
                        fragment.appendChild(createMessageElement(msg, isSent));
                    });

                    messagesContainerEl.insertBefore(fragment, messagesContainerEl.firstChild);
                    oldestMessageId = olderMessages[0].id;

                    const newScrollHeight = messagesContainerEl.scrollHeight;
                    messagesContainerEl.scrollTop = newScrollHeight - prevScrollHeight + prevScrollTop;
                })
                .catch(err => console.error('Error loading older messages:', err))
                .finally(() => {
                    isLoadingMore = false;
                });
        }
    });
  </script>
</body>
</html>
"""

SET_USERNAME_HTML = r"""
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>انتخاب نام کاربری</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Vazirmatn', Tahoma, sans-serif;
      background: #17212b;
      color: #fff;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
      padding: 1rem;
    }
    .card {
      background: #0e1621;
      padding: 2rem;
      border-radius: 1.5rem;
      text-align: center;
      max-width: 400px;
      width: 100%;
      box-shadow: 0 10px 30px rgba(0,0,0,0.5);
    }
    h2 { margin-bottom: 1rem; }
    input {
      width: 100%;
      padding: 0.8rem;
      font-size: 1rem;
      background: #212e3c;
      border: 1px solid #2b3a4a;
      border-radius: 0.8rem;
      color: #fff;
      margin: 1rem 0;
      outline: none;
      font-family: inherit;
    }
    .btn {
      background: #2b5278;
      color: #fff;
      border: none;
      padding: 0.8rem 2rem;
      border-radius: 0.8rem;
      font-size: 1rem;
      cursor: pointer;
      transition: background 0.2s;
      margin-top: 1rem;
    }
    .btn:hover { background: #3a6a99; }
    .error { color: #ff4d4d; margin-top: 1rem; font-size: 0.9rem; }
  </style>
</head>
<body>
  <div class="card">
    <h2>👤 نام کاربری خود را انتخاب کنید</h2>
    <p style="color: #aab2bb; font-size: 0.9rem;">این نام برای دوستان شما قابل جستجو خواهد بود.</p>
    <input type="text" id="usernameInput" placeholder="مثلاً amirrrr" maxlength="50">
    <button class="btn" onclick="submitUsername()">ذخیره و ادامه</button>
    <div id="errorMsg" class="error"></div>
  </div>

  <script>
    async function submitUsername() {
      const username = document.getElementById('usernameInput').value.trim();
      if (!username) {
        document.getElementById('errorMsg').textContent = 'نام کاربری نمی‌تواند خالی باشد.';
        return;
      }
      try {
        const resp = await fetch('/api/set_username', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username })
        });
        const data = await resp.json();
        if (data.success) {
          window.location.href = '/set-password';
        } else {
          document.getElementById('errorMsg').textContent = data.error || 'خطا در ثبت نام کاربری.';
        }
      } catch (err) {
        document.getElementById('errorMsg').textContent = 'خطای شبکه.';
      }
    }
  </script>
</body>
</html>
"""

SET_PASSWORD_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Set Password</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Vazirmatn', Tahoma, sans-serif;
      background: #17212b;
      color: #fff;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
      padding: 1rem;
    }
    .card {
      background: #0e1621;
      padding: 2rem;
      border-radius: 1.5rem;
      text-align: center;
      max-width: 400px;
      width: 100%;
      box-shadow: 0 10px 30px rgba(0,0,0,0.5);
    }
    h2 { margin-bottom: 0.5rem; }
    p { color: #aab2bb; font-size: 0.9rem; margin-bottom: 1.5rem; }
    input {
      width: 100%;
      padding: 0.8rem;
      font-size: 1rem;
      background: #212e3c;
      border: 1px solid #2b3a4a;
      border-radius: 0.8rem;
      color: #fff;
      margin: 0.5rem 0;
      outline: none;
      font-family: inherit;
    }
    .btn {
      background: #2b5278;
      color: #fff;
      border: none;
      padding: 0.8rem 2rem;
      border-radius: 0.8rem;
      font-size: 1rem;
      cursor: pointer;
      transition: background 0.2s;
      margin-top: 1rem;
      width: 100%;
    }
    .btn:hover { background: #3a6a99; }
    .btn-skip {
      background: transparent;
      color: #8ea2b8;
      border: 1px solid #2b3a4a;
      margin-top: 0.5rem;
    }
    .error { color: #ff4d4d; margin-top: 1rem; font-size: 0.9rem; }
    .success { color: #34d399; margin-top: 1rem; font-size: 0.9rem; }
  </style>
</head>
<body>
  <div class="card">
    <h2>🔒 تنظیم رمز عبور</h2>
    <p>می‌توانید برای ورود سریع‌تر رمز عبور تنظیم کنید (اختیاری)</p>
    <input type="password" id="passwordInput" placeholder="رمز عبور (حداقل ۶ کاراکتر)">
    <input type="password" id="confirmPasswordInput" placeholder="تکرار رمز عبور">
    <button class="btn" onclick="submitPassword()">ذخیره و ادامه</button>
    <button class="btn btn-skip" onclick="skipPassword()">بعداً تنظیم می‌کنم</button>
    <div id="msg" class="error"></div>
  </div>

  <script>
    async function submitPassword() {
      const pwd = document.getElementById('passwordInput').value;
      const confirm = document.getElementById('confirmPasswordInput').value;
      if (pwd.length < 6) {
        document.getElementById('msg').textContent = 'رمز عبور باید حداقل ۶ کاراکتر باشد.';
        document.getElementById('msg').className = 'error';
        return;
      }
      if (pwd !== confirm) {
        document.getElementById('msg').textContent = 'رمز عبور و تکرار آن مطابقت ندارند.';
        document.getElementById('msg').className = 'error';
        return;
      }
      try {
        const resp = await fetch('/api/set_password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ password: pwd })
        });
        const data = await resp.json();
        if (data.success) {
          window.location.href = '/chat';
        } else {
          document.getElementById('msg').textContent = data.error || 'خطا در ذخیره رمز.';
          document.getElementById('msg').className = 'error';
        }
      } catch (err) {
        document.getElementById('msg').textContent = 'خطای شبکه.';
        document.getElementById('msg').className = 'error';
      }
    }

    function skipPassword() {
      window.location.href = '/chat';
    }
  </script>
</body>
</html>
"""

dous_rooms = {}


def generate_room_code():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


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
                msg["created_at"] = msg["created_at"].isoformat()
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
    room_data["players"].append(request.sid)
    room_data["symbols"]["O"] = request.sid
    room_data["scores"]["wins"][request.sid] = 0
    room_data["replay_votes"].clear()
    join_room(room)
    emit("room_joined", {"room": room})

    my_scores = {"my_wins": 0, "opponent_wins": 0, "draws": 0}
    opp_scores = dict(my_scores)
    emit(
        "game_start",
        {"symbol": "O", "board": room_data["board"], "scores": my_scores},
        to=request.sid,
    )
    emit(
        "game_start",
        {"symbol": "X", "board": room_data["board"], "scores": opp_scores},
        to=room_data["players"][0],
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


@socketio.on("join_chat")
def handle_join_chat(data=None):
    user_id = session.get("user_id")
    if user_id:
        join_room(f"user_{user_id}")


@socketio.on("open_chat")
def handle_open_chat(data):
    chat_id = data.get("chat_id")
    if chat_id:
        join_room(f"chat_{chat_id}")


@socketio.on("join_chat_room")
def handle_join_chat_room(data):
    chat_id = data.get("chat_id")
    if chat_id:
        join_room(f"chat_{chat_id}")


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


def rubika_get_updates(token, max_pages=5):
    url = f"https://botapi.rubika.ir/v3/{token}/getUpdates"
    offset_id = None
    all_updates = []

    for _ in range(max_pages):
        payload = {"limit": "100"}
        if offset_id:
            payload["offset_id"] = offset_id

        try:
            resp = requests.post(url, json=payload, timeout=10)
            if not resp.ok:
                break
            data = resp.json()
            if data.get("status") != "OK":
                break

            updates = data.get("data", {}).get("updates", [])
            if not updates:
                break
            all_updates.extend(updates)

            next_offset = data.get("data", {}).get("next_offset_id")
            if next_offset:
                offset_id = next_offset
            else:
                break
        except:
            break

    return {"status": "OK", "data": {"updates": all_updates}} if all_updates else None


def rubika_get_chat(token, chat_id):
    url = f"https://botapi.rubika.ir/v3/{token}/getChat"
    try:
        resp = requests.post(url, json={"chat_id": chat_id}, timeout=10)
        if resp.ok:
            return resp.json()
    except:
        pass
    return None


@app.route("/")
def index():
    return render_template_string(MAIN_HTML)


@app.route("/douz/")
def douz_page():
    return render_template_string(DOUZ_HTML)


@app.route("/whisper/")
def whisper_home():
    return render_template_string(WHISPER_HTML)


@app.route("/whisper/settings", methods=["GET", "POST"])
def whisper_settings():
    if request.method == "GET":
        key = request.args.get("key", "")
        if key != SECRET_KEY:
            return "Access denied. Add ?key=YOUR_SECRET_KEY to the URL.", 403
        config = load_whisper_config()
        return render_template_string(
            WHISPER_SETTINGS_HTML,
            token=config.get("token", ""),
            chat_id=config.get("chat_id", ""),
        )
    if request.method == "POST":
        data = request.get_json()
        if not data or data.get("key") != SECRET_KEY:
            return jsonify({"success": False, "error": "Invalid security key."}), 403
        token = data.get("token", "").strip()
        chat_id = data.get("chat_id", "").strip()
        if not token or not chat_id:
            return jsonify(
                {"success": False, "error": "Both fields are required."}
            ), 400
        save_whisper_config(token, chat_id)
        return jsonify({"success": True})


@app.route("/whisper/send", methods=["POST"])
def whisper_send():
    config = load_whisper_config()
    token = config.get("token")
    chat_id = config.get("chat_id")
    if not token or not chat_id:
        return jsonify({"success": False, "error": "Bot not configured."}), 500
    data = request.get_json()
    if not data or "text" not in data:
        return jsonify({"success": False, "error": "No text provided"}), 400
    text = data["text"].strip()
    if not text:
        return jsonify({"success": False, "error": "Empty message"}), 400
    raw_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    ip = raw_ip.split(",")[0].strip() if raw_ip else "Unknown"
    user_agent = request.headers.get("User-Agent", "Unknown")
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    full_text = (
        f"📩 New message:\n{text}\n\n"
        f"──────────────────\n"
        f"🕵️ Sender info:\n"
        f"IP: {ip}\n"
        f"Device: {user_agent}\n"
        f"Time: {timestamp}"
    )
    api_url = f"https://botapi.rubika.ir/v3/{token}/sendMessage"
    try:
        resp = requests.post(
            api_url,
            json={"chat_id": chat_id, "text": full_text},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if resp.ok:
            return jsonify({"success": True})
        else:
            return jsonify(
                {"success": False, "error": f"API error: {resp.text}"}
            ), resp.status_code
    except requests.exceptions.RequestException as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/whisper/send_file", methods=["POST"])
def whisper_send_file():
    config = load_whisper_config()
    token = config.get("token")
    chat_id = config.get("chat_id")
    if not token or not chat_id:
        return jsonify({"success": False, "error": "Bot not configured."}), 500

    file = request.files.get("file")
    if not file:
        return jsonify({"success": False, "error": "No file provided."}), 400

    caption = request.form.get("text", "").strip()
    mime = file.mimetype.lower() if file.mimetype else ""

    if mime.startswith("image/"):
        rubika_type = "Image"
    elif mime.startswith("audio/") or mime.startswith("video/webm"):
        rubika_type = "File"
    else:
        rubika_type = "File"

    try:
        resp = requests.post(
            f"https://botapi.rubika.ir/v3/{token}/requestSendFile",
            json={"type": rubika_type},
            timeout=10,
        )
        if not resp.ok:
            return jsonify(
                {"success": False, "error": f"API error ({resp.status_code})"}
            ), 500

        resp_data = resp.json()
        upload_url = resp_data.get("data", {}).get("upload_url")
        if not upload_url:
            app.logger.error(f"No upload_url: {resp.text}")
            return jsonify({"success": False, "error": "No upload_url"}), 500

        files = {"file": (file.filename, file.stream, file.mimetype)}
        upload_resp = requests.post(upload_url, files=files, timeout=30)
        if not upload_resp.ok:
            app.logger.error(f"Upload failed: {upload_resp.text}")
            return jsonify({"success": False, "error": "Upload failed"}), 500

        upload_json = upload_resp.json()
        file_id = upload_json.get("data", {}).get("file_id")
        if not file_id:
            app.logger.error(f"No file_id after upload: {upload_resp.text}")
            return jsonify({"success": False, "error": "No file_id"}), 500

        send_data = {"chat_id": chat_id, "file_id": file_id}
        if caption:
            send_data["text"] = caption

        send_resp = requests.post(
            f"https://botapi.rubika.ir/v3/{token}/sendFile", json=send_data, timeout=10
        )
        if send_resp.ok:
            return jsonify({"success": True})
        else:
            app.logger.error(f"sendFile failed: {send_resp.text}")
            return jsonify({"success": False, "error": "sendFile failed"}), 500

    except Exception as e:
        app.logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/chat")
def chat_page():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template_string(CHAT_HTML)


@app.route("/api/search_users")
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


@app.route("/api/start_chat", methods=["POST"])
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


@app.route("/api/chats")
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
                        c["last_time"] = c["last_time"].isoformat()
    except RuntimeError:
        return jsonify({"error": "Database service unavailable"}), 503

    return jsonify(chats)


@app.route("/api/messages/<int:chat_id>")
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
        msg_dict = {
            "id": m["id"],
            "sender_id": m["sender_id"],
            "text": m["text"],
            "created_at": m["created_at"].isoformat(),
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


@app.route("/api/whoami")
def whoami():
    return jsonify(
        {
            "user_id": session.get("user_id"),
            "username": session.get("username", "unknown"),
        }
    )


@app.route("/login", methods=["GET"])
def login():
    if "user_id" in session:
        return redirect(url_for("chat_page"))

    code = "".join(
        secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8)
    )
    otp_token = secrets.token_hex(32)
    now_unix = int(datetime.utcnow().timestamp())
    expires_unix = now_unix + 90

    try:
        with database() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO otps (code, session_token, created_at_unix, expires_at_unix) VALUES (%s, %s, %s, %s)",
                    (code, otp_token, now_unix, expires_unix),
                )
    except RuntimeError:
        return jsonify({"error": "Database service unavailable"}), 503

    return render_template_string(LOGIN_HTML, code=code, otp_token=otp_token)


@app.route("/api/set_username", methods=["POST"])
def set_username():
    if "temp_rubika_chat_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    username = data.get("username", "").strip()
    if not username:
        return jsonify({"error": "Username cannot be empty."}), 400
    if not re.match(r"^[a-zA-Z0-9_]{3,20}$", username):
        return jsonify(
            {
                "error": "Username must be 3-20 characters, letters, numbers or underscore."
            }
        ), 400

    try:
        with database() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "INSERT INTO users (username, rubika_chat_id) VALUES (%s, %s) RETURNING id",
                    (username, session["temp_rubika_chat_id"]),
                )
                user = cur.fetchone()
            session.pop("temp_rubika_chat_id", None)
            session["user_id"] = user["id"]
            session["username"] = username
            return jsonify({"success": True})
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "Username already taken"}), 409
    except RuntimeError:
        return jsonify({"error": "Database service unavailable"}), 503


@app.route("/api/verify_otp")
def verify_otp():
    code = request.args.get("code", "").strip()
    otp_token = request.args.get("otp_token", "").strip()
    if not code or not otp_token:
        return jsonify({"success": False, "error": "پارامترها ناقص هستند."})
    try:
        with database() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM otps WHERE session_token = %s AND used = FALSE AND expires_at_unix > %s",
                    (otp_token, int(datetime.utcnow().timestamp())),
                )
                otp_record = cur.fetchone()
                if not otp_record:
                    return jsonify({"success": False, "error": "کد منقضی یا نامعتبر."})

                token = VERIFY_BOT_TOKEN
                if not token:
                    return jsonify(
                        {"success": False, "error": "ربات تأیید هویت تنظیم نشده است."}
                    )

                updates_data = rubika_get_updates(token, max_pages=2)
                if not updates_data or updates_data.get("status") != "OK":
                    return jsonify(
                        {"success": False, "error": "خطا در دریافت پیام‌های ربات."}
                    )

                updates = updates_data.get("data", {}).get("updates", [])
                verified_chat_id = None
                for update in updates:
                    if update.get("type") == "NewMessage":
                        new_msg = update.get("new_message", {})
                        if new_msg.get("text") == code and new_msg.get("time"):
                            msg_time = int(new_msg["time"])
                            otp_created = int(otp_record["created_at_unix"])
                            if msg_time >= otp_created:
                                verified_chat_id = update.get("chat_id")
                                break

                if not verified_chat_id:
                    return jsonify(
                        {"success": False, "error": "هنوز پیامی با این کد دریافت نشده."}
                    )

                cur.execute(
                    "UPDATE otps SET used = TRUE, rubika_chat_id = %s WHERE id = %s",
                    (verified_chat_id, otp_record["id"]),
                )

                chat_data = rubika_get_chat(token, verified_chat_id)
                if not chat_data or chat_data.get("status") != "OK":
                    return jsonify(
                        {"success": False, "error": "خطا در دریافت اطلاعات کاربر."}
                    )

                user_info = chat_data["data"]["chat"]
                rubika_first_name = (
                    user_info.get("first_name", "")
                    or user_info.get("username", "")
                    or "کاربر"
                )

                cur.execute(
                    "SELECT id, username FROM users WHERE rubika_chat_id = %s",
                    (verified_chat_id,),
                )
                existing_user = cur.fetchone()

                if existing_user:
                    user_id = existing_user["id"]
                    display_name = existing_user["username"] or rubika_first_name
                    session["user_id"] = user_id
                    session["username"] = display_name
                    return jsonify({"success": True, "new_user": False})
                else:
                    session["temp_rubika_chat_id"] = verified_chat_id
                    return jsonify({"success": True, "new_user": True})
    except RuntimeError:
        return jsonify({"error": "Database service unavailable"}), 503


@app.route("/api/change_username", methods=["POST"])
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


@app.route("/set-username")
def set_username_page():
    if "temp_rubika_chat_id" not in session:
        return redirect(url_for("login"))
    return render_template_string(SET_USERNAME_HTML)


@app.route("/api/set_password", methods=["POST"])
def set_password():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json()
    password = data.get("password", "")
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    password_hash = generate_password_hash(password)
    try:
        with database() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET password_hash = %s WHERE id = %s",
                    (password_hash, session["user_id"]),
                )
        return jsonify({"success": True})
    except RuntimeError:
        return jsonify({"error": "Database unavailable"}), 503


@app.route("/api/login_password", methods=["POST"])
def login_password():
    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "")

    try:
        with database() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, username, password_hash FROM users WHERE username = %s",
                    (username,),
                )
                user = cur.fetchone()
                if user and user["password_hash"]:
                    if check_password_hash(user["password_hash"], password):
                        session["user_id"] = user["id"]
                        session["username"] = user["username"]
                        return jsonify({"success": True})

                return jsonify(
                    {"success": False, "error": "Invalid username or password"}
                ), 401
    except RuntimeError:
        return jsonify({"error": "Database unavailable"}), 503


@app.route("/set-password")
def set_password_page():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template_string(SET_PASSWORD_HTML)


# if __name__ == "__main__":
#     socketio.run(
#         app,
#         host="127.0.0.1",
#         port=int(os.environ.get("PORT", 5000)),
#         debug=False,
#         allow_unsafe_werkzeug=True,
#     )
