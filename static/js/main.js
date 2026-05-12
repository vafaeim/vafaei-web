const body = document.body;
const themeToggleBtn = document.querySelector('.theme-toggle');

function setTheme(isLight) {
    body.classList.toggle('light-mode', isLight);
    themeToggleBtn.textContent = isLight ? '◐' : '◑';
    localStorage.setItem('theme', isLight ? 'light' : 'dark');
}

function toggleTheme() {
    setTheme(!body.classList.contains('light-mode'));
}
setTheme(localStorage.getItem('theme') === 'light');

const canvasP = document.getElementById('particles');
const ctxP = canvasP.getContext('2d');
let width, height;
const particles = [];
const PARTICLE_COUNT = 70;
const MOUSE_RADIUS = 100;

const mouse = {
    x: -1000,
    y: -1000
};
window.addEventListener('mousemove', (e) => {
    mouse.x = e.clientX;
    mouse.y = e.clientY;
});
window.addEventListener('touchmove', (e) => {
    if (e.touches.length > 0) {
        mouse.x = e.touches[0].clientX;
        mouse.y = e.touches[0].clientY;
    }
}, {
    passive: true
});

function resizeParticles() {
    width = window.innerWidth;
    height = window.innerHeight;
    canvasP.width = width;
    canvasP.height = height;
}
window.addEventListener('resize', resizeParticles);
resizeParticles();

class Particle {
    constructor() {
        this.reset();
        this.y = Math.random() * height;
    }
    reset() {
        this.x = Math.random() * width;
        this.y = -10;
        this.size = Math.random() * 2 + 0.8;
        this.speedY = Math.random() * 0.6 + 0.2;
        this.speedX = (Math.random() - 0.5) * 0.3;
        this.opacity = Math.random() * 0.6 + 0.2;
    }
    update() {
        this.y += this.speedY;
        this.x += this.speedX;

        const dx = this.x - mouse.x;
        const dy = this.y - mouse.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < MOUSE_RADIUS) {
            const angle = Math.atan2(dy, dx);
            const force = (MOUSE_RADIUS - dist) / MOUSE_RADIUS;
            this.x += Math.cos(angle) * force * 1.5;
            this.y += Math.sin(angle) * force * 1.5;
        }

        if (this.y > height + 10) this.reset();
        if (this.x < -10) this.x = width + 10;
        if (this.x > width + 10) this.x = -10;
    }
    draw() {
        ctxP.beginPath();
        ctxP.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        ctxP.fillStyle = `rgba(108, 92, 231, ${this.opacity})`;
        ctxP.fill();
    }
}

for (let i = 0; i < PARTICLE_COUNT; i++) particles.push(new Particle());

function animateParticles() {
    ctxP.clearRect(0, 0, width, height);
    particles.forEach(p => {
        p.update();
        p.draw();
    });
    requestAnimationFrame(animateParticles);
}
animateParticles();

fetch('/').then(r => {
    if (r.ok) document.getElementById('statusDot').innerHTML = '<span class="pulse"></span> live';
    else document.getElementById('statusDot').innerHTML = '<span style="color:#ff4d4d">●</span> offline';
}).catch(() => {
    document.getElementById('statusDot').innerHTML = '<span style="color:#ff4d4d">●</span> offline';
});

const canvas = document.getElementById('flappyCanvas');
const ctx = canvas.getContext('2d');
const resetBtn = document.getElementById('resetButton');

function getStyleVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

const bird = {
    x: 60,
    y: canvas.height / 2,
    r: 9,
    gravity: 0.45,
    lift: -7.5,
    vel: 0
};
let pipes = [];
const PW = 22,
    GAP = 115;
let frame = 0,
    score = 0,
    best = parseInt(localStorage.getItem('flappyBest') || '0');
let started = false,
    over = false;
let animId;

function resetGame() {
    bird.y = canvas.height / 2;
    bird.vel = 0;
    pipes = [];
    frame = 0;
    score = 0;
    over = false;
    started = true;
    resetBtn.classList.remove('show');
}

function drawBird() {
    ctx.save();
    ctx.translate(bird.x, bird.y);
    ctx.shadowColor = getStyleVar('--accent');
    ctx.shadowBlur = 14;
    ctx.fillStyle = getStyleVar('--bird-color');
    ctx.beginPath();
    ctx.arc(0, 0, bird.r, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;
    ctx.fillStyle = '#fff';
    ctx.beginPath();
    ctx.arc(2, -2, 3, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = '#000';
    ctx.beginPath();
    ctx.arc(3, -2, 1.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
}

function drawPipes() {
    ctx.fillStyle = getStyleVar('--pipe-color');
    ctx.shadowColor = getStyleVar('--accent');
    ctx.shadowBlur = 6;
    for (let p of pipes) {
        ctx.fillRect(p.x, 0, PW, p.top);
        ctx.fillRect(p.x, p.top + GAP, PW, canvas.height - p.top - GAP);
        ctx.fillRect(p.x - 3, p.top - 12, PW + 6, 12);
        ctx.fillRect(p.x - 3, p.top + GAP, PW + 6, 12);
    }
    ctx.shadowBlur = 0;
}

function updatePipes() {
    if (frame % 85 === 0) {
        let top = Math.random() * (canvas.height - GAP - 70) + 40;
        pipes.push({
            x: canvas.width,
            top,
            scored: false
        });
    }
    for (let p of pipes) p.x -= 2.2;
    pipes = pipes.filter(p => p.x > -PW);
}

function checkCollision() {
    for (let p of pipes) {
        if (bird.x + bird.r > p.x && bird.x - bird.r < p.x + PW) {
            if (bird.y - bird.r < p.top || bird.y + bird.r > p.top + GAP) return true;
        }
    }
    return bird.y + bird.r > canvas.height || bird.y - bird.r < 0;
}

function updateScore() {
    for (let p of pipes) {
        if (!p.scored && p.x + PW < bird.x) {
            score++;
            p.scored = true;
            if (score > best) {
                best = score;
                localStorage.setItem('flappyBest', best);
            }
        }
    }
}

function drawHUD() {
    ctx.fillStyle = getStyleVar('--text-secondary');
    ctx.font = 'bold 16px "Segoe UI"';
    ctx.textAlign = 'left';
    ctx.fillText(score, 15, 35);
    ctx.font = '12px "Segoe UI"';
    ctx.textAlign = 'right';
    ctx.fillText('best: ' + best, canvas.width - 15, 30);
}

function drawIdle() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    let bob = Math.sin(Date.now() * 0.008) * 5;
    ctx.save();
    ctx.translate(bird.x, bird.y + bob);
    ctx.shadowColor = getStyleVar('--accent');
    ctx.shadowBlur = 10;
    ctx.fillStyle = getStyleVar('--bird-color');
    ctx.beginPath();
    ctx.arc(0, 0, bird.r, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    ctx.fillStyle = getStyleVar('--text-secondary');
    ctx.font = '16px "Segoe UI"';
    ctx.textAlign = 'center';
    ctx.fillText('tap or press space', canvas.width / 2, canvas.height / 2 + 20);
    ctx.font = '12px "Segoe UI"';
    ctx.fillText('best: ' + best, canvas.width / 2, canvas.height / 2 + 45);
}

function drawGameOver() {
    ctx.fillStyle = getStyleVar('--text-secondary');
    ctx.textAlign = 'center';
    let cy = canvas.height / 2 - 30;
    ctx.font = '24px "Georgia"';
    ctx.fillText('game over', canvas.width / 2, cy);
    cy += 35;
    ctx.font = '16px "Segoe UI"';
    ctx.fillText('score: ' + score, canvas.width / 2, cy);
    cy += 25;
    ctx.fillText('best: ' + best, canvas.width / 2, cy);
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

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    drawPipes();
    drawBird();
    drawHUD();

    if (checkCollision()) {
        over = true;
        started = false;
        drawGameOver();
        resetBtn.classList.add('show');
    }
    frame++;
    animId = requestAnimationFrame(gameLoop);
}

function jump() {
    if (over) return;
    if (!started) {
        resetGame();
    } else {
        bird.vel = bird.lift;
    }
}

document.addEventListener('keydown', function(e) {
    if (e.code === 'Space') {
        if (document.activeElement?.tagName === 'BUTTON' || document.activeElement?.tagName === 'INPUT') return;
        e.preventDefault();
        jump();
    }
});
canvas.addEventListener('click', jump);
resetBtn.addEventListener('click', () => {
    if (over) resetGame();
});
animId = requestAnimationFrame(gameLoop);