const body = document.body;

function toggleTheme() {
    body.classList.toggle('light-mode');
    localStorage.setItem('theme', body.classList.contains('light-mode') ? 'light' : 'dark');
}
(localStorage.getItem('theme') === 'light') ? body.classList.add('light-mode'): body.classList.remove('light-mode');

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
const MESSAGE_LIMIT = 20;
const SCROLL_LOAD_LIMIT = 50;
let currentUsername = null;
let currentUserId = null;
let otherUserId = null;
let replyToMessage = null;
let typingTimeout;
let isEditing = false;
let typingIndicator = document.getElementById('typingIndicator');
const playDouzBtn = document.getElementById('playDouzBtn');
let activeChatType = 'private';
let selectedMembers = [];
const avatarCache = {};
let selectedFile = null;
let currentAudio = null;
let currentPlayBtn = null;
let currentProgress = null;
let currentDuration = null;
let progressInterval = null;
let isRecordingMode = false;
let pushMediaRecorder = null;
let pushAudioChunks = [];
let pushStream = null;
let pushVoiceType = null;
let isPushToTalkActive = false;
let selectionMode = false;
const selectedMessages = new Set();
let longPressTimer = null;
const LONG_PRESS_DURATION = 500;
let groupCreatorId = null;
let isDraggingFab = false;
let fabDragStartX = 0;
let fabDragStartY = 0;
let fabStartLeft = 0;
let fabStartTop = 0;
const DRAG_THRESHOLD = 5;
let fabHasMoved = false;
let pendingOfferSdp = null;
let pendingOfferResolver = null;
let isMuted = false;
let callTrackTimeout = null;

function enterSelectionMode(msgId) {
    selectionMode = true;
    selectedMessages.add(msgId);
    document.getElementById('selectionToolbar').classList.add('active');
    updateSelectionUI();
}

function exitSelectionMode() {
    selectionMode = false;
    selectedMessages.clear();
    document.getElementById('selectionToolbar').classList.remove('active');
    document.querySelectorAll('.message-row').forEach(row => {
        row.classList.remove('selected');
    });
    updateSelectionUI();
}

function updateSelectionUI() {
    const count = selectedMessages.size;
    document.getElementById('selectionInfo').textContent = count + ' selected';
    document.querySelectorAll('.message-row').forEach(row => {
        const msgId = parseInt(row.dataset.messageId);
        if (selectedMessages.has(msgId)) {
            row.classList.add('selected');
        } else {
            row.classList.remove('selected');
        }
    });
}

async function enterRecordingMode() {
    try {
        const testStream = await navigator.mediaDevices.getUserMedia({
            audio: true
        });
        testStream.getTracks().forEach(track => track.stop());
    } catch (err) {
        showToast('Microphone access denied');
        return;
    }

    isRecordingMode = true;
    document.getElementById('normalTextArea').style.display = 'none';
    document.getElementById('voiceRecordArea').style.display = 'flex';
    const voiceBtn = document.getElementById('voiceModeToggleBtn');
    voiceBtn.innerHTML = '<i class="fa-solid fa-keyboard"></i>';
    voiceBtn.title = 'Return to text';
    cancelAttachment();
}

function exitRecordingMode() {
    isRecordingMode = false;
    document.getElementById('normalTextArea').style.display = 'flex';
    document.getElementById('voiceRecordArea').style.display = 'none';
    const voiceBtn = document.getElementById('voiceModeToggleBtn');
    voiceBtn.innerHTML = '<i class="fa-solid fa-microphone"></i>';
    voiceBtn.title = 'Switch to voice mode';
    if (pushMediaRecorder && isPushToTalkActive) {
        pushMediaRecorder.stop();
    }
}

async function getAvatarUrl(userId) {
    if (!userId) return null;
    if (avatarCache.hasOwnProperty(userId)) {
        return avatarCache[userId];
    }
    try {
        const resp = await fetch('/api/user_status/' + userId);
        const data = await resp.json();
        avatarCache[userId] = data.avatar_url || null;
        return avatarCache[userId];
    } catch (e) {
        avatarCache[userId] = null;
        return null;
    }
}

const mainChat = document.getElementById('mainChat');
let swipeStartX = 0;
let swipeStartY = 0;

function getUserColorClass(userId) {
    if (!userId && userId !== 0) return '';
    return 'avatar-' + (parseInt(userId) % 24);
}

mainChat.addEventListener('touchstart', (e) => {
    swipeStartX = e.changedTouches[0].screenX;
    swipeStartY = e.changedTouches[0].screenY;
}, {
    passive: true
});

mainChat.addEventListener('touchend', (e) => {
    const touchEndX = e.changedTouches[0].screenX;
    const touchEndY = e.changedTouches[0].screenY;
    const dx = touchEndX - swipeStartX;
    const dy = touchEndY - swipeStartY;

    if (Math.abs(dx) > Math.abs(dy) && dx > 60 && window.innerWidth < 700) {
        mainChat.style.transition = 'transform 0.25s ease-out';
        mainChat.style.transform = 'translateX(100%)';

        setTimeout(() => {
            mainChat.style.transition = '';
            mainChat.style.transform = '';
            backToChats();
        }, 250);
    }
});

document.getElementById('voiceModeToggleBtn').addEventListener('click', () => {
    if (isRecordingMode) {
        exitRecordingMode();
    } else {
        enterRecordingMode();
    }
});

const pushBtn = document.getElementById('pushToTalkBtn');
pushBtn.addEventListener('mousedown', startPushToTalk);
pushBtn.addEventListener('mouseup', stopPushToTalk);
pushBtn.addEventListener('mouseleave', stopPushToTalk);
pushBtn.addEventListener('touchstart', (e) => {
    e.preventDefault();
    startPushToTalk();
});
pushBtn.addEventListener('touchend', (e) => {
    e.preventDefault();
    stopPushToTalk();
});

async function startPushToTalk() {
    if (isPushToTalkActive || pushBtn.disabled) return;
    try {
        pushStream = await navigator.mediaDevices.getUserMedia({
            audio: true
        });
        isPushToTalkActive = true;
        pushBtn.classList.add('recording');
        pushBtn.querySelector('.ptt-label').textContent = 'Recording...';

        pushAudioChunks = [];
        let options = {};
        if (MediaRecorder.isTypeSupported('audio/mp4')) {
            options.mimeType = 'audio/mp4';
        } else if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
            options.mimeType = 'audio/webm;codecs=opus';
        } else if (MediaRecorder.isTypeSupported('audio/webm')) {
            options.mimeType = 'audio/webm';
        }
        pushVoiceType = options.mimeType || 'audio/webm';
        pushMediaRecorder = new MediaRecorder(pushStream, options);

        pushMediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) pushAudioChunks.push(e.data);
        };

        pushMediaRecorder.onstop = async () => {
            const blob = new Blob(pushAudioChunks, {
                type: pushVoiceType
            });
            const ext = pushVoiceType.includes('mp4') ? 'm4a' : (pushVoiceType.includes('ogg') ? 'ogg' : 'webm');
            const file = new File([blob], 'voice_message.' + ext, {
                type: pushVoiceType
            });

            pushBtn.classList.remove('recording');
            pushBtn.disabled = true;
            pushBtn.querySelector('.ptt-label').textContent = 'Sending...';

            try {
                const formData = new FormData();
                formData.append('file', file);
                const resp = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });
                const data = await resp.json();
                if (data.success) {
                    socket.emit(activeChatType === 'group' ? 'send_group_message' : 'send_chat_message', {
                        text: '',
                        [activeChatType === 'group' ? 'group_id' : 'chat_id']: activeChatId,
                        attachment: data.attachment
                    });
                } else {
                    showToast('Upload failed');
                }
            } catch (e) {
                showToast('Upload connection error');
            }

            pushStream.getTracks().forEach(t => t.stop());
            pushStream = null;
            pushMediaRecorder = null;
            pushAudioChunks = [];
            pushVoiceType = null;
            isPushToTalkActive = false;
            pushBtn.disabled = false;
            pushBtn.querySelector('.ptt-label').textContent = 'Hold to Talk';
        };

        pushMediaRecorder.start();
    } catch (err) {
        showToast('Microphone access denied');
    }
}

function stopPushToTalk() {
    if (pushMediaRecorder && isPushToTalkActive) {
        pushMediaRecorder.stop();
    }
}

document.getElementById('messageContextMenu').addEventListener('click', async (e) => {
    const action = e.target.closest('.context-item')?.dataset.action;
    const messageData = document.getElementById('messageContextMenu').currentMessage;
    if (!messageData || !action) return;

    const {
        msg,
        isSent
    } = messageData;

    const menu = document.getElementById('messageContextMenu');
    menu.style.display = 'none';

    if (action === 'copy') {
        navigator.clipboard.writeText(msg.text || '');
        showToast('Copied!', true);
    } else if (action === 'react') {
        const row = document.querySelector(`.message-row[data-message-id="${msg.id}"]`);
        if (row) {
            const bubbleEl = row.querySelector('.bubble');
            if (bubbleEl) {
                showReactionPicker(msg, bubbleEl);
            }
        }
    } else if (action === 'reply') {
        replyToMessage = msg;
        const previewText = msg.text.length > 40 ? msg.text.substring(0, 40) + '...' : msg.text;
        document.getElementById('replyText').textContent = previewText;
        document.getElementById('replyPreview').classList.add('active');
        document.getElementById('chatInput').focus();
    } else if (action === 'edit') {
        if (!isSent) {
            showToast('You can only edit your own messages');
            return;
        }
        isEditing = true;

        const row = document.querySelector(`.message-row[data-message-id="${msg.id}"]`);
        if (!row) return;
        const bubble = row.querySelector('.bubble');
        if (!bubble) return;

        const originalContent = bubble.innerHTML;

        const editBox = document.createElement('div');
        editBox.className = 'edit-box';
        const textarea = document.createElement('textarea');
        textarea.value = msg.text;
        textarea.setAttribute('dir', 'auto');
        textarea.style.height = '60px';
        const actions = document.createElement('div');
        actions.className = 'edit-actions';

        const saveBtn = document.createElement('button');
        saveBtn.textContent = 'Save';
        const cancelBtn = document.createElement('button');
        cancelBtn.textContent = 'Cancel';
        cancelBtn.className = 'cancel';

        actions.appendChild(saveBtn);
        actions.appendChild(cancelBtn);
        editBox.appendChild(textarea);
        editBox.appendChild(actions);

        bubble.innerHTML = '';
        bubble.appendChild(editBox);

        textarea.focus();
        textarea.setSelectionRange(textarea.value.length, textarea.value.length);

        const finishEdit = () => {
            bubble.innerHTML = originalContent;
            isEditing = false;
        };

        cancelBtn.addEventListener('click', finishEdit);

        saveBtn.addEventListener('click', async () => {
            const newText = textarea.value.trim();
            if (!newText || newText === msg.text) {
                finishEdit();
                return;
            }
            try {
                const resp = await fetch(`/api/messages/${msg.id}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        text: newText
                    })
                });
                if (resp.ok) {
                    isEditing = false;
                    msg.text = newText;
                    msg.edited = true;
                    const newRow = createMessageElement(msg, isSent);
                    row.replaceWith(newRow);
                } else {
                    showToast('Failed to edit message');
                }
            } catch (e) {
                showToast('Connection error');
                finishEdit();
            }
        });
    } else if (action === 'delete') {
        if (!isSent) {
            showToast('You can only delete your own messages');
            return;
        }

        const modal = document.getElementById('deleteConfirmModal');
        modal.style.display = 'flex';

        const confirmBtn = document.getElementById('confirmDeleteBtn');
        const cancelBtn = document.getElementById('cancelDeleteBtn');

        const menu = document.getElementById('messageContextMenu');
        menu.style.display = 'none';

        const cleanup = () => {
            modal.style.display = 'none';
            confirmBtn.replaceWith(confirmBtn.cloneNode(true));
            cancelBtn.replaceWith(cancelBtn.cloneNode(true));
        };

        document.getElementById('confirmDeleteBtn').addEventListener('click', async () => {
            cleanup();
            try {
                const resp = await fetch(`/api/messages/${msg.id}`, {
                    method: 'DELETE'
                });
                if (!resp.ok) showToast('Failed to delete message');
            } catch (e) {
                showToast('Connection error');
            }
        }, {
            once: true
        });

        document.getElementById('cancelDeleteBtn').addEventListener('click', cleanup, {
            once: true
        });
    }
});


socket.on('message_edited', (data) => {
    if (data.chat_id === activeChatId) {
        const msgElements = document.querySelectorAll(`[data-message-id="${data.message_id}"]`);
        msgElements.forEach(el => {
            const bubble = el.querySelector('.bubble');
            if (!bubble) return;

            let msgTextSpan = bubble.querySelector('.msg-text');
            if (msgTextSpan) {
                msgTextSpan.textContent = data.text;
            } else {
                const textNodes = Array.from(bubble.childNodes).filter(
                    n => n.nodeType === Node.TEXT_NODE && n.textContent.trim() !== ''
                );
                if (textNodes.length > 0) {
                    textNodes[0].textContent = data.text;
                } else {
                    const textSpan = document.createElement('span');
                    textSpan.className = 'msg-text';
                    textSpan.textContent = data.text;
                    bubble.insertBefore(textSpan, bubble.firstChild);
                }
            }

            if (!bubble.querySelector('.edited-label')) {
                const editedSpan = document.createElement('span');
                editedSpan.className = 'edited-label';
                editedSpan.textContent = ' (edited)';
                bubble.appendChild(editedSpan);
            }
        });
    }
});

socket.on('message_deleted', (data) => {
    if (data.chat_id === activeChatId) {
        document.querySelectorAll(`[data-message-id="${data.message_id}"]`).forEach(el => {
            const bubble = el.querySelector('.bubble');
            if (bubble) renderDeletedBubble(bubble);
        });
    }
});

socket.on('message_reaction', (data) => {
    if (data.chat_id === activeChatId) {
        const row = document.querySelector(`.message-row[data-message-id="${data.message_id}"]`);
        if (row) {
            const bubble = row.querySelector('.bubble');
            const existing = bubble.querySelector('.reactions-container');
            if (existing) existing.remove();
            const msg = {
                reactions: data.reactions
            };
            if (msg.reactions && Object.keys(msg.reactions).length > 0) {
                const reactionsContainer = document.createElement('div');
                reactionsContainer.className = 'reactions-container';
                for (const [emoji, users] of Object.entries(msg.reactions)) {
                    const badge = document.createElement('span');
                    badge.className = 'reaction-badge';
                    if (users.includes(currentUserId)) badge.classList.add('active');
                    badge.innerHTML = `${emoji} <span class="reaction-count">${users.length}</span>`;
                    badge.addEventListener('click', (e) => {
                        e.stopPropagation();
                        toggleReaction(data.message_id, emoji);
                    });
                    reactionsContainer.appendChild(badge);
                }
                bubble.appendChild(reactionsContainer);
            }
        }
    }
});

function closeAllPopups() {
    if (currentReactionPicker) {
        currentReactionPicker.remove();
        currentReactionPicker = null;
    }
    const menu = document.getElementById('messageContextMenu');
    if (menu && menu.style.display !== 'none') {
        menu.style.display = 'none';
    }
}

function roundedRect(ctx, x, y, width, height, radius) {
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.lineTo(x + width - radius, y);
    ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
    ctx.lineTo(x + width, y + height - radius);
    ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
    ctx.lineTo(x + radius, y + height);
    ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
    ctx.lineTo(x, y + radius);
    ctx.quadraticCurveTo(x, y, x + radius, y);
    ctx.closePath();
}

function drawWaveform(canvas, peaks, fillFraction) {
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    if (!peaks || !Array.isArray(peaks) || peaks.length === 0) {
        peaks = new Array(80).fill(0.5);
    }

    const isLight = document.body.classList.contains('light-mode');
    const unplayedColor = isLight ? 'rgba(0,0,0,0.12)' : 'rgba(255,255,255,0.25)';

    const barWidth = w / peaks.length;
    const fillIndex = Math.floor(fillFraction * peaks.length);

    for (let i = 0; i < peaks.length; i++) {
        const barHeight = peaks[i] * h * 0.8 + 2;
        const x = i * barWidth;
        const y = (h - barHeight) / 2;

        if (i < fillIndex) {
            const gradient = ctx.createLinearGradient(x, y, x, y + barHeight);
            gradient.addColorStop(0, getComputedStyle(document.documentElement).getPropertyValue('--user-color').trim() || '#2b9cff');
            gradient.addColorStop(1, '#a78bfa');
            ctx.fillStyle = gradient;
        } else {
            ctx.fillStyle = unplayedColor;
        }

        ctx.beginPath();
        roundedRect(ctx, x + 1, y, barWidth - 2, barHeight, barWidth / 2);
        ctx.fill();
    }
}

let currentReactionPicker = null;

function showReactionPicker(msg, bubble) {
    if (currentReactionPicker) {
        currentReactionPicker.remove();
        currentReactionPicker = null;
    }
    const picker = document.createElement('div');
    picker.className = 'reaction-picker active';
    const emojis = ['👍', '❤️', '😂', '😢', '😡', '👏', '🎉', '💯', '🔥'];
    emojis.forEach(emoji => {
        const btn = document.createElement('button');
        btn.className = 'emoji-option';
        btn.textContent = emoji;
        btn.addEventListener('click', () => {
            toggleReaction(msg.id, emoji);
            picker.remove();
            currentReactionPicker = null;
        });
        picker.appendChild(btn);
    });

    const rect = bubble.getBoundingClientRect();
    picker.style.top = (rect.top - 50) + 'px';
    picker.style.left = (rect.left + rect.width / 2 - 100) + 'px';
    document.body.appendChild(picker);
    currentReactionPicker = picker;

    setTimeout(() => {
        const closePicker = (e) => {
            if (!picker.contains(e.target) && e.target !== bubble) {
                picker.remove();
                currentReactionPicker = null;
                document.removeEventListener('click', closePicker);
            }
        };
        document.addEventListener('click', closePicker);
    }, 10);
}

async function toggleReaction(messageId, emoji) {
    try {
        const resp = await fetch(`/api/messages/${messageId}/reaction`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                reaction: emoji
            })
        });
    } catch (e) {
        showToast('Connection error');
    }
}

function renderDeletedBubble(bubble) {
    bubble.innerHTML = `<div style="display:flex;align-items:center;gap:0.4rem;color:var(--text-secondary);font-size:0.85rem;opacity:0.7;">
  <i class="fa-solid fa-trash" style="font-size:0.8rem;"></i>
  <em>This message was deleted</em>
  </div>`;
    bubble.style.background = 'transparent';
    bubble.style.boxShadow = 'none';
    bubble.style.cursor = 'default';
    bubble.classList.remove('sent', 'received');
}

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
    socket.emit('typing', {
        chat_id: activeChatId
    });
    clearTimeout(typingTimeout);
    typingTimeout = setTimeout(() => {
        socket.emit('stop_typing', {
            chat_id: activeChatId
        });
    }, 1000);
});

document.getElementById('chatInput').addEventListener('keydown', function(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        sendChatMessage();
    }
});

socket.on('connect', () => {
    socket.emit('join_chat');
    if (activeChatId) {
        if (activeChatType === 'group') {
            socket.emit('join_group', {
                group_id: activeChatId
            });
        } else {
            socket.emit('join_chat_room', {
                chat_id: activeChatId
            });
        }
    }
    const urlParams = new URLSearchParams(window.location.search);
    const code = urlParams.get('code');
    if (code) {
        fetch('/api/join_group_by_code', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                code
            })
        }).then(r => r.json()).then(data => {
            if (data.success && data.group_id) {
                showToast('Joined group!', true);
                loadChats();
                openChat(data.group_id, 'group');
                window.history.replaceState({}, document.title, "/chat");
            } else {
                showToast(data.error || 'Invalid invite');
            }
        });
    }
});

socket.on('new_message', (msg) => {
    const chatId = Number(msg.chat_id);
    if (activeChatId === chatId) {
        let replaced = false;
        if (msg.sender_username === currentUsername) {
            const pendingEl = document.querySelector('.message-row[data-pending="true"]');
            if (pendingEl) {
                const newRow = createMessageElement(msg, true);
                pendingEl.replaceWith(newRow);
                replaced = true;
            }
        }
        if (!replaced) {
            appendMessage(msg, msg.sender_username === currentUsername);
        }
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

socket.on('new_group_message', (msg) => {
    if (activeChatId === msg.group_id && activeChatType === 'group') {
        let replaced = false;
        if (msg.sender_username === currentUsername) {
            const pendingEl = document.querySelector('.message-row[data-pending="true"]');
            if (pendingEl) {
                const newRow = createMessageElement(msg, true);
                pendingEl.replaceWith(newRow);
                replaced = true;
            }
        }
        if (!replaced) {
            appendMessage(msg, msg.sender_username === currentUsername);
        }
        socket.emit('group_seen', { group_id: msg.group_id });
    }
    loadChats();
});


socket.on('message_seen', (data) => {
    if (data.chat_id === activeChatId) {
        document.querySelectorAll('.message-row.sent .msg-ticks').forEach(tick => {
            tick.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#4fc3f7" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#4fc3f7" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-left:-10px;"><polyline points="20 6 9 17 4 12"/></svg>`;
        });
    }
});

socket.on('user_status_changed', (data) => {
    if (data.user_id == otherUserId) {
        updateOnlineStatus(data);
    }
});

socket.on('group_renamed', (data) => {
    if (activeChatId === data.group_id && activeChatType === 'group') {
        document.getElementById('chatHeader').textContent = data.name;
    }
    loadChats();
});

function showToast(message, isSuccess = false) {
    const toast = document.createElement('div');
    toast.className = 'error-toast';
    toast.style.background = isSuccess ? '#34d399' : '#ff4d4d';
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 2000);
}

fetch('/api/whoami').then(r => r.json()).then(d => {
    currentUserId = d.user_id;
    currentUsername = d.username;
});

function isEmojiOnly(text) {
    if (!text) return false;
    const segmenter = new Intl.Segmenter('en', {
        granularity: 'grapheme'
    });
    const graphemes = [...segmenter.segment(text)].map(s => s.segment);
    const emojiRegex = /\p{Emoji}/u;
    const allEmoji = graphemes.every(g => emojiRegex.test(g));
    return allEmoji && graphemes.length >= 1 && graphemes.length <= 3;
}

function searchUsers() {
    const q = document.getElementById('searchUserInput').value.trim();
    const resultsDiv = document.getElementById('searchResults');
    if (!q) {
        resultsDiv.style.display = 'none';
        return;
    }
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
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                user_id: userId
            })
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

function toggleSection(type) {
    const list = document.getElementById(type === 'groups' ? 'groupsList' : 'chatsList');
    const arrow = document.getElementById(type === 'groups' ? 'groupsArrow' : 'chatsArrow');
    if (list.style.display === 'none') {
        list.style.display = 'block';
        arrow.classList.remove('collapsed');
    } else {
        list.style.display = 'none';
        arrow.classList.add('collapsed');
    }
}

function loadChats() {
    Promise.all([
        fetch('/api/chats').then(r => r.json()),
        fetch('/api/groups').then(r => r.json())
    ]).then(([chats, groups]) => {
        const groupsList = document.getElementById('groupsList');
        const chatsList = document.getElementById('chatsList');
        groupsList.innerHTML = '';
        chatsList.innerHTML = '';

        let groupsUnread = 0;

        groups.forEach(g => {
            groupsUnread += g.unread_count || 0;
            const item = document.createElement('div');
            const isActive = (activeChatId === g.id && activeChatType === 'group');
            item.className = 'chat-item' + (isActive ? ' active' : '');
            item.dataset.chatId = g.id;
            item.dataset.otherUsername = g.name;
            item.dataset.type = 'group';

            item.addEventListener('click', function() {
                openChat(this, 'group');
            });

            const avatar = document.createElement('div');
            avatar.className = 'avatar ' + getUserColorClass(g.id);
            avatar.textContent = g.name[0].toUpperCase();
            item.appendChild(avatar);

            const infoDiv = document.createElement('div');
            infoDiv.className = 'chat-info';

            const nameDiv = document.createElement('div');
            nameDiv.className = 'chat-name';
            nameDiv.textContent = g.name;
            nameDiv.setAttribute('dir', 'auto');
            infoDiv.appendChild(nameDiv);

            const lastMsg = document.createElement('div');
            lastMsg.className = 'last-message';
            lastMsg.textContent = g.last_message || '';
            lastMsg.setAttribute('dir', 'auto');
            infoDiv.appendChild(lastMsg);

            item.appendChild(infoDiv);

            const timeWrapper = document.createElement('div');
            timeWrapper.className = 'chat-time-wrapper';

            const timeDiv = document.createElement('span');
            timeDiv.className = 'chat-time';
            timeDiv.textContent = g.last_time ?
                new Date(g.last_time).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit'
                }) :
                '';
            timeWrapper.appendChild(timeDiv);

            if (g.unread_count > 0) {
                const badge = document.createElement('span');
                badge.className = 'unread-badge';
                badge.textContent = g.unread_count;
                timeWrapper.appendChild(badge);
            }

            item.appendChild(timeWrapper);
            groupsList.appendChild(item);
        });

        let chatsUnread = 0;

        chats.forEach(c => {
            chatsUnread += c.unread_count || 0;
            const item = document.createElement('div');
            item.className = 'chat-item' + (activeChatId === c.id && activeChatType === 'private' ? ' active' : '');
            item.dataset.chatId = c.id;
            item.dataset.otherUsername = c.other_username;
            item.dataset.otherUserId = c.other_user_id;
            item.dataset.type = 'private';

            item.addEventListener('click', function() {
                openChat(this);
            });

            const avatar = document.createElement('div');
            avatar.className = 'avatar';
            const av = c.other_avatar_url;
            if (av) {
                const img = document.createElement('img');
                img.src = av;
                img.alt = c.other_username[0];
                img.draggable = false;
                avatar.appendChild(img);
            } else {
                avatar.className += ' ' + getUserColorClass(c.other_user_id);
                avatar.textContent = c.other_username[0].toUpperCase();
            }

            chats.forEach(c => {
                if (c.other_avatar_url) {
                    avatarCache[c.other_user_id] = c.other_avatar_url;
                }
            });

            item.appendChild(avatar);

            const infoDiv = document.createElement('div');
            infoDiv.className = 'chat-info';

            const nameDiv = document.createElement('div');
            nameDiv.className = 'chat-name';
            nameDiv.textContent = c.other_username;
            if (c.other_user_id === currentUserId) {
                nameDiv.textContent = 'Saved Messages';
                avatar.innerHTML = '<i class="fa-solid fa-bookmark"></i>';
                avatar.style.background = '#2b9cff';
            } else {
                nameDiv.textContent = c.other_username;
            }
            infoDiv.appendChild(nameDiv);

            const lastMsg = document.createElement('div');
            lastMsg.className = 'last-message';
            lastMsg.textContent = c.last_message || '';
            infoDiv.appendChild(lastMsg);

            item.appendChild(infoDiv);

            const timeWrapper = document.createElement('div');
            timeWrapper.className = 'chat-time-wrapper';

            const timeDiv = document.createElement('span');
            timeDiv.className = 'chat-time';
            timeDiv.textContent = c.last_time ?
                new Date(c.last_time).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit'
                }) :
                '';
            timeWrapper.appendChild(timeDiv);

            if (c.unread_count > 0) {
                const badge = document.createElement('span');
                badge.className = 'unread-badge';
                badge.textContent = c.unread_count;
                timeWrapper.appendChild(badge);
            }

            item.appendChild(timeWrapper);
            chatsList.appendChild(item);
        });

        const groupsBadge = document.getElementById('groupsUnread');
        groupsBadge.textContent = groupsUnread > 0 ? groupsUnread : '';
        groupsBadge.style.display = groupsUnread > 0 ? 'inline' : 'none';

        const chatsBadge = document.getElementById('chatsUnread');
        chatsBadge.textContent = chatsUnread > 0 ? chatsUnread : '';
        chatsBadge.style.display = chatsUnread > 0 ? 'inline' : 'none';

        document.querySelectorAll('.chat-item').forEach(item => {
            if (parseInt(item.dataset.otherUserId) === currentUserId) {
                item.classList.add('current-user');
            }
        });
    });
}

function updateOnlineStatus(status) {
    const el = document.getElementById('onlineStatus');
    if (status.online) {
        el.innerHTML = '<span style="color:#34d399;">●</span> online';
    } else if (status.last_seen) {
        const last = new Date(status.last_seen);
        const now = new Date();
        const diff = Math.floor((now - last) / 1000);
        let text;
        if (diff < 60) text = 'last seen just now';
        else if (diff < 3600) text = `last seen ${Math.floor(diff/60)}m ago`;
        else if (diff < 86400) text = `last seen ${Math.floor(diff/3600)}h ago`;
        else text = 'last seen ' + last.toLocaleDateString();
        el.textContent = text;
    } else {
        el.textContent = '';
    }
}

function openChat(chatElementOrId, type = 'private') {
    let chatId, initialUsername, initialUserId;

    if (isRecordingMode) exitRecordingMode();

    if (typeof chatElementOrId === 'object') {
        const el = chatElementOrId;
        chatId = parseInt(el.dataset.chatId);
        initialUsername = el.dataset.otherUsername;
        initialUserId = el.dataset.type === 'private' ? parseInt(el.dataset.otherUserId) : null;
        type = el.dataset.type || type;
    } else {
        chatId = chatElementOrId;
    }

    activeChatId = chatId;
    activeChatType = type;
    document.getElementById('onlineStatus').textContent = '';
    otherUserId = null;

    if (type === 'group') {
        socket.emit('join_group', {
            group_id: chatId
        });
        otherUserId = chatId;
    } else {
        socket.emit('join_chat_room', {
            chat_id: chatId
        });
    }

    const mainChat = document.getElementById('mainChat');
    mainChat.classList.add('active');
    document.getElementById('inputArea').style.display = 'flex';
    updateActionSwitch();
    const msgContainer = document.getElementById('messagesContainer');
    msgContainer.innerHTML = '';

    for (let i = 0; i < 7; i++) {
        const sk = document.createElement('div');
        sk.className = 'skeleton-bubble';
        sk.style.alignSelf = i % 2 === 0 ? 'flex-end' : 'flex-start';
        sk.style.width = (50 + Math.random() * 30) + '%';
        msgContainer.appendChild(sk);
    }
    oldestMessageId = null;

    const headerEl = document.getElementById('chatHeader');
    const avatarEl = document.getElementById('headerAvatar');
    const viewMembersBtn = document.getElementById('viewMembersBtn');

    if (initialUsername) {
        headerEl.textContent = initialUsername;
        if (initialUserId) {
            fetch('/api/user_status/' + initialUserId)
                .then(r => r.json())
                .then(data => {
                    const avatarEl = document.getElementById('headerAvatar');
                    avatarEl.innerHTML = '';
                    if (data.avatar_url) {
                        const img = document.createElement('img');
                        img.src = data.avatar_url;
                        img.alt = initialUsername[0];
                        img.draggable = false;
                        avatarEl.appendChild(img);
                        avatarEl.className = 'header-avatar';
                    } else {
                        avatarEl.textContent = initialUsername[0].toUpperCase();
                        avatarEl.className = 'header-avatar ' + getUserColorClass(initialUserId);
                    }
                });
        } else {
            avatarEl.textContent = initialUsername[0].toUpperCase();
            avatarEl.className = 'header-avatar';
        }
        viewMembersBtn.style.display = 'none';
    } else {
        headerEl.textContent = '...';
        avatarEl.textContent = '...';
        avatarEl.className = 'header-avatar';
    }

    if (type === 'group') {
        fetch(`/api/group_info/${chatId}`).then(r => r.json()).then(info => {
            document.getElementById('chatHeader').textContent = info.name;
            document.getElementById('headerAvatar').textContent = info.name[0].toUpperCase();
            document.getElementById('headerAvatar').className = 'header-avatar ' + getUserColorClass(chatId);
            const onlineEl = document.getElementById('onlineStatus');
            onlineEl.textContent = info.member_count + ' members';
            onlineEl.style.display = 'block';
            viewMembersBtn.dataset.members = JSON.stringify(info.members);
            viewMembersBtn.style.display = 'inline-block';
            renameGroupBtn.style.display = 'inline-block';
            inviteGroupBtn.style.display = 'inline-block';
            groupCreatorId = info.creator_id;
            const fab = document.getElementById('callFab');
            fab.style.left = '';
            fab.style.top = '';
            fab.style.right = '12px';
            fab.style.transform = 'translateY(-50%)';
            if (groupCreatorId && groupCreatorId !== currentUserId) {
                fab.style.display = 'flex';
                fab.title = 'Call group creator';
            } else {
                fab.style.display = 'none';
            }
        });

        fetch(`/api/group_messages/${chatId}?limit=${MESSAGE_LIMIT}`)
            .then(r => r.json())
            .then(messages => {
                document.querySelectorAll('.skeleton-bubble').forEach(el => el.remove());
                if (messages.length > 0) oldestMessageId = messages[0].id;
                messages.forEach(msg => appendMessage(msg, msg.sender_username === currentUsername));
                document.getElementById('messagesContainer').scrollTop =
                    document.getElementById('messagesContainer').scrollHeight;
                fixDateSeparators(msgContainer);
            });
    } else {
        if (initialUserId) {
            otherUserId = initialUserId;
            document.getElementById('headerAvatar').className = 'header-avatar ' + getUserColorClass(otherUserId);
            fetch('/api/user_status/' + otherUserId)
                .then(r => r.json())
                .then(status => updateOnlineStatus(status));
        }
        fetch('/api/chats').then(r => r.json()).then(chats => {
            renameGroupBtn.style.display = 'none';
            inviteGroupBtn.style.display = 'none';
            const chat = chats.find(c => c.id == chatId);
            if (chat) {
                if (!initialUsername) {
                    otherUserId = chat.other_user_id;
                    document.getElementById('chatHeader').textContent = chat.other_username;

                    getAvatarUrl(otherUserId).then(avatarUrl => {
                        const avatarEl = document.getElementById('headerAvatar');
                        avatarEl.innerHTML = '';
                        if (avatarUrl) {
                            const img = document.createElement('img');
                            img.src = avatarUrl;
                            img.draggable = false;
                            avatarEl.appendChild(img);
                            avatarEl.className = 'header-avatar';
                        } else {
                            avatarEl.textContent = chat.other_username[0].toUpperCase();
                            avatarEl.className = 'header-avatar ' + getUserColorClass(otherUserId);
                        }
                    });
                    fetch('/api/user_status/' + otherUserId)
                        .then(r => r.json())
                        .then(status => updateOnlineStatus(status));
                } else {
                    if (!otherUserId) otherUserId = chat.other_user_id;
                }
            }

            const fab = document.getElementById('callFab');
            fab.style.left = '';
            fab.style.top = '';
            fab.style.right = '12px';
            fab.style.transform = 'translateY(-50%)';
            if ((type === 'private' && otherUserId && otherUserId !== currentUserId) ||
                (type === 'group' && groupCreatorId && groupCreatorId !== currentUserId)) {
                fab.style.display = 'flex';
                fab.title = type === 'group' ? 'Call group creator' : 'Voice Call';
            } else {
                fab.style.display = 'none';
            }

            fetch(`/api/messages/${chatId}?limit=${MESSAGE_LIMIT}`)
                .then(r => r.json())
                .then(messages => {
                    document.querySelectorAll('.skeleton-bubble').forEach(el => el.remove());
                    if (messages.length > 0) oldestMessageId = messages[0].id;
                    messages.forEach(msg => appendMessage(msg, msg.sender_username === currentUsername));
                    document.getElementById('messagesContainer').scrollTop =
                        document.getElementById('messagesContainer').scrollHeight;
                    fixDateSeparators(msgContainer);
                });
        });
    }

    const chatItem = document.querySelector(`.chat-item[data-chat-id="${chatId}"]`);
    if (chatItem) {
        const badge = chatItem.querySelector('.unread-badge');
        if (badge) badge.remove();
    }
    socket.emit(type === 'group' ? 'group_seen' : 'seen', {
        [type === 'group' ? 'group_id' : 'chat_id']: chatId
    });

    if (window.innerWidth < 700) {
        document.getElementById('sidebar').classList.add('hidden');
    }
}

function createMessageElement(msg, isSent) {
    const row = document.createElement('div');
    row.className = 'message-row ' + (isSent ? 'sent' : 'received');
    row.dataset.messageId = msg.id;
    row.id = `message-${msg.id}`;
    let longPressJustTriggered = false;

    row.dataset.date = new Date(msg.created_at).toLocaleDateString('fa-IR', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });

    const swipeIndicator = document.createElement('div');
    swipeIndicator.className = 'swipe-indicator';
    swipeIndicator.innerHTML = '<i class="fa-solid fa-reply"></i>';
    row.appendChild(swipeIndicator);

    const bubble = document.createElement('div');
    bubble.className = 'bubble ' + (isSent ? 'sent' : 'received');
    bubble.setAttribute('dir', 'auto');

    if (activeChatType === 'group' && !isSent) {
        const senderName = document.createElement('div');
        senderName.className = 'group-sender-name ' + getUserColorClass(msg.sender_id);
        senderName.textContent = msg.sender_username;
        bubble.appendChild(senderName);
    }

    row.id = `message-${msg.id}`;
    if (msg.pending) {
        row.dataset.pending = 'true';
        bubble.style.opacity = '0.7';
        bubble.style.border = '1px dashed var(--border-color)';
    }

    if (msg.deleted) {
        renderDeletedBubble(bubble);
        row.appendChild(bubble);
        return row;
    }

    if (isEmojiOnly(msg.text)) {
        bubble.classList.add('emoji-only');
        bubble.textContent = msg.text;
        row.appendChild(bubble);
        return row;
    }

    if (msg.reply_to) {
        const replySenderId = msg.reply_to.sender_id;
        const quoteDiv = document.createElement('div');
        quoteDiv.className = 'reply-quote ' + getUserColorClass(replySenderId);
        quoteDiv.setAttribute('dir', 'auto');

        const senderSpan = document.createElement('div');
        senderSpan.className = 'reply-sender ' + getUserColorClass(replySenderId);
        senderSpan.textContent = msg.reply_to.sender_username;
        quoteDiv.appendChild(senderSpan);

        const previewSpan = document.createElement('div');
        const previewText = msg.reply_to.text.length > 60 ? msg.reply_to.text.substring(0, 60) + '...' : msg.reply_to.text;
        previewSpan.textContent = previewText;
        quoteDiv.appendChild(previewSpan);

        quoteDiv.style.cursor = 'pointer';
        quoteDiv.addEventListener('click', (e) => {
            e.stopPropagation();
            const targetId = msg.reply_to.id;
            if (targetId) {
                const targetEl = document.getElementById(`message-${targetId}`);
                if (targetEl) {
                    targetEl.scrollIntoView({
                        behavior: 'smooth',
                        block: 'center'
                    });
                    targetEl.style.transition = 'background 0.3s';
                    targetEl.style.background = 'rgba(43,156,255,0.2)';
                    setTimeout(() => {
                        targetEl.style.background = '';
                    }, 1500);
                } else {
                    console.log('Message not loaded in DOM');
                }
            }
        });

        bubble.appendChild(quoteDiv);
    }

    const time = document.createElement('span');
    time.className = 'message-time';
    time.textContent = new Date(msg.created_at).toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit'
    });

    const meta = document.createElement('span');
    meta.className = 'message-meta';
    meta.appendChild(time);

    const addLongPress = (el) => {
        el.addEventListener('mousedown', (e) => {
            if (isEditing) return;
            if (e.button !== 0) return;
            longPressTimer = setTimeout(() => {
                if (!selectionMode && isSent) {
                    longPressJustTriggered = true;
                    enterSelectionMode(msg.id);
                    setTimeout(() => {
                        longPressJustTriggered = false;
                    }, 300);
                }
                longPressTimer = null;
            }, LONG_PRESS_DURATION);
        });
        el.addEventListener('mouseup', () => {
            if (longPressTimer) {
                clearTimeout(longPressTimer);
                longPressTimer = null;
            }
        });
        el.addEventListener('mouseleave', () => {
            if (longPressTimer) {
                clearTimeout(longPressTimer);
                longPressTimer = null;
            }
        });
        el.addEventListener('touchstart', (e) => {
            if (isEditing) return;
            longPressTimer = setTimeout(() => {
                if (!selectionMode && isSent) {
                    enterSelectionMode(msg.id);
                }
                longPressTimer = null;
            }, LONG_PRESS_DURATION);
        }, {
            passive: true
        });
        el.addEventListener('touchend', () => {
            if (longPressTimer) {
                clearTimeout(longPressTimer);
                longPressTimer = null;
            }
        });
        el.addEventListener('touchcancel', () => {
            if (longPressTimer) {
                clearTimeout(longPressTimer);
                longPressTimer = null;
            }
        });
    };
    addLongPress(bubble);

    bubble.addEventListener('click', (e) => {
        if (isEditing) return;
        if (longPressJustTriggered) {
            longPressJustTriggered = false;
            return;
        }
        if (selectionMode) {
            e.stopPropagation();
            if (!isSent) {
                showToast('You can only select your own messages');
                return;
            }
            const msgId = msg.id;
            if (selectedMessages.has(msgId)) {
                selectedMessages.delete(msgId);
            } else {
                selectedMessages.add(msgId);
            }
            updateSelectionUI();
            return;
        }
        e.stopPropagation();
        const menu = document.getElementById('messageContextMenu');
        menu.style.display = 'none';

        const rect = bubble.getBoundingClientRect();
        const menuHeight = menu.offsetHeight || 150;
        const viewportHeight = window.innerHeight;

        if (rect.bottom + menuHeight + 10 > viewportHeight) {
            menu.style.top = (rect.top - menuHeight - 5) + 'px';
        } else {
            menu.style.top = (rect.bottom + 5) + 'px';
        }

        const menuWidth = menu.offsetWidth || 130;
        if (rect.left + menuWidth > window.innerWidth) {
            menu.style.left = (window.innerWidth - menuWidth - 10) + 'px';
        } else {
            menu.style.left = rect.left + 'px';
        }

        menu.currentMessage = {
            msg,
            isSent
        };
        const editBtn = menu.querySelector('[data-action="edit"]');
        const deleteBtn = menu.querySelector('[data-action="delete"]');

        if (isSent) {
            if (editBtn) editBtn.style.display = 'flex';
            if (deleteBtn) deleteBtn.style.display = 'flex';
        } else {
            if (editBtn) editBtn.style.display = 'none';
            if (deleteBtn) deleteBtn.style.display = 'none';
        }

        menu.style.display = 'block';

        const closeMenu = (ev) => {
            if (!menu.contains(ev.target) && ev.target !== bubble) {
                menu.style.display = 'none';
                document.removeEventListener('click', closeMenu);
            }
        };
        setTimeout(() => document.addEventListener('click', closeMenu), 10);
    });

    if (isSent) {
        const ticks = document.createElement('span');
        ticks.className = 'msg-ticks';
        const seenBy = msg.seen_by || [];

        let seen = false;
        if (activeChatType === 'group') {
            seen = seenBy.length > 0;
        } else {
            seen = seenBy.includes(otherUserId);
        }

        ticks.innerHTML = seen ?
            `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#4fc3f7" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#4fc3f7" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-left:-10px;"><polyline points="20 6 9 17 4 12"/></svg>` :
            `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color:#aaa;"><polyline points="20 6 9 17 4 12"/></svg>`;
        meta.appendChild(ticks);
    }

    if (msg.attachment) {
        const att = msg.attachment;

        if (att.type === 'image') {
            const wrapper = document.createElement('div');
            wrapper.className = 'message-image-wrapper';

            const img = document.createElement('img');
            img.src = att.url;
            img.className = 'message-image';
            img.alt = 'Image';
            img.addEventListener('click', (e) => {
                e.stopPropagation();
                openLightbox(att.url);
            });
            wrapper.appendChild(img);

            const downloadBtn = document.createElement('button');
            downloadBtn.className = 'download-image-btn';
            downloadBtn.innerHTML = '<i class="fa-solid fa-download"></i>';
            downloadBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                downloadAttachment(att.url, 'image.jpg');
            });
            wrapper.appendChild(downloadBtn);

            bubble.appendChild(wrapper);
        } else if (att.type === 'voice') {
            const player = document.createElement('div');
            player.className = 'voice-player';

            const playBtn = document.createElement('button');
            playBtn.className = 'voice-play-btn';
            playBtn.innerHTML = '<i class="fa-solid fa-play"></i>';

            const canvas = document.createElement('canvas');
            canvas.className = 'voice-waveform-canvas';
            canvas.width = 200;
            canvas.height = 40;

            let peaks = null;
            let isWaveformReady = false;

            async function loadPeaks() {
                if (peaks) return peaks;
                try {
                    const response = await fetch(att.url);
                    const arrayBuffer = await response.arrayBuffer();
                    const audioContext = new(window.AudioContext || window.webkitAudioContext)();
                    const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
                    const rawData = audioBuffer.getChannelData(0);
                    const samples = 80;
                    const blockSize = Math.floor(rawData.length / samples);
                    const tempPeaks = [];
                    for (let i = 0; i < samples; i++) {
                        let sum = 0;
                        for (let j = 0; j < blockSize; j++) {
                            const idx = i * blockSize + j;
                            if (idx < rawData.length) sum += Math.abs(rawData[idx]);
                        }
                        tempPeaks.push(sum / blockSize);
                    }
                    const maxPeak = Math.max(...tempPeaks) || 1;
                    peaks = tempPeaks.map(p => p / maxPeak);

                    const dur = audioBuffer.duration || 0;
                    durationSpan.textContent = `0:00 / ${formatTime(dur)}`;
                } catch (e) {
                    peaks = new Array(80).fill(0.5);
                }
                isWaveformReady = true;
                drawWaveform(canvas, peaks, 0);
                return peaks;
            }
            loadPeaks();

            drawWaveform(canvas, null, 0);

            canvas.addEventListener('click', (e) => {
                if (!currentAudio) return;
                e.stopPropagation();
                const rect = canvas.getBoundingClientRect();
                const ratio = (e.clientX - rect.left) / rect.width;
                const audio = document.getElementById('voiceAudio');
                audio.currentTime = ratio * (audio.duration || 0);
            });

            const durationSpan = document.createElement('span');
            durationSpan.className = 'voice-duration';
            durationSpan.textContent = '0:00';

            const downloadBtn = document.createElement('button');
            downloadBtn.className = 'voice-download-btn';
            downloadBtn.innerHTML = '<i class="fa-solid fa-download"></i>';
            downloadBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                downloadAttachment(att.url, 'voice_message.' + (att.url.split('.').pop()));
            });

            playBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                if (!peaks) {
                    peaks = await loadPeaks();
                }
                toggleVoicePlayback(att.url, playBtn, canvas, peaks, durationSpan);
            });

            player.appendChild(playBtn);
            player.appendChild(canvas);
            player.appendChild(durationSpan);
            player.appendChild(downloadBtn);
            bubble.appendChild(player);
        }
    }

    if (msg.text && msg.text.trim().length > 0) {
        if (msg.attachment) {
            const divider = document.createElement('div');
            divider.className = 'attachment-divider';
            bubble.appendChild(divider);
        }

        if (msg.text && msg.text.startsWith('GAME_INVITE:')) {
            try {
                const inviteData = JSON.parse(msg.text.slice(12));
                const inviteDiv = document.createElement('div');
                inviteDiv.className = 'game-invite';

                const textSpan = document.createElement('span');
                textSpan.className = 'invite-text';
                textSpan.textContent = `🎮 ${escapeHtml(inviteData.sender)} invited you to play!`;
                inviteDiv.appendChild(textSpan);

                const playBtn = document.createElement('button');
                playBtn.textContent = 'Play';
                playBtn.onclick = () => window.open(`/douz/?room=${encodeURIComponent(inviteData.room)}`, '_blank');
                inviteDiv.appendChild(playBtn);

                bubble.appendChild(inviteDiv);
            } catch (err) {
                const safeText = escapeHtml(msg.text);
                const withBreaks = safeText.replace(/\n/g, '<br>');
                const withLinks = withBreaks.replace(
                    /(https?:\/\/[^\s<]+)/g,
                    '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
                );
                const textSpan = document.createElement('span');
                textSpan.className = 'msg-text';
                textSpan.innerHTML = withLinks;
                bubble.appendChild(textSpan);
            }
        } else {
            const safeText = escapeHtml(msg.text);
            const withBreaks = safeText.replace(/\n/g, '<br>');
            const withLinks = withBreaks.replace(
                /(https?:\/\/[^\s<]+)/g,
                '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
            );
            const textSpan = document.createElement('span');
            textSpan.className = 'msg-text';
            textSpan.innerHTML = withLinks;
            bubble.appendChild(textSpan);
        }
    }

    bubble.appendChild(meta);

    if (msg.reactions && Object.keys(msg.reactions).length > 0) {
        const reactionsContainer = document.createElement('div');
        reactionsContainer.className = 'reactions-container';
        for (const [emoji, users] of Object.entries(msg.reactions)) {
            const badge = document.createElement('span');
            badge.className = 'reaction-badge';
            if (users.includes(currentUserId)) badge.classList.add('active');
            badge.innerHTML = `${emoji} <span class="reaction-count">${users.length}</span>`;
            badge.addEventListener('click', (e) => {
                e.stopPropagation();
                toggleReaction(msg.id, emoji);
            });
            reactionsContainer.appendChild(badge);
        }
        bubble.appendChild(reactionsContainer);
    }

    if (msg.edited) {
        const editedSpan = document.createElement('span');
        editedSpan.className = 'edited-label';
        editedSpan.textContent = ' (edited)';
        bubble.appendChild(editedSpan);
    }

    row.appendChild(bubble);

    let swipeStartX = 0,
        swipeStartY = 0,
        swipeMoved = false;

    row.addEventListener('touchstart', (e) => {
        swipeStartX = e.changedTouches[0].screenX;
        swipeStartY = e.changedTouches[0].screenY;
        swipeMoved = false;
    }, {
        passive: true
    });

    row.addEventListener('touchmove', (e) => {
        if (longPressTimer) {
            clearTimeout(longPressTimer);
            longPressTimer = null;
        }
        const touchX = e.changedTouches[0].screenX;
        const touchY = e.changedTouches[0].screenY;
        const dx = touchX - swipeStartX;
        const dy = touchY - swipeStartY;

        if (Math.abs(dx) > Math.abs(dy) && dx < -10) {
            e.preventDefault();
            swipeMoved = true;
            const translateX = Math.max(dx, -40);
            bubble.style.transform = `translateX(${translateX}px)`;
            row.classList.add('swiped');
        }
    }, {
        passive: false
    });

    row.addEventListener('touchend', (e) => {
        if (!swipeMoved) return;

        const touchEndX = e.changedTouches[0].screenX;
        const dx = touchEndX - swipeStartX;

        bubble.style.transform = '';
        row.classList.remove('swiped');
        swipeMoved = false;

        if (dx < -50) {
            e.stopPropagation();
            replyToMessage = msg;
            const previewText = msg.text.length > 40 ? msg.text.substring(0, 40) + '...' : msg.text;
            document.getElementById('replyText').textContent = previewText;
            document.getElementById('replyPreview').classList.add('active');
            document.getElementById('chatInput').focus();
        }
    });

    return row;
}

function appendMessage(msg, isSent) {
    const container = document.getElementById('messagesContainer');
    const row = createMessageElement(msg, isSent);
    container.appendChild(row);
    container.scrollTop = container.scrollHeight;
    addDateSeparatorIfNeeded(container);
}

function fixDateSeparators(container) {
    container.querySelectorAll('.date-separator').forEach(el => el.remove());

    const rows = [...container.querySelectorAll('.message-row')];
    if (rows.length === 0) return;

    let lastDate = null;
    rows.forEach(row => {
        const date = row.dataset.date;
        if (date && date !== lastDate) {
            lastDate = date;
            const separator = document.createElement('div');
            separator.className = 'date-separator';
            separator.style.cursor = 'pointer';
            separator.dataset.date = date;

            const span = document.createElement('span');
            span.textContent = date;
            separator.appendChild(span);
            container.insertBefore(separator, row);
        }
    });

    container.querySelectorAll('.date-separator').forEach((separator, index, all) => {
        if (index === 0) return;

        separator.addEventListener('click', async function goToPrevDay() {
            const previousSeparator = all[index - 1];
            const targetDate = previousSeparator.dataset.date;

            async function loadMoreUntilTarget() {
                if (!oldestMessageId || !activeChatId) return;
                if (isLoadingMore) return;
                isLoadingMore = true;

                try {
                    const url = activeChatType === 'group' ?
                        `/api/group_messages/${activeChatId}?limit=${SCROLL_LOAD_LIMIT}&before_id=${oldestMessageId}` :
                        `/api/messages/${activeChatId}?limit=${SCROLL_LOAD_LIMIT}&before_id=${oldestMessageId}`;

                    const resp = await fetch(url);
                    const older = await resp.json();

                    if (!older.length) {
                        oldestMessageId = null;
                        return;
                    }

                    const fragment = document.createDocumentFragment();
                    older.forEach(msg => {
                        const isSent = msg.sender_username === currentUsername;
                        fragment.appendChild(createMessageElement(msg, isSent));
                    });

                    const mc = document.getElementById('messagesContainer');
                    mc.insertBefore(fragment, mc.firstChild);
                    oldestMessageId = older[0].id;

                    fixDateSeparators(mc);

                    const freshSeparators = [...mc.querySelectorAll('.date-separator')];
                    const found = freshSeparators.some(s => s.dataset.date === targetDate);

                    if (!found && oldestMessageId) {
                        await loadMoreUntilTarget();
                    }
                } catch (e) {
                    console.error(e);
                } finally {
                    isLoadingMore = false;
                }
            }

            await loadMoreUntilTarget();

            const currentContainer = document.getElementById('messagesContainer');
            const freshSep = [...currentContainer.querySelectorAll('.date-separator')]
                .find(s => s.dataset.date === targetDate);
            if (freshSep && freshSep.nextElementSibling) {
                freshSep.nextElementSibling.scrollIntoView({
                    behavior: 'smooth',
                    block: 'center'
                });
            }
        });
    });
}

function addDateSeparatorIfNeeded(container) {
    const rows = [...container.querySelectorAll('.message-row')];
    if (rows.length === 0) return;
    const lastRow = rows[rows.length - 1];
    const prevRow = rows[rows.length - 2];
    const lastDate = lastRow.dataset.date;

    if (prevRow && prevRow.dataset.date === lastDate) {
        return;
    }

    const separator = document.createElement('div');
    separator.className = 'date-separator';
    separator.dataset.date = lastDate;
    separator.style.cursor = 'pointer';

    const span = document.createElement('span');
    span.textContent = lastDate;
    separator.appendChild(span);

    container.insertBefore(separator, lastRow);

    separator.addEventListener('click', async function goToPrevDay() {
        const allSeps = [...container.querySelectorAll('.date-separator')];
        const index = allSeps.indexOf(separator);
        if (index > 0) {
            const previousSep = allSeps[index - 1];
            const targetDate = previousSep.dataset.date;

            async function loadMoreUntilTarget() {
                if (!oldestMessageId || !activeChatId) return;
                if (isLoadingMore) return;
                isLoadingMore = true;
                try {
                    const url = activeChatType === 'group' ?
                        `/api/group_messages/${activeChatId}?limit=${SCROLL_LOAD_LIMIT}&before_id=${oldestMessageId}` :
                        `/api/messages/${activeChatId}?limit=${SCROLL_LOAD_LIMIT}&before_id=${oldestMessageId}`;
                    const resp = await fetch(url);
                    const older = await resp.json();
                    if (!older.length) {
                        oldestMessageId = null;
                        return;
                    }
                    const fragment = document.createDocumentFragment();
                    older.forEach(msg => {
                        const isSent = msg.sender_username === currentUsername;
                        fragment.appendChild(createMessageElement(msg, isSent));
                    });
                    container.insertBefore(fragment, container.firstChild);
                    oldestMessageId = older[0].id;
                    fixDateSeparators(container);
                    const freshSeps = [...container.querySelectorAll('.date-separator')];
                    const found = freshSeps.some(s => s.dataset.date === targetDate);
                    if (!found && oldestMessageId) {
                        await loadMoreUntilTarget();
                    }
                } catch (e) {
                    console.error(e);
                } finally {
                    isLoadingMore = false;
                }
            }

            await loadMoreUntilTarget();
            const freshSeps = [...container.querySelectorAll('.date-separator')];
            const targetSep = freshSeps.find(s => s.dataset.date === targetDate);
            if (targetSep && targetSep.nextElementSibling) {
                targetSep.nextElementSibling.scrollIntoView({
                    behavior: 'smooth',
                    block: 'center'
                });
            }
        }
    });
}

function rebuildDateSeparators(container) {
    const rows = [...container.querySelectorAll('.message-row')];
    let lastDate = null;
    rows.forEach(row => {
        const date = row.dataset.date;
        if (date && date !== lastDate) {
            lastDate = date;
            const separator = document.createElement('div');
            separator.className = 'date-separator';
            const span = document.createElement('span');
            span.textContent = date;
            separator.appendChild(span);
            container.insertBefore(separator, row);
        }
    });
}

function updateAllMyAvatars(url) {
    document.querySelectorAll('.chat-item').forEach(item => {
        const otherUserId = parseInt(item.dataset.otherUserId);
        if (otherUserId === currentUserId) {
            const avatar = item.querySelector('.avatar');
            if (avatar) {
                avatar.innerHTML = '';
                if (url) {
                    const img = document.createElement('img');
                    img.src = url;
                    img.alt = currentUsername ? currentUsername[0] : '?';
                    img.draggable = false;
                    avatar.appendChild(img);
                    avatar.style.background = 'transparent';
                    avatar.className = 'avatar';
                } else {
                    avatar.style.background = '';
                    avatar.className = 'avatar ' + getUserColorClass(currentUserId);
                    avatar.textContent = currentUsername ? currentUsername[0].toUpperCase() : '?';
                }
            }
        }
    });

    if (activeChatId === currentUserId && activeChatType === 'private') {
        const headerAvatar = document.getElementById('headerAvatar');
        if (headerAvatar) {
            headerAvatar.innerHTML = '';
            if (url) {
                const img = document.createElement('img');
                img.src = url;
                img.draggable = false;
                headerAvatar.appendChild(img);
                headerAvatar.style.background = 'transparent';
                headerAvatar.className = 'header-avatar';
            } else {
                headerAvatar.style.background = '';
                headerAvatar.className = 'header-avatar ' + getUserColorClass(currentUserId);
                headerAvatar.textContent = currentUsername ? currentUsername[0].toUpperCase() : '?';
            }
        }
    }

    const membersModal = document.getElementById('membersModal');
    if (membersModal.style.display === 'flex') {
        document.querySelectorAll('#membersList .member-avatar').forEach(avatar => {
            if (avatar.parentElement?.querySelector('span')?.textContent === currentUsername) {
                avatar.innerHTML = '';
                if (url) {
                    const img = document.createElement('img');
                    img.src = url;
                    img.draggable = false;
                    avatar.appendChild(img);
                    avatar.style.background = 'transparent';
                    avatar.className = 'member-avatar';
                } else {
                    avatar.style.background = '';
                    avatar.className = 'member-avatar ' + getUserColorClass(currentUserId);
                    avatar.textContent = currentUsername ? currentUsername[0].toUpperCase() : '?';
                }
            }
        });
    }
}

function renderAvatar(container, userId, avatarUrl, initial) {
    container.innerHTML = '';
    if (avatarUrl) {
        const img = document.createElement('img');
        img.src = avatarUrl;
        img.alt = initial;
        img.draggable = false;
        container.appendChild(img);
    } else {
        container.textContent = initial;
        container.className += ' ' + getUserColorClass(userId);
    }
}

function cancelReply() {
    replyToMessage = null;
    document.getElementById('replyPreview').classList.remove('active');
}

async function sendChatMessage() {
    const text = document.getElementById('chatInput').value.trim();
    if (!text && !selectedFile && !replyToMessage) return;
    if (!activeChatId) return;

    const sendBtn = document.getElementById('sendChatBtn');
    const sendIcon = document.getElementById('sendIcon');
    const sendSpinner = document.getElementById('sendSpinner');

    if (!socket.connected) {
        showToast('Connection lost. Reconnecting...');
        resetSendButton(sendBtn, sendIcon, sendSpinner);
        return;
    }

    sendBtn.disabled = true;
    sendIcon.style.display = 'none';
    sendSpinner.style.display = 'inline-block';

    let attachmentPayload = null;
    let sendPayload = {
        text: text,
        [activeChatType === 'group' ? 'group_id' : 'chat_id']: activeChatId
    };
    if (replyToMessage) {
        sendPayload.reply_to_message_id = replyToMessage.id;
        cancelReply();
    }

    if (selectedFile) {
        try {
            const formData = new FormData();
            formData.append('file', selectedFile);
            const resp = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            const data = await resp.json();
            if (data.success) {
                attachmentPayload = data.attachment;
            } else {
                showToast(data.error || 'Upload failed');
                resetSendButton(sendBtn, sendIcon, sendSpinner);
                return;
            }
        } catch (e) {
            showToast('Upload connection error');
            resetSendButton(sendBtn, sendIcon, sendSpinner);
            return;
        }
    }

    sendPayload.attachment = attachmentPayload;

    const tempMsg = {
        id: 'pending-' + Date.now(),
        chat_id: activeChatId,
        text: text || '',
        sender_username: currentUsername,
        sender_id: currentUserId,
        created_at: new Date().toISOString(),
        seen_by: [],
        attachment: attachmentPayload,
        reply_to: replyToMessage ? {
            id: replyToMessage.id,
            text: replyToMessage.text,
            sender_username: replyToMessage.sender_username,
            sender_id: replyToMessage.sender_id
        } : null,
        reactions: {},
        edited: false,
        deleted: false,
        pending: true
    };

    appendMessage(tempMsg, true);

    document.getElementById('chatInput').value = '';
    autoResize(document.getElementById('chatInput'));
    cancelAttachment();
    document.getElementById('chatInput').focus();
    resetSendButton(sendBtn, sendIcon, sendSpinner);

    socket.emit(activeChatType === 'group' ? 'send_group_message' : 'send_chat_message', sendPayload);
}

function resetSendButton(btn, icon, spinner) {
    btn.disabled = false;
    icon.style.display = '';
    spinner.style.display = 'none';
}

function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 100) + 'px';
}

function updateActionSwitch() {
    const input = document.getElementById('chatInput');
    const text = input.value.trim();
    const hasContent = text.length > 0 || selectedFile !== null;
    const sw = document.getElementById('actionSwitch');
    if (hasContent) {
        sw.classList.add('text-mode');
    } else {
        sw.classList.remove('text-mode');
    }
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

document.getElementById('logoutSidebarBtn').addEventListener('click', async () => {
    try {
        await fetch('/api/logout', {
            method: 'POST'
        });
        window.location.href = '/login';
    } catch (e) {
        showToast('Logout failed');
    }
});

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
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                username: newName
            })
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
    closeAllPopups();
    if (isLoadingMore) return;
    if (messagesContainerEl.scrollTop < 30 && oldestMessageId && activeChatId) {
        isLoadingMore = true;

        const prevScrollHeight = messagesContainerEl.scrollHeight;
        const prevScrollTop = messagesContainerEl.scrollTop;

        fetch(`/api/messages/${activeChatId}?limit=${SCROLL_LOAD_LIMIT}&before_id=${oldestMessageId}`)
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
                fixDateSeparators(messagesContainerEl);
                isLoadingMore = false;
            });
    }
});
playDouzBtn.addEventListener('click', async () => {
    if (!activeChatId) {
        showToast('No active chat selected');
        return;
    }
    try {
        const resp = await fetch('/api/create_douz_room', {
            method: 'POST'
        });
        const data = await resp.json();
        if (data.room) {
            socket.emit('send_chat_message', {
                chat_id: activeChatId,
                text: `GAME_INVITE:${JSON.stringify({ room: data.room, sender: currentUsername })}`
            });
        } else {
            showToast('Failed to create game room');
        }
    } catch (e) {
        showToast('Failed to create game room');
    }
});

const settingsMenuBtn = document.getElementById('settingsMenuBtn');
const settingsDropdown = document.getElementById('settingsDropdown');

settingsMenuBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    settingsDropdown.style.display = (settingsDropdown.style.display === 'block') ? 'none' : 'block';
});

document.addEventListener('click', (e) => {
    if (!settingsDropdown.contains(e.target) && e.target !== settingsMenuBtn) {
        settingsDropdown.style.display = 'none';
    }
});

const sessionsSidebarBtn = document.getElementById('sessionsSidebarBtn');
const sessionsModal = document.getElementById('sessionsModal');
const sessionsList = document.getElementById('sessionsList');
const closeSessionsModal = document.getElementById('closeSessionsModal');

sessionsSidebarBtn.addEventListener('click', async () => {
    try {
        const resp = await fetch('/api/sessions');
        const sessions = await resp.json();
        renderSessions(sessions);
        sessionsModal.style.display = 'flex';
    } catch (e) {
        showToast('Failed to load sessions');
    }
});

closeSessionsModal.addEventListener('click', () => {
    sessionsModal.style.display = 'none';
});

function renderSessions(sessions) {
    sessionsList.innerHTML = '';
    sessions.forEach(s => {
        const item = document.createElement('div');
        item.className = 'session-item';

        const infoDiv = document.createElement('div');
        infoDiv.className = 'session-info';

        const ipSpan = document.createElement('span');
        ipSpan.textContent = s.ip || 'Unknown IP';
        infoDiv.appendChild(ipSpan);

        const uaSpan = document.createElement('span');
        uaSpan.style.fontSize = '0.7rem';
        uaSpan.style.color = 'var(--text-secondary)';
        uaSpan.textContent = s.user_agent ? s.user_agent.substring(0, 50) : 'Unknown device';
        infoDiv.appendChild(uaSpan);

        const timeSpan = document.createElement('span');
        timeSpan.style.fontSize = '0.65rem';
        timeSpan.textContent = new Date(s.created_at).toLocaleString();
        infoDiv.appendChild(timeSpan);

        if (s.is_current) {
            const badge = document.createElement('span');
            badge.className = 'session-badge';
            badge.textContent = 'Current';
            infoDiv.appendChild(badge);
            item.appendChild(infoDiv);
        } else {
            item.appendChild(infoDiv);

            const terminateBtn = document.createElement('button');
            terminateBtn.textContent = 'Terminate';
            terminateBtn.addEventListener('click', async () => {
                try {
                    const res = await fetch(`/api/sessions/${s.token}`, {
                        method: 'DELETE'
                    });
                    if (res.ok) {
                        item.remove();
                        showToast('Session terminated', true);
                    } else {
                        showToast('Failed to terminate session');
                    }
                } catch (e) {
                    showToast('Connection error');
                }
            });
            item.appendChild(terminateBtn);
        }

        sessionsList.appendChild(item);
    });
}

document.getElementById('newGroupBtn').addEventListener('click', () => {
    document.getElementById('newGroupModal').style.display = 'flex';
    document.getElementById('groupNameInput').value = '';
    document.getElementById('selectedMembers').innerHTML = '';
    selectedMembers = [];
});

document.getElementById('cancelGroupBtn').addEventListener('click', () => {
    document.getElementById('newGroupModal').style.display = 'none';
});

function searchMembersForGroup() {
    const q = document.getElementById('groupMemberSearch').value.trim();
    const resultsDiv = document.getElementById('groupMemberSearchResults');
    if (!q) {
        resultsDiv.innerHTML = '';
        return;
    }

    fetch(`/api/search_users?q=${encodeURIComponent(q)}`)
        .then(r => r.json())
        .then(users => {
            resultsDiv.innerHTML = '';
            users.forEach(u => {
                if (u.id === currentUserId || selectedMembers.some(m => m.id === u.id)) return;

                const div = document.createElement('div');
                div.className = 'search-result-item';
                div.textContent = u.username;
                div.setAttribute('dir', 'auto');
                div.addEventListener('click', () => {
                    selectedMembers.push(u);
                    renderSelectedMembers();
                    resultsDiv.innerHTML = '';
                    document.getElementById('groupMemberSearch').value = '';
                });
                resultsDiv.appendChild(div);
            });
        });
}

function renderSelectedMembers() {
    const container = document.getElementById('selectedMembers');
    container.innerHTML = '';
    selectedMembers.forEach((m, idx) => {
        const tag = document.createElement('span');
        tag.style = 'display:inline-flex;align-items:center;background:var(--hover-bg);padding:0.2rem 0.5rem;border-radius:0.5rem;font-size:0.8rem;gap:0.3rem;';
        tag.textContent = m.username;
        const removeBtn = document.createElement('span');
        removeBtn.textContent = '✕';
        removeBtn.style = 'cursor:pointer;color:#ff4d4d;font-weight:bold;';
        removeBtn.addEventListener('click', () => {
            selectedMembers.splice(idx, 1);
            renderSelectedMembers();
        });
        tag.appendChild(removeBtn);
        container.appendChild(tag);
    });
}

document.getElementById('createGroupBtn').addEventListener('click', async () => {
    const name = document.getElementById('groupNameInput').value.trim();
    if (!name) {
        showToast('Please enter a group name');
        return;
    }
    if (selectedMembers.length === 0) {
        showToast('Add at least one member');
        return;
    }
    try {
        const resp = await fetch('/api/create_group', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: name,
                members: selectedMembers.map(m => m.id)
            })
        });
        if (resp.ok) {
            document.getElementById('newGroupModal').style.display = 'none';
            loadChats();
            showToast('Group created', true);
        } else {
            const data = await resp.json();
            showToast(data.error || 'Failed to create group');
        }
    } catch (e) {
        showToast('Connection error');
    }
});

const membersModal = document.getElementById('membersModal');
const membersList = document.getElementById('membersList');
const closeMembersModal = document.getElementById('closeMembersModal');
const viewMembersBtn = document.getElementById('viewMembersBtn');

viewMembersBtn.addEventListener('click', () => {
    const membersData = viewMembersBtn.dataset.members;
    if (!membersData) return;
    const members = JSON.parse(membersData);

    membersList.innerHTML = '';
    members.forEach(member => {
        const item = document.createElement('div');
        item.className = 'member-item';

        const avatar = document.createElement('div');
        avatar.className = 'member-avatar';
        if (member.avatar_url) {
            const img = document.createElement('img');
            img.src = member.avatar_url;
            img.alt = member.username[0];
            img.draggable = false;
            avatar.appendChild(img);
        } else {
            avatar.className += ' ' + getUserColorClass(member.id);
            avatar.textContent = member.username[0].toUpperCase();
        }
        item.appendChild(avatar);

        const nameSpan = document.createElement('span');
        nameSpan.textContent = member.username;
        item.appendChild(nameSpan);

        if (member.id === currentUserId) {
            const badge = document.createElement('span');
            badge.textContent = '(You)';
            badge.style.fontSize = '0.7rem';
            badge.style.color = 'var(--text-secondary)';
            item.appendChild(badge);
        }

        membersList.appendChild(item);
    });

    membersModal.style.display = 'flex';
});

closeMembersModal.addEventListener('click', () => {
    membersModal.style.display = 'none';
});

const renameGroupBtn = document.getElementById('renameGroupBtn');

renameGroupBtn.addEventListener('click', () => {
    const newName = prompt('Enter new group name:');
    if (newName && newName.trim() !== '') {
        fetch(`/api/rename_group/${activeChatId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: newName.trim()
            })
        }).then(r => r.json()).then(data => {
            if (data.success) {
                document.getElementById('chatHeader').textContent = newName.trim();
                loadChats();
            } else {
                showToast(data.error || 'Failed to rename');
            }
        });
    }
});

const inviteGroupBtn = document.getElementById('inviteGroupBtn');

inviteGroupBtn.addEventListener('click', async () => {
    const resp = await fetch(`/api/group_invite/${activeChatId}`);
    const data = await resp.json();
    if (data.invite_code) {
        navigator.clipboard.writeText(data.link);
        showToast('Invite link copied!', true);
    } else {
        showToast('Failed to get invite link');
    }
});

const changeAvatarSidebarBtn = document.getElementById('changeAvatarSidebarBtn');
const avatarModal = document.getElementById('avatarModal');
const avatarFileInput = document.getElementById('avatarFileInput');
const avatarPreview = document.getElementById('avatarPreview');
const uploadAvatarBtn = document.getElementById('uploadAvatarBtn');
const removeAvatarBtn = document.getElementById('removeAvatarBtn');
const closeAvatarModal = document.getElementById('closeAvatarModal');
const avatarMsg = document.getElementById('avatarMsg');

changeAvatarSidebarBtn.addEventListener('click', () => {
    fetch('/api/whoami').then(r => r.json()).then(d => {
        if (d.avatar_url) {
            avatarPreview.src = d.avatar_url;
        } else {
            avatarPreview.src = '';
        }
    });
    avatarModal.style.display = 'flex';
});

avatarFileInput.addEventListener('change', () => {
    const file = avatarFileInput.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = (e) => avatarPreview.src = e.target.result;
        reader.readAsDataURL(file);
    }
});

closeAvatarModal.addEventListener('click', () => {
    avatarModal.style.display = 'none';
});

uploadAvatarBtn.addEventListener('click', async () => {
    const file = avatarFileInput.files[0];
    if (!file) {
        avatarMsg.textContent = 'Select an image';
        return;
    }
    const formData = new FormData();
    formData.append('avatar', file);
    try {
        const resp = await fetch('/api/avatar', {
            method: 'POST',
            body: formData
        });
        const data = await resp.json();
        if (data.success) {
            updateAllMyAvatars(data.avatar_url);
            avatarModal.style.display = 'none';
            showToast('Avatar updated!', true);
        } else {
            avatarMsg.textContent = data.error || 'Upload failed';
        }
    } catch (e) {
        avatarMsg.textContent = 'Network error';
    }
});

removeAvatarBtn.addEventListener('click', async () => {
    try {
        const resp = await fetch('/api/avatar/remove', {
            method: 'POST'
        });
        const data = await resp.json();
        if (data.success) {
            updateAllMyAvatars(null);
            avatarPreview.src = '';
            showToast('Avatar removed!', true);
        } else {
            avatarMsg.textContent = data.error || 'Remove failed';
        }
    } catch (e) {
        avatarMsg.textContent = 'Network error';
    }
});

document.getElementById('attachBtn').addEventListener('click', () => {
    if (isRecordingMode) exitRecordingMode();
    document.getElementById('imageInput').click();
});

document.getElementById('imageInput').addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        selectedFile = e.target.files[0];
        updateActionSwitch();
        const reader = new FileReader();
        reader.onload = (ev) => {
            document.getElementById('previewThumb').style.backgroundImage = `url(${ev.target.result})`;
            document.getElementById('previewLabel').textContent = 'Image';
            document.getElementById('previewFilename').textContent = selectedFile.name;
            document.getElementById('attachmentPreview').classList.add('active');
            document.getElementById('sendChatBtn').style.display = 'flex';
        };
        reader.readAsDataURL(selectedFile);
    }
});

function cancelAttachment() {
    selectedFile = null;
    updateActionSwitch();
    document.getElementById('imageInput').value = '';
    document.getElementById('attachmentPreview').classList.remove('active');
}

document.querySelector('#attachmentPreview .cancel-attach').addEventListener('click', cancelAttachment);

function toggleVoicePlayback(url, playBtn, canvas, peaks, durationSpan) {
    const audio = document.getElementById('voiceAudio');

    if (currentAudio === url) {
        if (audio.paused) {
            audio.play();
            playBtn.classList.add('playing');
            playBtn.innerHTML = '<i class="fa-solid fa-pause"></i>';
            startProgressInterval(audio, canvas, peaks, durationSpan);
        } else {
            audio.pause();
            playBtn.classList.remove('playing');
            playBtn.innerHTML = '<i class="fa-solid fa-play"></i>';
            stopProgressInterval();
        }
    } else {
        if (currentAudio) {
            audio.pause();
            if (currentPlayBtn) {
                currentPlayBtn.classList.remove('playing');
                currentPlayBtn.innerHTML = '<i class="fa-solid fa-play"></i>';
            }
            stopProgressInterval();
        }
        currentAudio = url;
        currentPlayBtn = playBtn;
        currentProgress = canvas;
        currentDuration = durationSpan;
        audio.src = url;
        audio.play();
        playBtn.classList.add('playing');
        playBtn.innerHTML = '<i class="fa-solid fa-pause"></i>';
        audio.onloadedmetadata = () => {
            const dur = audio.duration || 0;
            durationSpan.textContent = `0:00 / ${formatTime(dur)}`;
        };
        audio.onended = () => {
            playBtn.classList.remove('playing');
            playBtn.innerHTML = '<i class="fa-solid fa-play"></i>';
            stopProgressInterval();
            currentAudio = null;
        };
        startProgressInterval(audio, canvas, peaks, durationSpan);
    }
}

function startProgressInterval(audio, canvas, peaks, durationSpan) {
    stopProgressInterval();
    progressInterval = setInterval(() => {
        const fraction = audio.currentTime / audio.duration;
        drawWaveform(canvas, peaks, fraction);
        durationSpan.textContent = formatTime(audio.currentTime) + ' / ' + formatTime(audio.duration);
    }, 100);
}

function stopProgressInterval() {
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
}

function seekVoice(e, progressBar) {
    if (!currentAudio) return;
    const audio = document.getElementById('voiceAudio');
    const rect = progressBar.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    audio.currentTime = ratio * (audio.duration || 0);
}

function formatTime(sec) {
    sec = Math.round(sec || 0);
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return m + ':' + (s < 10 ? '0' : '') + s;
}

function openLightbox(url) {
    const overlay = document.getElementById('lightboxOverlay');
    const img = document.getElementById('lightboxImage');
    img.src = url;
    overlay.style.display = 'flex';
    document.addEventListener('keydown', closeLightboxEsc);
}

function closeLightbox() {
    document.getElementById('lightboxOverlay').style.display = 'none';
    document.getElementById('lightboxImage').src = '';
    document.removeEventListener('keydown', closeLightboxEsc);
}

function closeLightboxEsc(e) {
    if (e.key === 'Escape') closeLightbox();
}

function downloadAttachment(url, filename) {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || 'file';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

document.getElementById('deleteSelectedBtn').addEventListener('click', () => {
    const count = selectedMessages.size;
    if (count === 0) return;
    if (!confirm(`Delete ${count} message(s)?`)) return;
    selectedMessages.forEach(msgId => {
        fetch(`/api/messages/${msgId}`, {
            method: 'DELETE'
        }).catch(() => {});
    });
    exitSelectionMode();
});

document.getElementById('cancelSelectionBtn').addEventListener('click', exitSelectionMode);

messagesContainerEl.addEventListener('click', (e) => {
    if (selectionMode && !e.target.closest('.message-row') && !e.target.closest('#selectionToolbar')) {
        exitSelectionMode();
    }
});

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && selectionMode) {
        exitSelectionMode();
    }
});

const rtcConfig = {
    iceServers: [{
        urls: 'stun:stun.l.google.com:19302'
    }, {
        urls: 'stun:stun1.l.google.com:19302'
    }]
};

let localCallStream = null;
let peerConnection = null;
let isInCall = false;
let isCaller = false;
let callPeerId = null;
let callTimerInterval = null;
let callStartTime = null;
let remoteAudioElement = null;
let callLogged = false;
let isCallEnding = false;

function showIncomingCallModal(callerName) {
    document.getElementById('incomingCallerName').textContent = callerName;
    document.getElementById('incomingCallModal').style.display = 'flex';
}

function hideIncomingCallModal() {
    document.getElementById('incomingCallModal').style.display = 'none';
}

function showActiveCallBar() {
    document.getElementById('activeCallBar').style.display = 'flex';
    startCallTimer();
}

function hideActiveCallBar() {
    document.getElementById('activeCallBar').style.display = 'none';
    stopCallTimer();
}

function startCallTimer() {
    callStartTime = Date.now();
    updateCallTimer();
    callTimerInterval = setInterval(updateCallTimer, 1000);
}

function stopCallTimer() {
    if (callTimerInterval) {
        clearInterval(callTimerInterval);
        callTimerInterval = null;
    }
}

function updateCallTimer() {
    const elapsed = Math.floor((Date.now() - callStartTime) / 1000);
    const mins = Math.floor(elapsed / 60);
    const secs = elapsed % 60;
    document.getElementById('activeCallTimer').textContent =
        `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

async function startCall(peerId) {
    if (!window.callAudioCtx) {
        window.callAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (window.callAudioCtx.state === 'suspended') {
        await window.callAudioCtx.resume();
    }

    const tempCtx = new(window.AudioContext || window.webkitAudioContext)();
    if (tempCtx.state === 'suspended') {
        await tempCtx.resume();
    }
    if (isInCall) return;
    callPeerId = peerId;
    isCaller = true;
    try {
        localCallStream = await navigator.mediaDevices.getUserMedia({
            audio: true
        });
    } catch (err) {
        showToast('Microphone access denied');
        return;
    }
    createPeerConnection();
    localCallStream.getTracks().forEach(track => peerConnection.addTrack(track, localCallStream));
    await new Promise(resolve => setTimeout(resolve, 200));

    const offer = await peerConnection.createOffer();
    await peerConnection.setLocalDescription(offer);
    socket.emit('call_offer', {
        to: peerId,
        sdp: offer
    });
    socket.emit('call_user', {
        to: peerId
    });

    isInCall = true;
    callLogged = false;
    isCallEnding = false;
}

async function applyRemoteOffer(sdp) {
    if (!peerConnection) return;
    await peerConnection.setRemoteDescription(new RTCSessionDescription(sdp));
    const answer = await peerConnection.createAnswer();
    await peerConnection.setLocalDescription(answer);
    socket.emit('call_answer', {
        to: callPeerId,
        sdp: answer
    });
}

async function acceptIncomingCall() {
    if (isInCall) return;
    isCaller = false;
    hideIncomingCallModal();
    try {
        localCallStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
        showToast('Microphone access denied');
        socket.emit('call_rejected', { to: callPeerId });
        return;
    }
    if (!window.callAudioCtx) {
        window.callAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (window.callAudioCtx.state === 'suspended') {
        await window.callAudioCtx.resume();
    }

    createPeerConnection();
    localCallStream.getTracks().forEach(track => peerConnection.addTrack(track, localCallStream));

    if (pendingOfferSdp) {
        await applyRemoteOffer(pendingOfferSdp);
        pendingOfferSdp = null;
    } else {
        await new Promise((resolve) => {
            pendingOfferResolver = resolve;
            setTimeout(() => {
                if (pendingOfferResolver) {
                    pendingOfferResolver();
                    pendingOfferResolver = null;
                }
            }, 12000);
        });
        if (pendingOfferSdp) {
            await applyRemoteOffer(pendingOfferSdp);
            pendingOfferSdp = null;
        }
    }

    socket.emit('call_accepted', {
        to: callPeerId
    });
    isInCall = true;
    callLogged = false;
    isCallEnding = false;
    showActiveCallBar();
}

function rejectIncomingCall() {
    socket.emit('call_rejected', {
        to: callPeerId
    });
    hideIncomingCallModal();
    callPeerId = null;
    isCallEnding = false;
}

function toggleMute() {
    if (!localCallStream) return;
    isMuted = !isMuted;
    localCallStream.getAudioTracks().forEach(track => {
        track.enabled = !isMuted;
    });

    const muteBtn = document.getElementById('muteCallBtn');
    if (isMuted) {
        muteBtn.classList.add('muted');
        muteBtn.innerHTML = '<i class="fa-solid fa-microphone-slash"></i>';
        muteBtn.title = 'Unmute microphone';
    } else {
        muteBtn.classList.remove('muted');
        muteBtn.innerHTML = '<i class="fa-solid fa-microphone"></i>';
        muteBtn.title = 'Mute microphone';
    }
}

function endCall() {
    if (isCallEnding) return;
    isCallEnding = true;

    if (!callLogged && isCaller && callStartTime && activeChatId) {
        callLogged = true;
        const endTime = Date.now();
        const durationSec = Math.floor((endTime - callStartTime) / 1000);
        const durationStr = formatTime(durationSec);
        const startTimeStr = new Date(callStartTime).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit'
        });
        const endTimeStr = new Date(endTime).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit'
        });
        const logText = `📞 Voice Call\nStarted: ${startTimeStr}\nEnded: ${endTimeStr}\nDuration: ${durationStr}`;

        const payload = {
            text: logText
        };
        if (activeChatType === 'group') {
            payload.group_id = activeChatId;
            socket.emit('send_group_message', payload);
        } else {
            payload.chat_id = activeChatId;
            socket.emit('send_chat_message', payload);
        }
    }

    isMuted = false;
    const muteBtn = document.getElementById('muteCallBtn');
    if (muteBtn) {
        muteBtn.classList.remove('muted');
        muteBtn.innerHTML = '<i class="fa-solid fa-microphone"></i>';
    }

    if (peerConnection) {
        peerConnection.close();
        peerConnection = null;
    }
    if (localCallStream) {
        localCallStream.getTracks().forEach(track => track.stop());
        localCallStream = null;
    }
    if (remoteAudioElement) {
        remoteAudioElement.srcObject = null;
        remoteAudioElement.remove();
        remoteAudioElement = null;
    }
    if (window.callAudioCtx) {
        window.callAudioCtx.close();
        window.callAudioCtx = null;
    }
    if (callTrackTimeout) {
        clearTimeout(callTrackTimeout);
        callTrackTimeout = null;
    }
    socket.emit('call_ended', {
        to: callPeerId
    });
    isInCall = false;
    isCaller = false;
    callPeerId = null;
    pendingOfferSdp = null;
    hideActiveCallBar();
    hideIncomingCallModal();
}

function createPeerConnection() {
    if (peerConnection) {
        peerConnection.close();
        peerConnection = null;
    }
    peerConnection = new RTCPeerConnection(rtcConfig);

    peerConnection.onicecandidate = (event) => {
        if (event.candidate) {
            socket.emit('ice_candidate', {
                to: callPeerId,
                candidate: event.candidate
            });
        }
    };

    peerConnection.ontrack = (event) => {
        if (!window.callAudioCtx) {
            window.callAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
        }
        if (window.callAudioCtx.state === 'suspended') {
            window.callAudioCtx.resume().catch(() => {});
        }

        if (remoteAudioElement) {
            remoteAudioElement.srcObject = null;
            remoteAudioElement.remove();
            remoteAudioElement = null;
        }

        remoteAudioElement = new Audio();
        remoteAudioElement.autoplay = true;
        remoteAudioElement.srcObject = event.streams[0];
        document.body.appendChild(remoteAudioElement);

        const streamNode = window.callAudioCtx.createMediaStreamSource(event.streams[0]);
        streamNode.connect(window.callAudioCtx.destination);

        let playAttempts = 0;
        const tryPlayRemote = () => {
            remoteAudioElement.play().then(() => {
                console.log('remote audio playing');
                if (callTrackTimeout) {
                    clearTimeout(callTrackTimeout);
                    callTrackTimeout = null;
                }
            }).catch(() => {
                if (playAttempts < 30) {
                    playAttempts++;
                    setTimeout(tryPlayRemote, 1000);
                }
            });
        };
        tryPlayRemote();
    };

    peerConnection.oniceconnectionstatechange = () => {
        if (peerConnection && (peerConnection.iceConnectionState === 'disconnected' ||
            peerConnection.iceConnectionState === 'failed')) {
            endCall();
            }
    };

    callTrackTimeout = setTimeout(() => {
        if (!remoteAudioElement || !remoteAudioElement.srcObject) {
            showToast('Could not connect audio');
            endCall();
        }
    }, 45000);
}

socket.on('incoming_call', (data) => {
    if (isInCall) {
        socket.emit('call_rejected', {
            to: data.from
        });
        return;
    }
    callPeerId = data.from;
    showIncomingCallModal(data.username);
});

socket.on('disconnect', () => {
    if (isInCall) endCall();
});

socket.on('call_accepted', (data) => {
    if (!isCaller) return;
});

socket.on('call_rejected', () => {
    showToast('Call declined');
    endCall();
});

socket.on('call_ended', () => {
    endCall();
});

socket.on('call_error', (data) => {
    showToast(data.msg || 'Call error');
    endCall();
});

socket.on('call_offer', async (data) => {
    if (peerConnection && peerConnection.signalingState !== 'closed') {
        await applyRemoteOffer(data.sdp);
        if (pendingOfferResolver) {
            pendingOfferResolver();
            pendingOfferResolver = null;
        }
    } else {
        pendingOfferSdp = data.sdp;
        if (pendingOfferResolver) {
            pendingOfferResolver();
            pendingOfferResolver = null;
        }
    }
});

socket.on('call_answer', async (data) => {
    if (!peerConnection) return;
    await peerConnection.setRemoteDescription(new RTCSessionDescription(data.sdp));
    if (isCaller && isInCall && !callTimerInterval) {
        showActiveCallBar();
    }
});

socket.on('ice_candidate', async (data) => {
    if (data.candidate) {
        try {
            await peerConnection.addIceCandidate(new RTCIceCandidate(data.candidate));
        } catch (e) {
            console.error('Error adding ICE candidate', e);
        }
    }
});

document.getElementById('acceptCallBtn').addEventListener('click', async () => {
    const tempCtx = new(window.AudioContext || window.webkitAudioContext)();
    if (tempCtx.state === 'suspended') {
        await tempCtx.resume();
    }
    await acceptIncomingCall();
});
document.getElementById('rejectCallBtn').addEventListener('click', rejectIncomingCall);
document.getElementById('endCallBtn').addEventListener('click', endCall);

window.addEventListener('beforeunload', () => {
    if (isInCall) endCall();
});

function onFabDragStart(e) {
    if (e.type === 'mousedown' && e.button !== 0) return;
    if (isInCall) return;

    e.preventDefault();
    const touch = e.touches ? e.touches[0] : e;
    fabDragStartX = touch.clientX;
    fabDragStartY = touch.clientY;

    const fab = document.getElementById('callFab');
    const fabRect = fab.getBoundingClientRect();
    fabStartLeft = fabRect.left;
    fabStartTop = fabRect.top;

    const container = document.getElementById('mainChat');
    const containerRect = container.getBoundingClientRect();
    const leftRelative = fabStartLeft - containerRect.left;
    const topRelative = fabStartTop - containerRect.top;

    fab.style.left = leftRelative + 'px';
    fab.style.top = topRelative + 'px';
    fab.style.right = 'auto';
    fab.style.transform = 'none';

    isDraggingFab = true;
    fabHasMoved = false;
    fab.style.transition = 'none';
    fab.style.opacity = '1';
}

function onFabDragMove(e) {
    if (!isDraggingFab) return;
    e.preventDefault();
    const touch = e.touches ? e.touches[0] : e;
    const deltaX = touch.clientX - fabDragStartX;
    const deltaY = touch.clientY - fabDragStartY;

    if (Math.abs(deltaX) > DRAG_THRESHOLD || Math.abs(deltaY) > DRAG_THRESHOLD) {
        fabHasMoved = true;
    }

    const fab = document.getElementById('callFab');
    let newLeft = fabStartLeft + deltaX;
    let newTop = fabStartTop + deltaY;

    const container = document.getElementById('mainChat');
    const containerRect = container.getBoundingClientRect();
    const fabRect = fab.getBoundingClientRect();
    if (newLeft < containerRect.left) newLeft = containerRect.left;
    if (newTop < containerRect.top) newTop = containerRect.top;
    if (newLeft + fabRect.width > containerRect.right) newLeft = containerRect.right - fabRect.width;
    if (newTop + fabRect.height > containerRect.bottom) newTop = containerRect.bottom - fabRect.height;

    fab.style.left = (newLeft - containerRect.left) + 'px';
    fab.style.top = (newTop - containerRect.top) + 'px';
    fab.style.right = 'auto';
    fab.style.transform = 'none';
}

function onFabDragEnd(e) {
    if (!isDraggingFab) return;
    isDraggingFab = false;

    const fab = document.getElementById('callFab');
    fab.style.transition = '';
    fab.style.opacity = '';

    if (!fabHasMoved) {
        const targetId = activeChatType === 'group' ? groupCreatorId : otherUserId;
        if (targetId && !isInCall) {
            startCall(targetId);
        }
    }
    fabHasMoved = false;
}

const fab = document.getElementById('callFab');

fab.addEventListener('mousedown', onFabDragStart);
fab.addEventListener('touchstart', onFabDragStart, {
    passive: false
});

window.addEventListener('mousemove', onFabDragMove);
window.addEventListener('touchmove', onFabDragMove, {
    passive: false
});

window.addEventListener('mouseup', onFabDragEnd);
window.addEventListener('touchend', onFabDragEnd);

document.getElementById('muteCallBtn').addEventListener('click', toggleMute);
