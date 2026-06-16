# WatchWithMe 🎬

WatchWithMe is a self-hosted, lightweight web application that allows you to upload video files, automatically package them into HTTP Live Streaming (HLS) formats, and watch them together with friends in perfect synchronization over a local network.

---

## 📂 Project Structure

```text
WatchWithMe/
├── data/                      # Auto-created storage directory (not in Git)
│   ├── media/                 # Packaged streams, thumbnails, and subtitles
│   │   ├── subtitles/
│   │   ├── thumbnails/
│   │   └── videos/
│   ├── temp/                  # Temporarily stored raw uploads
│   └── movies.db              # SQLite Database
├── src/                       # Application Source Code
│   ├── api.py                 # REST APIs & custom Range request server
│   ├── config.py              # Configurations & directory initialization
│   ├── database.py            # SQLite database schema & migrations
│   ├── main.py                # FastAPI Application & WebSocket Router
│   ├── utils.py               # FFmpeg, FFprobe processing, & HLS packaging
│   └── websocket.py           # WebSocket room connection manager
├── static/                    # Frontend assets
│   ├── app.js                 # Frontend application & sync protocol
│   ├── hls.min.js             # HLS stream rendering library (hls.js)
│   ├── index.css              # Frontend styling
│   └── index.html             # Application Web UI
├── app.py                     # Entry point to launch the application
├── requirements.txt           # Python library dependencies
└── TODO.md                    # Future features roadmap
```

---

## ✨ Key Features

1. **Self-Hosted Library:** Upload files (MP4, MKV, AVI, etc.) directly. The backend automatically probes video info, extracts duration, and displays them in a modern dashboard.
2. **Track Selector & Packaging:** Extract internal audio tracks and subtitle tracks during the HLS packaging process.
3. **HTTP Byte-Range HLS Streaming:** Streams are encoded into standard single-file HLS segments, served via a custom Range request handler to allow instant skipping/scrubbing without freezing.
4. **Synchronized Co-Watching (Watch Together):** Create shared rooms where playback states (play, pause, timeline skip) synchronize instantly between viewers. Features auto-initialized Cloudflare Quick Tunnels to seamlessly expose your session to friends over the internet with zero configuration.
5. **Precision Sync Locks:** Uses flag-based programmatic event isolation to prevent feedback loops and stutters while maintaining zero command latency.

---

## ⚙️ How the Code Works

### 1. HLS Packaging & The Byte-Range Server
When a video file is uploaded:
- **FFprobe Probing:** The backend runs `ffprobe` to identify audio and subtitle tracks.
- **FFmpeg Transcoding:** The backend transcodes the selected video/audio tracks into HLS using:
  ```bash
  ffmpeg -i input.mp4 -c:v libx264 -preset ultrafast -hls_flags single_file index.m3u8
  ```
  The `-hls_flags single_file` option stores the segments inside a single `.ts` file (`index.ts`) and creates an `index.m3u8` playlist referencing the segment byte offsets.
- **Custom Range Server:** Standard static mounts do not natively support byte-range requests required for single-file HLS playback. In `src/api.py`, a custom `/media/{file_path}` GET endpoint handles incoming HTTP `Range: bytes=start-end` headers, seeks the file stream to the offset, sends back the precise range of bytes requested, and responds with a `206 Partial Content` status.

### 2. Precise WebSocket Synchronization (Watch Together)
Synchronizing two media players over WebSockets is prone to event storms and infinite feedback loops (e.g. Client A seeks ➡️ Server broadcasts to Client B ➡️ Client B programmatically seeks ➡️ Client B fires a `seeked` event ➡️ Client B sends seek back to Client A).

To prevent this:
- **Programmatic Flags:** When Client B receives a remote WebSocket command (e.g. `play` or `seek`), it sets a corresponding action flag (`remoteActionPlay = true`, `remoteActionSeek = true`) before changing the video player state.
- **Event Consumption:** When the player fires event listeners (like `play`, `pause`, or `seeked`), the client checks these flags. If a flag is active, it consumes the flag and returns immediately, blocking the event from being broadcast back to the server.
- **Debounced Input:** User seeks are debounced by `250ms` so scrubbing the timeline does not flood the WebSocket server.

---

## 🚀 Setup & Installation

### Prerequisites
Make sure you have [FFmpeg](https://ffmpeg.org/) installed and added to your system environment variable `PATH`.

### Installation Steps
1. **Clone or navigate** to the project directory:
   ```bash
   cd WatchWithMe
   ```
2. **Create a virtual environment** (optional but recommended):
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```
3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Run the server**:
   ```bash
   python app.py
   ```
   The application will be accessible at: `http://localhost:8000`

---

## 📖 How to Use

### Watching Movies Locally
1. Click **Upload Film** on the dashboard.
2. Drag and drop your video file and (optional) subtitle file. Enter a title and click **Start Upload**.
3. Choose the audio track and subtitle tracks you want to package, then click **Package Stream**.
4. Once processing is complete, hover over the movie card and click **Watch Alone**.

### Watching Together with Friends
1. Hover over the processed movie card and click **Watch Together**.
2. Copy the shareable invite link generated in the top-right corner of the room bar and send it to viewers.
   - **Local Link:** For users on the same local network/Wi-Fi.
   - **Internet Link:** For users over the internet. A secure Cloudflare Quick Tunnel is automatically created in the background, allowing friends anywhere in the world to join without any firewall, port forwarding, or configuration.
3. Once others open the link in their browsers, they will connect to the room.
4. Clicking play, pause, or seeking the timeline will immediately synchronize the video stream state across all connected viewers in real time.
