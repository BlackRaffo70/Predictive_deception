#!/usr/bin/env python3
"""
evaluate_ollama.py

Valuta un modello locale Ollama per la predizione del prossimo comando SSH.
Usa l'API HTTP di Ollama: http://localhost:11434/api/generate

Requisiti:
    pip install requests tqdm

Esempio:
    ollama serve &
    python evaluate_ollama.py --data output/predictive_pairs.jsonl --model gemma:2b --n 100
"""
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="urllib3")
import argparse
import json
import os
import random
import time
from difflib import SequenceMatcher

import requests
from tqdm import tqdm

# ---------------------------
# Config / Argparse
# ---------------------------
def parse_args():
    p = argparse.ArgumentParser(description="Valutazione locale Ollama per predizione comandi SSH")
    p.add_argument("--data", default="output/predictive_pairs.jsonl", help="File JSONL con coppie {context,next}")
    p.add_argument("--out", default="output/ollama_results.jsonl", help="File di output con risultati")
    p.add_argument("--model", default="gemma:2b", help="Nome modello Ollama locale (es. gemma:2b, mistral:q4...)")
    p.add_argument("--ollama-url", default="http://localhost:11434/api/generate", help="URL API Ollama")
    p.add_argument("--n", type=int, default=100, help="Numero di esempi da testare (sample dal file)")
    p.add_argument("--temp", type=float, default=0.2, help="Temperature per la generazione")
    p.add_argument("--timeout", type=int, default=90, help="Timeout richieste (s)")
    p.add_argument("--seed", type=int, default=42, help="Seed per shuffle")
    return p.parse_args()

# ---------------------------
# Utils
# ---------------------------
def similarity(a, b):
    return SequenceMatcher(None, a.strip(), b.strip()).ratio()

def make_prompt(context):
    joined = "\n".join(context)
    return f"""
Sei un sistema di difesa che analizza una sessione SSH malevola.
Ecco i comandi che l'attaccante ha eseguito finora:

{joined}

In base a questa sequenza, predici il **prossimo comando shell probabile**.
Rispondi **solo** con un comando Linux valido, senza testo aggiuntivo o spiegazioni.
Se non sei sicuro, rispondi con il comando più comune successivo.
"""

def query_ollama(prompt, model, url, temp=0.2, timeout=90):
    """
    Query semplice a Ollama local API. Ritorna stringa (risposta) o '' in caso di errore.
    """
    payload = {"model": model, "prompt": prompt, "temperature": temp, "stream": False}
    try:
        r = requests.post(url, json=payload, timeout=timeout)
    except requests.exceptions.RequestException as e:
        raise ConnectionError(f"Errore di connessione a Ollama ({url}): {e}")
    if r.status_code != 200:
        raise RuntimeError(f"Ollama returned HTTP {r.status_code}: {r.text[:400]}")
    try:
        data = r.json()
    except Exception as e:
        raise RuntimeError(f"Impossibile parseare JSON dalla risposta Ollama: {e} -- raw: {r.text[:400]}")
    # Ollama normalmente restituisce {'response': '...'} (ma può variare)
    if isinstance(data, dict):
        # try common keys
        for k in ("response", "output", "text"):
            if k in data and isinstance(data[k], str):
                return data[k].strip()
        # maybe nested
        if "responses" in data and isinstance(data["responses"], list) and data["responses"]:
            if isinstance(data["responses"][0], str):
                return data["responses"][0].strip()
    # fallback: try to extract raw text
    # some Ollama endpoints might return raw text directly
    if isinstance(r.text, str) and r.text.strip():
        return r.text.strip()
    return ""

# ---------------------------
# Main
# ---------------------------
def main():
    args = parse_args()

    if not os.path.exists(args.data):
        print(f"File di input non trovato: {args.data}")
        print("Esegui prima lo script di build per creare output/predictive_pairs.jsonl")
        return

    # carica tutte le coppie
    pairs = []
    with open(args.data, "r", encoding="utf-8") as f:
        for line in f:
            try:
                pairs.append(json.loads(line))
            except:
                continue

    if not pairs:
        print("Nessuna coppia valida trovata nel file.")
        return

    random.seed(args.seed)
    random.shuffle(pairs)
    pairs = pairs[: args.n]

    # verifica connessione Ollama con una chiamata di test
    test_ctx = pairs[0]["context"] if pairs else ["whoami"]
    test_prompt = make_prompt(test_ctx)
    try:
        _ = query_ollama("Test ping. Rispondi brevemente 'ok'.", args.model, args.ollama_url, temp=0.0, timeout=args.timeout)
    except Exception as e:
        print("Impossibile connettersi a Ollama o problema con il server / modello.")
        print("Errore:", e)
        print("Assicurati di aver avviato `ollama serve` e che il modello sia scaricato (es. `ollama pull gemma:2b`).")
        return

    results = []
    print(f"🔍 Inizio test {len(pairs)} esempi con modello '{args.model}' (Ollama: {args.ollama_url})")
    for p in tqdm(pairs):
        context = p.get("context", [])
        expected = p.get("next", "").strip()
        prompt = make_prompt(context)

        try:
            resp_text = query_ollama(prompt, args.model, args.ollama_url, temp=args.temp, timeout=args.timeout)
        except Exception as e:
            print("Errore su una richiesta Ollama:", e)
            resp_text = ""

        # se la risposta contiene più righe, prendi la prima non-vuota
        predicted = ""
        if resp_text:
            # spesso il modello risponde con testi completi; estrai prima riga utile
            for line in resp_text.splitlines():
                s = line.strip()
                if s:
                    predicted = s
                    break

        sim = similarity(predicted, expected) if predicted and expected else 0.0
        match = int(predicted == expected and predicted != "")
        results.append({
            "context": context,
            "expected": expected,
            "predicted": predicted,
            "similarity": sim,
            "match": match,
            "raw_response": resp_text
        })

        # piccolo sleep per non sovraccaricare, opzionale
        time.sleep(0.05)

    # salva risultati
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as out:
        for r in results:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")

    # metriche riassuntive
    total = len(results)
    if total == 0:
        print("Nessun risultato raccolto.")
        return
    exact = sum(r["match"] for r in results)
    avg_sim = sum(r["similarity"] for r in results) / total
    non_empty_preds = sum(1 for r in results if r["predicted"])
    print("\n📊 RISULTATI FINALI (Ollama)")
    print("-----------------------------")
    print(f"Modello: {args.model}")
    print(f"Esempi testati: {total}")
    print(f"Predizioni non vuote: {non_empty_preds}/{total}")
    print(f"Exact match (rank1): {exact}/{total} -> {exact/total*100:.2f}%")
    print(f"Similarità media: {avg_sim*100:.2f}%")
    print(f"Risultati dettagliati salvati in: {args.out}")

if __name__ == "__main__":
    main()