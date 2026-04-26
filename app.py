import os
import json
import string
import random
import requests
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["SECRET_KEY"] = "amirrrr-secret-douz"

socketio = SocketIO(
    app,
    async_mode="threading",
    cors_allowed_origins=[
        "https://vafaei.runflare.run",
        "http://vafaei.runflare.run",
        "http://127.0.0.1:5000",
        "http://localhost:5000",
    ],
)

WHISPER_CONFIG_FILE = "whisper_config.json"
SECRET_KEY = "kavan2026"


def load_whisper_config():
    if os.path.exists(WHISPER_CONFIG_FILE):
        try:
            with open(WHISPER_CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            pass
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
        <a href="/whisper/">Anonymous Message</a>
        <a href="/douz/">Tic-Tac-Toe (Dous)</a>
        <a href="https://encrypt-vafaei.runflare.run/">Encrypt Text</a>
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
      --toggle-color: #999;
      --input-bg: rgba(255,255,255,0.03);
      --input-border: rgba(255,255,255,0.08);
      --button-bg: rgba(255,255,255,0.03);
      --button-border: rgba(255,255,255,0.1);
      --button-text: #aaa;
      --status-default: #666;
      --particle-color: rgba(255, 255, 255, 0.1);
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
      --toggle-color: #333;
      --input-bg: rgba(0,0,0,0.03);
      --input-border: rgba(0,0,0,0.08);
      --button-bg: rgba(0,0,0,0.03);
      --button-border: rgba(0,0,0,0.1);
      --button-text: #333;
      --status-default: #888;
      --particle-color: rgba(0, 0, 0, 0.1);
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Segoe UI', system-ui, -apple-system, BlinkMacSystemFont, Roboto, 'Helvetica Neue', sans-serif;
      background: var(--bg);
      min-height: 100vh; display: flex; align-items: center; justify-content: center;
      padding: 1.5rem; overflow: hidden; position: relative;
      transition: background 0.4s;
    }
    #particles { position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: 0; pointer-events: none; }
    .card {
      position: relative; z-index: 1;
      background: var(--card-bg); backdrop-filter: blur(15px); -webkit-backdrop-filter: blur(15px);
      border: 1px solid var(--border); border-radius: 0;
      padding: 3rem 2.5rem; max-width: 420px; width: 100%; text-align: center;
      transition: background 0.4s, border-color 0.4s;
    }
    .theme-toggle {
      position: absolute; top: 1rem; left: 1rem;
      background: none; border: 1px solid transparent;
      color: var(--toggle-color); font-size: 1.2rem; cursor: pointer;
      width: 36px; height: 36px; display: flex; align-items: center; justify-content: center;
      border-radius: 50%; transition: all 0.3s;
    }
    .theme-toggle:hover { border-color: var(--border); background: var(--link-hover-bg); }
    .rule { width: 40px; height: 1px; background: var(--rule-color); margin: 0 auto 2rem; transition: background 0.4s; }
    h1 {
      font-family: 'Georgia', 'Times New Roman', serif; font-size: 2rem; font-weight: 400;
      color: var(--text); letter-spacing: 0.1em; margin-bottom: 2.2rem; text-transform: lowercase;
      transition: color 0.4s;
    }
    textarea {
      width: 100%; height: 150px; background: var(--input-bg);
      border: 1px solid var(--input-border); border-radius: 0; padding: 1.2rem;
      color: var(--text-secondary); font-size: 0.95rem; font-family: 'Segoe UI', system-ui, sans-serif;
      resize: vertical; outline: none; text-align: start;
      transition: background 0.4s, border-color 0.4s, color 0.4s;
    }
    textarea:focus { border-color: var(--link-hover-border); }
    textarea::placeholder { color: #555; text-align: right; }
    button {
      margin-top: 1.8rem; width: 100%; padding: 0.9rem;
      border: 1px solid var(--button-border); background: var(--button-bg);
      color: var(--button-text); font-size: 1rem; font-weight: 400;
      letter-spacing: 0.08em; cursor: pointer;
      display: flex; align-items: center; justify-content: center; gap: 0.5rem;
      transition: all 0.2s; text-transform: lowercase;
    }
    button:hover {
      color: var(--text); border-color: var(--link-hover-border); background: var(--link-hover-bg);
    }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    .spinner { display: none; width: 16px; height: 16px; border: 2px solid rgba(255,255,255,0.2); border-top: 2px solid white; border-radius: 50%; animation: spin 0.8s linear infinite; }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    #status { margin-top: 1.5rem; font-size: 0.85rem; min-height: 1.5rem; color: var(--status-default); transition: all 0.2s; }
    .success { color: #5f9; } .error { color: #f66; } .loading { color: #fc6; }
    .footer { margin-top: 2rem; font-size: 0.6rem; color: var(--footer-color); letter-spacing: 0.15em; }
  </style>
</head>
<body>
  <canvas id="particles"></canvas>
  <div class="card">
    <button class="theme-toggle" onclick="toggleTheme()">◑</button>
    <div class="rule"></div>
    <h1>whisper</h1>
    <textarea id="message" placeholder="پیامت رو اینجا بنویس ((:" maxlength="2000" dir="auto"></textarea>
    <button id="sendBtn" onclick="sendMessage()">
      <span class="btn-text">send</span>
      <span class="spinner" id="spinner"></span>
    </button>
    <div id="status"></div>
    <div class="footer">—</div>
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
    function resizeParticles() { canvasP.width = window.innerWidth; canvasP.height = window.innerHeight; }
    resizeParticles();
    window.addEventListener('resize', resizeParticles);

    const particles = [];
    const particleCount = 50;
    class Particle {
      constructor() {
        this.x = Math.random() * canvasP.width;
        this.y = Math.random() * canvasP.height;
        this.size = Math.random() * 1.5 + 0.3;
        this.vx = (Math.random() - 0.5) * 0.3;
        this.vy = (Math.random() - 0.5) * 0.3;
      }
      update() {
        this.x += this.vx; this.y += this.vy;
        if (this.x < 0 || this.x > canvasP.width) this.vx *= -1;
        if (this.y < 0 || this.y > canvasP.height) this.vy *= -1;
      }
      draw() {
        ctxP.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--particle-color').trim();
        ctxP.beginPath();
        ctxP.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        ctxP.fill();
      }
    }
    for (let i = 0; i < particleCount; i++) particles.push(new Particle());
    function animateParticles() {
      ctxP.clearRect(0, 0, canvasP.width, canvasP.height);
      particles.forEach(p => { p.update(); p.draw(); });
      requestAnimationFrame(animateParticles);
    }
    animateParticles();

    const PROXY_URL = '/whisper/send';
    const messageInput = document.getElementById('message');
    const sendBtn = document.getElementById('sendBtn');
    const btnText = document.querySelector('.btn-text');
    const spinner = document.getElementById('spinner');
    const statusDiv = document.getElementById('status');

    async function sendMessage() {
      console.log('sendMessage called');
      const text = messageInput.value.trim();
      if (!text) {
        statusDiv.textContent = 'پیامت خالی بود که!';
        statusDiv.className = 'error';
        console.log('empty text');
        return;
      }
      sendBtn.disabled = true;
      btnText.style.display = 'none';
      spinner.style.display = 'inline-block';
      statusDiv.textContent = '...';
      statusDiv.className = 'loading';
      console.log('sending...');
      try {
        const response = await fetch(PROXY_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: text })
        });
        console.log('response status', response.status);
        const result = await response.json();
        if (result.success) {
          statusDiv.textContent = 'ارسال شد';
          statusDiv.className = 'success';
          messageInput.value = '';
          console.log('sent');
        } else {
          statusDiv.textContent = result.error || 'خطا';
          statusDiv.className = 'error';
          console.log('server error', result.error);
        }
      } catch (error) {
        statusDiv.textContent = 'قطع شد';
        statusDiv.className = 'error';
        console.error('connection error', error);
      } finally {
        sendBtn.disabled = false;
        btnText.style.display = 'inline';
        spinner.style.display = 'none';
      }
    }
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
    if (localStorage.getItem('theme') === 'light') body.classList.add('light-mode');

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


dous_rooms = {}


def generate_room_code():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


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
                "winner": winner_symbol,
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


if __name__ == "__main__":
    socketio.run(
        app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False
    )
