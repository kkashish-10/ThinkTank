"""TradingView Webhook Tunnel Manager.

Provides helpers to launch and configure Cloudflare Quick Tunnels
(cloudflared) or ngrok, allowing TradingView cloud servers to route
alerts directly to your local bot port without manual port forwarding.
"""

import subprocess
import shutil
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TunnelManager:
    """Manages secure inbound tunnels for TradingView webhooks."""

    def __init__(self, local_port: int = 8080):
        self.local_port = local_port
        self.process: Optional[subprocess.Popen] = None

    def start_cloudflare_tunnel(self) -> Optional[str]:
        """Start Cloudflare Quick Tunnel (cloudflared) if installed.
        
        Returns:
            Public tunnel URL or None
        """
        cloudflared_path = shutil.which("cloudflared")
        if not cloudflared_path:
            logger.warning(
                "Cloudflared executable not found in PATH. "
                "Download it from: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/ "
                "or run: ngrok http 8080"
            )
            return None

        cmd = [cloudflared_path, "tunnel", "--url", f"http://localhost:{self.local_port}"]
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            logger.info(f"Cloudflare Tunnel started for local port {self.local_port}")
            return "Tunnel started in background"
        except Exception as e:
            logger.error(f"Failed to launch cloudflared: {e}")
            return None

    def stop(self) -> None:
        """Stop background tunnel process."""
        if self.process:
            self.process.terminate()
            self.process = None
            logger.info("Tunnel stopped.")
