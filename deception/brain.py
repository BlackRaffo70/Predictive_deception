import json
import os
import posixpath
import random
import time
from datetime import datetime
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold


class CyberBrain:
    def __init__(self, brain_file_path):
        # Configurazione AI senza censure (per permettere output tipo "hacker")
        self.model = genai.GenerativeModel(
            model_name='gemini-flash-latest',
            safety_settings={
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
        )
        self.brain_file_path = brain_file_path
        self._reload_state()

    def _reload_state(self):
        """Ricarica filesystem, file statici e cache comandi dal JSON."""
        try:
            with open(self.brain_file_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
                self.filesystem = self.config.get("filesystem", {})
                self.static_files = self.config.get("static_files", {})
                self.command_cache = self.config.get("command_cache", {})
        except Exception as e:
            print(f"[ERROR BRAIN] Reload fallito: {e}")

    def _resolve_path(self, current_cwd, target_input):
        """Risolve percorsi relativi (../file) in assoluti (/home/file)."""
        if target_input.startswith("/"):
            return posixpath.normpath(target_input)
        return posixpath.normpath(posixpath.join(current_cwd, target_input))

    def _handle_local_ls(self, cwd, cmd_parts, file_list):
        """Simula output di ls -la localmente senza AI."""
        flags = "".join([part.replace("-", "") for part in cmd_parts[1:] if part.startswith("-")])
        show_hidden = 'a' in flags
        long_format = 'l' in flags

        visible_files = []
        for f in file_list:
            if f.startswith(".") and not show_hidden: continue
            visible_files.append(f)

        if show_hidden: visible_files = [".", ".."] + visible_files
        if not visible_files: return ""

        if not long_format:
            visible_files.sort()
            return "  ".join(visible_files)

        output_lines = [f"total {len(visible_files) * 4}"]
        now = datetime.now().strftime("%b %d %H:%M")

        for fname in visible_files:
            # Simulazione basilare permessi
            if fname in [".", ".."] or "." not in fname:  # Cartelle (euristica)
                perms, links, size = "drwxr-xr-x", 2, 4096
            else:
                perms, links, size = "-rw-r--r--", 1, random.randint(100, 5000)
                if fname.endswith(".sh") or fname.endswith(".py"): perms = "-rwxr-xr-x"

            output_lines.append(f"{perms} {links} root root {size} {now} {fname}")

        return "\n".join(output_lines)

    def predict_future(self, history):
        # Placeholder per logica futura
        return ["ls", "whoami", "exit"]

    def generate_response(self, command, context):
        # AGGIORNAMENTO STATO (Per vedere modifiche del Defender)
        self._reload_state()

        cwd = context['cwd']
        cmd_parts = command.split()
        base_cmd = cmd_parts[0] if cmd_parts else ""
        clean_cmd = command.strip()

        # ---------------------------------------------------------
        # LIVELLO 0: CACHE PREDITTIVA (Command Cache)
        # Se il comando esatto per questa cartella è nel JSON, rispondi subito.
        # ---------------------------------------------------------
        if cwd in self.command_cache:
            if clean_cmd in self.command_cache[cwd]:
                print(f"[BRAIN] Cache Hit Level 0: {clean_cmd}")
                return self.command_cache[cwd][clean_cmd]

        # ---------------------------------------------------------
        # LIVELLO 1: FILE STATICI (Lettura Veloce)
        # Gestisce cat, head, tail, grep su file noti.
        # ---------------------------------------------------------
        read_commands = ["cat", "head", "tail", "more", "less", "nano", "vi", "vim", "grep"]
        if base_cmd in read_commands:
            # Trova il file target negli argomenti
            target_file = None
            for part in cmd_parts[1:]:
                if not part.startswith("-") and not part.startswith('"'):
                    target_file = part
                    break

            if target_file:
                full_path = self._resolve_path(cwd, target_file)
                if full_path in self.static_files:
                    content = self.static_files[full_path]

                    if base_cmd == "head": return "\n".join(content.splitlines()[:10])
                    if base_cmd == "tail": return "\n".join(content.splitlines()[-10:])
                    if base_cmd == "grep" and len(cmd_parts) >= 3:
                        keyword = cmd_parts[1].strip('"\'')
                        lines = [l for l in content.splitlines() if keyword in l]
                        return "\n".join(lines)
                    return content  # cat, nano, etc restituiscono tutto

        # ---------------------------------------------------------
        # LIVELLO 2: FILESYSTEM LOCALE (ls)
        # ---------------------------------------------------------
        if base_cmd in ["ls", "ll", "la"]:
            if base_cmd == "ll": cmd_parts.append("-l")
            if base_cmd == "la": cmd_parts.append("-la")
            current_files = self.filesystem.get(cwd, [])
            return self._handle_local_ls(cwd, cmd_parts, current_files)

        # ---------------------------------------------------------
        # LIVELLO 3: AI GENERATIVA (Fallback)
        # ---------------------------------------------------------
        user = context['user']
        current_files = self.filesystem.get(cwd, [])
        files_str = ", ".join(current_files)

        prompt = f"""
        CONTEXT: Cybersecurity CTF simulator.
        ROLE: Ubuntu 20.04 terminal.
        STATE: User={user}, CWD={cwd}, Files={files_str}
        COMMAND: '{clean_cmd}'
        INSTRUCTIONS: Output raw terminal text only. Simulate execution logic.
        """

        try:
            response = self.model.generate_content(prompt)
            if not response.parts: return ""
            return response.text.replace("```text", "").replace("```", "").strip()
        except Exception as e:
            return f"Error: AI Backend unavailable ({e})"

    def get_autocomplete_candidates(self, current_buffer, cwd):
        self._reload_state()
        parts = "".join(current_buffer).split()
        if not parts: return None, []

        if current_buffer[-1] == " ":
            partial = ""
            is_command = False
        else:
            partial = parts[-1]
            is_command = (len(parts) == 1)

        candidates = []
        if is_command:
            common = ["ls", "cd", "cat", "wget", "curl", "clear", "exit", "whoami", "pwd", "python", "ssh", "grep",
                      "nano", "vi", "sudo", "docker", "git"]
            candidates = [c for c in common if c.startswith(partial)]
        else:
            files = self.filesystem.get(cwd, [])
            candidates = [f for f in files if f.startswith(partial)]

        return partial, candidates