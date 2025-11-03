#!/usr/bin/env python3
"""
Analizza dataset Cowrie aggregato (ogni sessione è un oggetto con ID → lista di eventi).

Esempio formato:
[
  {
    "0258c1b64b66": [
      {"eventid": "cowrie.session.connect", ...},
      {"eventid": "cowrie.command.input", "input": "whoami", ...},
      ...
    ]
  },
  ...
]
"""

import json
import argparse
from collections import Counter, defaultdict
import statistics
import os

def analyze_aggregated_dataset(input_file: str, output_prefix: str):
    print(f"🔍 Analisi file aggregato: {input_file}")

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    sessions = defaultdict(list)
    event_counter = Counter()

    # Ogni elemento del file è un dict con { session_id: [eventi] }
    for session_obj in data:
        for sid, events in session_obj.items():
            for ev in events:
                eventid = ev.get("eventid")
                event_counter[eventid] += 1
                if eventid == "cowrie.command.input":
                    cmd = ev.get("input") or ev.get("command") or ev.get("payload")
                    if cmd and isinstance(cmd, str):
                        sessions[sid].append(cmd.strip())

    print(f"\n📊 RISULTATI ANALISI")
    print("--------------------")
    print(f"Totale sessioni trovate: {len(sessions)}")
    print(f"Totale eventi: {sum(event_counter.values()):,}")
    print("\nTop 10 tipi di evento:")
    for ev, count in event_counter.most_common(10):
        print(f"  {ev:<30} {count:,}")

    lengths = [len(cmds) for cmds in sessions.values()]
    avg_len = statistics.mean(lengths) if lengths else 0
    median_len = statistics.median(lengths) if lengths else 0

    print("\n📈 STATISTICHE SESSIONI")
    print(f"  Numero medio di comandi per sessione: {avg_len:.2f}")
    print(f"  Mediana: {median_len}")
    print(f"  Minimo: {min(lengths) if lengths else 0}")
    print(f"  Massimo: {max(lengths) if lengths else 0}")

    all_cmds = [cmd for s in sessions.values() for cmd in s]
    top_cmds = Counter(all_cmds).most_common(15)
    print("\n🧠 Comandi più frequenti:")
    for cmd, count in top_cmds:
        print(f"  {cmd:<30} {count}")

    # Salva sequenze
    os.makedirs(os.path.dirname(output_prefix), exist_ok=True)
    output_path = f"{output_prefix}_sessions.jsonl"
    with open(output_path, "w", encoding="utf-8") as out:
        for sid, cmds in sessions.items():
            if len(cmds) >= 2:
                out.write(json.dumps({"session": sid, "commands": cmds}) + "\n")

    print(f"\n💾 File salvato: {output_path}")
    print(f"Totale sessioni con comandi: {len(sessions)}")

    # Salva statistiche
    stats_path = f"{output_prefix}_stats.json"
    stats = {
        "n_sessions": len(sessions),
        "avg_len": avg_len,
        "median_len": median_len,
        "event_types": dict(event_counter),
        "top_commands": top_cmds
    }
    with open(stats_path, "w", encoding="utf-8") as s:
        json.dump(stats, s, indent=2)
    print(f"📊 Statistiche salvate in: {stats_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analisi dataset Cowrie aggregato per sessione.")
    parser.add_argument("--input", required=True, help="File JSON aggregato (es: data/cowrie_2020-02-29.json)")
    parser.add_argument("--output", default="output/cowrie", help="Prefisso file di output")
    args = parser.parse_args()
    analyze_aggregated_dataset(args.input, args.output)