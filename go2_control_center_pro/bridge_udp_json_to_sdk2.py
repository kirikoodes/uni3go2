"""UDP JSON -> Unitree SDK2 bridge (base).

Use this helper when the UI runs with transport=udp_json.
It listens for JSON datagrams and forwards move/action commands
through Unitree SDK2 SportClient.
"""

import argparse
import json
import socket
import sys
import time


def create_sport_client():
    from unitree.robot.go2.sport.sport_client import SportClient

    sport = SportClient()
    if not sport.Init():
        raise RuntimeError("SportClient.Init() failed")
    return sport


def dispatch_action(sport, action):
    # Minimal compatibility table + dynamic fallback.
    aliases = {
        "stop": "StopMove",
        "standup": "StandUp",
        "stand_up": "StandUp",
        "standdown": "StandDown",
        "stand_down": "StandDown",
        "balance": "BalanceStand",
        "sit": "StandDown",
    }
    method_name = aliases.get(str(action).lower(), action)
    fn = getattr(sport, method_name, None)
    if not callable(fn):
        return False, f"Unknown action '{action}'"
    fn()
    return True, f"Action {method_name}()"


def main():
    parser = argparse.ArgumentParser(description="UDP JSON bridge for Go2 SDK2")
    parser.add_argument("--bind", default="0.0.0.0", help="local listen IP")
    parser.add_argument("--port", type=int, default=8082, help="local listen UDP port")
    parser.add_argument("--timeout", type=float, default=0.6, help="watchdog timeout in seconds")
    args = parser.parse_args()

    try:
        sport = create_sport_client()
    except Exception as exc:
        print(f"[BRIDGE] SDK2 init error: {exc}")
        return 2

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.bind, args.port))
    sock.settimeout(0.1)

    print(f"[BRIDGE] listening on udp://{args.bind}:{args.port}")
    print("[BRIDGE] expected packets:")
    print('  {"type":"move","vx":0.2,"vy":0.0,"wz":0.0}')
    print('  {"type":"action","action":"StopMove"}')

    last_move_ts = 0.0
    while True:
        now = time.time()
        try:
            data, addr = sock.recvfrom(4096)
            payload = json.loads(data.decode("utf-8", errors="ignore"))
            pkt_type = str(payload.get("type", "")).lower().strip()

            if pkt_type == "move":
                vx = float(payload.get("vx", 0.0))
                vy = float(payload.get("vy", 0.0))
                wz = float(payload.get("wz", 0.0))
                sport.Move(vx, vy, wz)
                last_move_ts = now
                print(f"[BRIDGE] move from {addr[0]}:{addr[1]} -> vx={vx:.3f} vy={vy:.3f} wz={wz:.3f}")
            elif pkt_type == "action":
                ok, msg = dispatch_action(sport, payload.get("action", ""))
                print(f"[BRIDGE] {'ok' if ok else 'warn'}: {msg}")
            else:
                print(f"[BRIDGE] ignore packet type='{pkt_type}'")
        except socket.timeout:
            pass
        except KeyboardInterrupt:
            print("\n[BRIDGE] stopping")
            break
        except Exception as exc:
            print(f"[BRIDGE] packet error: {exc}")

        # watchdog safety: if commands stop, send zero move once per timeout window
        if last_move_ts and (now - last_move_ts) > args.timeout:
            sport.Move(0.0, 0.0, 0.0)
            last_move_ts = now
            print("[BRIDGE] watchdog stop -> vx=vy=wz=0")

    return 0


if __name__ == "__main__":
    sys.exit(main())
