#!/usr/bin/env python3

"""
Defender runtime:

- segue in tempo reale il log JSONL prodotto dall'honeypot (mindtrap_log.json)
- mantiene uno stato JSON con la history dei comandi per sessione
- per ogni comando nuovo:
    1) aggiorna la history
    2) usa il tuo RAG + Gemini per predire i prossimi 5 comandi
       (VectorContextRetriever + make_rag_prompt + query_gemini)
    3) per ciascuna delle 5 predizioni:
        - se esiste già una difesa (in defenses_index.json) → riusa
        - altrimenti chiama un LLM per farsi dire quali file creare
    4) quando arriva il comando successivo:
        - se appartiene alle 5 predizioni → tiene solo quella branch
          ed elimina gli artefatti (file) creati per le altre 4
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import sys, os

# aggiunge la directory superiore (Predictive_deception/) al PYTHONPATH
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)



# ===================== IMPORT DAI TUOI SCRIPT =====================

from prompting.core_rag import VectorContextRetriever, make_rag_prompt
from prompting.evaluate_gemini_rag import query_gemini  # usa già google.genai.Client e GOOGLE_API_KEY

# ===================== CONFIGURAZIONE =============================

# Log JSONL prodotto dal tuo honeypot MindTrap
HONEYPOT_LOG = "mindtrap_log.json"   # cambia se hai un path diverso

# File dove salviamo la history dei comandi per sessione
COMMANDS_STATE_FILE = "runtime/commands_state.json"

# File dove salviamo l’indice delle difese già definite per comando
DEFENSE_INDEX_FILE = "runtime/defenses_index.json"

# Cartella dove creiamo fisicamente gli artefatti di difesa
DEFENSE_ARTIFACTS_DIR = "defense_artifacts"

os.makedirs("runtime", exist_ok=True)
os.makedirs(DEFENSE_ARTIFACTS_DIR, exist_ok=True)

# ====== CONFIG RAG / GEMINI ======
# IMPORTANTE:
# - deve essere lo stesso persist_dir che hai usato in evaluate_gemini_rag.py
#   dopo la linea: args.persist_dir = f"{args.persist_dir}_ctx{args.context_len}"
#   Esempio: "/media/matteo/T9/chroma_storage_ctx5"
RAG_PERSIST_DIR = "/chroma_storage"   # <--- MODIFICA QUI

CONTEXT_LEN = 5          # deve combaciare con --context-len usato per indicizzare il DB
RAG_K = 3                # quanti esempi simili recuperare dal DB
PRED_K = 5               # quanti comandi predire
GEMINI_MODEL = "gemini-flash-latest"

# Inizializza retriever sul DB già vettorizzato
rag = VectorContextRetriever(persist_dir=RAG_PERSIST_DIR)
print(f"[RAG] Vettori presenti nel DB: {rag.collection.count()}")

# ===================== STATO IN MEMORIA ===========================

# history_comandi[session_key] = [cmd1, cmd2, ...]
history_comandi: Dict[str, List[str]] = {}

# active_predictions[session_key] = {
#   "predicted_commands": [...],
#   "artifacts": { cmd_predetto: [lista_path_artefatti] }
# }
active_predictions: Dict[str, Dict[str, Any]] = {}

# ===================== UTILS JSON =================================


def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return default


def save_json(path: str, data: Any):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ===================== SESSION KEY ================================


def make_session_key(entry: Dict[str, Any]) -> str:
    """
    Crea una chiave di sessione a partire dalla riga di log.
    Puoi cambiarlo se nel log hai un vero session id.
    """
    ip = entry.get("ip", "unknown_ip")
    scenario = entry.get("scenario", "default")
    return f"{scenario}|{ip}"


# ===================== STATO COMANDI ==============================


def load_commands_state():
    global history_comandi
    history_comandi = load_json(COMMANDS_STATE_FILE, {})


def save_commands_state():
    save_json(COMMANDS_STATE_FILE, history_comandi)


def update_history(session_key: str, cmd: str):
    """
    Aggiunge il comando alla history in RAM e aggiorna il JSON su disco.
    """
    cmds = history_comandi.setdefault(session_key, [])
    cmds.append(cmd)
    save_commands_state()


# ===================== INDICE DIFESE ==============================


def load_defense_index() -> Dict[str, Any]:
    return load_json(DEFENSE_INDEX_FILE, {"by_command": {}})


def save_defense_index(index: Dict[str, Any]):
    save_json(DEFENSE_INDEX_FILE, index)


def find_existing_defense(command: str) -> Optional[Dict[str, Any]]:
    """
    Ritorna la difesa salvata se esiste già per questo comando.
    Per ora match esatto; in futuro puoi usare pattern/regex.
    """
    index = load_defense_index()
    return index.get("by_command", {}).get(command)


def register_defense(command: str, defense_meta: Dict[str, Any]):
    """
    Registra/aggiorna la difesa per un comando nel JSON di indice.
    """
    index = load_defense_index()
    by_cmd = index.setdefault("by_command", {})
    by_cmd[command] = defense_meta
    save_defense_index(index)


# ===================== ARTEFATTI DI DIFESA ========================


def materialize_defense_artifacts(defense: Dict[str, Any]) -> List[str]:
    """
    Crea fisicamente i file indicati nella difesa sul filesystem.
    Una difesa ha forma:
    {
      "description": "...",
      "artifacts": [
        {"path": "defense_artifacts/...", "content": "..."},
        ...
      ]
    }
    """
    paths: List[str] = []

    for art in defense.get("artifacts", []):
        path = art.get("path")
        content = art.get("content", "")
        if not path:
            continue

        p = Path(path)
        # Forza l'artefatto dentro DEFENSE_ARTIFACTS_DIR per sicurezza
        if not str(p).startswith(DEFENSE_ARTIFACTS_DIR):
            p = Path(DEFENSE_ARTIFACTS_DIR) / p.name

        os.makedirs(p.parent, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)

        paths.append(str(p))

    return paths


# ===================== LLM: CREAZIONE NUOVA DIFESA =================


def create_defense_for_predicted_command(command: str, session_key: str) -> Dict[str, Any]:
    """
    Usa lo stesso client Gemini (query_gemini) per generare
    una difesa per un comando predetto.
    """
    history = history_comandi.get(session_key, [])

    prompt = f"""
You are a defensive assistant in a cybersecurity lab with an SSH honeypot.
You have observed the following session:

COMMAND HISTORY (chronological):
{json.dumps(history, ensure_ascii=False)}

PREDICTED command (possible next move of the attacker):
"{command}"

Define a LOCAL defense strategy that consists of creating some files
(artifacts, scripts, config files, rules, fake logs, etc.) but do NOT execute real commands.

Return ONLY a JSON object with this EXACT structure:

{
  "description": "short description of the defense",
  "artifacts": [
    {"path": "defense_artifacts/something.sh", "content": "#!/bin/bash\necho 'dummy defense'"},
    {"path": "defense_artifacts/other.conf", "content": "key=value"}
  ]
}

No comments or extra text, JSON only.
""".strip()

    raw = query_gemini(prompt, model_name=GEMINI_MODEL, temp=0.0)
    if not raw:
        # fallback se il modello non risponde
        return {
            "description": f"Fallback defense for predicted command: {command}",
            "artifacts": [
                {
                    "path": f"{DEFENSE_ARTIFACTS_DIR}/fallback_{abs(hash(command))}.txt",
                    "content": f"Defense placeholder for predicted command: {command}"
                }
            ]
        }

    try:
        defense = json.loads(raw)
    except Exception:
        # fallback se l'output non è JSON valido
        defense = {
            "description": f"Unparseable LLM defense for command: {command}",
            "artifacts": [
                {
                    "path": f"{DEFENSE_ARTIFACTS_DIR}/unparsed_{abs(hash(command))}.txt",
                    "content": raw
                }
            ]
        }

    return defense


# ===================== PREDIZIONE PROSSIMI COMANDI =================


def predict_next_commands(session_key: str) -> List[str]:
    """
    Usa i TUOI mattoni:
    - VectorContextRetriever.retrieve(...)   (RAG)
    - make_rag_prompt(...)                  (costruzione prompt)
    - query_gemini(...)                     (chiamata al modello)
    per ottenere i PRED_K comandi predetti.
    """
    history = history_comandi.get(session_key, [])
    if not history:
        return ["ls", "whoami", "pwd", "cat /etc/os-release", "exit"]

    # contesto = ultimi CONTEXT_LEN comandi
    context_list = history[-CONTEXT_LEN:]

    # 1) RAG: recupero esempi simili dal DB vettoriale
    rag_text = rag.retrieve(current_context_list=context_list, k=RAG_K)

    # 2) costruzione prompt con la tua funzione
    prompt = make_rag_prompt(context_list=context_list, rag_text=rag_text, k=PRED_K)

    # 3) chiamata al tuo query_gemini
    raw = query_gemini(prompt, model_name=GEMINI_MODEL, temp=0.0)

    if not raw:
        return ["ls", "whoami", "pwd", "cat /etc/os-release", "exit"]

    # 4) ogni riga = un possibile comando
    candidates = [line.strip() for line in raw.splitlines() if line.strip()]
    if not candidates:
        return ["ls", "whoami", "pwd", "cat /etc/os-release", "exit"]

    return candidates[:PRED_K]


# ===================== GESTIONE DIFESE MULTI-BRANCH =================


def plan_and_apply_defenses(session_key: str, predictions: List[str]):
    """
    Per le 5 predizioni:
    - se esiste già una difesa per il comando → riusa
    - altrimenti chiede a un LLM che file creare
    - crea fisicamente i file
    - memorizza gli artefatti per poterli cancellare in seguito
    """
    state = {
        "predicted_commands": predictions,
        "artifacts": {}  # cmd -> [paths]
    }

    for cmd_pred in predictions:
        existing = find_existing_defense(cmd_pred)
        if existing:
            defense_meta = existing
        else:
            defense_meta = create_defense_for_predicted_command(cmd_pred, session_key)
            register_defense(cmd_pred, defense_meta)

        artifact_paths = materialize_defense_artifacts(defense_meta)
        state["artifacts"][cmd_pred] = artifact_paths

    active_predictions[session_key] = state


def cleanup_other_branches(session_key: str, actual_cmd: str):
    """
    Se il comando reale appartiene alle predizioni correnti:
    - mantiene solo la difesa associata a quel comando
    - elimina gli artefatti (file) delle altre 4 branch.
    """
    state = active_predictions.get(session_key)
    if not state:
        return

    preds = state.get("predicted_commands", [])
    if actual_cmd not in preds:
        return

    artifacts_by_cmd = state.get("artifacts", {})

    for cmd, paths in artifacts_by_cmd.items():
        if cmd == actual_cmd:
            continue
        for p in paths:
            try:
                os.remove(p)
                print(f"[CLEANUP] Rimosso artefatto: {p}")
            except FileNotFoundError:
                pass
            except Exception as e:
                print(f"[CLEANUP] Errore rimozione {p}: {e}")

    # tieni solo la branch corretta
    active_predictions[session_key] = {
        "predicted_commands": [actual_cmd],
        "artifacts": {actual_cmd: artifacts_by_cmd.get(actual_cmd, [])}
    }


# ===================== FOLLOW DEL LOG HONEYPOT =====================


def follow_log(path: str):
    """
    Implementa un tail -f sul file di log JSONL.
    Ogni riga deve essere un JSON con almeno: scenario, ip, cmd.
    """
    while not os.path.exists(path):
        print(f"[WAIT] In attesa che esista il file di log: {path}")
        time.sleep(1)

    with open(path, "r", encoding="utf-8") as f:
        # vai in fondo: se vuoi processare anche il passato, commenta questa riga
        f.seek(0, os.SEEK_END)

        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1)
                continue
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                print("[WARN] Riga non valida nel log, la skippo.")
                continue

            yield entry


# ===================== HANDLER PRINCIPALE ==========================


def handle_new_command(entry: Dict[str, Any]):
    """
    Funzione centrale chiamata per ogni riga di log (un comando).
    """
    session_key = make_session_key(entry)
    cmd = entry.get("cmd", "").strip()
    if not cmd:
        return

    print(f"[{datetime.now().isoformat()}] session={session_key} cmd={cmd}")

    # 1) Se questo comando era una delle predizioni precedenti, tieni solo quella branch
    cleanup_other_branches(session_key, cmd)

    # 2) Aggiorna history (memoria + JSON)
    update_history(session_key, cmd)

    # 3) Predici i prossimi PRED_K comandi con RAG + Gemini
    predictions = predict_next_commands(session_key)
    print(f"   -> Predizioni: {predictions}")

    # 4) Crea/applica difese per le 5 direzioni
    plan_and_apply_defenses(session_key, predictions)


# ===================== MAIN LOOP ==================================


def main():
    load_commands_state()
    print("[*] Defender runtime attivo.")
    print("[*] Ascolto log:", HONEYPOT_LOG)

    try:
        for entry in follow_log(HONEYPOT_LOG):
            try:
                handle_new_command(entry)
            except Exception as e:
                print("[ERROR] durante handle_new_command:", e)
    except KeyboardInterrupt:
        print("\n[STOP] Interrotto da tastiera.")


if __name__ == "__main__":
    main()