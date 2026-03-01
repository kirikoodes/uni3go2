GO2 Control Center — PRO (Windows)

Objectif
- Tout pilotage depuis une UI (sans taper de commandes)
- Test réseau (ICMP ping + UDP ping)
- Manette (pygame) + mapping "drone" :
  LY->vx (avance/recul), LX->vy (latéral), RX->wz (yaw)
- Sécurité watchdog : si perte Wi‑Fi / plus d’inputs => stop automatique
- Vidéo MJPEG (optionnel) : URL configurable

Installation (UI-only)
1) Double-clique: launch_windows.bat
2) Dans l’app, onglet "Setup" -> "Install dependencies"
3) Re-lance si besoin.

Notes importantes
- Onglet Network: utilise "Diagnostic réseau" pour vérifier ICMP + état du port TCP vidéo et distinguer un problème IP/Wi-Fi d'un serveur MJPEG absent.
- transport=udp_json : envoie des paquets UDP JSON (utile pour tester réseau et ton propre bridge)
- transport=udp_legged : essaie d’utiliser les bindings Python unitree_legged_sdk (si installés)
- transport=sdk2 : essaie d’utiliser unitree_sdk2_python (si installé) via SportClient/VuiClient.

Si ton Go2 n’accepte pas le JSON UDP, le test UDP montrera juste "sent" mais pas de réponse.
Dans ce cas, utilise SDK2 (le plus fiable) ou un bridge sur le robot/routeur.

Sécurité
- Le watchdog envoie STOP (vx=vy=wz=0) en boucle si l’app ne reçoit plus d’inputs.

Vidéo (important)
- D’après l’architecture Unitree Go2, un endpoint MJPEG HTTP standard n’est pas garanti par défaut.
- Si `http://192.168.12.1:8080/mjpeg` refuse la connexion, c’est souvent normal: il faut une source vidéo dédiée (bridge MJPEG/serveur caméra) et renseigner son URL exacte dans l’onglet Video.
- L’app teste maintenant quelques chemins MJPEG courants sur le même port pour aider au diagnostic, mais ne "devine" plus des ports alternatifs.

