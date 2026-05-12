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
        timerEl.textContent = 'Time is up';
        statusEl.innerHTML = '<div class="error">Code expired. Please get a new token.</div>';
        return;
    }
    const mins = Math.floor(timeLeft / 60);
    const secs = timeLeft % 60;
    timerEl.textContent = `Time remaining: ${mins}:${secs.toString().padStart(2, '0')}`;
}
setInterval(updateTimer, 1000);

async function checkVerification() {
    if (expired || checking) return;
    checking = true;
    statusEl.innerHTML = '<div class="info animate-pulse">Checking...</div>';
    try {
        const resp = await fetch(`/api/verify_otp?code=${encodeURIComponent(code)}&otp_token=${encodeURIComponent(otpToken)}`);
        const data = await resp.json();
        if (data.success) {
            statusEl.innerHTML = '<div class="success">Verified! Redirecting...</div>';
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
    const btn = document.querySelector('#passwordForm .btn');
    const errorEl = document.getElementById('errorPass');

    if (!username || !password) {
        errorEl.textContent = 'Please enter your username and password.';
        return;
    }

    const originalText = btn.textContent;
    btn.disabled = true;
    btn.classList.add('btn-loading');
    btn.innerHTML = '<span class="btn-spinner"></span> Login...';
    errorEl.textContent = '';

    try {
        const resp = await fetch('/api/login_password', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                username,
                password
            })
        });
        const data = await resp.json();

        if (data.success) {
            window.location.href = '/chat';
        } else {
            errorEl.textContent = data.error || 'Incorrect username or password.';
            btn.disabled = false;
            btn.classList.remove('btn-loading');
            btn.textContent = originalText;
        }
    } catch (err) {
        errorEl.textContent = 'Network error';
        btn.disabled = false;
        btn.classList.remove('btn-loading');
        btn.textContent = originalText;
    }
}

function switchTab(tab) {
    activeTab = tab;
    document.getElementById('tabOtp').classList.toggle('active', tab === 'otp');
    document.getElementById('tabPass').classList.toggle('active', tab === 'password');
    document.getElementById('otpForm').classList.toggle('active', tab === 'otp');
    document.getElementById('passwordForm').classList.toggle('active', tab === 'password');
}

function copyToken() {
    const token = document.getElementById('otpCode').textContent.trim();
    const btn = document.getElementById('copyTokenBtn');
    const icon = btn.querySelector('i');
    const span = btn.querySelector('span');

    navigator.clipboard.writeText(token).then(() => {
        icon.className = 'fa-solid fa-check';
        span.textContent = 'Copied!';
        btn.classList.add('copied');

        setTimeout(() => {
            icon.className = 'fa-solid fa-copy';
            span.textContent = 'Copy';
            btn.classList.remove('copied');
        }, 2000);
    }).catch(() => {
        showToast('Failed to copy token');
    });
}