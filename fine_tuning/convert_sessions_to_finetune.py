#!/usr/bin/env python3

# -------------------------
# INTRODUCTION -> some utils informations about the Python script
# -------------------------

"""
- MODALITÀ:

    
- PRE-REQUISITI:
    
        
- COMANDO PER ESECUZIONE:
    
"""

# -------------------------
# IMPORT SECTION -> imports necessary for the Python script
# -------------------------
import json
import os
import sys

# -------------------------
# FUNCTION SECTION -> definition of the function explained in the introduction
# -------------------------

def convert_sessions(input_path, output_path):

    # Create output directory if missing
    out_dir = os.path.dirname(output_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir)
        print(f"[INFO] Created folder: {out_dir}")

    fout = open(output_path, "w", encoding="utf-8")

    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except Exception:
                continue

            cmds = obj.get("commands")
            if not cmds or len(cmds) < 2:
                continue

            # Sliding window: (0→1), (1→2), (2→3), ...
            for i in range(len(cmds) - 1):

                context = cmds[:i+1]         # commands 0..i
                expected = cmds[i+1]         # next command

                prompt = "Commands:\n" + "\n".join(context) + "\nNext command:"
                response = expected

                record = {
                    "prompt": prompt,
                    "response": response
                }

                fout.write(json.dumps(record, ensure_ascii=False) + "\n")

    fout.close()
    print(f"[DONE] Wrote finetune data → {output_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("USAGE:\n  python convert_for_finetune.py input.jsonl output/output.jsonl")
        sys.exit(1)

    convert_sessions(sys.argv[1], sys.argv[2])

    "python convert_sessions_to_finetune.py output/cowrie_ALL_CLEAN.jsonl output/cowrie_finetune.jsonl"