GO2 Control Center — PRO (Windows)

Objectif
- Tout pilotage depuis une UI (sans taper de commandes)
- Test réseau (ICMP ping + UDP ping)
- Manette (pygame) + mapping "drone" :
  LY->vx (avance/recul), LX->vy (latéral), RX->wz (yaw)
- Pilotage clavier (sans manette): Z/S (avant/arrière), Q/D (latéral), E/R (yaw)
- Sécurité watchdog : si perte Wi‑Fi / plus d’inputs => stop automatique
- Envoi des commandes à fréquence fixe (send_hz) pour une conduite plus stable
- Vidéo MJPEG (optionnel) : URL configurable

Installation (UI-only)
1) Double-clique: launch_windows.bat
2) Dans l’app, onglet "Setup" -> "Install dependencies"
3) Re-lance si besoin.

Notes importantes
- Oui: le pilotage se fait bien via adresse IP (`robot_ip`) depuis ton PC vers le Go2.
- Cas standard Go2: connecte ton PC au Wi‑Fi local du robot et garde `robot_ip=192.168.12.1`.
- Dans l'UI, onglet Network: utilise "Check Wi-Fi route" puis "ICMP Ping" pour valider que ton PC voit le robot.
- Retour vidéo: onglet Video (MJPEG URL) puis "Apply" pour afficher le flux si le service vidéo robot est accessible.
- Bibliothèque de mouvements: onglet Teleop -> "Robot actions" (actions presets + méthode SDK2 custom pour appeler la librairie complète).
- Lumières: onglet Teleop -> "Robot lights" pour régler la luminosité (si `VuiClient` / support transport disponible).
- transport=udp_json : envoie des paquets UDP JSON (utile pour tester réseau et ton propre bridge)
- transport=udp_legged : essaie d’utiliser les bindings Python unitree_legged_sdk (si installés)
- transport=sdk2 : essaie d’utiliser unitree_sdk2_python (si installé) via SportClient/VuiClient.
  L'initialisation du channel SDK2 se fait avec l'IP robot configurée.

Si ton Go2 n’accepte pas le JSON UDP, le test UDP montrera juste "sent" mais pas de réponse.
Dans ce cas, utilise SDK2 (le plus fiable) ou un bridge sur le robot/routeur.

Sécurité
- Le watchdog envoie STOP (vx=vy=wz=0) en boucle si l’app ne reçoit plus d’inputs.
