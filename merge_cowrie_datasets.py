#!/usr/bin/env python3
import json, argparse, os, re
from glob import glob
from collections import defaultdict, Counter
import statistics
from analyze_and_clean import normalize_command, filter_short_sessions

def merge_all(input_dir: str, output_prefix: str):
    os.makedirs(os.path.dirname(output_prefix), exist_ok=True)

    files = sorted(glob(os.path.join(input_dir, "*.json")))
    if not files:
        print("❌ Nessun file JSON trovato.")
        return
    print(f"Trovati {len(files)} file Cowrie.\n")

    raw_sessions = defaultdict(list)
    raw_event_counter = Counter()
    clean_sessions = defaultdict(list)
    clean_event_counter = Counter()

    for path in files:
        print(f"📄 Processando: {path}")
        basename = os.path.basename(path)
        match = re.search(r"(\d{4}-\d{2}-\d{2})", basename)
        date = match.group(1) if match else "unknown"

        with open(path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except Exception as e:
                print(f"⚠️ Errore nel file {path}: {e}")
                continue

        for session_obj in data:
            for sid, events in session_obj.items():
                merged_sid = f"{date}_{sid}"
                for ev in events:
                    eventid = ev.get("eventid")
                    raw_event_counter[eventid] += 1
                    clean_event_counter[eventid] += 1

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

                    raw_sessions[merged_sid].append(raw_cmd.strip())
                    cleaned = normalize_command(raw_cmd)
                    if cleaned:
                        clean_sessions[merged_sid].append(cleaned)

    # --- RAW ---
    raw_sessions_path = f"{output_prefix}_merged_sessions_RAW.jsonl"
    raw_stats_path = f"{output_prefix}_merged_stats_RAW.json"
    with open(raw_sessions_path, "w", encoding="utf-8") as out:
        for sid, cmds in raw_sessions.items():
            out.write(json.dumps({"session": sid, "commands": cmds}) + "\n")
    raw_lengths = [len(v) for v in raw_sessions.values() if v]
    raw_stats = {
        "source_files": files,
        "total_files": len(files),
        "n_sessions": len(raw_sessions),
        "avg_len": statistics.mean(raw_lengths) if raw_lengths else 0,
        "median_len": statistics.median(raw_lengths) if raw_lengths else 0,
        "event_types": dict(raw_event_counter)
    }
    with open(raw_stats_path, "w", encoding="utf-8") as s:
        json.dump(raw_stats, s, indent=2)
    print(f"💾 RAW merge salvato: {raw_sessions_path}")

    # --- CLEAN ---
    clean_sessions_path = f"{output_prefix}_merged_sessions_CLEAN.jsonl"
    clean_stats_path = f"{output_prefix}_merged_stats_CLEAN.json"
    with open(clean_sessions_path, "w", encoding="utf-8") as out:
        for sid, cmds in clean_sessions.items():
            out.write(json.dumps({"session": sid, "commands": cmds}) + "\n")
    filter_short_sessions(clean_sessions_path, min_length=5)
    clean_lengths = []
    with open(clean_sessions_path, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            clean_lengths.append(len(obj.get("commands", [])))
    clean_stats = {
        "source_files": files,
        "total_files": len(files),
        "n_sessions": len(clean_lengths),
        "avg_len": statistics.mean(clean_lengths) if clean_lengths else 0,
        "median_len": statistics.median(clean_lengths) if clean_lengths else 0,
        "event_types": dict(clean_event_counter)
    }
    with open(clean_stats_path, "w", encoding="utf-8") as s:
        json.dump(clean_stats, s, indent=2)
    print(f"💾 CLEAN merge salvato: {clean_sessions_path}")

    print("\n✅ Merge completato con successo.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default="data")
    parser.add_argument("--output", default="output/cowrie")
    args = parser.parse_args()
    merge_all(args.input_dir, args.output)