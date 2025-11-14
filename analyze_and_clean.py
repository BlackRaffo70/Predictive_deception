#!/usr/bin/env python3
import json, argparse, os, re, statistics
from collections import defaultdict, Counter

# ----------------------------
# Normalizzazione dei comandi
# ----------------------------

def normalize_command(cmd: str) -> str:
    """Pulizia aggressiva e normalizzazione dei comandi Cowrie."""
    cmd = cmd.strip()

    # Rimuovi prefissi tipo CMD:
    cmd = re.sub(r'^CMD:\s*', '', cmd)

    # Oscura password / stringhe casuali / parametri per passwd
    cmd = re.sub(r'echo\s+-e\s+"[^"]+"(\|passwd\|bash)?', 'echo <SECRET>|passwd', cmd)
    cmd = re.sub(r'echo\s+"[^"]+"\|passwd', 'echo <SECRET>|passwd', cmd)

    # Oscura file temporanei con numeri casuali
    cmd = re.sub(r'/var/tmp/[\.\w-]*\d{3,}', '/var/tmp/<FILE>', cmd)
    cmd = re.sub(r'/tmp/[\.\w-]*\d{3,}', '/tmp/<FILE>', cmd)

    # Oscura qualsiasi filename con estensione sospetta
    cmd = re.sub(r'\b[\w\.-]+\.(log|txt|sh|bin|exe|tgz|gz)\b', '<FILE>', cmd)

    # Oscura URL
    cmd = re.sub(r'(https?|ftp)://\S+', '<URL>', cmd)

    # Oscura IP
    cmd = re.sub(r'\b\d{1,3}(?:\.\d{1,3}){3}\b', '<IP>', cmd)

    # Oscura username/password in echo "admin xxx"
    cmd = re.sub(r'echo\s+"admin\s+[^"]+"', 'echo "admin <SECRET>"', cmd)

    # Rimuovi doppi spazi
    cmd = re.sub(r'\s+', ' ', cmd).strip()

    return cmd


# ----------------------------
# Core script
# ----------------------------

def analyze_cowrie_dataset(input_file: str, output_prefix: str):

    print(f"Analisi file: {input_file}")

    basename = os.path.basename(input_file)
    match = re.search(r"(\d{4}-\d{2}-\d{2})", basename)
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

                clean = normalize_command(raw_cmd)
                if clean:
                    sessions[sid].append(clean)

    # Statistiche
    lengths = [len(c) for c in sessions.values() if c]
    avg_len = statistics.mean(lengths) if lengths else 0
    median_len = statistics.median(lengths) if lengths else 0

    # Output
    os.makedirs(os.path.dirname(output_prefix), exist_ok=True)

    out_sessions = f"{output_prefix}_sessions_{file_date}_CLEAN.jsonl"
    out_stats = f"{output_prefix}_stats_{file_date}_CLEAN.json"

    with open(out_sessions, "w", encoding="utf-8") as out:
        for sid, cmds in sessions.items():
            if cmds:
                out.write(json.dumps({
                    "session": sid,
                    "commands": cmds,
                    "source_file": file_date
                }) + "\n")

    with open(out_stats, "w", encoding="utf-8") as s:
        json.dump({
            "source_file": file_date,
            "n_sessions": len(sessions),
            "avg_len": avg_len,
            "median_len": median_len,
            "event_types": dict(event_counter)
        }, s, indent=2)

    print(f"Output: {out_sessions}")
    print(f"Statistiche: {out_stats}")
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="output/cowrie")
    args = parser.parse_args()
    analyze_cowrie_dataset(args.input, args.output)

    "python analyze_and_clean.py --input data/cowrie_2020-02-29.json --output output/cowrie"