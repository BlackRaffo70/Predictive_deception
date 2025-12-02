import paramiko
import json
import threading
import time
from datetime import datetime
import config
from brain import CyberBrain
from ssh_server import HoneyServer

def handle_connection(client, addr, scenario_config):
    print(f"[SESSION] Connection from {addr}")
    transport = None
    try:
        transport = paramiko.Transport(client)
        try:
            host_key = paramiko.RSAKey(filename=config.HOST_KEY_FILE)
        except:
            host_key = paramiko.RSAKey.generate(2048)
            host_key.write_private_key_file(config.HOST_KEY_FILE)
        
        transport.add_server_key(host_key)
        server = HoneyServer()
        transport.start_server(server=server)
        
        # Attendiamo che l'autenticazione sia completata per avere l'username
        chan = transport.accept(20)
        if chan is None: return

        # =================================================================
        # 1. SETUP CREDIBILITÀ UTENTE
        # =================================================================
        
        # Recuperiamo l'utente che ha digitato "ssh user@..."
        logged_user = transport.get_username()
        
        # Default: se l'utente non esiste, inventiamo una home standard
        # Questo serve se l'hacker prova "ssh pippo@..." -> lo facciamo entrare in /home/pippo
        target_cwd = "/root" if logged_user == "root" else f"/home/{logged_user}"
        
        # Cerchiamo se l'utente esiste davvero nel /etc/passwd dello scenario
        # per dargli la home directory corretta (es. www-data -> /var/www)
        passwd_content = scenario_config['static_files'].get('/etc/passwd', '')
        for line in passwd_content.splitlines():
            parts = line.split(':')
            # Formato passwd: user:x:uid:gid:desc:HOME:shell
            if len(parts) >= 6 and parts[0] == logged_user:
                target_cwd = parts[5] # Campo 6 è la Home
                break

        # Inizializza il Brain
        brain = CyberBrain(config.SCENARIO_PATH)
        
        state = {
            "user": logged_user,
            "cwd": target_cwd,
        }
        history = []

        # Determina il carattere del prompt (# per root, $ per altri)
        prompt_char = "#" if state['user'] == "root" else "$"

        # Inviamo il banner di benvenuto
        chan.send(scenario_config['banner'].replace("\n", "\r\n"))
        
        while True:
            # =================================================================
            # 2. PROMPT DINAMICO
            # =================================================================
            # Ricostruiamo il prompt per essere fedele all'utente corrente
            # Esempio: root@prod-04:/var/www# oppure admin@prod-04:/home/admin$
            
            # Scorciatoia estetica: /home/user diventa ~
            display_cwd = state['cwd']
            if state['user'] != "root" and display_cwd.startswith(f"/home/{state['user']}"):
                display_cwd = display_cwd.replace(f"/home/{state['user']}", "~", 1)
            elif state['user'] == "root" and display_cwd == "/root":
                display_cwd = "~"

            # Costruiamo il prompt manualmente per massimo controllo
            prompt = f"{state['user']}@{scenario_config['hostname']}:{display_cwd}{prompt_char} "
            chan.send(prompt)
            
            # --- GESTIONE INPUT BUFFER (Uguale a prima) ---
            cmd_buffer = []
            cursor_pos = 0 
            history_index = len(history)
            
            while True:
                char = chan.recv(1)
                if not char: raise Exception("Disconnect")
                
                if char == b'\r': 
                    chan.send(b'\r\n')
                    break
                
                elif char == b'\t':
                    partial, candidates = brain.get_autocomplete_candidates(cmd_buffer, state['cwd'])
                    if len(candidates) == 1:
                        match = candidates[0]
                        remainder = match[len(partial):]
                        for c in remainder:
                            cmd_buffer.insert(cursor_pos, c)
                            cursor_pos += 1
                        rest_of_line = "".join(cmd_buffer[cursor_pos:])
                        chan.send(remainder.encode() + rest_of_line.encode())
                        if rest_of_line: chan.send(b'\x1b[D' * len(rest_of_line))
                    elif len(candidates) > 1:
                        chan.send(b'\x07')
                
                elif char == b'\x7f' or char == b'\x08': 
                    if cursor_pos > 0:
                        cursor_pos -= 1
                        cmd_buffer.pop(cursor_pos)
                        rest_of_line = "".join(cmd_buffer[cursor_pos:])
                        chan.send(b'\x08' + rest_of_line.encode() + b' ' + b'\x08' * (len(rest_of_line) + 1))
                
                elif char == b'\x1b': 
                    seq = chan.recv(2)
                    if seq == b'[A' and history_index > 0:
                        history_index -= 1
                        chan.send(b'\x08'*cursor_pos + b' '*len(cmd_buffer) + b'\x08'*len(cmd_buffer))
                        cmd_str = history[history_index]
                        cmd_buffer = list(cmd_str)
                        cursor_pos = len(cmd_buffer)
                        chan.send(cmd_str.encode())
                    elif seq == b'[B':
                         if history_index < len(history):
                            history_index += 1
                            chan.send(b'\x08'*cursor_pos + b' '*len(cmd_buffer) + b'\x08'*len(cmd_buffer))
                            if history_index == len(history): 
                                cmd_buffer = []
                                cursor_pos = 0
                            else:
                                cmd_str = history[history_index]
                                cmd_buffer = list(cmd_str)
                                cursor_pos = len(cmd_buffer)
                                chan.send(cmd_str.encode())
                    elif seq == b'[C':
                        if cursor_pos < len(cmd_buffer):
                            cursor_pos += 1
                            chan.send(b'\x1b[C')
                    elif seq == b'[D':
                        if cursor_pos > 0:
                            cursor_pos -= 1
                            chan.send(b'\x1b[D')
                else:
                    try:
                        char_decoded = char.decode('utf-8')
                        cmd_buffer.insert(cursor_pos, char_decoded)
                        cursor_pos += 1
                        if cursor_pos == len(cmd_buffer):
                            chan.send(char)
                        else:
                            rest_of_line = "".join(cmd_buffer[cursor_pos-1:])
                            chan.send(rest_of_line.encode())
                            chan.send(b'\x1b[D' * (len(rest_of_line) - 1))
                    except: pass
            
            command = "".join(cmd_buffer).strip()
            if not command: continue
            history.append(command)
            
            # --- LOGICA DI RISPOSTA ---
            if command == "exit": break
            if command == "clear":
                chan.send(b'\033[H\033[2J')
                continue

            # LOGICA LOCALE (CD, WGET)
            processed_locally = False
            if scenario_config.get('type') == 'linux':
                if command.startswith("cd "):
                    try:
                        target = command.split()[1]
                        if target == "..":
                            parts = state['cwd'].split("/")
                            # Evita di andare sopra la root vuota
                            if len(parts) <= 2: state['cwd'] = "/" 
                            else: state['cwd'] = "/".join(parts[:-1])
                        elif target == "~":
                            # cd ~ porta alla home dell'utente corrente
                            state['cwd'] = "/root" if state['user'] == "root" else f"/home/{state['user']}"
                        else:
                            # Risolve path assoluti o relativi
                            if target.startswith("/"):
                                path = target
                            else:
                                current = state['cwd'].rstrip('/')
                                path = f"{current}/{target}"
                            state['cwd'] = path
                        processed_locally = True
                    except: pass
                
                elif command.startswith("wget"):
                    url = command.split()[-1]
                    fname = url.split("/")[-1] or "file"
                    chan.send(f"Connecting to {url}...\r\nSaved to '{fname}'.\r\n".encode())
                    if state['cwd'] not in brain.filesystem: brain.filesystem[state['cwd']] = []
                    brain.filesystem[state['cwd']].append(fname)
                    processed_locally = True
                
                elif command.startswith("sudo"):
                    # Piccolo trucco: sudo non fa nulla qui, ma rimuove "sudo" dal comando
                    # per passarlo al Brain pulito, oppure lo gestisce Gemini.
                    # Per ora lasciamo che Gemini gestisca l'output di sudo
                    pass

            # SE NON GESTITO LOCALMENTE, CHIEDI AL BRAIN
            if not processed_locally:
                output = brain.generate_response(command, state)
                if output: chan.send(output.replace("\n", "\r\n").encode() + b"\r\n")
            
            # LOGGING (Includiamo il CWD per il Defender!)
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "scenario": scenario_config['hostname'],
                "ip": addr[0],
                "cmd": command,
                "cwd": state['cwd'],
                "user": state['user'], # Salviamo anche chi ha lanciato il comando
                "prediction": brain.predict_future(history)
            }
            with open(config.LOG_FILE, "a") as f: f.write(json.dumps(log_entry) + "\n")

    except Exception as e: 
        print(f"[ERROR Session] {e}")
    finally: 
        if transport: transport.close()