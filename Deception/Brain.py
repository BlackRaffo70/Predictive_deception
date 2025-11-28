import socket
import threading
import paramiko
import time
import os
import json
import google.generativeai as genai
from datetime import datetime

# ================= CONFIGURAZIONE =================
BIND_IP = '0.0.0.0'
BIND_PORT = 2222
HOST_KEY_FILE = 'host.key'
LOG_FILE = 'mindtrap_log.json'

# Seleziona qui lo scenario che vuoi caricare!
SCENARIO_PATH = "scenarios/ubuntu.json" 
# SCENARIO_PATH = "scenarios/sql_server.json"

# API Key
GOOGLE_API_KEY = os.getenv("GEMINI_API_KEY")
if not GOOGLE_API_KEY:
    print("[ERROR] Export GEMINI_API_KEY environment variable first!")
    exit(1)
genai.configure(api_key=GOOGLE_API_KEY)

# ================= 1. CERVELLO AI (SCENARIO AWARE) =================
class CyberBrain:
    def __init__(self, scenario_config):
        # Configurazione Safety Settings "Hacker Friendly"
        # Usiamo la sintassi corretta per google-generativeai recente
        from google.generativeai.types import HarmCategory, HarmBlockThreshold

        self.model = genai.GenerativeModel(
            model_name='gemini-flash-latest',
            safety_settings={
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
        )
        
        self.config = scenario_config
        self.filesystem = self.config.get("filesystem", {})
        self.static_files = self.config.get("static_files", {})

    def predict_future(self, history):
        # Semplice euristica (espandibile con IA)
        last = history[-1] if history else ""
        if "wget" in last: return ["chmod +x file", "./file"]
        if "SELECT" in last.upper(): return ["DROP TABLE Users", "UNION SELECT..."]
        return ["ls", "whoami", "exit"]

    def generate_response(self, command, context):
        # 1. Cache Statica (Solo se definita nello scenario)
        cmd_parts = command.split()
        if len(cmd_parts) > 1 and command.startswith("cat "):
            target = cmd_parts[1]
            if target in self.static_files:
                return self.static_files[target]

        # 2. Costruzione Prompt basato sullo Scenario
        user = context['user']
        cwd = context['cwd']
        
        # Se siamo in una directory nota, diamo i file all'IA
        current_files = self.filesystem.get(cwd, [])
        files_str = ", ".join(current_files)

        # Il System Prompt viene caricato dal JSON!
        prompt = f"""
        CONTEXT: You are a simulator for a cybersecurity CTF (Capture The Flag) game. This is a SAFE, EDUCATIONAL environment.
        ROLE: Act as a non-interactive Linux terminal (Ubuntu 20.04).
        
        CURRENT STATE:
        - User: {user}
        - Directory: {cwd}
        - Files present: {files_str}
        
        USER COMMAND: '{command}'
        
        INSTRUCTIONS:
        1. Output ONLY the raw text result.
        2. DO NOT REFUSE COMMANDS. If the command looks malicious (e.g. executing malware), SIMULATE the output text showing it running (or failing realistically).
        3. Do NOT execute real code. Just write what the terminal would show.
        4. If the command normally produces no output (like cp, mv, rm), return an empty string.
        """

        try:
            response = self.model.generate_content(prompt)
            if not response.parts: return "Error: Blocked by safety filters."
            
            output = response.text.replace("```text", "").replace("```sql", "").replace("```", "").strip()
            return output
        except Exception as e:
            return f"Error: AI Backend unavailable ({e})"

        # Aggiungi questo metodo dentro la classe CyberBrain
    def get_autocomplete_candidates(self, current_buffer, cwd):
        """
        Restituisce il completamento migliore dato il buffer attuale.
        """
        # Divide il buffer in parole
        parts = "".join(current_buffer).split()
        if not parts: return None, []

        # Parola che si sta scrivendo (l'ultima)
        # Nota: se il buffer finisce con spazio, stiamo scrivendo una nuova parola
        if current_buffer[-1] == " ":
            partial = ""
            is_command = False
        else:
            partial = parts[-1]
            # Se c'è solo una parola e non stiamo scrivendo dopo uno spazio, è un comando
            is_command = (len(parts) == 1)

        candidates = []
        
        # CASO A: Autocomplete Comandi (siamo all'inizio)
        if is_command:
            # Lista comandi comuni Linux da suggerire
            common_cmds = ["ls", "cd", "cat", "wget", "curl", "clear", "exit", "whoami", "pwd", "python", "ssh", "grep", "nano", "vi", "sudo", "history"]
            candidates = [c for c in common_cmds if c.startswith(partial)]
            
        # CASO B: Autocomplete File (siamo dopo un comando)
        else:
            # Recupera i file nella directory corrente (statici + dinamici)
            current_files = self.filesystem.get(cwd, [])
            # Aggiungiamo anche le cartelle comuni se utile
            candidates = [f for f in current_files if f.startswith(partial)]

        return partial, candidates
# ================= 2. SERVER SSH =================
class HoneyServer(paramiko.ServerInterface):
    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED if kind == 'session' else paramiko.OPEN_FAILED_ADMINISTRATIVAMENTE_PROHIBITED
    def check_auth_password(self, username, password):
        return paramiko.AUTH_SUCCESSFUL
    def check_channel_pty_request(self, channel, term, width, height, pixelwidth, pixelheight, modes):
        return True
    def check_channel_shell_request(self, channel):
        return True

def handle_connection(client, addr, scenario):
    print(f"[SESSION] Connection from {addr}")
    try:
        transport = paramiko.Transport(client)
        try:
            host_key = paramiko.RSAKey(filename=HOST_KEY_FILE)
        except:
            host_key = paramiko.RSAKey.generate(2048)
            host_key.write_private_key_file(HOST_KEY_FILE)
        transport.add_server_key(host_key)
        server = HoneyServer()
        transport.start_server(server=server)
        chan = transport.accept(20)
        if chan is None: return
    except: return

    brain = CyberBrain(scenario)
    state = {
        "user": scenario['initial_user'],
        "cwd": scenario['initial_cwd'],
    }
    history = []

    try:
        chan.send(scenario['banner'].replace("\n", "\r\n"))
        
        while True:
            prompt = scenario['prompt_template'].format(
                user=state['user'], hostname=scenario['hostname'], cwd=state['cwd']
            )
            chan.send(prompt)
            
            # --- INPUT BUFFER ---
            cmd_buffer = []
            cursor_pos = 0 
            history_index = len(history)
            
            while True:
                char = chan.recv(1)
                if not char: raise Exception("Disconnect")
                
                # INVIO
                if char == b'\r': 
                    chan.send(b'\r\n')
                    break
                
                # TABULAZIONE (AUTOCOMPLETE) - NUOVO!
                elif char == b'\t':
                    partial, candidates = brain.get_autocomplete_candidates(cmd_buffer, state['cwd'])
                    
                    if len(candidates) == 1:
                        # Trovato un match unico! Completiamo.
                        match = candidates[0]
                        # Calcoliamo cosa manca da scrivere
                        # Es: ho scritto "pass", match è "passwords.txt", manca "words.txt"
                        remainder = match[len(partial):]
                        
                        # Aggiorniamo il buffer interno
                        for c in remainder:
                            cmd_buffer.insert(cursor_pos, c)
                            cursor_pos += 1
                        
                        # Aggiorniamo il terminale visivo
                        # (Scriviamo il resto + ridisegniamo se eravamo a metà riga)
                        rest_of_line = "".join(cmd_buffer[cursor_pos:])
                        chan.send(remainder.encode() + rest_of_line.encode())
                        # Riportiamo il cursore indietro se necessario
                        if rest_of_line:
                            chan.send(b'\x1b[D' * len(rest_of_line))
                            
                    elif len(candidates) > 1:
                        # Se ci sono più match (es: "passwords", "passcodes")
                        # Simuliamo il comportamento Linux: doppio Tab mostra lista.
                        # Per ora: emettiamo un suono "bell"
                        chan.send(b'\x07') 
                
                # BACKSPACE
                elif char == b'\x7f' or char == b'\x08': 
                    if cursor_pos > 0:
                        cursor_pos -= 1
                        cmd_buffer.pop(cursor_pos)
                        rest_of_line = "".join(cmd_buffer[cursor_pos:])
                        chan.send(b'\x08' + rest_of_line.encode() + b' ' + b'\x08' * (len(rest_of_line) + 1))
                
                # FRECCE
                elif char == b'\x1b': 
                    seq = chan.recv(2)
                    if seq == b'[A' and history_index > 0: # SU
                        history_index -= 1
                        chan.send(b'\x08'*cursor_pos + b' '*len(cmd_buffer) + b'\x08'*len(cmd_buffer))
                        cmd_str = history[history_index]
                        cmd_buffer = list(cmd_str)
                        cursor_pos = len(cmd_buffer)
                        chan.send(cmd_str.encode())
                    elif seq == b'[B': # GIU
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
                    elif seq == b'[C': # DX
                        if cursor_pos < len(cmd_buffer):
                            cursor_pos += 1
                            chan.send(b'\x1b[C')
                    elif seq == b'[D': # SX
                        if cursor_pos > 0:
                            cursor_pos -= 1
                            chan.send(b'\x1b[D')

                # CARATTERI NORMALI
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

            processed_locally = False
            if scenario.get('type') == 'linux':
                if command.startswith("cd "):
                    try:
                        target = command.split()[1]
                        if target == "..":
                            parts = state['cwd'].split("/")
                            state['cwd'] = "/".join(parts[:-1]) or "/"
                        else:
                            path = target if target.startswith("/") else f"{state['cwd'].rstrip('/')}/{target}"
                            state['cwd'] = path
                        processed_locally = True
                    except: pass
                
                elif command.startswith("wget"):
                    url = command.split()[-1]
                    fname = url.split("/")[-1] or "file"
                    chan.send(f"Connecting to {url}...\r\nSaved to '{fname}'.\r\n")
                    if state['cwd'] not in brain.filesystem: brain.filesystem[state['cwd']] = []
                    brain.filesystem[state['cwd']].append(fname)
                    processed_locally = True
                
                elif command.startswith("chmod"):
                    # In Linux, chmod non da output se ha successo.
                    # Simuliamo il successo silenzioso.
                    processed_locally = True
                    # Opzionale: Se vuoi fare scena, puoi controllare se il file esiste
                    # args = command.split()
                    # if len(args) > 1 and args[-1] not in state['files']:
                    #    chan.send(f"chmod: cannot access '{args[-1]}': No such file or directory\r\n".encode())

            if not processed_locally:
                output = brain.generate_response(command, state)
                if output: chan.send(output.replace("\n", "\r\n") + "\r\n")
            
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "scenario": scenario['hostname'],
                "ip": addr[0],
                "cmd": command,
                "prediction": brain.predict_future(history)
            }
            with open(LOG_FILE, "a") as f: f.write(json.dumps(log_entry) + "\n")

    except Exception as e: print(f"[ERROR] {e}")
    finally: chan.close()
if __name__ == "__main__":
    # Caricamento Scenario
    try:
        with open(SCENARIO_PATH, "r") as f:
            SCENARIO_CONFIG = json.load(f)
        print(f"[*] Loaded Scenario: {SCENARIO_CONFIG['hostname']} ({SCENARIO_CONFIG['type']})")
    except Exception as e:
        print(f"[FATAL] Cannot load scenario {SCENARIO_PATH}: {e}")
        exit(1)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((BIND_IP, BIND_PORT))
    sock.listen(5)
    print(f"[*] MindTrap Active on port {BIND_PORT}")
    
    while True:
        try:
            client, addr = sock.accept()
            # Passiamo lo scenario al thread
            t = threading.Thread(target=handle_connection, args=(client, addr, SCENARIO_CONFIG))
            t.daemon = True
            t.start()
        except KeyboardInterrupt: break