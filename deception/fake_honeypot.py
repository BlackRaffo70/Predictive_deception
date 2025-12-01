import json, time

LOG = "mindtrap_log.json"
ip = "192.168.1.150"
scenario = "default"

print("Fake mindtrap running. Scrivi comandi:")

while True:
    cmd = input("> ").strip()
    if not cmd:
        continue

    entry = {
        "scenario": scenario,
        "ip": ip,
        "cmd": cmd
    }

    with open(LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")

    print(f"[LOG] scritto: {entry}")