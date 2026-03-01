
# -*- coding: utf-8 -*-
import os, sys, json, time, threading, socket, subprocess, platform
from urllib.parse import urlparse
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

APP_TITLE = "Go2 Control Center — PRO"
CONFIG_FILE = "config.json"
REQ_FILE = "requirements.txt"

def now():
    return time.time()

def clamp(x, a, b):
    return a if x < a else b if x > b else x

def apply_deadzone(x, dz):
    if abs(x) < dz:
        return 0.0
    # rescale for smoothness
    s = 1 if x >= 0 else -1
    return s * (abs(x) - dz) / (1.0 - dz)

def is_http_url(url):
    parsed = urlparse(url)
    return (parsed.scheme or "http").lower() in ("http", "https")

def build_mjpeg_candidates(url):
    """Build a short list of likely MJPEG endpoints from a user-provided URL."""
    parsed = urlparse(url)
    scheme = parsed.scheme or "http"
    host = parsed.hostname
    if not host:
        return [url]

    # Keep probing conservative: same host and same port only.
    # Unitree Go2 architecture does not expose a guaranteed built-in MJPEG endpoint,
    # so users usually rely on an explicit bridge URL.
    port = parsed.port or (443 if scheme == "https" else 80)
    base_path = parsed.path or "/mjpeg"
    common_paths = [base_path, "/mjpeg", "/stream", "/stream.mjpg", "/video"]

    candidates = []
    seen = set()
    for path in common_paths:
        candidate = f"{scheme}://{host}:{int(port)}{path}"
        if candidate not in seen:
            candidates.append(candidate)
            seen.add(candidate)
    return candidates




def check_tcp_port(host, port, timeout=2.0):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        return sock.connect_ex((host, int(port))) == 0
    finally:
        try:
            sock.close()
        except Exception:
            pass
def list_ethernet_ipv4_candidates(log=None):
    """Best-effort detection of local Ethernet IPv4 addresses using OS commands."""
    cmd = ["ipconfig"] if platform.system().lower().startswith("win") else ["ip", "-4", "addr"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=4)
        out = p.stdout or ""
    except Exception as e:
        if callable(log):
            log(f"[ETH] interface detection error: {e}")
        return []

    lines = out.splitlines()
    candidates = []

    if platform.system().lower().startswith("win"):
        current_adapter = ""
        for raw in lines:
            line = raw.strip()
            low = line.lower()
            if line.endswith(":"):
                current_adapter = line[:-1]
                continue
            if ("ipv4" in low or "adresse ipv4" in low) and ":" in line:
                ip = line.split(":", 1)[1].strip().split("(")[0].strip()
                adapter_low = current_adapter.lower()
                if ("ethernet" in adapter_low or "eth" in adapter_low) and ip and ip != "127.0.0.1":
                    candidates.append((current_adapter, ip))
    else:
        current_adapter = ""
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            if line and line[0].isdigit() and ":" in line:
                # format: "2: eth0: <...>"
                current_adapter = line.split(":", 2)[1].strip()
                continue
            if line.startswith("inet "):
                ip = line.split()[1].split("/")[0]
                low = current_adapter.lower()
                if ("eth" in low or "en" in low) and ip != "127.0.0.1":
                    candidates.append((current_adapter, ip))

    # deduplicate
    seen = set()
    uniq = []
    for adapter, ip in candidates:
        key = (adapter, ip)
        if key not in seen:
            seen.add(key)
            uniq.append((adapter, ip))
    return uniq

def build_video_architecture_hint(url):
    parsed = urlparse(url)
    host = parsed.hostname or "robot"
    return (
        f". On Go2, no default MJPEG endpoint is guaranteed by Unitree architecture; "
        f"video is commonly transported via WebRTC/DTLS or other streams, so configure "
        f"an explicit MJPEG bridge/server URL for {host}."
    )

class Config:
    def __init__(self):
        self.data = {}
        self.load()

    def load(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        else:
            self.data = {}

    def save(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

class TransportBase:
    name = "base"
    def connect(self, cfg): raise NotImplementedError
    def send_move(self, vx, vy, wz): pass
    def send_action(self, action): pass
    def set_light(self, level): pass
    def close(self): pass

class UdpJsonTransport(TransportBase):
    name = "udp_json"
    def __init__(self, log):
        self.log = log
        self.sock = None
        self.addr = None

    def connect(self, cfg):
        ip = cfg["robot_ip"]
        port = int(cfg["udp"].get("json_port", cfg["udp"].get("robot_port", 8082)))
        self.addr = (ip, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        local_port = int(cfg["udp"].get("local_port", 0))
        try:
            self.sock.bind(("0.0.0.0", local_port))
        except Exception:
            pass
        self.sock.setblocking(False)
        self.log(f"[UDP_JSON] Ready -> {self.addr[0]}:{self.addr[1]}")
        return True

    def send_move(self, vx, vy, wz):
        if not self.sock: return
        pkt = json.dumps({"type":"move","vx":vx,"vy":vy,"wz":wz}).encode("utf-8")
        try:
            self.sock.sendto(pkt, self.addr)
        except Exception as e:
            self.log(f"[UDP_JSON] send error: {e}")

    def send_action(self, action):
        if not self.sock: return
        pkt = json.dumps({"type":"action","action":action}).encode("utf-8")
        try:
            self.sock.sendto(pkt, self.addr)
        except Exception as e:
            self.log(f"[UDP_JSON] action error: {e}")

    def set_light(self, level):
        if not self.sock: return
        pkt = json.dumps({"type":"lights","brightness":int(level)}).encode("utf-8")
        try:
            self.sock.sendto(pkt, self.addr)
        except Exception as e:
            self.log(f"[UDP_JSON] lights error: {e}")

    def close(self):
        if self.sock:
            try: self.sock.close()
            except: pass
        self.sock = None

class UdpLeggedTransport(TransportBase):
    name = "udp_legged"
    def __init__(self, log):
        self.log = log
        self.client = None

    def connect(self, cfg):
        try:
            from udp_legged_client import UdpLeggedClient, UdpConfig
        except Exception as e:
            self.log(f"[UDP_LEGGED] Missing module udp_legged_client.py: {e}")
            return False
        self.client = UdpLeggedClient(UdpConfig(
            robot_ip=cfg["robot_ip"],
            local_port=int(cfg["udp"].get("local_port", 8080)),
            robot_port=int(cfg["udp"].get("robot_port", 8082)),
            level=str(cfg["udp"].get("level","HIGHLEVEL")),
            frequency_hz=int(cfg.get("safety",{}).get("send_hz",50)),
        ))
        ok = self.client.init()
        self.log("[UDP_LEGGED] " + ("OK" if ok else "FAILED"))
        return ok

    def send_move(self, vx, vy, wz):
        if self.client: self.client.send_move(vx, vy, wz)

    def send_action(self, action):
        if self.client: self.client.send_action(action)

    def close(self):
        self.client = None

class Sdk2Transport(TransportBase):
    name = "sdk2"
    def __init__(self, log):
        self.log = log
        self.sport = None
        self.vui = None

    def connect(self, cfg):
        try:
            from unitree.robot.go2.sport.sport_client import SportClient
            self.sport = SportClient()
            if not self.sport.Init():
                self.log("[SDK2] SportClient Init failed")
                return False
        except Exception as e:
            self.log(f"[SDK2] Import/Init failed: {e}")
            return False

        try:
            from unitree.robot.go2.vui.vui_client import VuiClient
            self.vui = VuiClient()
            self.vui.Init()
        except Exception as e:
            self.vui = None
            self.log(f"[SDK2] Vui not available: {e}")

        self.log("[SDK2] Connected")
        return True

    def send_move(self, vx, vy, wz):
        if not self.sport: return
        try:
            self.sport.Move(float(vx), float(vy), float(wz))
        except Exception as e:
            self.log(f"[SDK2] Move error: {e}")

    def send_action(self, action):
        if not self.sport: return
        # Minimal safe actions. Others can be added once you confirm availability.
        m = str(action)
        try:
            fn = getattr(self.sport, m, None)
            if callable(fn):
                fn()
            else:
                self.log(f"[SDK2] Unknown action: {m}")
        except Exception as e:
            self.log(f"[SDK2] Action error: {e}")

    def set_light(self, level):
        if not self.vui:
            self.log("[SDK2] Light unavailable (VuiClient missing)")
            return
        try:
            self.vui.SetBrightness(int(level))
        except Exception as e:
            self.log(f"[SDK2] Light error: {e}")

    def close(self):
        self.sport = None
        self.vui = None

class VideoMJPEGViewer(ttk.Frame):
    def __init__(self, parent, log):
        super().__init__(parent)
        self.log = log
        self._running = False
        self._thread = None
        self.url = ""
        self.canvas = tk.Label(self, text="Video disabled", anchor="center")
        self.canvas.pack(fill="both", expand=True)
        self._imgtk = None

    def start(self, url):
        self.url = url
        try:
            import requests
            from PIL import Image, ImageTk
        except Exception as e:
            self.log(f"[VIDEO] Missing deps: {e}")
            return False

        if self._running:
            return True
        if not is_http_url(url):
            hint = "Video tab supports MJPEG over HTTP(S). For Go2 WebRTC/DTLS streams, use a bridge to MJPEG first."
            self.log(f"[VIDEO] unsupported URL scheme for built-in viewer: {url}. {hint}")
            self.canvas.configure(text=f"Video error: {hint}", image="")
            return False

        self._running = True
        self.canvas.configure(text="Connecting video...", image="")

        candidates = build_mjpeg_candidates(url)
        if len(candidates) > 1:
            self.log("[VIDEO] trying same-port endpoints: " + " | ".join(candidates[:4]) + (" ..." if len(candidates) > 4 else ""))

        def loop():
            import requests
            from PIL import Image, ImageTk
            last_error = None
            chosen_url = None

            for candidate in candidates:
                if not self._running:
                    break
                try:
                    r = requests.get(candidate, stream=True, timeout=3)
                    if r.status_code >= 400:
                        raise requests.HTTPError(f"HTTP {r.status_code}")
                    chosen_url = candidate
                    break
                except Exception as e:
                    last_error = e
                    self.log(f"[VIDEO] endpoint failed: {candidate} -> {e}")

            if not chosen_url:
                err_text = str(last_error) if last_error else "unknown error"
                hint = ""
                if "Failed to establish a new connection" in err_text or "10061" in err_text:
                    hint = build_video_architecture_hint(url)
                self.log(f"[VIDEO] error: {err_text}{hint}")
                self.canvas.after(0, lambda: self.canvas.configure(text=f"Video error: {err_text}{hint}", image=""))
                self._running = False
                return

            self.log(f"[VIDEO] connected: {chosen_url}")
            bytes_buf = b""
            try:
                for chunk in r.iter_content(chunk_size=4096):
                    if not self._running:
                        break
                    bytes_buf += chunk
                    a = bytes_buf.find(b"\xff\xd8")
                    b = bytes_buf.find(b"\xff\xd9")
                    if a != -1 and b != -1 and b > a:
                        jpg = bytes_buf[a:b+2]
                        bytes_buf = bytes_buf[b+2:]
                        try:
                            im = Image.open(io.BytesIO(jpg))
                            im = im.convert("RGB")
                            w = max(1, self.canvas.winfo_width())
                            h = max(1, self.canvas.winfo_height())
                            im.thumbnail((w, h))
                            imgtk = ImageTk.PhotoImage(im)
                            def upd():
                                self._imgtk = imgtk
                                self.canvas.configure(image=imgtk, text="")
                            self.canvas.after(0, upd)
                        except Exception:
                            pass
            except Exception as e:
                self.log(f"[VIDEO] stream error: {e}")
                self.canvas.after(0, lambda: self.canvas.configure(text=f"Video stream error: {e}", image=""))
            self._running = False
        import io
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._running = False

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1100x720")
        self.minsize(980, 640)

        self.cfg = Config()
        self.transport = None

        self.last_input_ts = 0.0
        self.teleop_enabled = tk.BooleanVar(value=False)
        self.video_enabled = tk.BooleanVar(value=bool(self.cfg.data.get("video",{}).get("enabled", False)))
        self.light_level = tk.IntVar(value=5)

        self._gamepad_thread = None
        self._gamepad_running = False

        self._watchdog_thread = None
        self._watchdog_running = True

        self._deps_installing = False

        self._build_ui()
        self._start_watchdog()

    # ---------- UI ----------
    def _build_ui(self):
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        left = ttk.Frame(self, padding=10)
        left.grid(row=0, column=0, sticky="nsw")
        right = ttk.Frame(self, padding=10)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        nb = ttk.Notebook(left)
        nb.pack(fill="both", expand=True)

        self.tab_setup = ttk.Frame(nb, padding=10)
        self.tab_network = ttk.Frame(nb, padding=10)
        self.tab_teleop = ttk.Frame(nb, padding=10)
        self.tab_video = ttk.Frame(nb, padding=10)
        self.tab_logs = ttk.Frame(nb, padding=10)

        nb.add(self.tab_setup, text="Setup")
        nb.add(self.tab_network, text="Network")
        nb.add(self.tab_teleop, text="Teleop")
        nb.add(self.tab_video, text="Video")
        nb.add(self.tab_logs, text="Logs")

        # Logs
        self.log_text = tk.Text(self.tab_logs, height=18, wrap="word")
        self.log_text.pack(fill="both", expand=True)
        self._log("[UI] Ready")

        # Right side: big status + mini controls
        self.status_var = tk.StringVar(value="Disconnected")
        ttk.Label(right, textvariable=self.status_var, font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="nw")

        self.video_view = VideoMJPEGViewer(right, self._log)
        self.video_view.grid(row=0, column=0, sticky="nsew", padx=(0,0), pady=(42,0))
        self.video_view.canvas.configure(text="Video preview (tab Video to configure)")

        # Setup tab
        self._build_setup_tab()
        self._build_network_tab()
        self._build_teleop_tab()
        self._build_video_tab()

    def _log(self, s):
        ts = time.strftime("%H:%M:%S")
        msg = f"[{ts}] {s}\n"
        try:
            self.log_text.insert("end", msg)
            self.log_text.see("end")
        except Exception:
            pass

    def _build_setup_tab(self):
        f = self.tab_setup
        ttk.Label(f, text="Dependencies & One-click setup", font=("Segoe UI", 11, "bold")).pack(anchor="w")

        self.dep_var = tk.StringVar(value="(not checked)")
        ttk.Label(f, textvariable=self.dep_var).pack(anchor="w", pady=(6,10))

        btns = ttk.Frame(f)
        btns.pack(fill="x")
        ttk.Button(btns, text="Check dependencies", command=self.check_deps).pack(side="left")
        ttk.Button(btns, text="Install dependencies", command=self.install_deps).pack(side="left", padx=8)

        ttk.Separator(f).pack(fill="x", pady=14)

        ttk.Label(f, text="Transport", font=("Segoe UI", 11, "bold")).pack(anchor="w")

        self.transport_var = tk.StringVar(value=self.cfg.data.get("transport","udp_json"))
        for name, label in [("udp_json","UDP JSON (test/bridge)"),
                            ("udp_legged","UDP legacy (unitree_legged_sdk bindings)"),
                            ("sdk2","SDK2 (unitree_sdk2_python)")]:
            ttk.Radiobutton(f, text=label, value=name, variable=self.transport_var).pack(anchor="w")

        ttk.Button(f, text="Connect", command=self.connect_transport).pack(anchor="w", pady=(10,0))
        ttk.Button(f, text="Disconnect", command=self.disconnect_transport).pack(anchor="w", pady=(6,0))

    def _build_network_tab(self):
        f = self.tab_network
        ttk.Label(f, text="Robot network configuration", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")

        cfg = self.cfg.data
        ttk.Label(f, text="Robot IP").grid(row=1, column=0, sticky="w", pady=(10,2))
        self.ip_entry = ttk.Entry(f)
        self.ip_entry.insert(0, cfg.get("robot_ip","192.168.12.1"))
        self.ip_entry.grid(row=2, column=0, sticky="ew")
        f.columnconfigure(0, weight=1)

        ports = ttk.Frame(f)
        ports.grid(row=3, column=0, sticky="ew", pady=10)
        ttk.Label(ports, text="UDP robot port").grid(row=0, column=0, sticky="w")
        self.port_entry = ttk.Entry(ports, width=10)
        self.port_entry.insert(0, str(cfg.get("udp",{}).get("robot_port",8082)))
        self.port_entry.grid(row=0, column=1, sticky="w", padx=8)

        ttk.Button(f, text="Save config", command=self.save_network_cfg).grid(row=4, column=0, sticky="w", pady=(6,0))

        ttk.Separator(f).grid(row=5, column=0, sticky="ew", pady=14)

        ttk.Label(f, text="Tests", font=("Segoe UI", 11, "bold")).grid(row=6, column=0, sticky="w")
        tbtns = ttk.Frame(f)
        tbtns.grid(row=7, column=0, sticky="ew", pady=8)
        ttk.Button(tbtns, text="ICMP Ping (OS ping)", command=self.icmp_ping).pack(side="left")
        ttk.Button(tbtns, text="UDP Ping (send test packet)", command=self.udp_ping).pack(side="left", padx=8)
        ttk.Button(tbtns, text="Diagnostic réseau", command=self.network_diagnosis).pack(side="left", padx=8)
        ttk.Button(tbtns, text="Ethernet check", command=self.ethernet_connection_check).pack(side="left", padx=8)

    def _build_teleop_tab(self):
        f = self.tab_teleop
        ttk.Label(f, text="Gamepad teleoperation (drone-style)", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")

        cfg = self.cfg.data.get("gamepad", {})
        self.dz_var = tk.DoubleVar(value=float(cfg.get("deadzone",0.15)))
        self.gvx = tk.DoubleVar(value=float(cfg.get("gain_vx",1.0)))
        self.gvy = tk.DoubleVar(value=float(cfg.get("gain_vy",1.0)))
        self.gwz = tk.DoubleVar(value=float(cfg.get("gain_wz",1.0)))

        row = 1
        for label, var, mn, mx, step in [
            ("Deadzone", self.dz_var, 0.0, 0.5, 0.01),
            ("Gain vx", self.gvx, 0.1, 2.0, 0.05),
            ("Gain vy", self.gvy, 0.1, 2.0, 0.05),
            ("Gain wz", self.gwz, 0.1, 2.0, 0.05),
        ]:
            ttk.Label(f, text=label).grid(row=row, column=0, sticky="w", pady=(10,2))
            s = ttk.Scale(f, from_=mn, to=mx, orient="horizontal", variable=var)
            s.grid(row=row+1, column=0, sticky="ew")
            row += 2

        f.columnconfigure(0, weight=1)

        ttk.Separator(f).grid(row=row, column=0, sticky="ew", pady=14); row += 1

        self.teleop_status = tk.StringVar(value="Gamepad: stopped")
        ttk.Label(f, textvariable=self.teleop_status, font=("Segoe UI", 10, "bold")).grid(row=row, column=0, sticky="w"); row += 1

        btns = ttk.Frame(f)
        btns.grid(row=row, column=0, sticky="ew", pady=8); row += 1
        ttk.Button(btns, text="Start gamepad", command=self.start_gamepad).pack(side="left")
        ttk.Button(btns, text="Stop gamepad", command=self.stop_gamepad).pack(side="left", padx=8)
        ttk.Button(btns, text="STOP NOW", command=self.stop_now).pack(side="left", padx=8)

        self.motion_var = tk.StringVar(value="vx=0.00 vy=0.00 wz=0.00")
        ttk.Label(f, textvariable=self.motion_var).grid(row=row, column=0, sticky="w"); row += 1

        ttk.Separator(f).grid(row=row, column=0, sticky="ew", pady=14); row += 1

        ttk.Label(f, text="Safety watchdog", font=("Segoe UI", 11, "bold")).grid(row=row, column=0, sticky="w"); row += 1
        self.wd_var = tk.DoubleVar(value=float(self.cfg.data.get("safety",{}).get("watchdog_timeout_sec",0.6)))
        ttk.Label(f, text="Timeout (sec)").grid(row=row, column=0, sticky="w", pady=(8,2)); row += 1
        ttk.Scale(f, from_=0.2, to=3.0, orient="horizontal", variable=self.wd_var).grid(row=row, column=0, sticky="ew"); row += 1
        ttk.Button(f, text="Save teleop settings", command=self.save_teleop_cfg).grid(row=row, column=0, sticky="w", pady=10)

    def _build_video_tab(self):
        f = self.tab_video
        ttk.Label(f, text="Video (MJPEG)", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        cfg = self.cfg.data.get("video", {})
        self.video_url = tk.StringVar(value=str(cfg.get("url","")))
        self.video_enabled.set(bool(cfg.get("enabled", False)))

        ttk.Checkbutton(f, text="Enable video preview", variable=self.video_enabled).grid(row=1, column=0, sticky="w", pady=(10,2))
        ttk.Label(f, text="MJPEG URL").grid(row=2, column=0, sticky="w", pady=(10,2))
        ttk.Entry(f, textvariable=self.video_url).grid(row=3, column=0, sticky="ew")
        f.columnconfigure(0, weight=1)

        btns = ttk.Frame(f)
        btns.grid(row=4, column=0, sticky="ew", pady=10)
        ttk.Button(btns, text="Apply", command=self.apply_video).pack(side="left")
        ttk.Button(btns, text="Stop video", command=self.stop_video).pack(side="left", padx=8)

    # ---------- actions ----------
    def check_deps(self):
        missing = []
        for mod in ("pygame","requests","PIL"):
            try:
                __import__(mod if mod != "PIL" else "PIL.Image")
            except Exception:
                missing.append(mod)

        sdk2_ready = True
        try:
            from unitree.robot.go2.sport.sport_client import SportClient  # noqa: F401
        except Exception:
            sdk2_ready = False

        if missing:
            self.dep_var.set("Missing: " + ", ".join(missing))
            self._log("[SETUP] Missing deps: " + ", ".join(missing))
        else:
            self.dep_var.set("OK: all dependencies available")
            self._log("[SETUP] All deps OK")

        if sdk2_ready:
            self._log("[SETUP] SDK2 base library detected (movement control ready with transport=sdk2)")
        else:
            self._log("[SETUP] SDK2 base library missing. Install 'unitree-sdk2py' for real robot movement.")

    def install_deps(self):
        if self._deps_installing:
            self._log("[SETUP] Install already in progress")
            return

        self._deps_installing = True

        # run pip in a background thread
        def run():
            self._log("[SETUP] Installing dependencies...")
            cmd = [sys.executable, "-m", "pip", "install", "-r", REQ_FILE]
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for line in p.stdout:
                    self._log(line.rstrip())
                rc = p.wait()
                self._log(f"[SETUP] pip exit code: {rc}")
                self.check_deps()
            except Exception as e:
                self._log(f"[SETUP] install error: {e}")
            finally:
                self._deps_installing = False

        threading.Thread(target=run, daemon=True).start()

    def save_network_cfg(self):
        self.cfg.data["robot_ip"] = self.ip_entry.get().strip()
        self.cfg.data.setdefault("udp", {})
        self.cfg.data["udp"]["robot_port"] = int(self.port_entry.get().strip())
        # also set json_port for udp_json
        self.cfg.data["udp"]["json_port"] = int(self.port_entry.get().strip())
        self.cfg.save()
        self._log("[CFG] Network saved")
        messagebox.showinfo("Saved", "Network configuration saved.")

    def save_teleop_cfg(self):
        g = self.cfg.data.setdefault("gamepad", {})
        g["deadzone"] = float(self.dz_var.get())
        g["gain_vx"] = float(self.gvx.get())
        g["gain_vy"] = float(self.gvy.get())
        g["gain_wz"] = float(self.gwz.get())
        self.cfg.data.setdefault("safety", {})
        self.cfg.data["safety"]["watchdog_timeout_sec"] = float(self.wd_var.get())
        self.cfg.save()
        self._log("[CFG] Teleop saved")
        messagebox.showinfo("Saved", "Teleop settings saved.")

    def connect_transport(self):
        self.cfg.load()
        self.cfg.data["transport"] = self.transport_var.get()
        self.cfg.save()

        if self.transport:
            self.transport.close()
            self.transport = None

        name = self.transport_var.get()
        if name == "udp_json":
            self.transport = UdpJsonTransport(self._log)
        elif name == "udp_legged":
            self.transport = UdpLeggedTransport(self._log)
        elif name == "sdk2":
            self.transport = Sdk2Transport(self._log)
        else:
            messagebox.showerror("Transport", f"Unknown transport: {name}")
            return

        ok = self.transport.connect(self.cfg.data)
        if ok:
            self.status_var.set(f"Connected via {name}")
        else:
            self.status_var.set("Disconnected")
            messagebox.showwarning("Connect failed", f"Could not connect using {name}.\nSee Logs tab.")

    def disconnect_transport(self):
        self.stop_gamepad()
        if self.transport:
            self.transport.close()
            self.transport = None
        self.status_var.set("Disconnected")
        self._log("[NET] Disconnected")

    def icmp_ping(self):
        ip = self.ip_entry.get().strip()
        if not ip:
            messagebox.showerror("Ping", "Robot IP is empty")
            return
        # OS ping
        count_flag = "-n" if platform.system().lower().startswith("win") else "-c"
        cmd = ["ping", count_flag, "1", ip]
        self._log("[PING] " + " ".join(cmd))
        def run():
            try:
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                self._log(p.stdout.strip() or p.stderr.strip())
                if p.returncode == 0:
                    messagebox.showinfo("Ping", "ICMP Ping OK")
                else:
                    messagebox.showwarning("Ping", "ICMP Ping FAILED (see logs)")
            except Exception as e:
                self._log(f"[PING] error: {e}")
                messagebox.showerror("Ping", str(e))
        threading.Thread(target=run, daemon=True).start()

    def udp_ping(self):
        if not self.transport:
            messagebox.showwarning("UDP Ping", "Connect a transport first (Setup tab -> Connect).")
            return
        # For udp_json: send a ping packet; for others: send a stop (harmless)
        try:
            self.transport.send_action("ping")
            self._log("[UDP] ping sent (best-effort)")
            messagebox.showinfo("UDP Ping", "UDP packet sent. (Some robots won't reply; check behavior/logs.)")
        except Exception as e:
            self._log(f"[UDP] ping error: {e}")
            messagebox.showerror("UDP Ping", str(e))


    def network_diagnosis(self):
        ip = self.ip_entry.get().strip()
        if not ip:
            messagebox.showerror("Diagnostic", "Robot IP is empty")
            return

        video_cfg = self.cfg.data.get("video", {})
        video_url = str(video_cfg.get("url", "")).strip()
        video_host = None
        video_port = None
        if video_url:
            parsed = urlparse(video_url)
            video_host = parsed.hostname
            if parsed.hostname:
                video_port = parsed.port or (443 if parsed.scheme == "https" else 80)

        udp_port = int(self.cfg.data.get("udp", {}).get("robot_port", 8082))
        count_flag = "-n" if platform.system().lower().startswith("win") else "-c"
        cmd = ["ping", count_flag, "1", ip]

        self._log("[DIAG] starting network diagnosis")
        self._log("[DIAG] " + " ".join(cmd))

        def run():
            ping_ok = False
            try:
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=6)
                self._log(p.stdout.strip() or p.stderr.strip())
                ping_ok = (p.returncode == 0)
            except Exception as e:
                self._log(f"[DIAG] ping error: {e}")

            if ping_ok:
                self._log(f"[DIAG] ICMP OK -> {ip}")
            else:
                self._log(f"[DIAG] ICMP FAILED -> {ip}")

            # UDP note: no handshake, only best-effort send visibility.
            self._log(f"[DIAG] UDP command channel target: {ip}:{udp_port} (no handshake by design)")

            if video_host and video_port:
                tcp_ok = check_tcp_port(video_host, video_port, timeout=2.5)
                if tcp_ok:
                    self._log(f"[DIAG] TCP video port OPEN -> {video_host}:{video_port}")
                else:
                    self._log(f"[DIAG] TCP video port CLOSED/REFUSED -> {video_host}:{video_port}")
                    self._log("[DIAG] hint: start/configure a MJPEG bridge/server and verify URL in Video tab")

            if ping_ok and not self.transport:
                self._log("[DIAG] hint: network reachable, now connect transport in Setup tab")

            if ping_ok:
                messagebox.showinfo("Diagnostic réseau", "Diagnostic terminé. Voir l'onglet Logs pour le détail.")
            else:
                messagebox.showwarning("Diagnostic réseau", "Ping ICMP échoué. Vérifie Wi-Fi, IP robot et interface réseau.")

        threading.Thread(target=run, daemon=True).start()

    def ethernet_connection_check(self):
        ip = self.ip_entry.get().strip()
        if not ip:
            messagebox.showerror("Ethernet", "Robot IP is empty")
            return

        self._log("[ETH] starting Ethernet connection check")

        def run():
            adapters = list_ethernet_ipv4_candidates(log=self._log)
            if adapters:
                self._log("[ETH] local Ethernet IPv4: " + " | ".join([f"{a}={v}" for a, v in adapters]))
            else:
                self._log("[ETH] no active Ethernet IPv4 adapter detected")

            count_flag = "-n" if platform.system().lower().startswith("win") else "-c"
            cmd = ["ping", count_flag, "1", ip]
            self._log("[ETH] " + " ".join(cmd))

            ping_ok = False
            try:
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=6)
                self._log(p.stdout.strip() or p.stderr.strip())
                ping_ok = (p.returncode == 0)
            except Exception as e:
                self._log(f"[ETH] ping error: {e}")

            if ping_ok:
                self._log(f"[ETH] robot reachable from host -> {ip}")
                messagebox.showinfo("Ethernet", "Ethernet check OK (robot reachable).")
            else:
                self._log(f"[ETH] robot unreachable -> {ip}")
                self._log("[ETH] hint: verify cable, NIC state, IP subnet (ex: PC 192.168.12.x / robot 192.168.12.1)")
                if not adapters:
                    self._log("[ETH] hint: no Ethernet adapter detected/enabled on this host")
                messagebox.showwarning("Ethernet", "Ethernet check failed (see Logs tab).")

        threading.Thread(target=run, daemon=True).start()

    def apply_video(self):
        self.cfg.data.setdefault("video", {})
        self.cfg.data["video"]["enabled"] = bool(self.video_enabled.get())
        self.cfg.data["video"]["url"] = self.video_url.get().strip()
        self.cfg.save()
        if self.video_enabled.get() and self.video_url.get().strip():
            self._log("[VIDEO] start " + self.video_url.get().strip())
            ok = self.video_view.start(self.video_url.get().strip())
            if not ok:
                messagebox.showwarning("Video", "Video could not start (missing deps or URL issue). See logs.")
        else:
            self.stop_video()

    def stop_video(self):
        self.video_view.stop()
        self._log("[VIDEO] stopped")

    def stop_now(self):
        self._send_move(0.0, 0.0, 0.0, force=True)

    # ---------- teleop ----------
    def start_gamepad(self):
        if self._gamepad_running:
            return
        if not self.transport:
            messagebox.showwarning("Teleop", "Connect transport first (Setup tab).")
            return
        try:
            import pygame
        except Exception as e:
            messagebox.showerror("Teleop", f"pygame missing: {e}\nUse Setup -> Install dependencies.")
            return

        self._gamepad_running = True
        self.teleop_status.set("Gamepad: starting...")
        self._log("[GAMEPAD] starting")

        def loop():
            import pygame
            pygame.init()
            pygame.joystick.init()

            if pygame.joystick.get_count() == 0:
                self._log("[GAMEPAD] No gamepad detected.")
                self.teleop_status.set("Gamepad: not found")
                self._gamepad_running = False
                return

            js = pygame.joystick.Joystick(0)
            js.init()
            self._log(f"[GAMEPAD] Connected: {js.get_name()}")
            self.teleop_status.set(f"Gamepad: {js.get_name()}")

            # mapping: LY->vx, LX->vy, RX->wz
            # pygame axis indices vary by controller; default:
            # 0=lx, 1=ly, 2=rx, 3=ry in many cases.
            last_ui = 0.0
            while self._gamepad_running:
                pygame.event.pump()

                lx = js.get_axis(0)
                ly = js.get_axis(1)
                rx = js.get_axis(2)

                cfg = self.cfg.data.get("gamepad", {})
                dz = float(self.dz_var.get())
                inv_ly = bool(cfg.get("invert_ly", True))
                inv_lx = bool(cfg.get("invert_lx", False))
                inv_rx = bool(cfg.get("invert_rx", False))

                if inv_ly: ly = -ly
                if inv_lx: lx = -lx
                if inv_rx: rx = -rx

                vx = apply_deadzone(float(ly), dz) * float(self.gvx.get())
                vy = apply_deadzone(float(lx), dz) * float(self.gvy.get())
                wz = apply_deadzone(float(rx), dz) * float(self.gwz.get())

                vx = clamp(vx, -1.0, 1.0)
                vy = clamp(vy, -1.0, 1.0)
                wz = clamp(wz, -1.0, 1.0)

                self._send_move(vx, vy, wz)

                t = now()
                if t - last_ui > 0.05:
                    last_ui = t
                    self.motion_var.set(f"vx={vx:+.2f}  vy={vy:+.2f}  wz={wz:+.2f}")

                time.sleep(0.02)

            # stop on exit
            self._send_move(0.0, 0.0, 0.0, force=True)
            try:
                js.quit()
            except Exception:
                pass
            pygame.joystick.quit()
            pygame.quit()
            self._log("[GAMEPAD] stopped")
            self.teleop_status.set("Gamepad: stopped")

        self._gamepad_thread = threading.Thread(target=loop, daemon=True)
        self._gamepad_thread.start()

    def stop_gamepad(self):
        if not self._gamepad_running:
            return
        self._gamepad_running = False

    def _send_move(self, vx, vy, wz, force=False):
        self.last_input_ts = now()
        if not self.transport:
            return
        # reduce spam if unchanged
        if not force:
            # still send at high rate; leave as is
            pass
        self.transport.send_move(vx, vy, wz)

    # ---------- watchdog ----------
    def _start_watchdog(self):
        if self._watchdog_thread:
            return

        def loop():
            while self._watchdog_running:
                timeout = float(self.wd_var.get()) if hasattr(self, "wd_var") else float(self.cfg.data.get("safety",{}).get("watchdog_timeout_sec",0.6))
                if self.transport and self._gamepad_running:
                    if now() - self.last_input_ts > timeout:
                        # stop repeats
                        self.transport.send_move(0.0, 0.0, 0.0)
                time.sleep(0.1)

        self._watchdog_thread = threading.Thread(target=loop, daemon=True)
        self._watchdog_thread.start()

    def on_close(self):
        try:
            self._watchdog_running = False
            self.stop_gamepad()
            self.stop_video()
            if self.transport:
                self.transport.send_move(0.0, 0.0, 0.0)
                self.transport.close()
        finally:
            self.destroy()

def main():
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()

if __name__ == "__main__":
    main()
