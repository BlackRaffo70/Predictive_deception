#!/usr/bin/env python3

# -------------------------
# INTRODUCTION -> some utils informations about the Python script
# -------------------------

"""
- MODALITÀ:

    Lo script serve per processare più file del dataset Zenodo con record=3687527. Lo script richiama 
    analyze_and_clean.py per ogni file, esegue il merge dei file CLEAN e RAW prodotti, calcolando anche 
    le statistiche aggregate. Il file CLEAN (se non viene prodotto si utilizza quella RAW) contenente il merge dei 
    file viene poi suddiviso in modo randomico in due file: uno contenente il 70% delle righe del file iniziale, 
    l'altro contenente il restante 30%. Queste funzionalità sono espresse attraverso la definizione di due funzioni:
        
        - merge_all(input_dir: str, output_prefix: str) -> esegue analyze_and_clean.py per ogni file, generando file RAW e CLEAN (senza ripetizione di sessioni contenenti gli stessi comandi), esegue il merge di tutti i file RAW/CLEAN creati e calcola le statistiche aggregate
        - split_jsonl_file(input_path: str, output_train: str, output_test: str, train_ratio: float = 0.7) -> Divide un file .jsonl in due file (train/test) selezionando le righe in modo casuale senza ripetizioni.

- PRE-REQUISITI:
    Presenza dello script analyze_and_clean.py
        
- COMANDO PER ESECUZIONE:

    - Analisi locale semplificativa:

        python inspectDataset/merge_cowrie_datasets.py --want clean
    
    - Analisi intero dataset (su dispositivo di archiviazione esterno):
    
        python inspectDataset/merge_cowrie_datasets.py --input /media/matteo/T9/DatasetZenodo  --output /media/matteo/T9/outputMerge/cowrie  --want clean

    dove le flag sono:
    - input = Cartella di input da analizzare
    - output = Radice dei file di output generati
    - filter = Specifica il numero di comandi minimo che devono avere le sessioni dopo il filtraggio
    - want = Preferenza sui file da generare: raw = solo file raw; clean = solo file clean; both = entrambi
"""

# -------------------------
# IMPORT SECTION -> imports necessary for the Python script
# -------------------------

import argparse
import os
from glob import glob
import re
import json
import random
import statistics
from tqdm import tqdm
import analyze_and_clean

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

def merge_all(args):
    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    files = sorted(glob(os.path.join(args.input, "*.json")))
    if not files:
        print("❌ Nessun file JSON trovato.")
        return

    print(f"Trovati {len(files)} file Cowrie.\n")

    raw_outputs = []
    clean_outputs = []
    aggregated_events = {}

    # analyze_and_clean.py per ogni file
    for path in files:
        basename = os.path.basename(path)
        match = re.search(r"(\d{4}-\d{2}-\d{2})", basename)
        date = match.group(1) if match else "unknown"

        print(f"▶️ Elaborazione: {basename}")
        class Arguments:
            input = path
            output = args.output
            want = args.want
            filter = args.filter

        stats = analyze_and_clean.analyze_cowrie_dataset(Arguments)

        if args.want == "both" or args.want == "raw":   
            raw_path = f"{args.output}_sessions_{date}_RAW.jsonl"
            raw_outputs.append(raw_path)
        if args.want == "both" or args.want == "clean":  
            clean_path = f"{args.output}_sessions_{date}_CLEAN.jsonl"
            clean_outputs.append(clean_path)

        # aggiunge EVENT_TYPES alle stats globali
        events = stats.get("event_types", {})
        for k, v in events.items():
            aggregated_events[k] = aggregated_events.get(k, 0) + v
            
    print("\n🧩 Tutti i file elaborati. Inizio merge finale...\n")
    
    raw_lengths = []
    clean_lengths = []

    # Merge di tutti i file RAW senza duplicati
    if args.want == "both" or args.want == "raw":
        merged_raw_path = f"{args.output}_ALL_RAW.jsonl"
        # Set delle liste commands già inserite nel file di merge
        seen_commands_raw = set()
        with open(merged_raw_path, "w", encoding="utf-8") as out:
            with tqdm(total=len(raw_outputs), desc="Merge RAW", unit="file", ncols=100) as pbar:
                for file in raw_outputs:
                    if os.path.exists(file):
                        with open(file, "r", encoding="utf-8") as read_file:
                            for line in read_file:
                                obj = json.loads(line)
                                commands_tuple = tuple(obj.get("commands", []))
                                if commands_tuple not in seen_commands_raw:
                                    seen_commands_raw.add(commands_tuple)
                                    out.write(line)
                    pbar.update(1)
        
        raw_lengths = [len(commands) for commands in seen_commands_raw]

    # Merge di tutti i file CLEAN senza duplicati
    if args.want == "both" or args.want == "clean":
        merged_clean_path = f"{args.output}_ALL_CLEAN.jsonl"
        # Set delle liste commands già inserite nel file di merge
        seen_commands_clean = set()
        with open(merged_clean_path, "w", encoding="utf-8") as out:
            with tqdm(total=len(clean_outputs), desc="Merge CLEAN", unit="file", ncols=100) as pbar:
                for fp in clean_outputs:
                    if os.path.exists(fp):
                        with open(fp, "r", encoding="utf-8") as f:
                            for line in f:
                                obj = json.loads(line)
                                commands_tuple = tuple(obj.get("commands", []))
                                if commands_tuple not in seen_commands_clean:
                                    seen_commands_clean.add(commands_tuple)
                                    out.write(line)
                    pbar.update(1)
        
        clean_lengths = [len(commands) for commands in seen_commands_clean]

    # Calcolo statistiche aggregate
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

    stats_final_path = f"{args.output}_ALL_STATS.json"
    with open(stats_final_path, "w", encoding="utf-8") as s:
        json.dump(aggregated_stats, s, indent=2)

    # Split del file finale. 
    # Questo varia a seconda della modalità scelta: se presente il file CLEAN si esegue ad esso, altrimenti al file RAW
    train_path = f"{args.output}_TRAIN.jsonl"
    test_path = f"{args.output}_TEST.jsonl"

    if args.want == "both" or args.want == "clean":
        print("\n✂️  Suddivisione del file CLEAN in TRAIN (70%) e TEST (30%)...")
        split_jsonl_file(input_path=merged_clean_path, output_train=train_path, output_test=test_path, train_ratio=0.7)
    else:
        print("\n✂️  Suddivisione del file RAW in TRAIN (70%) e TEST (30%)...")
        split_jsonl_file(input_path=merged_raw_path, output_train=train_path, output_test=test_path, train_ratio=0.7)

    # Eliminazione file intermedi (tutti i file CLEAN e RAW dei singoli file del dataset)
    print("\n🧹 Eliminazione dei file intermedi...")
    if args.want == "both" or args.want == "clean":
        for fp in clean_outputs:
            if os.path.exists(fp):
                os.remove(fp)

    if args.want == "both" or args.want == "raw":
        for fp in raw_outputs:
            if os.path.exists(fp):
                os.remove(fp)

    # Stampe finali
    print("\n🎉 Merge completato con successo!")
    if args.want == "both" or args.want == "raw": print(f"📦 RAW finale:   {merged_raw_path}")
    if args.want == "both" or args.want == "clean": print(f"📦 CLEAN finale: {merged_clean_path}")
    print(f"📊 STATS finali: {stats_final_path}")
    print(f"📂 TRAIN: {train_path}")
    print(f"📂 TEST:  {test_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data", help="Cartella da analizzare")
    parser.add_argument("--output", default="output/cowrie", help="Radice dei file di output generati")
    parser.add_argument("--filter", type=int, default=5, help="Numero di sessioni per filtraggio. Le sessioni che presentano meno comandi del numero specificato, vengono filtrate")
    parser.add_argument("--want", choices=["raw", "clean", "both"], default="both", help="Preferenza sui file da generare: raw = solo file raw; clean = solo file clean; both = entrambi")
    args = parser.parse_args()
    merge_all(args)