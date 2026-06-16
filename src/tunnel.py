import os
import sys
import shutil
import platform
import urllib.request
import subprocess
import threading
import re
import logging

logger = logging.getLogger("WatchWithMe.Tunnel")

# Global variables to store tunnel status
_tunnel_process = None
_tunnel_url = None
_tunnel_thread = None

# Download URLs for different platforms
CLOUDFLARED_URLS = {
    ("Windows", "AMD64"): "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe",
    ("Windows", "x86_64"): "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe",
    ("Linux", "x86_64"): "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
    ("Linux", "AMD64"): "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
    ("Darwin", "x86_64"): "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64",
    ("Darwin", "arm64"): "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-arm64",
}

def get_binary_path():
    """Returns the path to the local cloudflared binary, or system PATH binary if available."""
    # 1. Check if cloudflared is already in system PATH
    system_cf = shutil.which("cloudflared")
    if system_cf:
        logger.info(f"Using system-installed cloudflared: {system_cf}")
        return system_cf

    # 2. Otherwise, use a local path in data/bin
    bin_dir = os.path.join("data", "bin")
    os.makedirs(bin_dir, exist_ok=True)
    
    ext = ".exe" if platform.system() == "Windows" else ""
    local_path = os.path.join(bin_dir, f"cloudflared{ext}")
    return local_path

def download_cloudflared(target_path):
    """Downloads the cloudflared binary for the current platform if it doesn't exist."""
    if os.path.exists(target_path):
        return True

    sys_name = platform.system()
    machine = platform.machine()
    
    # Try to match the architecture key
    url = CLOUDFLARED_URLS.get((sys_name, machine))
    if not url:
        # Fallback search or generic
        logger.warning(f"No pre-configured cloudflared binary URL found for {sys_name} {machine}.")
        return False

    logger.info(f"Downloading cloudflared binary from: {url}")
    logger.info(f"Saving to: {target_path}")

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        
        # Download and write to disk
        with urllib.request.urlopen(req) as response, open(target_path, "wb") as out_file:
            # Copy chunks to show progress
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            block_size = 1024 * 1024  # 1MB chunks
            
            while True:
                chunk = response.read(block_size)
                if not chunk:
                    break
                downloaded += len(chunk)
                out_file.write(chunk)
                if total_size > 0:
                    percent = (downloaded / total_size) * 100
                    logger.info(f"Download progress: {percent:.1f}% ({downloaded}/{total_size} bytes)")
        
        # Make executable on Unix
        if sys_name != "Windows":
            os.chmod(target_path, 0o755)
            
        logger.info("cloudflared binary downloaded successfully!")
        return True
    except Exception as e:
        logger.error(f"Failed to download cloudflared binary: {e}")
        # Clean up partial downloads
        if os.path.exists(target_path):
            try:
                os.remove(target_path)
            except:
                pass
        return False

def _monitor_tunnel(process):
    """Monitors the cloudflared process output to find the Quick Tunnel URL."""
    global _tunnel_url
    
    # Cloudflared log pattern for Quick Tunnels:
    # e.g., "Your quick tunnel has been created! Visit it at: https://xxxx.trycloudflare.com"
    # Or in structured logs: "https://xxxx.trycloudflare.com"
    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
    
    # Read stderr since cloudflared prints logs there by default
    while True:
        line = process.stderr.readline()
        if not line:
            break
            
        line_str = line.decode("utf-8", errors="replace").strip()
        if not line_str:
            continue
            
        logger.debug(f"cloudflared: {line_str}")
        
        # Match trycloudflare URL
        match = url_pattern.search(line_str)
        if match:
            url = match.group(0)
            _tunnel_url = url
            logger.info("=" * 80)
            logger.info(f" CLOUDFLARE TUNNEL CREATED SUCCESSFULLY!")
            logger.info(f" Public URL: {url}")
            logger.info(f" Share this link with friends to watch together!")
            logger.info("=" * 80)

def start_tunnel(port: int = 8000):
    """Starts the Cloudflare Quick Tunnel in the background."""
    global _tunnel_process, _tunnel_url, _tunnel_thread
    
    if _tunnel_process is not None:
        logger.warning("Tunnel is already running.")
        return _tunnel_url

    binary_path = get_binary_path()
    
    # Download binary if it's a local path and doesn't exist
    if not os.path.exists(binary_path):
        if not download_cloudflared(binary_path):
            logger.error("Could not start tunnel: cloudflared binary is missing and download failed.")
            return None

    logger.info(f"Starting Cloudflare Tunnel on port {port}...")
    
    try:
        # Run cloudflared tunnel command
        # On Windows, we prevent a console window popping up using creationflags on Popen if needed,
        # but since we run from python cli, CREATE_NO_WINDOW is good to keep it backgrounded cleanly.
        creationflags = 0
        if platform.system() == "Windows":
            creationflags = 0x08000000  # CREATE_NO_WINDOW
            
        _tunnel_process = subprocess.Popen(
            [binary_path, "tunnel", "--url", f"http://127.0.0.1:{port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags
        )
        
        # Start thread to read logs and grab the URL
        _tunnel_thread = threading.Thread(target=_monitor_tunnel, args=(_tunnel_process,), daemon=True)
        _tunnel_thread.start()
        
        return _tunnel_process
    except Exception as e:
        logger.error(f"Failed to start cloudflared process: {e}")
        _tunnel_process = None
        return None

def stop_tunnel():
    """Stops the running Cloudflare Tunnel."""
    global _tunnel_process, _tunnel_url
    
    if _tunnel_process:
        logger.info("Stopping Cloudflare Tunnel...")
        try:
            _tunnel_process.terminate()
            # Wait up to 3 seconds for exit
            _tunnel_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            logger.warning("Tunnel process did not terminate. Killing it...")
            try:
                _tunnel_process.kill()
            except Exception as e:
                logger.error(f"Failed to kill tunnel process: {e}")
        except Exception as e:
            logger.error(f"Error terminating tunnel process: {e}")
            
        _tunnel_process = None
        _tunnel_url = None
        logger.info("Cloudflare Tunnel stopped.")

def get_tunnel_url():
    """Gets the current active Cloudflare Tunnel URL, or None if not started/ready."""
    return _tunnel_url
