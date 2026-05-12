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