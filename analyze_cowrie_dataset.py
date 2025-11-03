#!/usr/bin/env python3
"""
Analisi del dataset Cowrie (formato aggregato con chiave 'data' per i comandi).
Conta i comandi più usati dagli attaccanti.
"""

import json
import argparse
from collections import defaultdict, Counter
import statistics
import os

def analyze_cowrie_dataset(input_file: str, output_prefix: str):
    print(f"🔍 Analisi file aggregato: {input_file}")

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
    with open(f"{output_prefix}_sessions.jsonl", "w", encoding="utf-8") as out:
        for sid, cmds in sessions.items():
            if cmds:
                out.write(json.dumps({"session": sid, "commands": cmds}) + "\n")

    with open(f"{output_prefix}_stats.json", "w", encoding="utf-8") as s:
        json.dump({
            "n_sessions": n_sessions,
            "avg_len": avg_len,
            "median_len": median_len,
            "event_types": dict(event_counter),
            "top_commands": cmd_counter.most_common(50)
        }, s, indent=2)

    print(f"\n💾 File salvato: {output_prefix}_sessions.jsonl")
    print(f"📊 Statistiche salvate in: {output_prefix}_stats.json")
    print(f"✅ Totale sessioni con comandi: {len([x for x in sessions.values() if x])}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analisi dataset Cowrie aggregato (chiave 'data').")
    parser.add_argument("--input", required=True, help="File JSON Cowrie aggregato (es: data/cowrie_2020-02-29.json)")
    parser.add_argument("--output", default="output/cowrie", help="Prefisso per i file di output")
    args = parser.parse_args()
    analyze_cowrie_dataset(args.input, args.output)