import json, random
from tqdm import tqdm

input_sessions = "output/cowrie_sessions.jsonl"
output_pairs = "output/predictive_pairs.jsonl"

pairs = []

with open(input_sessions, "r", encoding="utf-8") as f:
    for line in f:
        session = json.loads(line)
        cmds = session["commands"]
        # genera coppie (context → next)
        for i in range(1, len(cmds)):
            context = cmds[:i]
            next_cmd = cmds[i]
            pairs.append({"context": context, "next": next_cmd})

print(f"Totale coppie generate: {len(pairs):,}")
random.shuffle(pairs)

with open(output_pairs, "w", encoding="utf-8") as out:
    for p in pairs:
        out.write(json.dumps(p) + "\n")

print(f"💾 Dataset predittivo salvato in: {output_pairs}")