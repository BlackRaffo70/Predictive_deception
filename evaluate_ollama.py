#!/usr/bin/env python3
# evaluate_ollama.py - versione migliorata (estrazione codice, progress bar, prompt stringente)
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="urllib3")
import argparse, json, os, random, time, re
from difflib import SequenceMatcher
import requests
from tqdm import tqdm

# ---------------------------
# Helpers
# ---------------------------
def similarity(a, b):
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.strip(), b.strip()).ratio()

def normalize_first_command(text: str) -> str:
    """Estrae il comando dal testo raw della risposta:
       - cerca code fences ```...```
       - cerca inline backticks `...`
       - altrimenti prende la prima riga non-vuota,
       - rimuove frasi di tipo 'The next command is:', 'Il prossimo comando è', ecc.
    """
    if not text:
        return ""
    # prima ricerca code fence (```...```)
    m = re.search(r'```(?:bash|sh)?\s*(.*?)\s*```', text, re.S | re.I)
    if m:
        first = m.group(1).strip().splitlines()[0].strip()
        return _clean_pred_line(first)

    # poi inline backticks `...`
    m2 = re.search(r'`([^`]+)`', text)
    if m2:
        return _clean_pred_line(m2.group(1).strip())

    # altrimenti prendi prima riga non-vuota e puliscila
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        # se la riga contiene solo "Il prossimo comando..." ignora e continua
        if re.match(r'^(the next command|il prossimo comando|next command|predicted command|l\'ultimo comando)', s.lower()):
            # prova a cercare dopo ":" nella stessa riga
            if ':' in s:
                after = s.split(':',1)[1].strip()
                if after:
                    return _clean_pred_line(after)
            continue
        return _clean_pred_line(s)
    return ""

def _clean_pred_line(s: str) -> str:
    s = s.strip().strip(' "\'`')
    # se la riga contiene prefissi comuni, rimuovili
    s = re.sub(r'^(the next command (is|:)|next command is|predicted command is|command:|il prossimo comando (è|:))\s*', '', s, flags=re.I)
    # rimuovi markup come **cmd** o html
    s = re.sub(r'[\*\_]{1,3}', '', s)
    # togli eventuali punti finali
    s = s.rstrip('.;')
    # prendi solo la prima linea se ancora presenza newline
    return s.splitlines()[0].strip()

def make_prompt(context):
    # prompt stringente in inglese (i modelli rispondono meglio)
    joined = "\n".join(context)
    return f"""You are an assistant that MUST output EXACTLY ONE Linux shell command (no explanation, no text).
Given the command history below, output ONLY the next likely shell command on a single line, nothing else.

Command history:
{joined}

Output the next command (one line, raw shell command):"""

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
    except Exception as e:
        raise RuntimeError(f"Invalid JSON from Ollama: {e} - raw: {r.text[:400]}")
    # common keys
    if isinstance(data, dict):
        for k in ("response","output","text"):
            if k in data and isinstance(data[k], str):
                return data[k].strip()
        # try responses list
        if "responses" in data and isinstance(data["responses"], list) and data["responses"]:
            if isinstance(data["responses"][0], str):
                return data["responses"][0].strip()
    # fallback to raw text
    return r.text.strip()

# ---------------------------
# Main
# ---------------------------
def main():
    p = argparse.ArgumentParser(description="Eval local Ollama model for SSH next-command prediction")
    p.add_argument("--data", default="output/predictive_pairs.jsonl")
    p.add_argument("--out", default="output/ollama_results.jsonl")
    p.add_argument("--model", default="mistral:latest")
    p.add_argument("--ollama-url", default="http://localhost:11434/api/generate")
    p.add_argument("--n", type=int, default=100)
    p.add_argument("--temp", type=float, default=0.1)
    p.add_argument("--timeout", type=int, default=90)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    if not os.path.exists(args.data):
        print(f"Input file not found: {args.data}")
        return

    # load pairs
    pairs = []
    with open(args.data, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                obj = json.loads(line)
            except:
                continue
            # accept different keys
            ctx = obj.get("context") or obj.get("input") or obj.get("commands") or []
            nxt = obj.get("next") or obj.get("expected") or obj.get("target") or ""
            if not ctx or not nxt:
                continue
            pairs.append({"context": ctx, "expected": nxt})

    if not pairs:
        print("No valid pairs found in input.")
        return

    random.seed(args.seed)
    random.shuffle(pairs)
    pairs = pairs[: min(args.n, len(pairs)) ]

    # quick ping to Ollama
    try:
        _ = query_ollama("Ping. Reply 'ok' only.", args.model, args.ollama_url, temp=0.0, timeout=args.timeout)
    except Exception as e:
        print("Unable to contact Ollama or model error:", e)
        print("Make sure `ollama serve` is running and the model is pulled.")
        return

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    results = []
    print(f"🔍 Starting {len(pairs)} examples on model '{args.model}' ({args.ollama_url})")
    with open(args.out, "w", encoding="utf-8") as fout:
        for p_item in tqdm(pairs, desc="Evaluating", unit="pair"):
            ctx = p_item["context"]
            expected = p_item["expected"].strip()
            prompt = make_prompt(ctx)
            try:
                raw = query_ollama(prompt, args.model, args.ollama_url, temp=args.temp, timeout=args.timeout)
            except Exception as e:
                raw = ""
                err = str(e)
            else:
                err = None

            predicted = normalize_first_command(raw)
            sim = similarity(predicted, expected) if predicted and expected else 0.0
            match = int(predicted == expected and predicted != "")

            rec = {
                "context": ctx,
                "expected": expected,
                "predicted": predicted,
                "similarity": round(sim, 6),
                "match": match,
                "raw_response": raw,
                "error": err
            }
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fout.flush()
            results.append(rec)
            # slight sleep to avoid spamming local server
            time.sleep(0.05)

    # summary
    total = len(results)
    non_empty = sum(1 for r in results if r["predicted"])
    exact = sum(r["match"] for r in results)
    avg_sim = sum(r["similarity"] for r in results) / total if total else 0.0

    print("\n📊 RESULTS (Ollama)")
    print("-------------------")
    print(f"Model: {args.model}")
    print(f"Examples tested: {total}")
    print(f"Non-empty predictions: {non_empty}/{total}")
    print(f"Exact match (rank1): {exact}/{total} -> {exact/total*100:.2f}%")
    print(f"Average similarity: {avg_sim*100:.2f}%")
    print(f"Saved detailed results to: {args.out}")

if __name__ == "__main__":
    main()