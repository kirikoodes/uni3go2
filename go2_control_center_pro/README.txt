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

Activer le contrôle mouvement du robot (librairie de base)
1) Installer la librairie officielle SDK2 (base recommandée):
   - `pip install unitree-sdk2py`
   - Si ta version Python/OS ne supporte pas le wheel, installe depuis le repo officiel Unitree SDK2 Python.
2) Dans l’application, onglet Setup:
   - sélectionne `transport=sdk2`
   - clique `Connect`
3) Lance la manette dans l’onglet Teleop (`Start gamepad`).

Bridge prêt à l’emploi (udp_json -> SDK2)
- Fichier fourni: `bridge_udp_json_to_sdk2.py`
- Utilité: si tu veux garder `transport=udp_json` dans l’UI, le bridge convertit les paquets JSON en commandes SDK2 réelles.
- Démarrage:
  - `python bridge_udp_json_to_sdk2.py --bind 0.0.0.0 --port 8082`
- Puis dans l’app:
  - `transport=udp_json`
  - `robot_ip=<IP de la machine qui exécute le bridge>`
  - `UDP robot port=8082`

Notes importantes
- Onglet Network: utilise "Diagnostic réseau" pour vérifier ICMP + état du port TCP vidéo et distinguer un problème IP/Wi-Fi d'un serveur MJPEG absent.
- Bouton "Ethernet check": détecte les interfaces Ethernet locales (best-effort) et teste la reachability robot via ping pour valider le lien filaire.
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

WebRTC / DTLS (utile ?)
- Oui, c'est souvent le mode vidéo natif le plus réaliste sur Go2.
- Cette application intègre seulement un viewer MJPEG HTTP(S) dans l'UI.
- Si ta source est WebRTC/DTLS, ajoute un bridge (WebRTC -> MJPEG) puis configure l'URL MJPEG dans l’onglet Video.
- En pratique: WebRTC/DTLS pour faible latence, MJPEG pour simplicité d’intégration Tkinter.
