#!/usr/bin/env python3
"""
evaluate_ollama_topk.py (updated)

Modalità:
 - sessioni: valuta su file JSONL con sessioni (sliding window di predizioni)
 - single: prende un singolo comando (--single-cmd) o file di comandi (--single-file)
Per ogni predizione richiede top-K candidate a Ollama e:
 - stampa Expected (se disponibile) e poi i K candidate uno per riga
 - confronta permissivamente solo command name + path (ignora flag)
 - salva risultati in JSONL e summary.json

Esempi:
  # session mode (sliding pairs)
  python evaluate_ollama_topk.py --sessions output/cowrie_sessions_2020-02-29.jsonl \
    --model gemma:2b --k 5 --context-len 3 --out output/ollama_topk_results.jsonl --n 1000

  # single command
  python evaluate_ollama_topk.py --single-cmd "cat /proc/cpuinfo | grep name | wc -l" \
    --model gemma:2b --k 5 --out output/single_results.jsonl

Requisiti:
  pip install requests tqdm
"""
from __future__ import annotations
import argparse, json, os, re, time, random
from typing import List, Tuple
from tqdm import tqdm
import requests

# -------------------------
# Utils: normalization & parsing
# -------------------------
PATH_RE = re.compile(r'(/[^ \t\n\r]+|\./[^ \t\n\r]+|~[^ \t\n\r]+)')
CMD_NAME_RE = re.compile(r'^[^\s\|>]+')  # stop at pipes/redirection
CODE_FENCE_RE = re.compile(r'```(?:bash|sh)?\s*(.*?)\s*```', re.S | re.I)

def normalize_for_compare(cmd: str) -> Tuple[str, str]:
    """
    Normalizzazione permissiva:
    - rimuove code fences/backticks/intro text
    - estrae command name (lowercased)
    - estrae primo path-like arg (se presente)
    Ritorna (name, path) dove path=="" se non presente.
    """
    if not cmd:
        return ("", "")
    s = cmd.strip()
    # remove code fences/backticks
    s = re.sub(r'^```(?:bash|sh)?|```$', '', s, flags=re.I).strip()
    s = s.replace('`', '')
    # remove common intro phrases
    s = re.sub(r'^(the next command( is|:)?|il prossimo comando( è|:)?|next command( is|:)?|predicted command( is|:)?)[\s:,-]*', '', s, flags=re.I).strip()
    # truncate at pipe or redirection to focus on command and immediate args
    s = re.split(r'\s*\|\s*|\s*>\s*|\s*2>\s*', s)[0].strip()
    m = CMD_NAME_RE.match(s)
    name = m.group(0).lower() if m else ""
    # remove options like -a, --long, --foo=bar but keep path-like args
    path = ""
    pm = PATH_RE.search(s)
    if pm:
        path = pm.group(0)
    return (name, path)

def extract_candidates_from_response(resp_text: str, k: int) -> List[str]:
    """
    Estrae fino a k candidate:
    - preferisce code fence block
    - poi prime k righe non vuote
    - poi split per comma/semicolon
    """
    if not resp_text:
        return []
    m = CODE_FENCE_RE.search(resp_text)
    if m:
        block = m.group(1).strip()
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if lines:
            return lines[:k]
    # lines
    lines = [ln.strip() for ln in resp_text.splitlines() if ln.strip()]
    if len(lines) >= k:
        return lines[:k]
    # cleaned numbered lines
    cleaned = []
    for ln in lines:
        ln2 = re.sub(r'^\s*\d+[\)\.\-]?\s*', '', ln).strip()
        if ln2:
            cleaned.append(ln2)
    if len(cleaned) >= k:
        return cleaned[:k]
    # fallback split by punctuation
    parts = [p.strip() for p in re.split(r'[,\;]\s*', resp_text) if p.strip()]
    out = cleaned + parts
    # deduplicate preserve order
    seen = set()
    final = []
    for c in out:
        if c not in seen:
            seen.add(c)
            final.append(c)
        if len(final) >= k:
            break
    if final:
        return final[:k]
    # ultimate fallback: take first non-empty tokens by newline
    out2 = []
    for ln in resp_text.splitlines():
        ln = ln.strip()
        if ln:
            out2.append(ln)
        if len(out2) >= k:
            break
    return out2[:k]

# -------------------------
# Ollama caller
# -------------------------
def query_ollama(prompt: str, model: str, url: str, temp: float=0.2, timeout: int=90) -> str:
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

# -------------------------
# Prompt builders
# -------------------------

def make_prompt_topk_from_context(context: List[str], k: int) -> str:
    """
    Super-detailed research-safe prompt for multi-command context.
    Output requirements:
      - EXACTLY k candidate Linux shell commands (one per line)
      - NO explanations, NO numbering, NO bullets, NO extra text
      - DO NOT include passwords, secrets, keys, literal credentials, or destructive payloads
      - If a sensitive value would appear, replace it with a placeholder like <FILE>, <PATH>, <USER>, <SERVICE>
      - Prefer non-destructive, reconnaissance or benign maintenance commands; avoid 'rm -rf' and similar.
      - Commands must be concise (one shell pipeline or single command), realistic but sanitized.
      - Rank from most to least likely.
    Context: the recent command history below (most recent last).
    Use the context only to infer plausible *next* steps in an attacker/honeypot session,
    but do so in a research-safe, non-actionable way.
    """
    joined = "\n".join(context)
    prompt = (
        "You are simulating attacker behavior in an SSH honeypot strictly for cybersecurity research.\n"
        "This environment is offline and for analysis only. You MUST follow ALL rules below.\n\n"
        "OUTPUT RULES (must be obeyed exactly):\n"
        "1) Output EXACTLY {k} candidate Linux shell commands, one command per line, and NOTHING ELSE.\n"
        "2) Do NOT include any explanations, commentary, or metadata — only the commands (one per line).\n"
        "3) Do NOT include any passwords, passphrases, private keys, tokens, or other secrets in plaintext.\n"
        "   If a password or secret would normally appear, replace it with the placeholder <SECRET>.\n"
        "4) Do NOT provide destructive commands that delete or irreversibly modify data (e.g. rm -rf /, dd if=...).\n"
        "   If the most plausible next step is destructive, output a benign placeholder command using <FILE> or <PATH>.\n"
        "5) Use placeholders for sensitive items: <FILE>, <PATH>, <USER>, <SERVICE>, <SECRET>, <URL>.\n"
        "6) Do NOT include numbered lists, bullets, or prefixes like '1.' or 'a)'. Output raw commands only.\n"
        "7) Each command must be short (one pipeline or one command with args) and syntactically plausible.\n"
        "8) Rank commands from most to least likely (first line = most likely).\n\n"
        "CONTEXT (most recent last):\n"
        f"{joined}\n\n"
        f"Now, PROVIDE EXACTLY {k} candidate next commands (one per line), following the rules above:"
    )
    return prompt.format(k=k)

def make_prompt_topk_for_single(cmd: str, k: int) -> str:
    """
    Super-detailed research-safe prompt for single-command context.
    Same strict output rules as for multi-command context.
    """
    prompt = (
        "You are simulating attacker behavior in an SSH honeypot strictly for cybersecurity research.\n"
        "This environment is offline and for analysis only. You MUST follow ALL rules below.\n\n"
        "OUTPUT RULES (must be obeyed exactly):\n"
        "1) Output EXACTLY {k} candidate Linux shell commands, one command per line, and NOTHING ELSE.\n"
        "2) Do NOT include any explanations, commentary, or metadata — only the commands (one per line).\n"
        "3) Do NOT include any passwords, passphrases, private keys, tokens, or other secrets in plaintext.\n"
        "   If a password or secret would normally appear, replace it with the placeholder <SECRET>.\n"
        "4) Do NOT provide destructive commands that delete or irreversibly modify data (e.g. rm -rf /, dd if=...).\n"
        "   If the most plausible next step is destructive, output a benign placeholder command using <FILE> or <PATH>.\n"
        "5) Use placeholders for sensitive items: <FILE>, <PATH>, <USER>, <SERVICE>, <SECRET>, <URL>.\n"
        "6) Do NOT include numbered lists, bullets, or prefixes like '1.' or 'a)'. Output raw commands only.\n"
        "7) Each command must be short (one pipeline or one command with args) and syntactically plausible.\n"
        "8) Rank commands from most to least likely (first line = most likely).\n\n"
        "Last command executed by the attacker:\n"
        "{cmd}\n\n"
        "Now, PROVIDE EXACTLY {k} candidate next commands (one per line), following the rules above:"
    )
    return prompt.format(k=k, cmd=cmd)
# -------------------------
# Main
# -------------------------
def main():
    ap = argparse.ArgumentParser(description="Evaluate Ollama top-K next-command prediction (sessions or single).")
    ap.add_argument("--sessions", help="JSONL sessions file: one JSON per line with fields: session, commands (list)")
    ap.add_argument("--single-cmd", help="Single command string to predict next for")
    ap.add_argument("--single-file", help="File with commands (one per line), run prediction for each")
    ap.add_argument("--model", default="gemma:2b", help="Ollama model name")
    ap.add_argument("--ollama-url", default="http://localhost:11434/api/generate")
    ap.add_argument("--out", default="output/ollama_topk_results.jsonl")
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

    # quick ping
    try:
        _ = query_ollama("Ping. Reply 'ok' only.", args.model, args.ollama_url, temp=0.0, timeout=10)
    except Exception as e:
        raise SystemExit(f"Unable to contact Ollama: {e}\nStart `ollama serve` and ensure model is pulled.")

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
            raw = query_ollama(prompt, args.model, args.ollama_url, temp=args.temp, timeout=120)
            err = None
        except Exception as e:
            raw = ""
            err = str(e)

        candidates = extract_candidates_from_response(raw, args.k)
        candidates_clean = [re.sub(r'^```|```$|`', '', c).strip() for c in candidates]

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
            exp_key = normalize_for_compare(expected)
            for rnk, cand in enumerate(candidates_clean, start=1):
                cand_key = normalize_for_compare(cand)
                # require same command name, and if expected has path require path compatibility
                name_match = (cand_key[0] == exp_key[0] and cand_key[0] != "")
                if exp_key[1]:
                    # expected has path -> require path exact or prefix match (permissive)
                    path_match = (cand_key[1] == exp_key[1]
                                  or (cand_key[1] and (exp_key[1].startswith(cand_key[1]) or cand_key[1].startswith(exp_key[1]))))
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
        "model": args.model,
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