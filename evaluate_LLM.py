#!/usr/bin/env python3
# evaluate_LLM.py
# Versione migliorata per OpenRouter / modelli "openrouter:...:free"
#
# Funzionalità:
# - prompt ottimizzato per restituire solo il comando shell
# - retries con exponential backoff su 429/5xx
# - fallback su lista modelli (opzionale)
# - misura exact match + similarity (difflib) + jaccard token overlap
# - salva risultati incrementali in JSONL
#
# Uso:
# export OPENROUTER_API_KEY="or_..."
# python evaluate_LLM.py --data output/predictive_pairs.jsonl --model "deepseek/deepseek-r1-0528:free" --n 50 --sleep 1.0 --fallback "meta-llama/llama-3.3-8b-instruct:free,mistralai/mistral-7b-instruct:free"

import os
import sys
import json
import time
import argparse
import requests
from tqdm import tqdm
from difflib import SequenceMatcher

# -------------------------
# Config
# -------------------------
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "deepseek/deepseek-r1-0528:free"
MAX_TOKENS = 64
TEMPERATURE = 0.2
TIMEOUT = 60
DEFAULT_SLEEP = 1.0

# -------------------------
# Utils: text cleaning & metrics
# -------------------------
def clean_prediction(raw_text: str) -> str:
    """
    Pulisce il testo di output cercando di estrarre il comando principale.
    Strategie:
    - prendi la prima riga non vuota
    - rimuovi virgolette esterne
    - se la riga inizia con frasi tipo "The command is", togline la parte verbale
    - ritorna la linea pulita, altrimenti l'intero testo stripped
    """
    if not raw_text:
        return ""
    # split by newline and take first meaningful line
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    if not lines:
        return raw_text.strip()
    first = lines[0]
    # spesso i modelli rispondono "The next command is: cat /etc/passwd" -> estrai dopo ':' o 'is'
    import re
    # remove leading phrases
    first = re.sub(r'^[\-\s"\'`]*', '', first)
    # look for colon
    if ':' in first:
        parts = first.split(':', 1)
        cand = parts[1].strip()
        if cand:
            first = cand
    else:
        # remove common prefixes
        first = re.sub(r'^(the next command (is|:)|next command is|predicted command is|command:)\s*', '', first, flags=re.I)
    # strip surrounding quotes/backticks
    first = first.strip(' "\'`')
    # if ends with '.' or ',' remove trailing punctuation
    first = first.rstrip('.,;')
    return first.strip()

def exact_match(a: str, b: str) -> bool:
    return (a.strip() == b.strip()) if a and b else False

def difflib_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a.strip(), b.strip()).ratio() if a and b else 0.0

def jaccard_tokens(a: str, b: str) -> float:
    # tokenizza per whitespace e simboli semplici
    if not a or not b:
        return 0.0
    import re
    ta = set(re.findall(r"[A-Za-z0-9_\-./]+", a.lower()))
    tb = set(re.findall(r"[A-Za-z0-9_\-./]+", b.lower()))
    if not ta and not tb:
        return 0.0
    inter = ta.intersection(tb)
    union = ta.union(tb)
    return len(inter) / len(union) if union else 0.0

# -------------------------
# OpenRouter call + retries
# -------------------------
def call_openrouter(prompt: str, api_key: str, model: str, max_tokens:int=MAX_TOKENS, temperature:float=TEMPERATURE, timeout:int=TIMEOUT, max_retries:int=5):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature
    }

    backoff = 1.0
    for attempt in range(1, max_retries+1):
        try:
            r = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=timeout)
        except requests.RequestException as e:
            # network error -> backoff and retry
            if attempt == max_retries:
                return None, f"network_error: {e}"
            time.sleep(backoff)
            backoff *= 2
            continue

        if r.status_code == 200:
            try:
                data = r.json()
            except Exception as e:
                return None, f"invalid_json: {e}"
            # parse common shapes
            if isinstance(data, dict):
                if "choices" in data and data["choices"]:
                    ch = data["choices"][0]
                    # chat-style
                    if isinstance(ch, dict) and "message" in ch and isinstance(ch["message"], dict):
                        return ch["message"].get("content","").strip(), None
                    # old-style
                    if isinstance(ch, dict) and "text" in ch:
                        return ch.get("text","").strip(), None
                # fallback common fields
                for k in ("generated_text","output","result","response"):
                    if k in data and isinstance(data[k], str):
                        return data[k].strip(), None
            # nothing parsed
            return "", None

        # handle status codes with retry/backoff
        if r.status_code in (429, 503, 500, 502, 504):
            # get message snippet
            try:
                reason = r.json()
            except Exception:
                reason = r.text[:200]
            if attempt == max_retries:
                return None, f"http_{r.status_code}: {reason}"
            # exponential backoff with jitter
            time.sleep(backoff + (0.1 * attempt))
            backoff *= 2
            continue
        elif r.status_code == 404:
            # model not found -> no retry, inform caller
            try:
                reason = r.json()
            except Exception:
                reason = r.text[:200]
            return None, f"http_404: {reason}"
        else:
            # other client error -> return message
            try:
                reason = r.json()
            except Exception:
                reason = r.text[:200]
            return None, f"http_{r.status_code}: {reason}"

    return None, "max_retries_exceeded"

# -------------------------
# Prompt builder
# -------------------------
def build_prompt(context, few_shot_examples=None):
    """
    Prompt molto diretto: istruisce il modello a rispondere SOLO con il comando shell.
    few_shot_examples: opzionale lista di (ctx_list, next) per few-shot
    """
    prefix = ""
    if few_shot_examples:
        ex_lines = []
        for ctx, nxt in few_shot_examples:
            ex_lines.append("Esempio contesto:")
            ex_lines.extend(ctx)
            ex_lines.append("Risposta attesa: " + nxt)
            ex_lines.append("---")
        prefix = "\n".join(ex_lines) + "\n\n"

    body = "\n".join(context)
    prompt = (
        f"{prefix}"
        "Sei un modello che predice il prossimo comando shell in una sessione SSH (honeypot).\n"
        "Dato il contesto (i comandi eseguiti finora),\n"
        "RISPOSTA OBBLIGATORIA: scrivi SOLO il comando shell successivo e NULL'ALTRO (niente spiegazioni, nessun testo aggiuntivo).\n\n"
        f"Contesto:\n{body}\n\nRispondi con il comando successivo:"
    )
    return prompt

# -------------------------
# Main
# -------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="output/predictive_pairs.jsonl", help="File jsonl con coppie context/next")
    parser.add_argument("--n", type=int, default=20, help="Numero esempi da testare")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="ID modello (OpenRouter style)")
    parser.add_argument("--fallback", default="", help="Lista modelli separati da ',' per fallback (opzionale)")
    parser.add_argument("--out", default="output/openrouter_results.jsonl", help="File di output (JSONL)")
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP, help="Secondi di sleep fra richieste")
    parser.add_argument("--few_shot", type=int, default=0, help="Quanti esempi few-shot includere (0 = off)")
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("Errore: variabile OPENROUTER_API_KEY non impostata.")
        sys.exit(1)

    if not os.path.exists(args.data):
        print(f"Errore: file dati non trovato: {args.data}")
        sys.exit(1)

    # carica coppie
    pairs = []
    with open(args.data, "r", encoding="utf-8") as f:
        for line in f:
            try:
                j = json.loads(line)
                if "context" in j and ("next" in j or "target" in j):
                    nxt = j.get("next") or j.get("target")
                    pairs.append({"context": j["context"], "next": nxt})
            except Exception:
                continue

    if not pairs:
        print("Nessuna coppia valida trovata.")
        sys.exit(1)

    pairs = pairs[:args.n]
    # prepare few-shot examples if richiesto
    few_shot_examples = None
    if args.few_shot and args.few_shot > 0:
        few_shot_examples = []
        for p in pairs[:args.few_shot]:
            few_shot_examples.append((p["context"], p["next"]))

    # fallback list
    fallback_models = [m.strip() for m in args.fallback.split(",") if m.strip()]
    # ensure primary model is first
    model_chain = [args.model] + [m for m in fallback_models if m != args.model]

    out_file = args.out
    os.makedirs(os.path.dirname(out_file) or ".", exist_ok=True)
    # clear existing output file (start fresh)
    if os.path.exists(out_file):
        # make backup
        os.rename(out_file, out_file + ".bak")

    results = []
    failed = 0

    print(f"📂 Caricati {len(pairs)} esempi. Model chain: {model_chain}")

    for idx, p in enumerate(tqdm(pairs, desc="Valutazione")):
        context = p["context"]
        expected = p["next"]
        prompt = build_prompt(context, few_shot_examples=few_shot_examples)
        raw_pred = None
        error_msg = None
        used_model = None

        # try model chain with retries inside call_openrouter
        for m in model_chain:
            resp, err = call_openrouter(prompt, api_key, m)
            if resp is not None:
                raw_pred = resp
                used_model = m
                break
            else:
                # err contains reason; if 404 then try next model immediately
                error_msg = err
                if err and err.startswith("http_404"):
                    # try next model in chain
                    continue
                # if rate-limited or other, wait a bit and then try next model in chain
                # but prefer to retry same model inside call_openrouter (already attempted)
                # so we go to next model in chain
                continue

        if raw_pred is None:
            # all models failed for this example
            failed += 1
            out_entry = {
                "context": context,
                "expected": expected,
                "predicted_raw": "",
                "predicted": "",
                "exact": False,
                "ratio": 0.0,
                "jaccard": 0.0,
                "model": used_model or args.model,
                "error": error_msg or "no_response"
            }
            results.append(out_entry)
            # append to file
            with open(out_file, "a", encoding="utf-8") as of:
                of.write(json.dumps(out_entry, ensure_ascii=False) + "\n")
            # small sleep to avoid hammering
            time.sleep(args.sleep)
            continue

        # clean prediction
        cleaned = clean_prediction(raw_pred)
        ex = exact_match(cleaned, expected)
        ratio = difflib_ratio(cleaned, expected)
        jacc = jaccard_tokens(cleaned, expected)

        out_entry = {
            "context": context,
            "expected": expected,
            "predicted_raw": raw_pred,
            "predicted": cleaned,
            "exact": ex,
            "ratio": round(ratio, 4),
            "jaccard": round(jacc, 4),
            "model": used_model or args.model,
            "error": None
        }
        results.append(out_entry)
        # write incremental
        with open(out_file, "a", encoding="utf-8") as of:
            of.write(json.dumps(out_entry, ensure_ascii=False) + "\n")

        time.sleep(args.sleep)

    # summary
    total = len(results)
    exacts = sum(1 for r in results if r.get("exact"))
    avg_ratio = sum(r.get("ratio", 0.0) for r in results) / total if total else 0.0
    avg_jacc = sum(r.get("jaccard", 0.0) for r in results) / total if total else 0.0

    print("\n📊 RISULTATI FINALI")
    print("-------------------")
    print(f"Esempi processati: {total}")
    print(f"Exact match: {exacts}/{total} -> {exacts/total*100:.2f}%")
    print(f"Similarità media (difflib): {avg_ratio*100:.2f}%")
    print(f"Token Jaccard medio: {avg_jacc*100:.2f}%")
    print(f"Falliti: {failed}")

    # write summary file
    summary = {
        "total": total,
        "exact_matches": exacts,
        "exact_pct": exacts/total if total else 0.0,
        "avg_ratio": avg_ratio,
        "avg_jaccard": avg_jacc,
        "failed": failed,
        "model_chain": model_chain
    }
    with open(out_file + ".summary.json", "w", encoding="utf-8") as sf:
        json.dump(summary, sf, indent=2)

if __name__ == "__main__":
    main()