#!/usr/bin/env python3

# -------------------------
# INTRODUCTION
# -------------------------
"""
Defender Runtime (Enhanced):
- Monitora il log dell'honeypot.
- Predice i prossimi comandi con RAG + Gemini.
- Aggiorna `ubuntu.json` in tempo reale:
    1. command_cache: per l'output immediato dei comandi (es. git status output).
    2. static_files: per il contenuto dei file (es. cat config.php).
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import sys, os
import re

# SETUP PATHS
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)

from prompting.core_rag import VectorContextRetriever, make_rag_prompt
from prompting.evaluate_gemini_rag import query_gemini

# ================= CONFIGURAZIONE =================

# Directory Output
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE_DIR, "output_deception")

# File gestiti
HONEYPOT_LOG = os.path.join(OUT_DIR, "honeypot_log", "mindtrap_log.json")
COMMANDS_STATE_FILE = os.path.join(OUT_DIR, "runtime", "commands_state.json")
DEFENSE_INDEX_FILE = os.path.join(OUT_DIR, "runtime", "defenses_index.json")

# --- NUOVO: Path dello Scenario (Il "Cervello" da aggiornare) ---
# Assicurati che questo punti al file 'ubuntu.json' usato dal server SSH!
SCENARIO_FILE = os.path.join(ROOT_DIR, "deception/scenarios", "ubuntu.json")

# RAG Config
RAG_PERSIST_DIR = "/home/enrico/Documents/LM/Cybersec/Predictive_deception/chroma_storage"
CONTEXT_LEN = 5
RAG_K = 3
PRED_K = 5
GEMINI_MODEL = "gemini-flash-latest"

# Setup Directory
os.makedirs(os.path.join(OUT_DIR, "runtime"), exist_ok=True)
os.makedirs(os.path.join(OUT_DIR, "honeypot_log"), exist_ok=True)

# Init RAG
print(f"[*] Loading RAG from {RAG_PERSIST_DIR}...")
rag = VectorContextRetriever(persist_dir=RAG_PERSIST_DIR)

# ================= STATO MEMORIA =================

history_comandi: Dict[str, List[str]] = {}
active_predictions: Dict[str, Dict[str, Any]] = {}


# ================= UTILS JSON =================

def load_json(path: str, default):
    if not os.path.exists(path): return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default


def save_json(path: str, data: Any):
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, indent=2)


def load_scenario() -> Dict[str, Any]:
    return load_json(SCENARIO_FILE, {})


def save_scenario(data: Dict[str, Any]):
    # Salvataggio atomico per evitare corruzione durante la lettura dell'honeypot
    temp_path = SCENARIO_FILE + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    os.replace(temp_path, SCENARIO_FILE)


# ================= GESTIONE SCENARIO (INJECTION) =================

def inject_prediction_into_scenario(cwd: str, command: str, defense_data: Dict[str, Any]):
    """
    Inserisce nel JSON dello scenario:
    1. La risposta del comando (command_cache)
    2. I file artefatti (static_files)
    """
    scenario = load_scenario()

    # 1. Inject Command Cache (Output del comando)
    cmd_output = defense_data.get("terminal_output")
    if cmd_output:
        if "command_cache" not in scenario: scenario["command_cache"] = {}
        if cwd not in scenario["command_cache"]: scenario["command_cache"][cwd] = {}

        scenario["command_cache"][cwd][command] = cmd_output
        print(f"[INJECT] Cache aggiornata per '{command}' in {cwd}")

    # 2. Inject Artifacts (File statici)
    # Utile se il comando è 'cat file' o se il comando implica la creazione di file
    for artifact in defense_data.get("artifacts", []):
        path = artifact.get("path")  # Es: "config.php" o "/var/www/config.php"
        content = artifact.get("content")

        if path and content:
            # Risoluzione path assoluto
            if not path.startswith("/"):
                path = os.path.join(cwd, path).replace("\\", "/")  # Windows fix

            # Aggiorna static_files
            if "static_files" not in scenario: scenario["static_files"] = {}
            scenario["static_files"][path] = content

            # Aggiorna filesystem listing (opzionale, per ls)
            parent_dir = os.path.dirname(path)
            fname = os.path.basename(path)

            if "filesystem" not in scenario: scenario["filesystem"] = {}
            if parent_dir not in scenario["filesystem"]: scenario["filesystem"][parent_dir] = []

            if fname not in scenario["filesystem"][parent_dir]:
                scenario["filesystem"][parent_dir].append(fname)

            print(f"[INJECT] File creato: {path}")

    save_scenario(scenario)


def remove_prediction_from_scenario(cwd: str, command: str, defense_data: Dict[str, Any]):
    """
    Pulisce lo scenario quando una predizione non si avvera.
    """
    scenario = load_scenario()
    changed = False

    # 1. Rimuovi Command Cache
    if "command_cache" in scenario and cwd in scenario["command_cache"]:
        if command in scenario["command_cache"][cwd]:
            del scenario["command_cache"][cwd][command]
            changed = True
            print(f"[CLEAN] Rimossa cache per '{command}'")

    # 2. Rimuovi Artifacts (Opzionale: potremmo volerli lasciare per persistenza)
    # Per ora li rimuoviamo per non inquinare troppo
    for artifact in defense_data.get("artifacts", []):
        path = artifact.get("path")
        if path:
            if not path.startswith("/"): path = os.path.join(cwd, path)

            # Rimuovi da static_files
            if "static_files" in scenario and path in scenario["static_files"]:
                del scenario["static_files"][path]
                changed = True

            # Rimuovi da filesystem list
            parent_dir = os.path.dirname(path)
            fname = os.path.basename(path)
            if "filesystem" in scenario and parent_dir in scenario["filesystem"]:
                if fname in scenario["filesystem"][parent_dir]:
                    scenario["filesystem"][parent_dir].remove(fname)
                    changed = True

    if changed:
        save_scenario(scenario)


# ================= LLM GENERATION =================

def create_defense_for_predicted_command(command: str, cwd: str, session_key: str) -> Dict[str, Any]:
    prompt = f"""
You are a Cyber Deception Architect.
CONTEXT: Attacker is in directory: '{cwd}'. Predicted next command: '{command}'.

TASK: Generate the realistic output and side-effects for this command.

OUTPUT FORMAT (JSON ONLY):
{{
  "terminal_output": "The exact text printed to stdout/stderr. If command is silent (like mkdir), leave empty.",
  "artifacts": [
    {{
      "path": "filename_or_path",
      "content": "File content if the command reads/creates a file (e.g. for 'cat config.php' or 'touch info.txt')"
    }}
  ]
}}

RULES:
- "terminal_output" MUST mimic Ubuntu 20.04 exactly.
- If command is 'ls', generate the output list matching the artifacts.
- If command is 'git status', generate a realistic status.
- Artifacts are optional, use only if relevant.
- NO Markdown, NO explanations. ONLY JSON.
""".strip()

    raw = query_gemini(prompt, model_name=GEMINI_MODEL, temp=0.0)

    # Pulizia Output
    try:
        # Rimuove blocchi markdown ```json ... ```
        clean_text = re.sub(r"```json|```", "", str(raw)).strip()
        # Cerca la prima parentesi graffa
        start = clean_text.find("{")
        end = clean_text.rfind("}") + 1
        if start != -1 and end != -1:
            clean_text = clean_text[start:end]

        return json.loads(clean_text)
    except Exception as e:
        print(f"[LLM ERROR] Parsing fallito per {command}: {e}")
        return {"terminal_output": f"Error: command '{command}' execution failed.", "artifacts": []}


# ================= CORE LOGIC =================

def make_session_key(entry):
    return f"{entry.get('scenario', 'def')}|{entry.get('ip', 'unk')}"


def update_history(session_key, cmd):
    cmds = history_comandi.setdefault(session_key, [])
    cmds.append(cmd)
    save_json(COMMANDS_STATE_FILE, history_comandi)


def predict_next_commands(session_key):
    history = history_comandi.get(session_key, [])
    if not history: return ["ls", "id", "whoami"]

    context_list = history[-CONTEXT_LEN:]
    rag_text = rag.retrieve(current_context_list=context_list, k=RAG_K)
    prompt = make_rag_prompt(context_list=context_list, rag_text=rag_text, k=PRED_K)

    raw = query_gemini(prompt, model_name=GEMINI_MODEL, temp=0.0)
    if not raw: return ["ls"]

    return [line.strip() for line in raw.splitlines() if line.strip()][:PRED_K]


def plan_and_apply_defenses(session_key: str, cwd: str, predictions: List[str]):
    """
    Genera output e file per le predizioni e le inietta in ubuntu.json
    """
    state = {
        "predicted_commands": predictions,
        "defense_data": {}  # cmd -> json_data
    }

    # Carica indice difese esistenti (per risparmiare LLM calls)
    defense_index = load_json(DEFENSE_INDEX_FILE, {})

    for cmd in predictions:
        # Check cache locale script
        if cmd in defense_index:
            defense_data = defense_index[cmd]
            print(f"[DEFENSE] Reusing cache for '{cmd}'")
        else:
            # Chiedi a Gemini
            print(f"[DEFENSE] Generating for '{cmd}'...")
            defense_data = create_defense_for_predicted_command(cmd, cwd, session_key)
            defense_index[cmd] = defense_data

        state["defense_data"][cmd] = defense_data

        # INIEZIONE NELLO SCENARIO (LIVE)
        inject_prediction_into_scenario(cwd, cmd, defense_data)

    save_json(DEFENSE_INDEX_FILE, defense_index)
    active_predictions[session_key] = state


def cleanup_other_branches(session_key: str, actual_cmd: str, current_cwd: str):
    """
    Rimuove dallo scenario le predizioni non avverate per mantenere pulito il JSON.
    """
    state = active_predictions.get(session_key)
    if not state: return

    preds = state.get("predicted_commands", [])
    data_map = state.get("defense_data", {})

    # Se il comando reale non era previsto, potremmo voler pulire tutto.
    # Qui assumiamo di pulire tutto ciò che è diverso da actual_cmd

    for pred_cmd in preds:
        if pred_cmd == actual_cmd:
            continue  # Manteniamo la "timeline" corretta

        # Rimuovi le timeline alternative
        if pred_cmd in data_map:
            remove_prediction_from_scenario(current_cwd, pred_cmd, data_map[pred_cmd])

    # Reset stato predizioni attive
    active_predictions[session_key] = {}


# ================= MAIN =================

def follow_log(path):
    print(f"[*] Watching {path}...")
    while not os.path.exists(path): time.sleep(1)
    with open(path, "r", encoding="utf-8") as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1)
                continue
            try:
                yield json.loads(line)
            except:
                pass


def handle_new_command(entry):
    session = make_session_key(entry)
    cmd = entry.get("cmd", "").strip()
    # PRENDIAMO IL CWD DAL LOG (IMPORTANTE!)
    # Il log deve contenere il cwd dove è stato eseguito il comando
    cwd = entry.get("cwd", "/root")  # fallback default

    print(f"\n[{datetime.now().time()}] CMD: {cmd} (in {cwd})")

    # 1. Cleanup predizioni vecchie non avverate
    cleanup_other_branches(session, cmd, cwd)

    # 2. Aggiorna history
    update_history(session, cmd)

    # 3. Predici futuro
    predictions = predict_next_commands(session)
    print(f"   -> Predicting: {predictions}")

    # 4. Popola scenario
    plan_and_apply_defenses(session, cwd, predictions)


def main():
    global history_comandi
    history_comandi = load_json(COMMANDS_STATE_FILE, {})

    # Check scenario
    if not os.path.exists(SCENARIO_FILE):
        print(f"[ERROR] Scenario file not found at: {SCENARIO_FILE}")
        print("Please fix SCENARIO_FILE path in the script.")
        exit(1)

    try:
        for entry in follow_log(HONEYPOT_LOG):
            handle_new_command(entry)
    except KeyboardInterrupt:
        print("\n[STOP] Exiting.")


if __name__ == "__main__":
    main()