#!/usr/bin/env python3
"""
evaluate_ollama_topk.py

Valuta un modello Ollama generando top-K candidate per il prossimo comando
e misura se il comando effettivamente eseguito compare tra le K.

Esempio:
  python evaluate_ollama_topk.py \
    --sessions output/cowrie_sessions_2020-02-29.jsonl \
    --model gemma:2b \
    --ollama-url http://localhost:11434/api/generate \
    --out output/ollama_topk_results.jsonl \
    --k 5 --context-len 3 --n 1000

Requisiti:
  pip install requests tqdm
"""
import argparse
import json
import os
import re
import time
import random
from tqdm import tqdm
from difflib import SequenceMatcher
import requests

# -------------------------
# Helpers: parsing & normalizing
# -------------------------
PATH_RE = re.compile(r'(/[^ \t\n\r]+|\./[^ \t\n\r]+|~[^ \t\n\r]+)')
CMD_NAME_RE = re.compile(r'^[^\s]+')

def normalize_for_compare(cmd: str):
    """
    Riduce una stringa di comando alla tupla (command_name, path) per confronto permissivo.
    - rimuove leading/trailing whitespace e code fences/backticks
    - estrae il nome del comando (prima token)
    - trova la prima argomento che sembra un path (file/dir)
    - ritorna "command path" (path empty string se non presente)
    """
    if not cmd:
        return ("", "")
    s = cmd.strip()
    # rimuovi code fences o backticks
    s = re.sub(r'^```(?:bash|sh)?|```$','', s, flags=re.I).strip()
    s = s.replace('`', '').strip()
    # rimuovi frasi introduttive
    s = re.sub(r'^(the next command( is|:)?|il prossimo comando( è|:)?|next command( is|:)?|predicted command( is|:)?)[\s:,-]*','', s, flags=re.I).strip()
    # prendi il nome comando
    m = CMD_NAME_RE.match(s)
    name = m.group(0) if m else ""
    # rimuovi opzioni tipo -a --long --flag=value
    # but keep path-like args
    path = ""
    path_m = PATH_RE.search(s)
    if path_m:
        path = path_m.group(0)
    # Lowercase name for comparison
    return (name.split()[0].lower() if name else "", path)

def candidate_lines_from_response(resp_text: str, k: int):
    """
    Estrai fino a k comandi candidati dalla risposta del modello.
    La risposta può essere:
      - 5 righe separate
      - un blocco con ```...```
      - una frase con virgole
    Restituisce lista di stringhe (raw).
    """
    if not resp_text:
        return []
    # prima cerca code fence
    m = re.search(r'```(?:bash|sh)?\s*(.*?)\s*```', resp_text, re.S | re.I)
    if m:
        block = m.group(1).strip()
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        return lines[:k]
    # altrimenti split per linee
    lines = [ln.strip() for ln in resp_text.splitlines() if ln.strip()]
    if len(lines) >= k:
        return lines[:k]
    # se poche righe ma contiene numeri "1) cmd" rimuovili prefissi
    cleaned = []
    for ln in lines:
        # rimuovi "1) " o "1. " o "- "
        ln2 = re.sub(r'^\s*\d+[\)\.\-]?\s*', '', ln)
        ln2 = ln2.strip()
        if ln2:
            cleaned.append(ln2)
    if len(cleaned) >= k:
        return cleaned[:k]
    # fallback: split by comma/semicolon
    parts = re.split(r'[,\;]\s*', resp_text)
    parts = [p.strip() for p in parts if p.strip()]
    # prefer longer candidate list
    candidates = cleaned + parts
    # deduplicate preserving order
    seen = set()
    out = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
        if len(out) >= k:
            break
    # if still not enough, take first k words lines
    if not out:
        # take first k non-empty tokens by newline
        for ln in resp_text.splitlines():
            ln = ln.strip()
            if ln:
                out.append(ln)
            if len(out) >= k:
                break
    return out[:k]

# re-use query function similar to your other scripts
def query_ollama(prompt, model, url, temp=0.2, timeout=90):
    payload = {"model": model, "prompt": prompt, "temperature": temp, "stream": False}
    try:
        r = requests.post(url, json=payload, timeout=timeout)
    except requests.exceptions.RequestException as e:
        raise ConnectionError(f"Ollama connection error: {e}")
    if r.status_code != 200:
        raise RuntimeError(f"Ollama returned HTTP {r.status_code}: {r.text[:400]}")
    try:
        data = r.json()
    except Exception:
        return r.text.strip()
    if isinstance(data, dict):
        for k in ("response","output","text"):
            if k in data and isinstance(data[k], str):
                return data[k].strip()
        if "responses" in data and isinstance(data["responses"], list) and data["responses"]:
            r0 = data["responses"][0]
            return r0 if isinstance(r0, str) else str(r0)
    return r.text.strip()

def make_prompt_topk(context, k):
    joined = "\n".join(context)
    # request top-k, numbered
    return f"""You MUST produce exactly {k} candidate Linux shell commands (one per line), ranked from most to least likely.
Output ONLY the commands, one per line, no explanations and no extra text.

Command history:
{joined}

Provide {k} candidate next commands (one per line):"""

# -------------------------
# Main
# -------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", required=True,
                    help="JSONL with sessions (one per line), fields: session, commands (list).")
    ap.add_argument("--model", default="gemma:2b", help="Ollama model name")
    ap.add_argument("--ollama-url", default="http://localhost:11434/api/generate")
    ap.add_argument("--out", default="output/ollama_topk_results.jsonl")
    ap.add_argument("--k", type=int, default=5, help="Top-K candidates")
    ap.add_argument("--context-len", type=int, default=3, help="Max previous commands to include in context")
    ap.add_argument("--n", type=int, default=0, help="Max steps to evaluate (0 = all)")
    ap.add_argument("--temp", type=float, default=0.15)
    ap.add_argument("--sleep", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    if not os.path.exists(args.sessions):
        raise SystemExit(f"Sessions file not found: {args.sessions}")

    # load sessions
    sessions = []
    with open(args.sessions, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln: continue
            try:
                obj = json.loads(ln)
            except:
                continue
            # accept both {"session":..., "commands":[...]} or {"session_id":..., "commands":...}
            sid = obj.get("session") or obj.get("session_id") or obj.get("id")
            cmds = obj.get("commands") or obj.get("cmds") or obj.get("commands_list")
            if not sid or not cmds: continue
            sessions.append({"session": sid, "commands": cmds})

    if not sessions:
        raise SystemExit("No sessions loaded.")

    random.seed(args.seed)

    # quick ping
    try:
        _ = query_ollama("Ping. Reply 'ok' only.", args.model, args.ollama_url, temp=0.0, timeout=30)
    except Exception as e:
        raise SystemExit(f"Unable to contact Ollama: {e}")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    fout = open(args.out, "w", encoding="utf-8")

    total_steps = 0
    results = []
    # iterate sessions and generate prediction tasks (sliding)
    tasks = []
    for sess in sessions:
        cmds = sess["commands"]
        # for each consecutive pair i -> i+1, construct a task
        for i in range(len(cmds)-1):
            ctx_start = max(0, i - (args.context_len - 1))
            context = cmds[ctx_start:i+1]  # include current command at end
            expected = cmds[i+1]
            tasks.append({"session": sess["session"], "index": i, "context": context, "expected": expected})

    if args.n and args.n > 0:
        random.shuffle(tasks)
        tasks = tasks[:args.n]

    total_steps = len(tasks)
    print(f"Total prediction steps: {total_steps}")

    # metrics
    topk_hits = 0
    top1_hits = 0
    non_empty = 0

    for t in tqdm(tasks, desc="Predicting", unit="step"):
        ctx = t["context"]
        expected = t["expected"]
        prompt = make_prompt_topk(ctx, args.k)
        try:
            raw = query_ollama(prompt, args.model, args.ollama_url, temp=args.temp, timeout=120)
            err = None
        except Exception as e:
            raw = ""
            err = str(e)
        candidates = candidate_lines_from_response(raw, args.k)
        # normalize expected
        exp_key = normalize_for_compare(expected)
        found_in_topk = False
        for rank, cand in enumerate(candidates, start=1):
            cand_key = normalize_for_compare(cand)
            # compare command name equality and directory/path equality if expected has a path
            # permissive: if expected path empty, only compare command name
            name_match = (cand_key[0] == exp_key[0] and cand_key[0] != "")
            if exp_key[1]:
                # expected has path -> require same path or prefix match
                path_match = (cand_key[1] == exp_key[1] or (cand_key[1] and exp_key[1].startswith(cand_key[1])) or (exp_key[1].startswith(cand_key[1]) if cand_key[1] else False))
            else:
                path_match = True  # no path in expected -> ignore path
            if name_match and path_match:
                found_in_topk = True
                if rank == 1:
                    top1_hits += 1
                topk_hits += 1
                break

        if candidates:
            non_empty += 1

        rec = {
            "session": t["session"],
            "index": t["index"],
            "context": ctx,
            "expected_raw": expected,
            "expected_norm": exp_key,
            "candidates_raw": candidates,
            "candidates_norm": [normalize_for_compare(c) for c in candidates],
            "hit_in_topk": bool(found_in_topk),
            "error": err
        }
        fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fout.flush()
        results.append(rec)
        time.sleep(args.sleep)

    fout.close()

    total = len(results)
    topk_rate = topk_hits / total if total else 0.0
    top1_rate = top1_hits / total if total else 0.0
    non_empty_rate = non_empty / total if total else 0.0

    print("\n=== SUMMARY ===")
    print(f"Total steps: {total}")
    print(f"Non-empty predictions: {non_empty}/{total} ({non_empty_rate*100:.2f}%)")
    print(f"Top-{args.k} hits: {topk_hits}/{total} -> {topk_rate*100:.2f}%")
    print(f"Top-1 hits: {top1_hits}/{total} -> {top1_rate*100:.2f}%")
    # also save a small summary file
    summary = {
        "total_steps": total,
        "non_empty": non_empty,
        "topk_hits": topk_hits,
        "top1_hits": top1_hits,
        "topk_rate": topk_rate,
        "top1_rate": top1_rate,
        "model": args.model,
        "k": args.k,
        "context_len": args.context_len
    }
    with open(args.out + ".summary.json", "w", encoding="utf-8") as s:
        json.dump(summary, s, indent=2)

if __name__ == "__main__":
    main()