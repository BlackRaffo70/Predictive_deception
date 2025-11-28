#!/usr/bin/env python3

# -------------------------
# INTRODUCTION -> some utils informations about the Python script
# -------------------------

"""
- MODALITÀ:

    Il codice è uno script Python per processare un SINGOLO file del dataset Zenodo record=3687527, contenente sessioni di attacco di un Cowrie SSH honeypot.
    Le funzioni presentate e le loro funzionalità principali sono:

        - normalize_command(cmd: str) -> Pulisce e normalizza un singolo comando shell (rimuove informazioni sensibili, maschera URL, IP, file, password ecc.)
        - filter_short_sessions(file_path: str, min_length: int = 5) -> Filtra le sessioni con meno di min_length comandi
        - analyze_cowrie_dataset(input_file: str, output_prefix: str) -> Analizza un file aggregato di sessioni Cowrie e genera file di output a seconda dell'opzione --want: file RAW (comandi NON normalizzati) e file CLEAN (comandi normalizzati), restituendo le statistiche

- PRE-REQUISITI:
    Aver scaricato il file di sessione Cowrie da dataset Zenodo. Per farlo si può utilizzare il file utilities_script/download_zenodo.py
        
- COMANDO PER ESECUZIONE:
    python3 inspectDataset/analyze_and_clean.py --input data/cyberlab_2020-02-02.json --output output/cowrie

    dove le flag sono:
    - input = File di input da analizzare
    - output = Radice dei file di output generati
    - filter = Specifica il numero di comandi minimo che devono avere le sessioni dopo il filtraggio
    - want = Preferenza sui file da generare: raw = solo file raw; clean = solo file clean; both = entrambi
"""

# -------------------------
# IMPORT SECTION -> imports necessary for the Python script
# -------------------------

import json
import argparse
from collections import defaultdict, Counter
import statistics
import os
import re

# -------------------------
# FUNCTIONS SECTION -> definition of the functions explained in the introduction
# -------------------------

def normalize_command(cmd: str) -> str:
    cmd = cmd.strip()
    cmd = re.sub(r'^CMD:\s*', '', cmd)
    cmd = re.sub(r'echo\s+-e\s+"[^"]+"(\|passwd\|bash)?', 'echo <SECRET>|passwd', cmd)
    cmd = re.sub(r'echo\s+"[^"]+"\|passwd', 'echo <SECRET>|passwd', cmd)
    cmd = re.sub(r'/var/tmp/[\.\w-]*\d{3,}', '/var/tmp/<FILE>', cmd)
    cmd = re.sub(r'/tmp/[\.\w-]*\d{3,}', '/tmp/<FILE>', cmd)
    cmd = re.sub(r'\b[\w\.-]+\.(log|txt|sh|bin|exe|tgz|gz)\b', '<FILE>', cmd)
    cmd = re.sub(r'(https?|ftp)://\S+', '<URL>', cmd)
    cmd = re.sub(r'\b\d{1,3}(?:\.\d{1,3}){3}\b', '<IP>', cmd)
    cmd = re.sub(r'echo\s+"admin\s+[^"]+"', 'echo "admin <SECRET>"', cmd)
    cmd = re.sub(r'\s+', ' ', cmd).strip()
    return cmd

def filter_short_sessions(file_path: str, min_length: int):
    filtered_lines = []

    # Per ogni riga del file specificato, vedo se il numero di comandi per sessione dell'elemento json è >= min_length
    with open(file_path, "r", encoding="utf-8") as file:

        for line in file:

            try:
                obj = json.loads(line)
                if "commands" in obj and len(obj["commands"]) >= min_length:
                    filtered_lines.append(obj)
            except json.JSONDecodeError:
                continue

    # Il file viene sovrascritto con i soli elementi json che contengono >= min_length comandi per sessione
    with open(file_path, "w", encoding="utf-8") as file:

        for obj in filtered_lines:
            file.write(json.dumps(obj, ensure_ascii=False) + "\n")
            
    print(f"Filtrate sessioni con meno di {min_length} comandi. Rimanenti: {len(filtered_lines)}")

def analyze_cowrie_dataset(args):
    print(f"🔍 Analisi file aggregato: {args.input}")

    # Prelevo la data, utile per i file di output
    source_name = os.path.basename(args.input)
    match = re.search(r"(\d{4}-\d{2}-\d{2})", source_name)
    file_date = match.group(1) if match else "unknown"

    # Caricamento del contenuto del file in data
    with open(args.input, "r", encoding="utf-8") as file: data = json.load(file)

    # Calcolo delle statistiche delle varie sessioni contenute nel file
    sessions = defaultdict(list)
    event_counter = Counter()
    for session_obj in data:
        for sid, events in session_obj.items():
            for ev in events:
                eventid = ev.get("eventid")
                event_counter[eventid] += 1
                if eventid == "cowrie.command.input":
                    cmd = (
                        ev.get("data")
                        or ev.get("input")
                        or ev.get("command")
                        or ev.get("payload")
                        or ev.get("message")
                    )
                    if cmd and isinstance(cmd, str):
                        if cmd.startswith("CMD: "):
                            cmd = cmd[5:]
                        sessions[sid].append(cmd.strip())

    n_sessions = len(sessions)
    lengths = [len(cmds) for cmds in sessions.values() if cmds]
    avg_len = statistics.mean(lengths) if lengths else 0
    median_len = statistics.median(lengths) if lengths else 0

    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    # Creazione file RAW filtrato -> i comandi di ogni sessione NON vengono normalizzati
    if args.want == "both" or args.want == "raw":
        out_sessions_raw = f"{args.output}_sessions_{file_date}_RAW.jsonl"
        with open(out_sessions_raw, "w", encoding="utf-8") as out:
            for sid, cmds in sessions.items():
                out.write(json.dumps({"session": sid, "commands": cmds, "source_file": file_date}) + "\n")
        filter_short_sessions(out_sessions_raw, args.filter)

        print(f"💾 RAW salvato: {out_sessions_raw}")

    # Creazione file CLEAN filtrato -> i comandi di ogni sessione vengono normalizzati
    if args.want == "both" or args.want == "clean":
        out_sessions_clean = f"{args.output}_sessions_{file_date}_CLEAN.jsonl"
        with open(out_sessions_clean, "w", encoding="utf-8") as out:
            for sid, cmds in sessions.items():
                cleaned = [normalize_command(c) for c in cmds]  # Normalizzazione del comando
                if cleaned:
                    out.write(json.dumps({"session": sid, "commands": cleaned, "source_file": file_date}) + "\n")
        filter_short_sessions(out_sessions_clean, args.filter)

        print(f"💾 CLEAN salvato: {out_sessions_clean}")
    
    # Return delle statistiche del file
    stats = {
        "source_file": file_date,
        "n_sessions": n_sessions,
        "avg_len": avg_len,
        "median_len": median_len,
        "event_types": dict(event_counter)
    }

    return stats

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="File di input da analizzare")
    parser.add_argument("--filter", type=int, default=5, help="Numero di sessioni per filtraggio. Le sessioni che presentano meno comandi del numero specificato, vengono filtrate")
    parser.add_argument("--output", default="output/cowrie", help="Radice dei file di output generati")
    parser.add_argument("--want", choices=["raw", "clean", "both"], default="both", help="Preferenza sui file da generare: raw = solo file raw; clean = solo file clean; both = entrambi")
    args = parser.parse_args()
    analyze_cowrie_dataset(args)
