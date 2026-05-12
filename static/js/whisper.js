// Theme
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

// Elements
const messagesContainer = document.getElementById('messagesContainer');
const messageInput = document.getElementById('messageInput');
const sendButton = document.getElementById('sendBtn');
const sendIcon = sendButton.querySelector('.send-icon');
const sendSpinner = document.getElementById('sendSpinner');
const imageInput = document.getElementById('imageInput');
const voiceBtn = document.getElementById('voiceBtn');
const previewArea = document.getElementById('previewArea');
const previewText = document.getElementById('previewText');
const previewIcon = document.getElementById('previewIcon');
const emojiPanel = document.getElementById('emojiPanel');

let selectedFile = null;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let isSending = false;

function addMessage(text, isEmojiOnly = false) {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message';
    const bubble = document.createElement('div');
    bubble.className = 'bubble' + (isEmojiOnly ? ' emoji-only' : '');
    bubble.textContent = text;
    const timeSpan = document.createElement('span');
    timeSpan.className = 'time';
    timeSpan.textContent = new Date().toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit'
    });
    bubble.appendChild(timeSpan);
    msgDiv.appendChild(bubble);
    messagesContainer.appendChild(msgDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function toggleSendButton() {
    const hasContent = messageInput.value.trim() || selectedFile;
    if (hasContent) sendButton.classList.add('visible');
    else sendButton.classList.remove('visible');
}

function toggleEmojiPanel() {
    emojiPanel.classList.toggle('open');
}

function sendEmoji(emoji) {
    addMessage(emoji, true);
    sendToServer({
        text: emoji
    });
    emojiPanel.classList.remove('open');
}

function setSendingState(sending) {
    isSending = sending;
    sendButton.disabled = sending;
    sendIcon.style.display = sending ? 'none' : 'block';
    sendSpinner.style.display = sending ? 'block' : 'none';
}

function showPreview(label, iconClass, fileName) {
    previewIcon.innerHTML = `<i class="${iconClass}"></i>`;
    previewText.textContent = fileName || label;
    previewArea.classList.add('active');
    toggleSendButton();
}

function handlePhotoSelect(input) {
    if (input.files.length > 0) {
        selectedFile = input.files[0];
        showPreview('Image', 'fa-solid fa-image', selectedFile.name);
        if (mediaRecorder && isRecording) mediaRecorder.stop();
    }
}

function removeAttachment() {
    selectedFile = null;
    imageInput.value = '';
    previewArea.classList.remove('active');
    toggleSendButton();
}

async function toggleRecording() {
    if (isRecording) {
        mediaRecorder.stop();
        return;
    }
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: true
        });
        isRecording = true;
        voiceBtn.classList.add('recording');
        voiceBtn.innerHTML = '<i class="fa-solid fa-stop"></i>';
        showPreview('Recording...', 'fa-solid fa-microphone');

        audioChunks = [];
        let options = {};
        if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
            options.mimeType = 'audio/webm;codecs=opus';
        } else if (MediaRecorder.isTypeSupported('audio/webm')) {
            options.mimeType = 'audio/webm';
        }
        mediaRecorder = new MediaRecorder(stream, options);

        mediaRecorder.ondataavailable = e => {
            if (e.data.size > 0) audioChunks.push(e.data);
        };
        mediaRecorder.onstop = () => {
            const mimeType = options.mimeType || 'audio/webm';
            const ext = mimeType.includes('ogg') ? 'ogg' : 'webm';
            const blob = new Blob(audioChunks, {
                type: mimeType
            });
            selectedFile = new File([blob], `voice.${ext}`, {
                type: mimeType
            });
            showPreview('Voice message', 'fa-solid fa-microphone', `voice.${ext}`);

            stream.getTracks().forEach(t => t.stop());
            isRecording = false;
            voiceBtn.classList.remove('recording');
            voiceBtn.innerHTML = '<i class="fa-solid fa-microphone"></i>';
        };
        mediaRecorder.start();
        removeAttachment(); // clear previous file
    } catch (err) {
        alert('Microphone access denied.');
        isRecording = false;
        voiceBtn.classList.remove('recording');
        voiceBtn.innerHTML = '<i class="fa-solid fa-microphone"></i>';
    }
}

async function sendToServer(payload) {
    try {
        let response;
        if (selectedFile) {
            const formData = new FormData();
            formData.append('file', selectedFile);
            if (payload.text) formData.append('text', payload.text);
            response = await fetch('/whisper/send_file', {
                method: 'POST',
                body: formData
            });
        } else {
            response = await fetch('/whisper/send', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });
        }
        const result = await response.json();
        if (!result.success) console.error('Send failed:', result.error);
    } catch (err) {
        console.error('Connection error:', err);
    }
}

async function sendMessage() {
    const text = messageInput.value.trim();
    if (!text && !selectedFile) return;
    if (isSending) return;

    // Show in UI
    if (selectedFile) {
        if (text) addMessage(text);
        addMessage('📎 ' + (selectedFile.type.startsWith('image/') ? 'Photo' : 'Voice message'));
    } else if (text) {
        addMessage(text);
    }

    emojiPanel.classList.remove('open');
    setSendingState(true);

    await sendToServer({
        text
    });

    messageInput.value = '';
    removeAttachment();
    setSendingState(false);
    toggleSendButton();
    messageInput.focus();
}

messageInput.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 100) + 'px';
    toggleSendButton();
});

window.addEventListener('load', () => messageInput.focus());