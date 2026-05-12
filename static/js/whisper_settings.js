const form = document.getElementById('settingsForm');
const msgDiv = document.getElementById('msg');
form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const token = document.getElementById('token').value.trim();
    const chat_id = document.getElementById('chat_id').value.trim();
    if (!token || !chat_id) {
        msgDiv.textContent = 'both fields required';
        msgDiv.className = 'error';
        return;
    }
    try {
        const response = await fetch('/whisper/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                token,
                chat_id,
                key: new URLSearchParams(window.location.search).get('key')
            })
        });
        const result = await response.json();
        if (result.success) {
            msgDiv.textContent = 'saved';
            msgDiv.className = 'success';
        } else {
            msgDiv.textContent = result.error;
            msgDiv.className = 'error';
        }
    } catch (err) {
        msgDiv.textContent = 'connection error';
        msgDiv.className = 'error';
    }
});