#!/usr/bin/env python3

# -------------------------
# INTRODUCTION -> some utils informations about the Python script
# -------------------------

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

# -------------------------
# IMPORT SECTION -> imports necessary for the Python script
# -------------------------

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import sys, os


# --- FIX IMPORTS (non tocchiamo core_rag) ---
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)
sys.path.append(os.path.join(ROOT_DIR, "prompting"))

from prompting.core_rag import VectorContextRetriever, make_rag_prompt
from prompting.evaluate_gemini_rag import query_gemini

# ----------------------------------------------------------------------
# 🔧 OUTPUT DIRECTORY CENTRALIZZATA
# Tutto ciò che il defender genera (state, difese, log, artefatti, debug)
# verrà inserito dentro:  deception/output_deception/
# ----------------------------------------------------------------------

# Percorso assoluto della cartella corrente (deception/)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Cartella principale per tutti gli output
OUT_DIR = os.path.join(BASE_DIR, "output_deception")

# ----------------------------------------------------------------------
# 🔒 Percorsi specifici dei file gestiti dal defender
# ----------------------------------------------------------------------

# Log JSONL prodotto dal tuo finto honeypot (o vero se integrato)
HONEYPOT_LOG = os.path.join(OUT_DIR, "honeypot_log", "mindtrap_log.json")

# File dove il defender tiene traccia della history dei comandi per sessione
COMMANDS_STATE_FILE = os.path.join(OUT_DIR, "runtime", "commands_state.json")

# File dove registriamo quali difese sono già state create per ogni comando
DEFENSE_INDEX_FILE = os.path.join(OUT_DIR, "runtime", "defenses_index.json")

# Cartella contiene i file di difesa generati dal LLM
DEFENSE_ARTIFACTS_DIR = os.path.join(OUT_DIR, "defense_artifacts")

# ----------------------------------------------------------------------
# 📁 Creazione automatica delle cartelle (evita errori "No such file or directory")
# ----------------------------------------------------------------------
os.makedirs(os.path.join(OUT_DIR, "runtime"), exist_ok=True)         # stato interno
os.makedirs(os.path.join(OUT_DIR, "defense_artifacts"), exist_ok=True) # artefatti difesa
os.makedirs(os.path.join(OUT_DIR, "honeypot_log"), exist_ok=True)      # log honeypot monitorato
os.makedirs(os.path.join(OUT_DIR, "debug"), exist_ok=True)             # debug opzionale

# (Da qui in avanti lo script continua normalmente…)

# ====== CONFIG RAG / GEMINI ======
# IMPORTANTE:
# - deve essere lo stesso persist_dir che hai usato in evaluate_gemini_rag.py
#   dopo la linea: args.persist_dir = f"{args.persist_dir}_ctx{args.context_len}"
#   Esempio: "/media/matteo/T9/chroma_storage_ctx5"
RAG_PERSIST_DIR = os.getenv("chroma_storage")

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
    history = history_comandi.get(session_key, [])
    cmd_safe = command.replace("%", "%%")

    prompt = f"""
You must output ONLY a JSON object.

FORMAT (STRICT):

{{
  "description": "short description of the defense",
  "intended_path": "/realistic/system/path/that/an/attacker/would_expect",
  "artifacts": [
    {{
      "path": "defense_artifacts/<SAFE_FILENAME>",
      "content": "<FILE CONTENT>"
    }}
  ]
}}

RULES:
- EXACTLY ONE artifact inside the "artifacts" list.
- ALWAYS include the field "intended_path".
- "intended_path" must be a REALISTIC Linux path where such a file *would normally exist*.
- DO NOT output markdown or explanations.

Generate JSON for predicted command: "{cmd_safe}".
""".strip()

    # ---- 1) CHIAMATA A GEMINI ----
    raw = query_gemini(prompt, model_name=GEMINI_MODEL, temp=0.0)

    # ---- 2) PULIZIA ANTI-THOUGHT SIGNATURE ----
    if hasattr(raw, "candidates"):
        parts = []
        for c in raw.candidates:
            for p in c.content.parts:
                if hasattr(p, "text"):
                    parts.append(p.text)
        raw = "\n".join(parts)

    if not isinstance(raw, str):
        raw = str(raw)

    # ---- 3) ESTRAZIONE JSON PULITO ----
    import re
    candidates = re.findall(r"\{.*?\}", raw, flags=re.DOTALL)

    clean = "{}"
    for c in candidates:
        try:
            json.loads(c)
            clean = c
            break
        except:
            pass

    # ---- 4) PARSING O FALLBACK ----
    try:
        defense = json.loads(clean)
    except:
        defense = {
            "description": f"Fallback defense for predicted command: {command}",
            "intended_path": f"/var/log/deception/{command.replace(' ', '_')}.log",
            "artifacts": [
                {
                    "path": f"{DEFENSE_ARTIFACTS_DIR}/fallback_{abs(hash(command))}.txt",
                    "content": ""
                }
            ]
        }
        return defense

    # ---- 5) FIX UNIVERSALE intended_path ----
    if "intended_path" not in defense or not defense["intended_path"]:
        safe_cmd = command.replace(" ", "_").replace("/", "_")
        defense["intended_path"] = f"/var/log/deception/{safe_cmd}.log"

    # ---- 6) FIX UNIVERSALE artifacts ----
    arts = defense.get("artifacts", [])

    if not arts:
        arts = [{
            "path": f"{DEFENSE_ARTIFACTS_DIR}/{abs(hash(command))}.txt",
            "content": ""
        }]

    normalized = []
    for a in arts:
        fname = os.path.basename(a.get("path", "artifact.txt"))
        normalized.append({
            "path": f"{DEFENSE_ARTIFACTS_DIR}/{fname}",
            "content": a.get("content", "")
        })

    defense["artifacts"] = normalized

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

    new_defenses = []      # <--- comandi che NON c'erano
    reused_defenses = []   # <--- comandi che GIÀ esistevano

    state = {
        "predicted_commands": predictions,
        "artifacts": {}  # cmd -> [paths]
    }

    for cmd_pred in predictions:
        existing = find_existing_defense(cmd_pred)

        if existing:
            # Difesa già nota
            reused_defenses.append(cmd_pred)
            defense_meta = existing
        else:
            # NUOVA difesa generata
            new_defenses.append(cmd_pred)
            defense_meta = create_defense_for_predicted_command(cmd_pred, session_key)
            register_defense(cmd_pred, defense_meta)

        artifact_paths = materialize_defense_artifacts(defense_meta)
        state["artifacts"][cmd_pred] = artifact_paths

    active_predictions[session_key] = state

    # 🔥 LOG PULITO
    if new_defenses:
        print(f"[DEFENSE] Nuove difese create: {new_defenses}")
    if reused_defenses:
        print(f"[DEFENSE] Difese già esistenti riutilizzate: {reused_defenses}")

    print("[DEFENSE] Generazione difese completata.\n")


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
    print(f"[DONE] Difese generate per '{cmd}' (session: {session_key})")


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