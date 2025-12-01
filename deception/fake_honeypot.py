#!/usr/bin/env python3
import json, time, os
from datetime import datetime

# Percorso nuovo, compatibile con defender.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "output_deception", "honeypot_log")
LOG = os.path.join(LOG_DIR, "mindtrap_log.json")

# Crea cartelle se non esistono
os.makedirs(LOG_DIR, exist_ok=True)

ip = "192.168.1.150"
scenario = "default"

print("Fake honeypot attivo. Scrivi comandi per simulare un attaccante.\n")

while True:
    cmd = input("> ").strip()
    if not cmd:
        continue

    entry = {
        "timestamp": datetime.now().isoformat(),
        "scenario": scenario,
        "ip": ip,
        "cmd": cmd
    }

    # Appende una riga JSONL
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    print(f"[LOG] scritto: {entry}")