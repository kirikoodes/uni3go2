# Stub: this file is here so the app can import it if you add real bindings later.
# If you already have the previous project with udp_legged_client.py, copy it here.
from dataclasses import dataclass

@dataclass
class UdpConfig:
    robot_ip: str
    local_port: int = 8080
    robot_port: int = 8082
    level: str = "HIGHLEVEL"
    frequency_hz: int = 50

class UdpLeggedClient:
    def __init__(self, cfg: UdpConfig): self.cfg = cfg
    def init(self) -> bool:
        raise RuntimeError("udp_legged bindings not installed. Use transport=udp_json or sdk2.")
    def send_move(self, vx: float, vy: float, wz: float): pass
    def send_action(self, action: str): pass
