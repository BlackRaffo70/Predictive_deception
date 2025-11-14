#!/usr/bin/env python3
import json, argparse, os, re
from glob import glob
from collections import defaultdict, Counter
import statistics

# Importa la tua funzione di pulizia
from analyze_and_clean import normalize_command


def merge_all(input_dir: str, output_prefix: str):

    files = sorted(glob(os.path.join(input_dir, "*.json")))
    if not files:
        print("❌ Nessun file JSON trovato.")
        return

    print(f"Trovati {len(files)} file Cowrie.\n")

    # MERGE GREZZO
    raw_sessions = defaultdict(list)
    raw_event_counter = Counter()

    # MERGE CLEAN
    clean_sessions = defaultdict(list)
    clean_event_counter = Counter()

    for path in files:
        print(f"📄 Processando: {path}")

        basename = os.path.basename(path)
        match = re.search(r"(\d{4}-\d{2}-\d{2})", basename)
        date = match.group(1) if match else "unknown"

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for session_obj in data:
            for sid, events in session_obj.items():

                merged_sid = f"{date}_{sid}"

                for ev in events:

                    eventid = ev.get("eventid")

                    # Conta raw
                    raw_event_counter[eventid] += 1
                    clean_event_counter[eventid] += 1  # stessa struttura

                    if eventid != "cowrie.command.input":
                        continue

                    raw_cmd = (
                        ev.get("data")
                        or ev.get("input")
                        or ev.get("command")
                        or ev.get("payload")
                        or ev.get("message")
                    )

                    if not raw_cmd or not isinstance(raw_cmd, str):
                        continue

                    # --------------------------
                    # MERGE GREZZO
                    # --------------------------
                    raw_sessions[merged_sid].append(raw_cmd.strip())

                    # --------------------------
                    # MERGE CLEAN (pulito)
                    # --------------------------
                    cleaned = normalize_command(raw_cmd)
                    if cleaned:
                        clean_sessions[merged_sid].append(cleaned)

    # ---------------------------------
    # STATISTICHE RAW
    # ---------------------------------
    raw_lengths = [len(v) for v in raw_sessions.values() if v]
    raw_stats = {
        "source_files": files,
        "total_files": len(files),
        "n_sessions": len(raw_sessions),
        "avg_len": statistics.mean(raw_lengths) if raw_lengths else 0,
        "median_len": statistics.median(raw_lengths) if raw_lengths else 0,
        "event_types": dict(raw_event_counter)
    }

    # ---------------------------------
    # STATISTICHE CLEAN
    # ---------------------------------
    clean_lengths = [len(v) for v in clean_sessions.values() if v]
    clean_stats = {
        "source_files": files,
        "total_files": len(files),
        "n_sessions": len(clean_sessions),
        "avg_len": statistics.mean(clean_lengths) if clean_lengths else 0,
        "median_len": statistics.median(clean_lengths) if clean_lengths else 0,
        "event_types": dict(clean_event_counter)
    }

    # ---------------------------------
    # SCRITTURA FILE RAW
    # ---------------------------------
    raw_sessions_path = f"{output_prefix}_merged_sessions.jsonl"
    raw_stats_path = f"{output_prefix}_merged_stats.json"

    with open(raw_sessions_path, "w", encoding="utf-8") as out:
        for sid, cmds in raw_sessions.items():
            out.write(json.dumps({
                "session": sid,
                "commands": cmds
            }) + "\n")

    with open(raw_stats_path, "w", encoding="utf-8") as s:
        json.dump(raw_stats, s, indent=2)

    print(f"\n💾 Merge RAW salvato in: {raw_sessions_path}")
    print(f"📊 Stats RAW salvate in: {raw_stats_path}")


    # ---------------------------------
    # SCRITTURA FILE CLEAN
    # ---------------------------------
    clean_sessions_path = f"{output_prefix}_merged_sessions_CLEAN.jsonl"
    clean_stats_path = f"{output_prefix}_merged_stats_CLEAN.json"

    with open(clean_sessions_path, "w", encoding="utf-8") as out:
        for sid, cmds in clean_sessions.items():
            out.write(json.dumps({
                "session": sid,
                "commands": cmds
            }) + "\n")

    with open(clean_stats_path, "w", encoding="utf-8") as s:
        json.dump(clean_stats, s, indent=2)

    print(f"\n💾 Merge CLEAN salvato in: {clean_sessions_path}")
    print(f"📊 Stats CLEAN salvate in: {clean_stats_path}")

    print("\n✅ Merge completato con successo.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default="data")
    parser.add_argument("--output", default="output/cowrie")
    args = parser.parse_args()

    merge_all(args.input_dir, args.output)


    "python merge_cowrie_datasets.py --input-dir data --output output/cowrie"