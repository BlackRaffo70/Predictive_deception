#!/usr/bin/env python3

# -------------------------
# INTRODUCTION -> some utils informations about the Python script
# -------------------------

"""
- MODALITÀ:

    - sessioni: valuta su file JSONL con sessioni (sliding window di predizioni)
    - single: prende un singolo comando (--single-cmd) o file di comandi (--single-file)
    Per ogni predizione richiede top-K candidate a Gemini e:
    - stampa Expected (se disponibile) e poi i K candidate uno per riga
    - confronta permissivamente solo command name + path (ignora flag)
    - salva risultati in JSONL e summary.json

- PRE-REQUISITI (comandi da eseguire da riga di comando):

    export GOOGLE_API_KEY=CHIAVE API    -> comando per esportare in locale la chiave per eseguire API Gemini (da rifare ogni volta che si chiude il terminale)
    source .env/bin/activate            -> comando per attivare eviroment virtuale
    pip install --upgrade google-genai" -> comando per scaricare le API Gemini

- COMANDO PER ESECUZIONE (ATTENZIONE -> è necessario eseguire la prima riga di pre-requisiti ogni volta che si chiude il terminale):

    - Per quanto riguarda prompting con contesto, a seconda del modello:

        python prompting/evaluate_GEMINI_topk.py --sessions output/cowrie_ALL_CLEAN.jsonl --k 5 --n 25 --context-len 10

    - Per quanto riguarda prompting SENZA contesto:
    
        python prompting/evaluate_GEMINI_topk.py --single-cmd "cat /proc/cpuinfo | grep name | wc -l" --model gemma:2b --k 5 --out output/single_results.jsonl

    dove le varie flag sono:
    - sessions = (solo CON contesto) flag attraverso cui si passa il file contente le sessioni di attacco (che al loro interno presentano i comandi su cui bisogna eseguire la prediction)
    - single-cmd = (solo SENZA contesto) flag attraverso cui si passa il comando di cui è necessario predirne il successivo
    - model = modello LLM utilizzato
    - k = numero di comandi generati per la prediction
    - out = file che viene popolato con i risultati della prediction eseguita
    - n = (solo CON contesto) numero di comandi 
    - context-len = (solo CON contesto) numero di comandi precedenti al comando di cui bisogna prevederne il successivo (forniscono il contesto di attacco per LLM)

"""

# -------------------------
# IMPORT SECTION -> imports necessary for the Python script
# -------------------------

from __future__ import annotations
import argparse, json, os, re, time, random
from typing import List, Tuple
from tqdm import tqdm
import requests
import utils
from google.genai import Client
import os

# -------------------------
# GEMINI CALLER SECTION -> creates a client for interacting with Gemini models via the Google API and defines a utility function which sends a prompt to the model and returns the generated text.
# -------------------------

client = Client(api_key=os.getenv("GOOGLE_API_KEY"))

def query_gemini(prompt: str, temp: float = 0.2):
    try:
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=prompt,
            config={"temperature": temp}
        )
        return response.text
    except Exception as e:
        return f"[GEMINI ERROR] {e}"
    
# -------------------------
# PROMPTING SECTION -> definition of the two functions (with and whitout context) containing the prompt
# -------------------------

def _whitelist_commands() -> str:
    commands = "\n".join(utils.WHITELIST)
    return f"ALLOWED COMMANDS:\n{commands}\n\n"

def _whitelist_files() -> str:
    files = "\n".join(utils.WHITELISTFILES)
    return f"ALLOWED FILES:\n{files}\n\n"

def _whitelist_folders() -> str:
    folders = "\n".join(utils.WHITELISTFOLDERS)
    return f"ALLOWED FOLDERS:\n{folders}\n\n"

def make_prompt_topk_from_context(context: List[str], k: int) -> str:
    ctx = "\n".join(context[-10:])

    prompt = f"""
You are a system executing an attacker simulation inside a honeypot. 
YOU MUST OBEY THE RULES STRICTLY. NO EXPLANATIONS. NO TEXT. NO COMMENTS.

TASK:
Predict the next {k} most likely Linux commands.

STRICT OUTPUT RULES:
1) Output EXACTLY {k} commands, one per line. NO EXTRA TEXT.
2) Allowed commands = ONLY from WHITELIST below.
3) Allowed files = ONLY from WHITELISTFILES and WHITELISTFOLDERS below.
4) You MUST choose commands EXACTLY as attackers in real SSH honeypots.
5) Commands MUST be similar in style to the recent context.
6) YOU ARE FORBIDDEN to output commands not in whitelist.

WHITELIST COMMANDS:
{_whitelist_commands()}

WHITELIST FILES:
{_whitelist_files()}

WHITELIST FOLDERS:
{_whitelist_folders()}

CONTEXT:
{ctx}

If ANY output line is NOT in WHITELIST:  
→ You MUST replace it with a RANDOM ITEM FROM THE WHITELIST.

NOW OUTPUT EXACTLY {k} RAW COMMANDS:
""".strip()

    return prompt

def make_prompt_topk_for_single(cmd: str, k: int) -> str:

    prompt = (
        "You need to simulate the behavior of an attacker conducting a command-line attack on an SSH honeypot, with the goal of predicting the next command the attacker enters. "
        "It is important to consider the context (the commands passed below), putting yourself in the shoes of an attacker who has to find a vulnerability"
        "The environment is isolated and non-operational. FOLLOW ALL RULES EXACTLY.\n\n"

        "OUTPUT RULES (MUST BE OBEYED):\n"
        f"1) Output EXACTLY {k} commands, one command per line, and NOTHING ELSE.\n"
        "2) The command can ONLY be costructed in this way: choose commands ONLY from the WHITELIST, combining if necessary with files present in WHITELISTFILES or folders present in WHITELISTFOLDERS. The whitelists are below.\n"
        "3) Commands can be constructed using pipelines (linux command '|') \n"
        "4) Commands can present redirections ('>' or '>>') when the target is a whitelisted file or a file inside a whitelisted folder (use <FILE> when appropriate).\n"
        "5) DO NOT INCLUDE NUMBERING, BULLETS EXLPAINATIONS, OR EXTRA TEXT - ONLY RAW COMMANDS."
        "6) Rank commands from most to least likely (first line = most likely).\n\n"

        "WHITELIST (containing commands):\n"
        f"{_whitelist_commands}\n\n"

        "WHITELISTFILES (containing critics files that can be used with previous commands):\n"
        f"{_whitelist_files}\n\n"

        "WHITELISTFOLDERS (containing critics folders that can be used with previous commands):\n"
        f"{_whitelist_folders}\n\n"

        "LAST COMMAND EXECUTED (most recent):\n"
        f"{cmd}\n\n"

        f"Now OUTPUT EXACTLY {k} candidate next commands, one per line. "
    )
    return prompt



# -------------------------
# MAIN SECTION
# -------------------------
def main():
    ap = argparse.ArgumentParser(description="Evaluate GEMINI top-K next-command prediction (sessions or single).")
    ap.add_argument("--sessions", help="JSONL sessions file: one JSON per line with fields: session, commands (list)")
    ap.add_argument("--single-cmd", help="Single command string to predict next for")
    ap.add_argument("--single-file", help="File with commands (one per line), run prediction for each")
    ap.add_argument("--out", default="output/ollama_gemini_results.jsonl")
    ap.add_argument("--k", type=int, default=5, help="Top-K candidates")
    ap.add_argument("--context-len", type=int, default=3, help="Context length when using sessions")
    ap.add_argument("--n", type=int, default=0, help="Max steps to evaluate (0 = all)")
    ap.add_argument("--temp", type=float, default=0.15)
    ap.add_argument("--sleep", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    # validate modes
    mode_sessions = bool(args.sessions)
    mode_single = bool(args.single_cmd or args.single_file)
    if not (mode_sessions or mode_single):
        raise SystemExit("Provide --sessions OR --single-cmd OR --single-file")

    tasks = []  # each task: dict with context(list) and expected (optional) and meta
    if mode_sessions:
        if not os.path.exists(args.sessions):
            raise SystemExit(f"Sessions file not found: {args.sessions}")
        sessions = []
        with open(args.sessions, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    obj = json.loads(ln)
                except:
                    continue
                sid = obj.get("session") or obj.get("session_id") or obj.get("id")
                cmds = obj.get("commands") or obj.get("cmds") or obj.get("commands_list")
                if not sid or not cmds or len(cmds) < 2:
                    continue
                sessions.append({"session": sid, "commands": cmds})
        # build sliding tasks: for each i -> i+1
        for sess in sessions:
            cmds = sess["commands"]
            for i in range(len(cmds) - 1):
                # build context window ending at cmds[i]
                start = max(0, i - (args.context_len - 1))
                context = cmds[start:i+1]  # include cmds[i] as last context command
                expected = cmds[i+1]
                tasks.append({"session": sess["session"], "index": i, "context": context, "expected": expected})
    else:
        # single mode
        single_cmds = []
        if args.single_cmd:
            single_cmds.append(args.single_cmd.strip())
        if args.single_file:
            if not os.path.exists(args.single_file):
                raise SystemExit(f"Single-file not found: {args.single_file}")
            with open(args.single_file, "r", encoding="utf-8") as f:
                for ln in f:
                    ln = ln.strip()
                    if ln:
                        single_cmds.append(ln)
        for cmd in single_cmds:
            tasks.append({"session": "single", "index": 0, "context": [cmd], "expected": None})

    if args.n and args.n > 0:
        random.seed(args.seed)
        random.shuffle(tasks)
        tasks = tasks[:args.n]

    total = len(tasks)
    print(f"Total prediction tasks: {total}")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    fout = open(args.out, "w", encoding="utf-8")
    results = []

    topk_hits = 0
    top1_hits = 0
    non_empty = 0

    for t in tqdm(tasks, desc="Predicting", unit="step"):
        context = t["context"]
        expected = t.get("expected")
        # build prompt
        if len(context) == 1:
            prompt = make_prompt_topk_for_single(context[0], args.k)
        else:
            prompt = make_prompt_topk_from_context(context, args.k)

        try:
            raw = query_gemini(prompt, temp=args.temp)
            err = None

        except Exception as e:
            raw = ""
            err = str(e)

        candidates = raw.splitlines()[:args.k]
        candidates_clean = [c.strip() for c in candidates if c.strip()]

        # print expected + candidates (each on its own line)
        print("\n---")
        print("Context (last commands):")
        for c in context:
            print("  " + c)
        if expected:
            print("Expected:", expected)
        else:
            print("Expected: (not provided)")

        print(f"Top-{args.k} candidates:")
        if not candidates_clean:
            if raw:
                print(" (no parsed lines, raw response below)\n")
                print(raw)
            else:
                print(" (no response)")
        else:
            for i, c in enumerate(candidates_clean, start=1):
                print(f" {i}. {c}")

        # permissive comparison: check if expected normalized matches any candidate normalized
        hit = False
        if expected and candidates_clean:
            exp_keys = utils.normalize_for_compare(expected)
            if not exp_keys:
                continue
            exp_cmd = exp_keys[0]  # take first command in pipeline

            for rnk, cand in enumerate(candidates_clean, start=1):
                cand_keys = utils.normalize_for_compare(cand)
                if not cand_keys:
                    continue
                cand_cmd = cand_keys[0]

                # require same command name, and if expected has path require path compatibility
                name_match = (cand_cmd[0] == exp_cmd[0] and cand_cmd[0] != "")
                if exp_cmd[1]:
                    path_match = (cand_cmd[1] == exp_cmd[1]
                                  or (cand_cmd[1] and (exp_cmd[1].startswith(cand_cmd[1]) or cand_cmd[1].startswith(exp_cmd[1]))))
                else:
                    path_match = True

                if name_match and path_match:
                    hit = True
                    if rnk == 1:
                        top1_hits += 1
                    topk_hits += 1
                    break

        if candidates_clean:
            non_empty += 1

        rec = {
            "session": t.get("session"),
            "index": t.get("index"),
            "context": context,
            "expected_raw": expected,
            "candidates_raw": candidates_clean,
            "hit_in_topk": bool(hit),
            "error": err
        }
        fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fout.flush()
        results.append(rec)
        time.sleep(args.sleep)

    fout.close()

    total_done = len(results)
    topk_rate = topk_hits / total_done if total_done else 0.0
    top1_rate = top1_hits / total_done if total_done else 0.0
    non_empty_rate = non_empty / total_done if total_done else 0.0

    summary = {
        "total_tasks": total_done,
        "non_empty": non_empty,
        "topk_hits": topk_hits,
        "top1_hits": top1_hits,
        "topk_rate": topk_rate,
        "top1_rate": top1_rate,
        "k": args.k,
        "context_len": args.context_len
    }
    with open(args.out + ".summary.json", "w", encoding="utf-8") as s:
        json.dump(summary, s, indent=2)

    print("\n=== SUMMARY ===")
    print(f"Total tasks: {total_done}")
    print(f"Non-empty predictions: {non_empty}/{total_done} ({non_empty_rate*100:.2f}%)")
    print(f"Top-{args.k} hits: {topk_hits}/{total_done} -> {topk_rate*100:.2f}%")
    print(f"Top-1 hits: {top1_hits}/{total_done} -> {top1_rate*100:.2f}%")
    print(f"Detailed results: {args.out}")
    print(f"Summary: {args.out}.summary.json")


if __name__ == "__main__":
    main()