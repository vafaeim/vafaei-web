from flask import Flask, render_template_string

app = Flask(__name__)

HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>amirrrr</title>
  <style>
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }

    body {
      font-family: 'Segoe UI', system-ui, -apple-system, BlinkMacSystemFont, Roboto, 'Helvetica Neue', sans-serif;
      background: #000;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1.5rem;
      overflow: hidden;
      position: relative;
    }

    /* پارتیکل‌های پس‌زمینه */
    #particles {
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      z-index: 0;
      pointer-events: none;
    }

    .card {
      position: relative;
      z-index: 1;
      background: rgba(10, 10, 10, 0.85);
      backdrop-filter: blur(15px);
      -webkit-backdrop-filter: blur(15px);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 0;
      padding: 3rem 2.5rem;
      max-width: 420px;
      width: 100%;
      text-align: center;
    }

    /* خط تزئینی بالای نام */
    .rule {
      width: 40px;
      height: 1px;
      background: rgba(255, 255, 255, 0.3);
      margin: 0 auto 2rem;
    }

    h1 {
      font-family: 'Georgia', 'Times New Roman', serif;
      font-size: 2rem;
      font-weight: 400;
      color: #e8e8e8;
      letter-spacing: 0.15em;
      margin-bottom: 2.5rem;
      text-transform: lowercase;
    }

    .links {
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }

    a {
      display: block;
      padding: 0.75rem 1rem;
      color: #999;
      text-decoration: none;
      font-size: 0.9rem;
      font-weight: 400;
      letter-spacing: 0.05em;
      border: 1px solid rgba(255, 255, 255, 0.06);
      transition: all 0.3s ease;
      text-align: center;
    }

    a:hover {
      color: #fff;
      border-color: rgba(255, 255, 255, 0.2);
      background: rgba(255, 255, 255, 0.03);
    }

    .footer {
      margin-top: 2.5rem;
      font-size: 0.65rem;
      color: #333;
      letter-spacing: 0.1em;
    }
  </style>
</head>
<body>
  <canvas id="particles"></canvas>

  <div class="card">
    <div class="rule"></div>
    <h1>amirrrr</h1>
    <div class="links">
      <a href="https://whisper-vafaei.runflare.run" target="_blank">Anonymous Message</a>
      <a href="https://github.com/vafaeim" target="_blank">GitHub</a>
      <a href="https://kaggle.com/vafaeii" target="_blank">Kaggle</a>
      <a href="https://t.me/amirvafaeim" target="_blank">Telegram</a>
      <a href="https://rubika.ir/amir__kavan" target="_blank">Rubika</a>
    </div>
    <div class="footer">—</div>
  </div>

  <script>
    const canvas = document.getElementById('particles');
    const ctx = canvas.getContext('2d');
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    const particles = [];
    const particleCount = 50;

    class Particle {
      constructor() {
        this.x = Math.random() * canvas.width;
        this.y = Math.random() * canvas.height;
        this.size = Math.random() * 1.5 + 0.3;
        this.speedX = (Math.random() - 0.5) * 0.3;
        this.speedY = (Math.random() - 0.5) * 0.3;
      }
      update() {
        this.x += this.speedX;
        this.y += this.speedY;
        if (this.x < 0 || this.x > canvas.width) this.speedX *= -1;
        if (this.y < 0 || this.y > canvas.height) this.speedY *= -1;
      }
      draw() {
        ctx.fillStyle = 'rgba(255, 255, 255, 0.15)';
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    for (let i = 0; i < particleCount; i++) {
      particles.push(new Particle());
    }

    function animateParticles() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      particles.forEach(p => { p.update(); p.draw(); });
      requestAnimationFrame(animateParticles);
    }
    animateParticles();

    window.addEventListener('resize', () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    });
  </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML)


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
