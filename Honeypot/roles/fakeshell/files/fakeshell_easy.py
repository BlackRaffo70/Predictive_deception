#!/usr/bin/env python3
import os
import json
import subprocess
import sys
import pty
import shlex

LOG_FILE = "/var/log/fakeshell.json"
ip = "192.168.1.150"

# Inizializza log
def log_command(cmd):
    entry = {
        "ip": ip,
        "cmd": cmd
    }

    with open(LOG_FILE,"a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

# Imposta la working directory iniziale come quella dell’utente
home_dir = os.path.expanduser("~")
cwd = home_dir

# Banner simile a Ubuntu
print(f"Welcome to Ubuntu 22.04.3 LTS\n")

while True:
    try:
        cmd = input(f"{cwd}$ ")
    except EOFError:
        break

    if not cmd.strip():
        continue

    log_command(cmd)

    if cmd in ["exit", "quit"]:
        print("logout")
        break

    # Gestione cd
    if cmd.startswith("cd"):
        try:
            parts = shlex.split(cmd)
            target = parts[1] if len(parts) > 1 else home_dir
            new_dir = os.path.abspath(os.path.join(cwd, target))

            if os.path.isdir(new_dir):
                cwd = new_dir
            else:
                print(f"cd: {target}: No such file or directory")
        except Exception as e:
            print("cd error:", e)
        continue

    # Esegui comando reale con pseudo-terminali (PRO → shell realistica)
    try:
        pid, fd = pty.fork()

        if pid == 0:
            # Child: cambia directory e lancia comando reale
            os.chdir(cwd)
            os.execvp("/bin/bash", ["bash", "-c", cmd])

        else:
            # Parent: mostra output del comando
            while True:
                try:
                    output = os.read(fd, 1024)
                    if not output:
                        break
                    sys.stdout.buffer.write(output)
                    sys.stdout.flush()
                except OSError:
                    break

    except Exception as e:
        print(f"Error executing command: {str(e)}")

print("Bye!")