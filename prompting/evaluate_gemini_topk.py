#!/usr/bin/env python3

# -------------------------
# INTRODUCTION -> some utils informations about the Python script
# -------------------------

"""
- MODALITÀ:
    Il file contiene la funzione query_gemini() che crea il client per mandare il prompt a LLM gemini 
    (è possibile scegliere il modello). Tutte le funzionalità di effettivo prompting sono contenute all'interno
    del file core_topk.py in quanto in comune con lo script evaluate_ollama_topk.py. I risultati della 
    valutazione della prediction vengono salvati nel file output/ollama_gemini_result.jsonl

- PRE-REQUISITI (comandi da eseguire da riga di comando):

    export GOOGLE_API_KEY=CHIAVE API    -> comando per esportare in locale la chiave per eseguire API Gemini (da rifare ogni volta che si chiude il terminale)
    source .venv/bin/activate           -> comando per attivare enviroment virtuale
    pip install --upgrade google-genai  -> comando per scaricare le API Gemini

- COMANDO PER ESECUZIONE (ATTENZIONE -> è necessario eseguire la prima riga di pre-requisiti ogni volta che si chiude il terminale):

    - Per quanto riguarda prompting con contesto, a seconda del modello:

        python prompting/evaluate_gemini_topk.py --sessions output/cowrie_ALL_CLEAN.jsonl --k 5 --n 25 --context-len 10

    - Per quanto riguarda prompting SENZA contesto:
    
        python prompting/evaluate_GEMINI_topk.py --single-cmd "cat /proc/cpuinfo | grep name | wc -l" --model gemma:2b --k 5 --output output/single_results.jsonl

    dove le varie flag più importanti sono:
    - sessions = (solo CON contesto) flag attraverso cui si passa il file contente le sessioni di attacco (che al loro interno presentano i comandi su cui bisogna eseguire la prediction)
    - single-cmd = (solo SENZA contesto) flag attraverso cui si passa il comando di cui è necessario predirne il successivo
    - k = numero di comandi generati per la prediction
    - out = file che viene popolato con i risultati della prediction eseguita
    - n = (solo CON contesto) numero di comandi 
    - context-len = (solo CON contesto) numero di comandi precedenti al comando di cui bisogna prevederne il successivo (forniscono il contesto di attacco per LLM)
"""

# -------------------------
# IMPORT SECTION -> imports necessary for the Python script
# -------------------------

from __future__ import annotations
import argparse, os
import sys
import core_topk
from google.genai.types import HarmCategory, HarmBlockThreshold
from google.genai import Client
import os

# -------------------------
# GEMINI CALLER SECTION -> creates a client for interacting with Gemini models via the Google API and defines a utility function which sends a prompt to the model and returns the generated text.
# -------------------------

client = Client(api_key=os.getenv("GOOGLE_API_KEY"))

def query_gemini(prompt: str, model_name: str, temp: float = 0.0):
    try:
        #Visto che stiamo simulando degli attacchi, è necessario disattivare i blocchi di sicurezza
        safety_config = [
            {"category": HarmCategory.HARM_CATEGORY_HATE_SPEECH, "threshold": HarmBlockThreshold.BLOCK_NONE},
            {"category": HarmCategory.HARM_CATEGORY_HARASSMENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
            {"category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, "threshold": HarmBlockThreshold.BLOCK_NONE},
            {"category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
        ]

        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={
                "temperature": temp, 
                "top_p": 0.1,
                "max_output_tokens": 1024,
                "safety_settings": safety_config # APPLICHIAMO I FILTRI PERMISSIVI
            }
        )
        # Controllo difensivo: se il modello restituisce None o non ha testo
        if not response or not response.text: return "" 
        else: return response.text

    except Exception as exc:
        err_str = str(exc)
        # Gestione dell'errore in caso di error 404
        if "404" in err_str: 
            print(f"\n[ERRORE FATALE] Modello '{model_name}' non trovato.")
            sys.exit(1)
        # Restituzione di una stringa vuota per non rompere il loop
        return ""
    
# -------------------------
# MAIN SECTION
# -------------------------

def main():
    ap = argparse.ArgumentParser(description="Evaluate GEMINI top-K next-command prediction (sessions or single).")
    ap.add_argument("--sessions", help="JSONL sessions file: one JSON per line with fields: session, commands (list)")
    ap.add_argument("--single-cmd", choices=["yes", "no"], default="no", help="Per abilitare la prediction di un solo comando")
    ap.add_argument("--output", default=None)
    ap.add_argument("--model", default="gemini-flash-latest", help="Nome modello (es. gemini-1.5-pro-latest, gemini-pro)")  # modello spesso più stabile
    ap.add_argument("--k", type=int, default=5, help="Top-K candidates")
    ap.add_argument("--context-len", type=int, default=3, help="Context length when using sessions")
    ap.add_argument("--guaranteed-ctx", choices=["yes", "no"], default="yes", help="Per la creazione dei task, se il valore è yes, viene garantita la presenta di contesto costituita da context-len comandi")
    ap.add_argument("--n", type=int, default=0, help="Max steps to evaluate (0 = all)")
    
    args = ap.parse_args()
    if args.output is None:
        args.output = f"output/topk/gemini_topk_results_n{args.n}_ctx{args.context_len}_k{args.k}.jsonl"
    core_topk.prediction_evaluation(args, "gemini", query_model=query_gemini)

if __name__ == "__main__":
    main()