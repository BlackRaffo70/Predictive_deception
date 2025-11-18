#!/usr/bin/env python3

# -------------------------
# INTRODUCTION -> some utils informations about the Python script
# -------------------------

"""
- MODALITÀ:

    Il codice è uno script Python per analizzare e normalizzare i dataset Cowrie, in particolare i log di sessioni SSH honeypot.
    Le funzioni presentate e le loro funzionalità principali sono:

        - normalize_command(cmd: str) -> Pulisce e normalizza un singolo comando shell (rimuove informazioni sensibili, maschera URL, IP, file, password ecc.)
        - filter_short_sessions(file_path: str, min_length: int = 5) -> Filtra le sessioni con meno di min_length comandi
        - analyze_cowrie_dataset(input_file: str, output_prefix: str) -> Analizza un file aggregato di sessioni Cowrie e genera output RAW (originale) e CLEAN (utilizza filter_short_sessions) con statistiche.

- PRE-REQUISITI:
    Aver scaricato il file di sessione Cowrie da dataset Zenodo passato con flag --input
        
- COMANDO PER ESECUZIONE:
    python3 inspectDataset/analyze_and_clean.py --input data/cyberlab_2020-02-02.json --output output/cowrie
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

def filter_short_sessions(file_path: str, min_length: int = 5):
    filtered_lines = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
                if "commands" in obj and len(obj["commands"]) >= min_length:
                    filtered_lines.append(obj)
            except json.JSONDecodeError:
                continue
    with open(file_path, "w", encoding="utf-8") as f:
        for obj in filtered_lines:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    print(f"Filtrate sessioni con meno di {min_length} comandi. Rimanenti: {len(filtered_lines)}")

def analyze_cowrie_dataset(input_file: str, output_prefix: str):
    print(f"🔍 Analisi file aggregato: {input_file}")

    source_name = os.path.basename(input_file)
    match = re.search(r"(\d{4}-\d{2}-\d{2})", source_name)
    file_date = match.group(1) if match else "unknown"

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

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

    os.makedirs(os.path.dirname(output_prefix), exist_ok=True)

    # RAW
    out_sessions_raw = f"{output_prefix}_sessions_{file_date}_RAW.jsonl"
    out_stats_raw = f"{output_prefix}_stats_{file_date}_RAW.json"
    with open(out_sessions_raw, "w", encoding="utf-8") as out:
        for sid, cmds in sessions.items():
            out.write(json.dumps({"session": sid, "commands": cmds, "source_file": file_date}) + "\n")

    # 🔥 FILTRAGGIO RAW Aggiunto qui
    filter_short_sessions(out_sessions_raw, min_length=5)

    with open(out_stats_raw, "w", encoding="utf-8") as s:
        json.dump({
            "source_file": file_date,
            "n_sessions": n_sessions,
            "avg_len": avg_len,
            "median_len": median_len,
            "event_types": dict(event_counter)
        }, s, indent=2)
    print(f"💾 RAW salvato: {out_sessions_raw}")

    # CLEAN
    out_sessions_clean = f"{output_prefix}_sessions_{file_date}_CLEAN.jsonl"
    out_stats_clean = f"{output_prefix}_stats_{file_date}_CLEAN.json"
    with open(out_sessions_clean, "w", encoding="utf-8") as out:
        for sid, cmds in sessions.items():
            cleaned = [normalize_command(c) for c in cmds]
            if cleaned:
                out.write(json.dumps({"session": sid, "commands": cleaned, "source_file": file_date}) + "\n")

    filter_short_sessions(out_sessions_clean, min_length=5)

    with open(out_stats_clean, "w", encoding="utf-8") as s:
        json.dump({
            "source_file": file_date,
            "n_sessions": n_sessions,
            "avg_len": avg_len,
            "median_len": median_len,
            "event_types": dict(event_counter)
        }, s, indent=2)
    print(f"💾 CLEAN salvato: {out_sessions_clean}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="output/cowrie")
    args = parser.parse_args()
    analyze_cowrie_dataset(args.input, args.output)