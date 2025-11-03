"""
Analisi preliminare del dataset Cowrie Honeypot (CyberLab o simili).

Questo script:
  - Legge tutti i file JSON line-based in una cartella.
  - Conta i tipi di eventi presenti.
  - Estrae le sequenze di comandi da ogni sessione (eventid == 'cowrie.command.input').
  - Calcola statistiche base.
  - Salva i risultati e le sequenze pulite in file JSONL.

Autore: [Il tuo nome]
Data: [oggi]
"""

import json
import glob
from collections import defaultdict, Counter
import argparse
import statistics
import os

def analyze_dataset(input_pattern: str, output_prefix: str, max_files: int = None):
    """
    Analizza i log Cowrie e salva i risultati.
    """
    print(f"🔍 Analisi dei file: {input_pattern}")
    files = sorted(glob.glob(input_pattern))
    if max_files:
        files = files[:max_files]
        print(f"➡️  Limitato a {len(files)} file")

    sessions = defaultdict(list)
    event_counter = Counter()
    total_lines = 0

    for file in files:
        with open(file, "r", encoding="utf-8") as f:
            for line in f:
                total_lines += 1
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                eventid = ev.get("eventid")
                event_counter[eventid] += 1

                # estrai solo i comandi digitati
                if eventid == "cowrie.command.input":
                    sid = ev.get("session") or ev.get("sessionid") or "unknown"
                    cmd = ev.get("input", "").strip()
                    if cmd:
                        sessions[sid].append(cmd)

    print("\n📊 RISULTATI ANALISI")
    print("--------------------")
    print(f"Totale file analizzati: {len(files)}")
    print(f"Totale righe lette: {total_lines:,}")
    print(f"Totale sessioni trovate: {len(sessions):,}")
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

    # comandi più frequenti
    all_cmds = [c for s in sessions.values() for c in s]
    top_cmds = Counter(all_cmds).most_common(15)

    print("\n🧠 Comandi più frequenti:")
    for cmd, count in top_cmds:
        print(f"  {cmd:<30} {count}")

    # salva le sequenze per uso successivo
    output_dir = os.path.dirname(output_prefix)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    output_path = f"{output_prefix}_sessions.jsonl"
    with open(output_path, "w", encoding="utf-8") as out:
        for sid, cmds in sessions.items():
            if len(cmds) >= 2:
                out.write(json.dumps({"session": sid, "commands": cmds}) + "\n")

    print(f"\n💾 File salvato: {output_path}")
    print(f"Totale sessioni salvate: {len(sessions)}")

    # salva anche statistiche
    stats_path = f"{output_prefix}_stats.json"
    stats = {
        "n_files": len(files),
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
    parser = argparse.ArgumentParser(description="Analisi iniziale del dataset Cowrie Honeypot (JSON log).")
    parser.add_argument("--input", default="data/*.json", help="Pattern dei file JSON da analizzare (es: data/*.json)")
    parser.add_argument("--output", default="output/cowrie", help="Prefisso file di output")
    parser.add_argument("--maxfiles", type=int, default=None, help="Limita il numero di file da leggere (per test)")
    args = parser.parse_args()

    analyze_dataset(args.input, args.output, args.maxfiles)