// WatchWithMe Client Application

// Global State
let moviesList = [];
let activeMovieId = null;
let currentRoomId = null;
let currentSocket = null;
let hlsInstance = null;
let remoteActionPlay = false;
let remoteActionPause = false;
let remoteActionSeek = false;
let nickname = localStorage.getItem("wwm_nickname") || "Viewer " + Math.floor(Math.random() * 1000);
let heartbeatInterval = null;

// UI Element selectors
const viewDashboard = document.getElementById("view-dashboard");
const viewRoom = document.getElementById("view-room");
const moviesGrid = document.getElementById("movies-grid");
const moviesEmpty = document.getElementById("movies-empty");
const moviesCount = document.getElementById("movies-count");
const searchInput = document.getElementById("search-input");
const videoPlayer = document.getElementById("video-player");

// Modals
const modalUpload = document.getElementById("modal-upload");
const modalManage = document.getElementById("modal-manage");
const modalSelectTracks = document.getElementById("modal-select-tracks");

// Select Tracks Form elements
const selectTracksForm = document.getElementById("select-tracks-form");
const audioTracksList = document.getElementById("audio-tracks-list");
const subtitleTracksList = document.getElementById("subtitle-tracks-list");
const selectTracksMovieId = document.getElementById("select-tracks-movie-id");

// Nickname & Chat
const nicknameInput = document.getElementById("nickname-input");
const btnUpdateNickname = document.getElementById("btn-update-nickname");
const chatMessages = document.getElementById("chat-messages");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");

// Toast elements
const toastEl = document.getElementById("toast");
const toastIcon = document.getElementById("toast-icon");
const toastTitle = document.getElementById("toast-title");
const toastMessage = document.getElementById("toast-message");

// Helper: Formatter for duration
function formatDuration(seconds) {
    if (!seconds || seconds <= 0) return "0:00";
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    let result = "";
    if (hrs > 0) {
        result += hrs + ":" + (mins < 10 ? "0" : "");
    }
    result += mins + ":" + (secs < 10 ? "0" : "") + secs;
    return result;
}

// Helper: Toast Notifications
function showToast(title, message, type = "success") {
    toastTitle.textContent = title;
    toastMessage.textContent = message;
    
    toastIcon.className = "toast-icon";
    if (type === "success") {
        toastIcon.classList.add("toast-success-icon");
        toastIcon.innerHTML = '<i class="ph-bold ph-check"></i>';
    } else {
        toastIcon.classList.add("toast-error-icon");
        toastIcon.innerHTML = '<i class="ph-bold ph-warning"></i>';
    }
    
    toastEl.classList.add("active");
    setTimeout(() => {
        toastEl.classList.remove("active");
    }, 4000);
}

// Navigation Router: Check hash for room invites
function checkHashRoute() {
    const hash = window.location.hash;
    if (hash && hash.startsWith("#room=")) {
        const roomId = hash.replace("#room=", "");
        if (roomId && roomId !== currentRoomId) {
            joinRoom(roomId);
        }
    } else if (currentRoomId) {
        // Left the room
        leaveRoom(false);
    }
}

// Fetch Movies list
async function fetchMovies(query = "") {
    try {
        const url = query ? `/api/movies?q=${encodeURIComponent(query)}` : '/api/movies';
        const response = await fetch(url);
        if (!response.ok) throw new Error("Could not fetch movies");
        
        moviesList = await response.json();
        renderMoviesGrid();
    } catch (error) {
        console.error("Error fetching movies:", error);
        showToast("Error", "Could not fetch film library", "error");
    }
}

// Render library grid
function renderMoviesGrid() {
    moviesGrid.innerHTML = "";
    moviesCount.textContent = moviesList.length;
    
    if (moviesList.length === 0) {
        moviesEmpty.classList.remove("hidden");
        return;
    }
    moviesEmpty.classList.add("hidden");
    
    let isProcessingAny = false;
    
    moviesList.forEach(movie => {
        const card = document.createElement("div");
        card.className = "movie-card";
        
        // Thumbnail or status indicator
        let thumbContent = "";
        let detailsButton = "";
        let statusBadge = "";
        
        if (movie.status === 'ready') {
            thumbContent = `<img src="${movie.thumbnail_url}" alt="${movie.title}" class="movie-thumbnail">`;
            detailsButton = `
                <div class="movie-card-overlay">
                    <button class="btn-card-action btn-accent" onclick="watchAlone(${movie.id})">
                        <i class="ph-fill ph-play"></i> Watch Alone
                    </button>
                    <button class="btn-card-action" onclick="createRoom(${movie.id})">
                        <i class="ph-bold ph-users-three"></i> Watch Together
                    </button>
                </div>
            `;
            statusBadge = `<span class="status-badge status-ready"><i class="ph ph-check-circle"></i> Ready</span>`;
        } else if (movie.status === 'processing') {
            isProcessingAny = true;
            const progress = movie.progress || 0;
            thumbContent = `
                <div style="height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; background: rgba(255,255,255,0.02); padding: 16px;">
                    <div style="text-align: center; width: 80%;">
                        <i class="ph ph-circle-notch animate-spin" style="font-size: 24px; color: var(--accent); margin-bottom: 12px; display: inline-block;"></i>
                        <div style="font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 6px;">Packaging Stream...</div>
                        <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 12px;">Progress: ${progress}%</div>
                        <div class="progress-track" style="height: 4px; background: rgba(255,255,255,0.05); border-radius: 2px; overflow: hidden; width: 100%;">
                            <div class="progress-fill" style="width: ${progress}%; background: var(--accent); height: 100%; transition: width 0.3s ease;"></div>
                        </div>
                    </div>
                </div>
            `;
            statusBadge = `<span class="status-badge status-processing"><i class="ph ph-circle-notch animate-spin"></i> Processing (${progress}%)</span>`;
        } else {
            thumbContent = `
                <div style="height: 100%; display: flex; align-items: center; justify-content: center; background: var(--danger-bg);">
                    <div style="text-align: center; color: var(--danger); padding: 12px;">
                        <i class="ph ph-warning-octagon" style="font-size: 24px; margin-bottom: 8px;"></i>
                        <div style="font-size: 11px; font-weight: 600;">Transcoding Failed</div>
                        <div style="font-size: 9px; color: var(--text-muted); margin-top: 4px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;" title="${movie.error_message || ''}">${movie.error_message || 'Unknown error'}</div>
                    </div>
                </div>
            `;
            statusBadge = `<span class="status-badge status-failed"><i class="ph ph-x-circle"></i> Failed</span>`;
        }
        
        card.innerHTML = `
            <div class="movie-thumb-wrapper">
                ${thumbContent}
                ${detailsButton}
            </div>
            <div class="movie-details">
                <div class="movie-title-row">
                    <h4 class="movie-title" title="${movie.title}">${movie.title}</h4>
                    <button class="btn-manage-trigger" onclick="openManageModal(${movie.id})" title="Manage film">
                        <i class="ph-bold ph-gear-six"></i>
                    </button>
                </div>
                <p class="movie-desc">${movie.description || "No synopsis available."}</p>
                <div class="movie-meta">
                    <span class="movie-duration">
                        <i class="ph ph-clock"></i>
                        <span>${formatDuration(movie.duration)}</span>
                    </span>
                    ${statusBadge}
                </div>
            </div>
        `;
        
        moviesGrid.appendChild(card);
    });
    
    // Polling while movies are processing
    if (isProcessingAny) {
        setTimeout(() => {
            // Check library state again
            if (currentRoomId === null) { // Only poll if we are on dashboard
                fetchMovies();
            }
        }, 3000);
    }
}

// Watch Alone Mode
async function watchAlone(movieId) {
    try {
        const response = await fetch(`/api/movies/${movieId}`);
        if (!response.ok) throw new Error("Could not get movie details");
        const movie = await response.json();
        
        // Hide dashboard, show room in "solo" mode
        viewDashboard.classList.add("hidden");
        viewRoom.classList.remove("hidden");
        
        const logo = document.getElementById("logo");
        if (logo) logo.style.pointerEvents = "none"; // disable logo navigation during playback
        
        document.getElementById("room-movie-title").textContent = movie.title;
        // Hide sidebar and room share details for solo mode
        document.getElementById("room-sidebar").classList.add("hidden");
        document.querySelector(".share-link-box").classList.add("hidden");
        
        // Load video (awaits HLS setup before play)
        await loadVideoSource(movie.playlist_url, movie.subtitles);
        
        // Set up custom back button action
        document.getElementById("btn-leave-room").onclick = function() {
            leaveRoom(true);
        };
        
        showToast("Playing Film", `Now streaming: ${movie.title}`);
        
        // Attempt immediate play (handles browser autoplay constraints gracefully)
        try {
            await videoPlayer.play();
        } catch (playErr) {
            console.log("Autoplay blocked, waiting for user interaction.", playErr);
        }
    } catch (error) {
        console.error("Error starting watchAlone:", error);
        showToast("Error", "Could not play film", "error");
    }
}

// Watch Together Room: Create Room
function createRoom(movieId) {
    const roomId = Math.random().toString(36).substring(2, 8);
    window.location.hash = `room=${roomId}`; // Updates hash, triggers checkHashRoute -> joinRoom
    activeMovieId = movieId;
}

// Join room websocket & UI setup
async function joinRoom(roomId) {
    currentRoomId = roomId;
    viewDashboard.classList.add("hidden");
    viewRoom.classList.remove("hidden");
    
    const logo = document.getElementById("logo");
    if (logo) logo.style.pointerEvents = "none";
    
    // UI details
    document.getElementById("room-sidebar").classList.remove("hidden");
    document.querySelector(".share-link-box").classList.remove("hidden");
    
    let inviteUrl = `${window.location.origin}/#room=${roomId}`;
    document.getElementById("room-share-url").value = inviteUrl;
    
    
    // Clear chat messages
    chatMessages.innerHTML = `
        <div class="message-item system">
            <span class="message-text">Welcome to the co-watch room! Share the link to invite friends.</span>
        </div>
    `;
    
    // Close any open modals
    closeAllModals();
    
    // WebSocket protocol (ws or wss)
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/room/${roomId}`;
    
    if (heartbeatInterval) {
        clearInterval(heartbeatInterval);
        heartbeatInterval = null;
    }
    
    if (currentSocket) {
        currentSocket.close();
    }
    
    currentSocket = new WebSocket(wsUrl);
    
    currentSocket.onopen = function() {
        console.log("WebSocket connected to room:", roomId);
        
        heartbeatInterval = setInterval(() => {
            if (currentSocket && currentSocket.readyState === WebSocket.OPEN) {
                currentSocket.send(JSON.stringify({ type: "ping" }));
            }
        }, 20000); // 20s keep-alive heartbeat
        
        // If we created the room with a movie selected, set it
        if (activeMovieId) {
            currentSocket.send(JSON.stringify({
                type: "change_movie",
                movie_id: activeMovieId
            }));
            activeMovieId = null;
        } else {
            // Joiners request initial sync
            currentSocket.send(JSON.stringify({
                type: "sync_request"
            }));
        }
    };
    
    currentSocket.onmessage = async function(event) {
        const data = JSON.parse(event.data);
        console.log("WS Message received:", data);
        
        if (data.type === "room_state") {
            const state = data.state;
            if (state.movie_id) {
                await loadRoomMovie(state.movie_id);
                
                const timeDiff = Math.abs(videoPlayer.currentTime - state.time);
                if (timeDiff > 1.0) {
                    remoteActionSeek = true;
                    videoPlayer.currentTime = state.time;
                }
                
                if (!state.paused && videoPlayer.paused) {
                    remoteActionPlay = true;
                    videoPlayer.play().catch(() => {
                        remoteActionPlay = false;
                    });
                } else if (state.paused && !videoPlayer.paused) {
                    remoteActionPause = true;
                    videoPlayer.pause();
                }
            }
        } 
        else if (data.type === "change_movie") {
            await loadRoomMovie(data.movie_id);
        } 
        else if (data.type === "play") {
            const timeDiff = Math.abs(videoPlayer.currentTime - data.time);
            if (timeDiff > 1.0) {
                remoteActionSeek = true;
                videoPlayer.currentTime = data.time;
            }
            if (videoPlayer.paused) {
                remoteActionPlay = true;
                videoPlayer.play().catch(() => {
                    remoteActionPlay = false;
                });
            }
            appendSystemMessage("Stream played.");
        } 
        else if (data.type === "pause") {
            const timeDiff = Math.abs(videoPlayer.currentTime - data.time);
            if (timeDiff > 1.0) {
                remoteActionSeek = true;
                videoPlayer.currentTime = data.time;
            }
            if (!videoPlayer.paused) {
                remoteActionPause = true;
                videoPlayer.pause();
            }
            appendSystemMessage("Stream paused.");
        } 
        else if (data.type === "seek") {
            const timeDiff = Math.abs(videoPlayer.currentTime - data.time);
            if (timeDiff > 0.5) {
                remoteActionSeek = true;
                videoPlayer.currentTime = data.time;
            }
            appendSystemMessage(`Stream scrubbed to ${formatDuration(Math.round(data.time))}`);
        } 
        else if (data.type === "chat") {
            appendChatMessage(data.nickname, data.message, false);
        }
    };
    
    currentSocket.onclose = function() {
        console.log("WebSocket closed");
        if (heartbeatInterval) {
            clearInterval(heartbeatInterval);
            heartbeatInterval = null;
        }
        if (currentRoomId === roomId) {
            appendSystemMessage("Sync connection lost. Reconnecting in 3s...");
            setTimeout(() => {
                if (currentRoomId === roomId) {
                    joinRoom(roomId);
                }
            }, 3000);
        }
    };
    
    // Set up back navigation
    document.getElementById("btn-leave-room").onclick = function() {
        leaveRoom(true);
    };
    
    // Sync local nickname
    nicknameInput.value = nickname;
}

// Load Movie inside collaborative room
async function loadRoomMovie(movieId) {
    try {
        const response = await fetch(`/api/movies/${movieId}`);
        if (!response.ok) throw new Error("Could not fetch movie info");
        const movie = await response.json();
        
        document.getElementById("room-movie-title").textContent = movie.title;
        await loadVideoSource(movie.playlist_url, movie.subtitles);
        appendSystemMessage(`Loaded movie: ${movie.title}`);
    } catch (err) {
        console.error(err);
        showToast("Error", "Could not load selected movie", "error");
    }
}

// Load video file in Hls.js / Native Video Tag
function loadVideoSource(playlistUrl, subtitles = []) {
    return new Promise((resolve, reject) => {
        if (hlsInstance) {
            hlsInstance.destroy();
            hlsInstance = null;
        }
        
        // Remove previous track items
        videoPlayer.innerHTML = "";
        videoPlayer.src = "";
        
        // Add subtitle tracks safely
        if (subtitles && Array.isArray(subtitles)) {
            subtitles.forEach((sub, index) => {
                if (!sub || !sub.vtt_url) return;
                const track = document.createElement("track");
                track.kind = "subtitles";
                track.label = sub.language || "Unknown";
                track.srclang = (sub.language || "en").substring(0, 2).toLowerCase();
                track.src = sub.vtt_url;
                if (index === 0) track.default = true;
                videoPlayer.appendChild(track);
            });
        }
        
        // Stream setup
        if (typeof Hls !== 'undefined' && Hls.isSupported()) {
            hlsInstance = new Hls({
                maxBufferSize: 60 * 1024 * 1024, // 60MB buffer
                maxBufferLength: 30,             // Buffer 30 seconds of video
                maxMaxBufferLength: 60,
                enableWorker: true,
                manifestLoadingMaxRetry: 10,
                levelLoadingMaxRetry: 10,
                fragLoadingMaxRetry: 10
            });
            hlsInstance.loadSource(playlistUrl);
            hlsInstance.attachMedia(videoPlayer);
            
            hlsInstance.on(Hls.Events.MANIFEST_PARSED, () => {
                resolve();
            });
            
            hlsInstance.on(Hls.Events.ERROR, (event, data) => {
                if (data.fatal) {
                    console.error("Hls fatal error occurred:", data);
                    reject(new Error("HLS stream setup failure"));
                }
            });
        } 
        else if (videoPlayer.canPlayType('application/vnd.apple.mpegurl')) {
            // Native HLS for Safari/iOS
            videoPlayer.src = playlistUrl;
            videoPlayer.addEventListener('loadedmetadata', () => {
                resolve();
            }, { once: true });
        } 
        else {
            showToast("Player Error", "HLS streaming is not supported in this browser or Hls library failed to load.", "error");
            reject(new Error("HLS unsupported"));
        }
    });
}

// Leave Room
function leaveRoom(clearHash = true) {
    if (heartbeatInterval) {
        clearInterval(heartbeatInterval);
        heartbeatInterval = null;
    }
    if (currentSocket) {
        currentSocket.close();
        currentSocket = null;
    }
    
    if (hlsInstance) {
        hlsInstance.destroy();
        hlsInstance = null;
    }
    
    videoPlayer.pause();
    videoPlayer.src = "";
    videoPlayer.innerHTML = "";
    
    currentRoomId = null;
    
    viewRoom.classList.add("hidden");
    viewDashboard.classList.remove("hidden");
    
    const logo = document.getElementById("logo");
    if (logo) logo.style.pointerEvents = "auto";
    
    if (clearHash) {
        window.location.hash = "";
    }
    
    fetchMovies();
}

// Chat system formatting
function appendSystemMessage(text) {
    const msg = document.createElement("div");
    msg.className = "message-item system";
    msg.innerHTML = `<span class="message-text">${text}</span>`;
    chatMessages.appendChild(msg);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Render normal chat messages
function appendChatMessage(sender, message, isSelf = false) {
    const msg = document.createElement("div");
    msg.className = "message-item" + (isSelf ? " self" : "");
    msg.innerHTML = `
        <span class="message-sender">${sender}</span>
        <div class="message-bubble">${message}</div>
    `;
    chatMessages.appendChild(msg);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Modal open/close actions
function openModal(modal) {
    modal.classList.add("active");
}

function closeAllModals() {
    document.querySelectorAll(".modal-overlay").forEach(modal => {
        modal.classList.remove("active");
    });
}

// Populate Stream Track Selector Modal
function openSelectTracksModal(data) {
    selectTracksMovieId.value = data.movie_id;
    audioTracksList.innerHTML = "";
    subtitleTracksList.innerHTML = "";
    
    // Populate Audio Tracks
    if (data.audio_tracks && data.audio_tracks.length > 0) {
        data.audio_tracks.forEach((track, i) => {
            const label = document.createElement("label");
            label.className = "track-option";
            label.innerHTML = `
                <input type="radio" name="audio_track" value="${track.index}" ${i === 0 ? 'checked' : ''}>
                <div class="track-info-detail">
                    <span class="track-name">Track ${track.index} (${track.language})</span>
                    <span class="track-meta-desc">Codec: ${track.codec.toUpperCase()} - ${track.title}</span>
                </div>
            `;
            audioTracksList.appendChild(label);
        });
    } else {
        audioTracksList.innerHTML = `<div style="font-size: 12px; color: var(--text-muted); padding: 8px;">No audio tracks detected. Default stream mapping will be used.</div>`;
    }
    
    // Populate Subtitle Tracks
    if (data.subtitle_tracks && data.subtitle_tracks.length > 0) {
        data.subtitle_tracks.forEach((track) => {
            const label = document.createElement("label");
            label.className = "track-option";
            label.innerHTML = `
                <input type="checkbox" name="subtitle_track" value="${track.index}">
                <div class="track-info-detail">
                    <span class="track-name">Track ${track.index} (${track.language})</span>
                    <span class="track-meta-desc">Codec: ${track.codec.toUpperCase()} - ${track.title}</span>
                </div>
            `;
            subtitleTracksList.appendChild(label);
        });
    } else {
        subtitleTracksList.innerHTML = `<div style="font-size: 12px; color: var(--text-muted); padding: 8px;">No internal text subtitle tracks detected.</div>`;
    }
    
    openModal(modalSelectTracks);
}

// Subtitles Track management Modal population
let manageMovieId = null;

async function openManageModal(movieId) {
    manageMovieId = movieId;
    try {
        const response = await fetch(`/api/movies/${movieId}`);
        if (!response.ok) throw new Error("Could not fetch movie info");
        const movie = await response.json();
        
        document.getElementById("manage-movie-title").textContent = movie.title;
        renderSubtitlesList(movie.subtitles);
        
        openModal(modalManage);
    } catch (err) {
        console.error(err);
        showToast("Error", "Could not load management details", "error");
    }
}

function renderSubtitlesList(subtitles) {
    const list = document.getElementById("manage-subtitles-list");
    list.innerHTML = "";
    
    if (subtitles.length === 0) {
        list.innerHTML = `<div style="font-size: 12px; color: var(--text-muted); text-align: center; py: 8px;">No subtitle tracks loaded.</div>`;
        return;
    }
    
    subtitles.forEach(sub => {
        const item = document.createElement("div");
        item.className = "subtitle-item";
        item.innerHTML = `
            <span class="subtitle-lang">${sub.language}</span>
            <span style="font-size: 10px; color: var(--text-muted); font-family: monospace; flex-grow: 1; margin-left: 12px;">WebVTT track</span>
        `;
        list.appendChild(item);
    });
}

// Hook all Events
document.addEventListener("DOMContentLoaded", () => {
    // Initial fetch
    fetchMovies();
    checkHashRoute();
    
    // Hash routing check
    window.addEventListener("hashchange", checkHashRoute);
    
    // Open upload modal
    document.getElementById("btn-open-upload").addEventListener("click", () => {
        // Reset form
        document.getElementById("upload-form").reset();
        document.getElementById("video-file-name").textContent = "Choose video or drag here";
        document.getElementById("subtitle-file-name").textContent = "Select SRT/VTT...";
        document.getElementById("upload-progress-container").classList.add("hidden");
        openModal(modalUpload);
    });
    
    // Close modal hooks
    document.querySelectorAll(".btn-close-modal").forEach(btn => {
        btn.addEventListener("click", closeAllModals);
    });
    
    // Click outside modal closing
    document.querySelectorAll(".modal-overlay").forEach(overlay => {
        overlay.addEventListener("click", (e) => {
            if (e.target === overlay) closeAllModals();
        });
    });
    
    // Drag and drop video naming indicator
    const videoInput = document.getElementById("upload-video");
    videoInput.addEventListener("change", () => {
        if (videoInput.files.length > 0) {
            document.getElementById("video-file-name").textContent = videoInput.files[0].name;
            // Autofill title if empty
            const titleInput = document.getElementById("upload-title");
            if (!titleInput.value) {
                // remove extension
                const name = videoInput.files[0].name.replace(/\.[^/.]+$/, "");
                // Replace hyphens/underscores with space, capitalize
                titleInput.value = name.replace(/[_-]/g, " ").replace(/\b\w/g, c => c.toUpperCase());
            }
        }
    });

    const subInput = document.getElementById("upload-subtitle");
    subInput.addEventListener("change", () => {
        if (subInput.files.length > 0) {
            document.getElementById("subtitle-file-name").textContent = subInput.files[0].name;
        }
    });

    // Upload Form Submit using XHR to support progress bars!
    const uploadForm = document.getElementById("upload-form");
    uploadForm.addEventListener("submit", (e) => {
        e.preventDefault();
        
        const formData = new FormData(uploadForm);
        const xhr = new XMLHttpRequest();
        
        // Progress UI display
        const progressContainer = document.getElementById("upload-progress-container");
        const progressBar = document.getElementById("upload-bar");
        const percentText = document.getElementById("upload-percent");
        const statusText = document.getElementById("upload-status-text");
        
        progressContainer.classList.remove("hidden");
        document.getElementById("btn-submit-upload").disabled = true;
        
        xhr.upload.onprogress = function(event) {
            if (event.lengthComputable) {
                const percent = Math.round((event.loaded / event.total) * 100);
                progressBar.style.width = percent + "%";
                percentText.textContent = percent + "%";
                if (percent === 100) {
                    statusText.textContent = "Analyzing film structure...";
                }
            }
        };
        
        xhr.onload = function() {
            document.getElementById("btn-submit-upload").disabled = false;
            if (xhr.status === 200) {
                try {
                    const resData = JSON.parse(xhr.responseText);
                    showToast("Upload Succeeded", "File tracks analyzed successfully.");
                    closeAllModals();
                    
                    if (resData.status === "pending_selection") {
                        openSelectTracksModal(resData);
                    } else {
                        fetchMovies();
                    }
                } catch (e) {
                    console.error("Error parsing upload response:", e);
                    closeAllModals();
                    fetchMovies();
                }
            } else {
                console.error("Upload error:", xhr.responseText);
                showToast("Upload Failed", "Could not process movie file.", "error");
            }
        };
        
        xhr.onerror = function() {
            document.getElementById("btn-submit-upload").disabled = false;
            showToast("Upload Failed", "Network transport error occurred.", "error");
        };
        
        xhr.open("POST", "/api/movies/upload");
        xhr.send(formData);
    });

    // Select Tracks form submit
    selectTracksForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const movieId = selectTracksMovieId.value;
        const selectedAudio = selectTracksForm.querySelector('input[name="audio_track"]:checked');
        const selectedSubCheckboxes = selectTracksForm.querySelectorAll('input[name="subtitle_track"]:checked');
        
        const formData = new FormData();
        if (selectedAudio) {
            formData.append("audio_track_index", selectedAudio.value);
        }
        
        const subIndices = Array.from(selectedSubCheckboxes).map(cb => cb.value).join(",");
        formData.append("subtitle_track_indexes", subIndices);
        
        try {
            document.getElementById("btn-submit-process").disabled = true;
            const response = await fetch(`/api/movies/${movieId}/process`, {
                method: "POST",
                body: formData
            });
            
            if (!response.ok) throw new Error("Processing packaging request failed");
            
            showToast("Packaging Started", "Video stream packaging has successfully started.");
            closeAllModals();
            fetchMovies();
        } catch (error) {
            console.error(error);
            showToast("Error", "Could not start packaging stream", "error");
        } finally {
            document.getElementById("btn-submit-process").disabled = false;
        }
    });
    
    // Manage Modal: Add Subtitle inline Form
    const addSubFile = document.getElementById("manage-sub-file");
    addSubFile.addEventListener("change", () => {
        if (addSubFile.files.length > 0) {
            document.getElementById("manage-sub-file-name").textContent = addSubFile.files[0].name;
        }
    });
    
    const addSubForm = document.getElementById("add-subtitle-form");
    addSubForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (!manageMovieId) return;
        
        const langInput = document.getElementById("manage-sub-lang");
        const formData = new FormData();
        formData.append("language", langInput.value);
        formData.append("file", addSubFile.files[0]);
        
        try {
            const response = await fetch(`/api/movies/${manageMovieId}/subtitles`, {
                method: "POST",
                body: formData
            });
            
            if (!response.ok) throw new Error("Failed to upload subtitle");
            
            showToast("Subtitles Added", `Subtitle in ${langInput.value} successfully parsed.`);
            addSubForm.reset();
            document.getElementById("manage-sub-file-name").textContent = "Choose SRT/VTT...";
            
            // Refresh subtitles list in modal
            const movieRes = await fetch(`/api/movies/${manageMovieId}`);
            const movie = await movieRes.json();
            renderSubtitlesList(movie.subtitles);
        } catch (error) {
            console.error(error);
            showToast("Error", "Could not save subtitle track", "error");
        }
    });
    
    // Delete Movie
    document.getElementById("btn-delete-movie").addEventListener("click", async () => {
        if (!manageMovieId) return;
        
        const confirmDelete = confirm("Are you absolutely sure you want to delete this film? This cannot be undone.");
        if (!confirmDelete) return;
        
        try {
            const response = await fetch(`/api/movies/${manageMovieId}`, {
                method: "DELETE"
            });
            if (!response.ok) throw new Error("Delete request failed");
            
            showToast("Film Deleted", "Film and files successfully removed.");
            closeAllModals();
            fetchMovies();
        } catch (error) {
            console.error(error);
            showToast("Error", "Failed to delete film files", "error");
        }
    });
    
    // Update Nickname
    btnUpdateNickname.addEventListener("click", () => {
        const value = nicknameInput.value.trim();
        if (value) {
            nickname = value;
            localStorage.setItem("wwm_nickname", nickname);
            showToast("Nickname Saved", `Chat active as: ${nickname}`);
            
            // Notify other users of nickname change if connected
            if (currentSocket && currentSocket.readyState === WebSocket.OPEN) {
                currentSocket.send(JSON.stringify({
                    type: "chat",
                    nickname: "System",
                    message: `Viewer changed display name to: ${nickname}`
                }));
            }
        }
    });
    
    // Submit Chat
    chatForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const text = chatInput.value.trim();
        if (text && currentSocket && currentSocket.readyState === WebSocket.OPEN) {
            // Send chat message
            currentSocket.send(JSON.stringify({
                type: "chat",
                nickname: nickname,
                message: text
            }));
            
            // Display locally
            appendChatMessage(nickname, text, true);
            chatInput.value = "";
        }
    });
    
    // Copy Room Link
    document.getElementById("btn-copy-room-link").addEventListener("click", () => {
        const shareInput = document.getElementById("room-share-url");
        shareInput.select();
        document.execCommand("copy");
        showToast("Link Copied", "Shareable room URL copied to clipboard.");
    });
    
    // Search inputs
    const handleSearch = (e) => {
        fetchMovies(e.target.value.trim());
    };
    searchInput.addEventListener("input", handleSearch);
    
    // HTML5 Video Playback sync triggers
    videoPlayer.addEventListener("play", () => {
        if (remoteActionPlay) {
            remoteActionPlay = false; // consume it
            return;
        }
        if (videoPlayer.seeking || !currentSocket || currentSocket.readyState !== WebSocket.OPEN) return;
        currentSocket.send(JSON.stringify({
            type: "play",
            time: videoPlayer.currentTime
        }));
    });
    
    videoPlayer.addEventListener("pause", () => {
        if (remoteActionPause) {
            remoteActionPause = false; // consume it
            return;
        }
        if (videoPlayer.seeking || !currentSocket || currentSocket.readyState !== WebSocket.OPEN) return;
        currentSocket.send(JSON.stringify({
            type: "pause",
            time: videoPlayer.currentTime
        }));
    });
    
    let seekTimeout = null;
    videoPlayer.addEventListener("seeked", () => {
        if (remoteActionSeek) {
            remoteActionSeek = false; // consume it
            return;
        }
        if (!currentSocket || currentSocket.readyState !== WebSocket.OPEN) return;
        
        // Debounce user seek commands to avoid flooding the websocket during timeline scrubbing
        if (seekTimeout) clearTimeout(seekTimeout);
        seekTimeout = setTimeout(() => {
            currentSocket.send(JSON.stringify({
                type: "seek",
                time: videoPlayer.currentTime
            }));
        }, 250);
    });
});
