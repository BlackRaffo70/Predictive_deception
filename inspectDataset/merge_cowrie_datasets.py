#!/usr/bin/env python3

# -------------------------
# INTRODUCTION -> some utils informations about the Python script
# -------------------------

"""
- MODALITÀ:

    Lo script serve per processare più file del dataset Zenodo con record=3687527. Lo script richiama 
    analyze_and_clean.py per ogni file, esegue il merge dei file CLEAN e RAW prodotti, calcolando anche 
    le statistiche aggregate. Il file CLEAN contenente il merge dei file viene poi suddiviso in modo randomico
    in due file: uno contenente il 70% delle righe del file iniziale, l'altro contenente il restante 30%.
    Queste funzionalità sono espresse attraverso l definizione di due funzioni:
        
        - merge_all(input_dir: str, output_prefix: str) -> esegue analyze_and_clean.py per ogni file, generando file RAW e CLEAN, esegue il merge di tutti i file RAW e CLEAN creati e calcola le statistiche aggregate
        - split_jsonl_file(input_path: str, output_train: str, output_test: str, train_ratio: float = 0.7) -> Divide un file .jsonl in due file (train/test) selezionando le righe in modo casuale senza ripetizioni.

- PRE-REQUISITI:
    Presenza dello script analyze_and_clean.py
        
- COMANDO PER ESECUZIONE:
    python inspectDataset/merge_cowrie_datasets.py
"""

# -------------------------
# IMPORT SECTION -> imports necessary for the Python script
# -------------------------

import argparse
import os
from glob import glob
import subprocess
import re
import json
import random
import statistics

# -------------------------
# FUNCTION SECTION -> definition of the function explained in the introduction
# -------------------------

def split_jsonl_file(input_path: str, output_train: str, output_test: str, train_ratio: float = 0.7) -> None:
    # Caricamento righe e randomizzazione
    with open(input_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    random.shuffle(lines)

    # Calcolo divisione del file in base a train_ratio
    split_point = int(len(lines) * train_ratio)
    train_lines = lines[:split_point]
    test_lines = lines[split_point:]

    # Scrittura dei due file
    with open(output_train, "w", encoding="utf-8") as f_train:
        f_train.writelines(train_lines)

    with open(output_test, "w", encoding="utf-8") as f_test:
        f_test.writelines(test_lines)

def merge_all(input_dir: str, output_prefix: str):
    os.makedirs(os.path.dirname(output_prefix), exist_ok=True)

    files = sorted(glob(os.path.join(input_dir, "*.json")))
    if not files:
        print("❌ Nessun file JSON trovato.")
        return

    print(f"Trovati {len(files)} file Cowrie.\n")

    raw_outputs = []
    clean_outputs = []
    stats_outputs = []
    aggregated_events = {}

    # analyze_and_clean.py per ogni file
    for path in files:
        basename = os.path.basename(path)
        match = re.search(r"(\d{4}-\d{2}-\d{2})", basename)
        date = match.group(1) if match else "unknown"

        out_prefix = f"{output_prefix}_{date}"

        print(f"▶️ Elaborazione: {basename}")

        cmd = [
            "python3",
            "inspectDataset/analyze_and_clean.py",
            "--input", path,
            "--output", out_prefix
        ]

        subprocess.run(cmd, check=True)

        raw_path = f"{out_prefix}_sessions_{date}_RAW.jsonl"
        clean_path = f"{out_prefix}_sessions_{date}_CLEAN.jsonl"
        stats_path = f"{out_prefix}_stats_{date}.json"

        raw_outputs.append(raw_path)
        clean_outputs.append(clean_path)
        stats_outputs.append(stats_path)

        # aggiunge EVENT_TYPES alle stats globali
        if os.path.exists(stats_path):
            try:
                with open(stats_path, "r", encoding="utf-8") as s:
                    st = json.load(s)
                    events = st.get("event_types", {})
                    for k, v in events.items():
                        aggregated_events[k] = aggregated_events.get(k, 0) + v
            except:
                pass

    print("\n🧩 Tutti i file elaborati. Inizio merge finale...\n")

    # Merge di tutti i file RAW
    merged_raw_path = f"{output_prefix}_ALL_RAW.jsonl"
    with open(merged_raw_path, "w", encoding="utf-8") as out:
        for fp in raw_outputs:
            if os.path.exists(fp):
                with open(fp, "r", encoding="utf-8") as f:
                    out.write(f.read())

    # Merge di tutti i file CLEAN
    merged_clean_path = f"{output_prefix}_ALL_CLEAN.jsonl"
    with open(merged_clean_path, "w", encoding="utf-8") as out:
        for fp in clean_outputs:
            if os.path.exists(fp):
                with open(fp, "r", encoding="utf-8") as f:
                    out.write(f.read())

    # Calcolo statistiche aggregate
    raw_lengths = []
    with open(merged_raw_path, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            raw_lengths.append(len(obj.get("commands", [])))

    clean_lengths = []
    with open(merged_clean_path, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            clean_lengths.append(len(obj.get("commands", [])))

    aggregated_stats = {
        "total_source_files": len(files),
        "total_sessions_raw": len(raw_lengths),
        "total_sessions_clean": len(clean_lengths),
        "avg_session_length_raw": statistics.mean(raw_lengths) if raw_lengths else 0,
        "median_session_length_raw": statistics.median(raw_lengths) if raw_lengths else 0,
        "avg_session_length_clean": statistics.mean(clean_lengths) if clean_lengths else 0,
        "median_session_length_clean": statistics.median(clean_lengths) if clean_lengths else 0,
        "event_types": aggregated_events
    }

    stats_final_path = f"{output_prefix}_ALL_STATS.json"
    with open(stats_final_path, "w", encoding="utf-8") as s:
        json.dump(aggregated_stats, s, indent=2)

    # Split del file CLEAN finale
    train_path = f"{output_prefix}_TRAIN.jsonl"
    test_path = f"{output_prefix}_TEST.jsonl"

    print("\n✂️  Suddivisione del file CLEAN in TRAIN (70%) e TEST (30%)...")

    split_jsonl_file(input_path=merged_clean_path, output_train=train_path, output_test=test_path, train_ratio=0.7)

    # Eliminazione file intermedi (tutti i file CLEAN, RAW e stats dei singoli file del dataset)
    print("\n🧹 Eliminazione dei file intermedi...")
    for fp in raw_outputs + clean_outputs + stats_outputs:
        if os.path.exists(fp):
            os.remove(fp)

    # Stampe finali
    print("\n🎉 Merge completato con successo!")
    print(f"📦 RAW finale:   {merged_raw_path}")
    print(f"📦 CLEAN finale: {merged_clean_path}")
    print(f"📊 STATS finali: {stats_final_path}")
    print(f"📂 TRAIN: {train_path}")
    print(f"📂 TEST:  {test_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default="data")
    parser.add_argument("--output", default="output/cowrie")
    args = parser.parse_args()
    merge_all(args.input_dir, args.output)