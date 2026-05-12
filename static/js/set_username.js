async function submitPassword() {
    const pwd = document.getElementById('passwordInput').value;
    const confirm = document.getElementById('confirmPasswordInput').value;
    if (pwd.length < 6) {
        document.getElementById('msg').textContent = 'Password must be at least 6 characters.';
        return;
    }
    if (pwd !== confirm) {
        document.getElementById('msg').textContent = 'Passwords do not match.';
        return;
    }

    const btn = document.getElementById('submitPasswordBtn');
    const originalText = 'Save & Continue';
    btn.disabled = true;
    btn.classList.add('btn-loading');
    btn.innerHTML = '<span class="btn-spinner"></span> Saving...';
    document.getElementById('msg').textContent = '';

    try {
        const resp = await fetch('/api/set_password', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                password: pwd
            })
        });
        const data = await resp.json();
        if (data.success) {
            window.location.href = '/chat';
        } else {
            document.getElementById('msg').textContent = data.error || 'Error saving password.';
            btn.disabled = false;
            btn.classList.remove('btn-loading');
            btn.textContent = originalText;
        }
    } catch (err) {
        document.getElementById('msg').textContent = 'Network error.';
        btn.disabled = false;
        btn.classList.remove('btn-loading');
        btn.textContent = originalText;
    }
}

function skipPassword() {
    window.location.href = '/chat';
}