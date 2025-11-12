#!/usr/bin/env python3
"""
Analisi del dataset Cowrie (formato aggregato con chiave 'data' per i comandi).
Conta i comandi più usati dagli attaccanti e salva anche la data del file analizzato,
includendola nel nome dei file di output.

python3 analyze_cowrie_dataset.py --input data/cowrie_2020-02-29.json --output output/cowrie
"""

import json
import argparse
from collections import defaultdict, Counter
import statistics
import os
import re

def analyze_cowrie_dataset(input_file: str, output_prefix: str):
    print(f"🔍 Analisi file aggregato: {input_file}")

    # Estrai la data dal nome del file, es: cowrie_2020-02-29.json → 2020-02-29
    source_name = os.path.basename(input_file)
    match = re.search(r"(\d{4}-\d{2}-\d{2})", source_name)
    file_date = match.group(1) if match else "unknown"

    # Carica il dataset
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    sessions = defaultdict(list)
    event_counter = Counter()

    # Ogni elemento è {session_id: [eventi]}
    for session_obj in data:
        for sid, events in session_obj.items():
            for ev in events:
                eventid = ev.get("eventid")
                event_counter[eventid] += 1

                # I comandi sono nel campo 'data'
                if eventid == "cowrie.command.input":
                    cmd = (
                        ev.get("data")
                        or ev.get("input")
                        or ev.get("command")
                        or ev.get("payload")
                        or ev.get("message")
                    )
                    if cmd and isinstance(cmd, str):
                        # molti eventi hanno "CMD: whoami" → rimuovilo
                        if cmd.startswith("CMD: "):
                            cmd = cmd[5:]
                        sessions[sid].append(cmd.strip())

    # Statistiche di base
    n_sessions = len(sessions)
    lengths = [len(cmds) for cmds in sessions.values() if cmds]
    avg_len = statistics.mean(lengths) if lengths else 0
    median_len = statistics.median(lengths) if lengths else 0

    print("\n📊 RISULTATI ANALISI")
    print("--------------------")
    print(f"Totale eventi letti: {sum(event_counter.values()):,}")
    print(f"Totale eventi cowrie.command.input: {event_counter['cowrie.command.input']:,}")
    print(f"Totale sessioni trovate: {n_sessions}")

    print("\n📈 STATISTICHE SESSIONI")
    print(f"  Numero medio di comandi per sessione: {avg_len:.2f}")
    print(f"  Mediana: {median_len}")
    print(f"  Minimo: {min(lengths) if lengths else 0}")
    print(f"  Massimo: {max(lengths) if lengths else 0}")

    # Conta i comandi globali
    all_cmds = [cmd for cmds in sessions.values() for cmd in cmds]
    cmd_counter = Counter(all_cmds)

    print("\n🧠 Top 20 comandi più utilizzati:")
    for cmd, count in cmd_counter.most_common(20):
        print(f"  {cmd:<40} {count}")

    # Salva i risultati
    os.makedirs(os.path.dirname(output_prefix), exist_ok=True)

    # ✅ Aggiungi la data ai nomi dei file di output
    out_sessions_path = f"{output_prefix}_sessions_{file_date}.jsonl"
    out_stats_path = f"{output_prefix}_stats_{file_date}.json"

    with open(out_sessions_path, "w", encoding="utf-8") as out:
        for sid, cmds in sessions.items():
            if cmds:
                out.write(json.dumps({
                    "session": sid,
                    "commands": cmds,
                    "source_file": file_date
                }) + "\n")

    with open(out_stats_path, "w", encoding="utf-8") as s:
        json.dump({
            "source_file": file_date,
            "n_sessions": n_sessions,
            "avg_len": avg_len,
            "median_len": median_len,
            "event_types": dict(event_counter),
            "top_commands": cmd_counter.most_common(50)
        }, s, indent=2)

    print(f"\n💾 File salvato: {out_sessions_path}")
    print(f"📊 Statistiche salvate in: {out_stats_path}")
    print(f"✅ Totale sessioni con comandi: {len([x for x in sessions.values() if x])}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analisi dataset Cowrie aggregato (chiave 'data').")
    parser.add_argument("--input", required=True, help="File JSON Cowrie aggregato (es: data/cowrie_2020-02-29.json)")
    parser.add_argument("--output", default="output/cowrie", help="Prefisso per i file di output")
    args = parser.parse_args()
    analyze_cowrie_dataset(args.input, args.output)