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
import shutil
import subprocess
import shlex
from google.genai.types import HarmCategory, HarmBlockThreshold
from google.genai import Client
import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv

# -------------------------
# CONFIGURATIONS
# -------------------------

# Carica le variabili dal file .env -> lettura chiave GOOGLE_API
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

api_key = os.getenv("api_key")
if not api_key:
    sys.exit("ERRORE CRITICO: La variabile d'ambiente api_key non è impostata nel file .env")

client_gemini = Client(api_key=api_key)

#Creazione delle cartelle di output all'interno della cartella corrente
REAL_FS_BASE = "/home/user"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE_DIR, "output_deception")
HONEYPOT_LOG = "/var/log/fakeshell.json"                # json monitorato
COMMANDS_STATE_FILE = os.path.join(OUT_DIR, "runtime", "commands_state.json") # File dove il defender tiene traccia della history dei comandi per sessione
DEFENSE_INDEX_FILE = os.path.join(OUT_DIR, "runtime", "defenses_index.json") # File dove registriamo quali difese sono già state create per ogni comando

# Nota: manteniamo la variabile ma non la usiamo come cartella primaria per scrivere
DEFENSE_ARTIFACTS_DIR = os.path.join(OUT_DIR, "defense_artifacts") # Cartella concettuale contenente i file di difesa generati dal LLM (non più popolata automaticamente)
# creiamo solo le cartelle runtime e debug
os.makedirs(os.path.join(OUT_DIR, "runtime"), exist_ok=True) 
# non creare DEFENSE_ARTIFACTS_DIR perché non viene usata per scrittura operativa
os.makedirs(os.path.join(OUT_DIR, "debug"), exist_ok=True)   

# runtime file che riflette gli artefatti creati nel filesystem
ACTIVE_ARTIFACTS_FILE = os.path.join(OUT_DIR, "runtime", "active_artifacts.json")

# -------------------------
# QUERY SECTION
# -------------------------

RAG_PERSIST_DIR = "/home/vagrant/chroma_storage_ctx5"   # <--- MODIFICA QUI
CONTEXT_LEN = 5          # deve combaciare con --context-len usato per indicizzare il DB
RAG_K = 3                
PRED_K = 5              
GEMINI_MODEL = "gemini-flash-latest"


def query_gemini(prompt: str, model_name: str, temp: float = 0.0) -> str:

    try:
        #Visto che stiamo simulando degli attacchi, è necessario disattivare i blocchi di sicurezza
        safety_config = [
            {"category": HarmCategory.HARM_CATEGORY_HATE_SPEECH, "threshold": HarmBlockThreshold.BLOCK_NONE},
            {"category": HarmCategory.HARM_CATEGORY_HARASSMENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
            {"category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, "threshold": HarmBlockThreshold.BLOCK_NONE},
            {"category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
        ]

        response = client_gemini.models.generate_content(
            model=model_name,
            contents=prompt,
            config={
                "temperature": temp,
                "top_p": 0.1,
                "max_output_tokens": 1024,
                "safety_settings": safety_config # APPLICHIAMO I FILTRI PERMISSIVI
            }
        )

        # Controllo difensivo: se il modello restituisce None o non ha testo
        if not response or not response.text: return ""
        else: return response.text

    except Exception as exc:
        err_str = str(exc)
        # Gestione dell'errore in caso di error 404
        if "404" in err_str:
            print(f"\n[ERRORE FATALE] Modello '{model_name}' non trovato.")
            sys.exit(1)
        # Restituzione di una stringa vuota per non rompere il loop
        return ""


def make_rag_prompt(context_list: List[str], rag_text: str, k: int) -> str:
    current_history = "\n".join(context_list[-10:])
    return f"""
You are an AI simulating a cyber-attacker inside an SSH honeypot.
Your task is to predict the EXACT next command the attacker will type.

INSTRUCTIONS:
1. Analyze the 'CURRENT SESSION' below.
2. Look at the 'SIMILAR PAST ATTACKS' provided (Retrieval Augmented Generation) to understand attacker patterns.
3. Output the {k} most likely next commands.
4. Output ONLY raw commands, one per line. No explanations.

========================================
{rag_text}
========================================

CURRENT SESSION HISTORY:
{current_history}

PREDICT NEXT {k} COMMANDS (Raw text only):
""".strip()

class VectorContextRetriever:

    def __init__(self, persist_dir: str, collection_name="honeypot_attacks"):
        print(f"--- Apertura RAG DB già esistente ({persist_dir}) ---")

        # Apre un client che punta a un database ChromaDB già indicizzato
        self.client = chromadb.PersistentClient(path=persist_dir)

        # Modello di embedding (necessario per effettuare query sul DB esistente)
        self.emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )

        # Verifica che la collection esista già
        existing = [c.name for c in self.client.list_collections()]
        if collection_name not in existing:
            raise ValueError(
                f"La collection '{collection_name}' non esiste nel DB! "
                f"Collection trovate: {existing}"
            )

        # Apertura della collection esistente (NO creazione!)
        self.collection = self.client.get_collection(
            name=collection_name,
            embedding_function=self.emb_fn
        )

        print(f"--- Collection '{collection_name}' caricata correttamente ---")

    def retrieve(self, current_context_list: List[str], k: int) -> str:

        if not current_context_list:
            return ""

        query_text = " || ".join(current_context_list)

        # Query ai vettori già presenti nel DB
        results = self.collection.query(
            query_texts=[query_text],
            n_results=k
        )

        if not results['ids']:
            return ""

        # Estrazione dati
        ids = results['ids'][0]
        docs = results['documents'][0]
        metas = results['metadatas'][0]

        formatted_examples = ""

        for i in range(len(ids)):
            hist_ctx = docs[i].replace(" || ", "\n")
            hist_next = metas[i]['next_command']

            formatted_examples += (
                f"--- SIMILAR PAST ATTACK (Example {i+1}) ---\n"
                f"Context:\n{hist_ctx}\n"
                f"Attacker Next Move:\n{hist_next}\n\n"
            )

        return formatted_examples

rag = VectorContextRetriever(persist_dir=RAG_PERSIST_DIR)

# -------------------------
# STATE SECTION and UTILS 
# -------------------------

history_comandi: Dict[str, List[str]] = {}      # Storia dei comandi inseriti per sessione -> history_comandi[sessione] = {cmd1, cmd2, ..}
active_predictions: Dict[str, Dict[str, Any]] = {}  # Storia delle prediction per sessione -> active_predictions[sessione] = {"predicted_commands": [...], artifacts": { cmd_predetto: [lista_path_artefatti]}

# runtime mapping reale degli artefatti presenti in FS: path -> metadata
active_artifacts: Dict[str, Dict[str, Any]] = {}

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


# ===================== ACTIVE ARTIFACTS RUNTIME IO ===================

def load_active_artifacts():
    global active_artifacts
    active_artifacts = load_json(ACTIVE_ARTIFACTS_FILE, {})


def save_active_artifacts():
    save_json(ACTIVE_ARTIFACTS_FILE, active_artifacts)


# ===================== SESSION KEY ================================

# Crea una chiave di sessione in base a ip e scenario
def make_session_key(entry: Dict[str, Any]) -> str:
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

# -------------------------
# HANDLER NEW COMMAND -> workflow of handling new command:                                
# -------------------------

def handle_new_command(entry: Dict[str, Any]):
    session_key = make_session_key(entry)
    cmd = entry.get("cmd", "").strip()
    if not cmd:
        return

    print(f"[{datetime.now().isoformat()}] session={session_key} cmd={cmd}")

    # se il comando era una delle predizioni precedenti, tieni la branch difensiva applicata
    cleanup_other_branches(session_key, cmd)

    # Aggiorna history (memoria + JSON)
    update_history(session_key, cmd)

    # 3) Predici i prossimi PRED_K comandi con RAG + Gemini
    predictions = predict_next_commands(session_key)
    print(f"   -> Predizioni: {predictions}")

    # 4) Crea/applica difese per le 5 direzioni
    plan_and_apply_defenses(session_key, predictions)
    print(f"[DONE] Difese generate per '{cmd}' (session: {session_key})")


def cleanup_other_branches(session_key: str, actual_cmd: str):
    # Verifico la presenza di prediction correnti (se non sono presenti sono al primo comando della sessione)
    state = active_predictions.get(session_key)
    if not state:
        return

    # Verifico che il comando inserito non sia nelle prediction correnti
    preds = state.get("predicted_commands", [])
    if actual_cmd not in preds:
        return

    # Se è presente, recupero gli artefatti prodotti, rimuovendo quelli relativi agli altri comandi
    artifacts_by_cmd = state.get("artifacts", {})

    for cmd, paths in artifacts_by_cmd.items():
        if cmd == actual_cmd:
            continue
        for p in paths:
            try:
                # rimuovo il file reale se esiste
                if p and os.path.exists(p):
                    try:
                        # rimuovo anche con sudo per forzare la pulizia
                        subprocess.run(["sudo", "rm", "-f", p], check=False)
                        print(f"[REAL-FS] Rimosso artefatto reale: {p}")
                    except Exception as e:
                        print(f"[CLEANUP] Errore rimozione reale {p}: {e}")

                # rimuovo la traccia nel runtime active_artifacts
                if p and p in active_artifacts:
                    del active_artifacts[p]
                    print(f"[RUNTIME] Rimosso riferimento runtime per: {p}")
            except FileNotFoundError:
                pass
            except Exception as e:
                print(f"[CLEANUP] Errore rimozione {p}: {e}")

    # persist runtime changes
    save_active_artifacts()

    # Mantenimento degli artefatti relativi solo al comando predetto
    active_predictions[session_key] = {
        "predicted_commands": [actual_cmd],
        "artifacts": {actual_cmd: artifacts_by_cmd.get(actual_cmd, [])}
    }

def predict_next_commands(session_key: str) -> List[str]:
    # La prima prediction, nel caso di mancanza di history, è eseguita manualmente 
    history = history_comandi.get(session_key, [])
    if not history:
        return ["ls", "whoami", "pwd", "cat /etc/os-release", "exit"]

    context_list = history[-CONTEXT_LEN:]

    #  Recupero esempi di attacchi simili dal DB vettoriale
    rag_text = rag.retrieve(current_context_list=context_list, k=RAG_K)

    # Costruzione prompt
    prompt = make_rag_prompt(context_list=context_list, rag_text=rag_text, k=PRED_K)

    # Chiamata Gemini
    raw = query_gemini(prompt, model_name=GEMINI_MODEL)
    
    candidates = []
    if raw:
        print("[PREDICTION] Risposta ottenuta correttamente\n")
        candidates = [line.strip() for line in raw.splitlines() if line.strip()]
        return candidates[:PRED_K]
    else: 
        print("[PREDICTION] Risposta vuota\n")
        return ["ls", "whoami", "pwd", "cat /etc/os-release", "exit"]

def plan_and_apply_defenses(session_key: str, predictions: List[str]):
    new_defenses = []      
    reused_defenses = []

    state = {
        "predicted_commands": predictions,
        "artifacts": {}  # cmd -> [paths]
    }

    # Per ogni comando predetto, valuto se esiste già un prototipo di difesa
        # Se esiste -> la difesa viene riutilizzata
        # Se NON esiste -> viene inviata una query Gemini per far generare gli artefatti da LLM
    # In entrambi i casi, la difesa viene prodotta e inserita nella cartella /defense_artifacts (logica), ma i file reali nel filesystem sono creati in intended_path

    for cmd_pred in predictions:
        existing = find_existing_defense(cmd_pred)

        if existing:
            reused_defenses.append(cmd_pred)
            defense_meta = existing
        else:
            new_defenses.append(cmd_pred)
            defense_meta = create_defense_for_predicted_command(cmd_pred, session_key)
            register_defense(cmd_pred, defense_meta)

        # materializza gli artefatti reali; ora prende anche session_key e cmd_pred per metadata runtime
        artifact_paths = materialize_defense_artifacts(defense_meta, session_key, cmd_pred)
        state["artifacts"][cmd_pred] = artifact_paths

    active_predictions[session_key] = state

    # salva lo stato runtime aggiornato (active_artifacts è già aggiornato dentro materialize)
    save_active_artifacts()

    if new_defenses:
        print(f"[DEFENSE] Nuove difese create: {new_defenses}")
    if reused_defenses:
        print(f"[DEFENSE] Difese già esistenti riutilizzate: {reused_defenses}")

    print("[DEFENSE] Generazione difese completata.\n")


# -------------------------
# ARTFICATS SECTION -> functions used by plan_and_apply_defenses for the to think and create defense artifacts                              
# -------------------------

def create_defense_for_predicted_command(command: str, session_key: str) -> Dict[str, Any]:
    cmd_safe = command.replace("%", "%%")
    print(f"[DEFENSE]Pensando agli artefatti da creare per il comando {cmd_safe}")

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

    # Chiamata Gemini
    raw = query_gemini(prompt, model_name=GEMINI_MODEL)

    print("\n=== RAW GEMINI OUTPUT (ORIGINAL) ===")
    print(raw)
    print("====================================\n")

    # ---- 4) PARSING O FALLBACK ----
    try:
        defense = json.loads(raw)
    except:
        defense = {
            "description": f"Fallback defense for predicted command: {command}",
            "intended_path": f"/var/log/deception/{command.replace(' ', '_')}.log",
            "artifacts": [
                {
                    # path concettuale, non utilizzato come path reale
                    "path": f"{command.replace(' ', '_')}_fallback.txt",
                    "content": ""
                }
            ]
        }
        return defense

    print("\n=== FINAL DEFENSE OBJECT ===")
    print(defense)
    print("====================================\n")

    # ---- 5) FIX UNIVERSALE intended_path ----
    if "intended_path" not in defense or not defense["intended_path"]:
        safe_cmd = command.replace(" ", "_").replace("/", "_")
        defense["intended_path"] = f"{REAL_FS_BASE}/{safe_cmd}.txt"

    # ---- 6) FIX UNIVERSALE artifacts ----
    arts = defense.get("artifacts", [])

    if not arts:
        arts = [{
            "path": f"{command.replace(' ', '_')}_fallback.txt",
            "content": ""
        }]

    normalized = []
    for a in arts:
        # manteniamo il path concettuale (basename) ma non usiamo più DEFENSE_ARTIFACTS_DIR direttamente
        fname = os.path.basename(a.get("path", "artifact.txt"))
        normalized.append({
            "path": fname,
            "content": a.get("content", "")
        })

    defense["artifacts"] = normalized

    return defense

def materialize_defense_artifacts(defense: Dict[str, Any], session_key: str, predicted_command: str) -> List[str]:
    """
    Crea fisicamente i file indicati nella difesa sul filesystem.
    Restituisce la lista dei path reali che sono stati creati con successo.
    """
    paths: List[str] = []

    intended_real_path = defense.get("intended_path")

    # Se intended_path non esiste saltiamo
    if not intended_real_path:
        return paths

    # Prendiamo il content del primo artifact (regola del formato)
    arts = defense.get("artifacts", [])
    if not arts:
        return paths

    # Usando il primo artifact (il formato richiede esattamente uno)
    art = arts[0]
    content = art.get("content", "")

    real_path = intended_real_path

    try:
        # Creazione directory (senza sudo — in genere consentito)
        os.makedirs(os.path.dirname(real_path), exist_ok=True)

        # Scrittura sicura usando sudo tee con input bytes
        # evitiamo issues di quoting: passiamo content via stdin
        proc = subprocess.run(["sudo", "tee", real_path], input=content.encode("utf-8"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if proc.returncode == 0:
            print(f"[REAL-FS] Creato file reale: {real_path}")

            # aggiungo metadata al runtime active_artifacts
            meta = {
                "command": predicted_command,
                "session": session_key,
                "timestamp": int(time.time())
            }
            active_artifacts[real_path] = meta
            paths.append(real_path)
        else:
            print(f"[REAL-FS][ERRORE] tee fallito per {real_path} (returncode={proc.returncode})")
    except Exception as e:
        print(f"[REAL-FS][ERRORE] impossibile creare {real_path}: {e}")

    return paths

# -------------------------
# MAIN SECTION
# -------------------------

# Funzione che realizza un tail -f sul file di log JSONL.
def follow_log(path: str):
    while not os.path.exists(path):
        print(f"[WAIT] In attesa che esista il file di log: {path}")
        time.sleep(1)

    with open(path, "r", encoding="utf-8") as f:
        f.seek(0, os.SEEK_END)          # se si vuole processare anche il passato è necessario commentare questa riga

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

def main():
    load_commands_state()
    load_active_artifacts()
    print("[*] Defender runtime attivo.")
    print("[*] Ascolto log:", HONEYPOT_LOG)
    
    # Ogni nuova riga inserita nel file json, viene processata da handle_new_command
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
