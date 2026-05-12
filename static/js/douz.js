const body = document.body;

function toggleTheme() {
    body.classList.toggle('light-mode');
    localStorage.setItem('theme', body.classList.contains('light-mode') ? 'light' : 'dark');
}
(localStorage.getItem('theme') === 'light') ? body.classList.add('light-mode'): body.classList.remove('light-mode');

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
    if (code) socket.emit('join_room', {
        room: code
    });
});

cells.forEach(cell => {
    cell.addEventListener('click', () => {
        if (!mySymbol || currentTurn !== mySymbol) return;
        const idx = cell.dataset.idx;
        socket.emit('make_move', {
            room: myRoom,
            index: idx
        });
    });
});

socket.on('room_created', (data) => {
    myRoom = data.room;
    joinGameRoom(data.room);
    roomCodeSpan.textContent = data.room;
    statusDiv.textContent = 'waiting for opponent...';
    updateScores({
        my_wins: 0,
        opponent_wins: 0,
        draws: 0
    });
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
    socket.emit('request_replay', {
        room: myRoom
    });
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

const urlParams = new URLSearchParams(window.location.search);
const prejoinRoom = urlParams.get('room');
if (prejoinRoom) {
    socket.on('connect', () => {
        socket.emit('join_room', {
            room: prejoinRoom
        });
    });
    if (socket.connected) {
        socket.emit('join_room', {
            room: prejoinRoom
        });
    }
} else {
    lobby.classList.remove('hidden');
    gameArea.classList.add('hidden');
}

socket.on('error', (data) => {
    showToast(data.msg);
    if (data.msg === 'Room not found' || data.msg === 'Room full') {
        lobby.classList.remove('hidden');
        gameArea.classList.add('hidden');
    }
});

leaveBtn.addEventListener('click', () => {
    socket.emit('leave_room', {
        room: myRoom
    });
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

function showToast(msg) {
    const toast = document.getElementById('toast');
    toast.textContent = msg;
    toast.style.display = 'block';
    setTimeout(() => {
        toast.style.display = 'none';
    }, 3000);
}