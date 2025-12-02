#!/usr/bin/env python3

# -------------------------
# INTRODUCTION -> some utils informations about the Python script
# -------------------------

"""
- MODALITÀ:
    Il file contiene la funzione query_gemini() che crea il client per mandare il prompt a LLM gemini 
    (è possibile scegliere il modello). Tutte le funzionalità di effettivo prompting sono contenute all'interno
    del file core_topk.py in quanto in comune con lo script evaluate_ollama_topk.py. 

- PRE-REQUISITI (comandi da eseguire da riga di comando):

    export GOOGLE_API_KEY=CHIAVE API    -> comando per esportare in locale la chiave per eseguire API Gemini (da rifare ogni volta che si chiude il terminale)
    source .venv/bin/activate           -> comando per attivare enviroment virtuale
    pip install --upgrade google-genai  -> comando per scaricare le API Gemini

- COMANDO PER ESECUZIONE (ATTENZIONE -> è necessario eseguire la prima riga di pre-requisiti ogni volta che si chiude il terminale):

    - Per quanto riguarda prompting SENZA whitelist:

        python3 prompting/evaluate_gemini_topk.py --sessions /media/matteo/T9/outputMerge/cowrie_ALL_CLEAN.jsonl --k 5 --context-len 3 --n 10 --whitelist no

    - Per quanto riguarda prompting CON whitelist:
    
        python3 prompting/evaluate_gemini_topk.py --sessions /media/matteo/T9/outputMerge/cowrie_ALL_CLEAN.jsonl --k 5 --context-len 3 --n 10

    dove le varie flag sono:
    - sessions = file contenente le sessioni di attacco (che al loro interno presentano i comandi su cui bisogna eseguire la prediction)
    - whitelist = flag per specificare se eseguire il prompting che integra l'utilizzo di whitelist
    - output = per specificare il nome del file che contiene le prediction
    - k = numero di comandi generati per la prediction
    - model = per specificare il modello di Gemini
    - n = numero di predictio da eseguire per test  
    - context-len = numero di comandi precedenti al comando di cui bisogna prevederne il successivo (forniscono il contesto di attacco per LLM)
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

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    sys.exit("ERRORE CRITICO: La variabile d'ambiente GOOGLE_API_KEY non è impostata.")

client = Client(api_key=api_key)

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
    ap.add_argument("--sessions", help="File json contenenti le sessioni: ogni riga deve essere strutturata come: session, commands (list)")
    ap.add_argument("--whitelist", choices=["yes", "no"], default="yes", help="Con opzione attivata, esegue il prompt con whitelist")
    ap.add_argument("--output", default=None, help="Nome del file dove verranno generati i risultati della prediction")
    ap.add_argument("--model", default="gemini-flash-latest", help="Nome modello (es. gemini-1.5-pro-latest, gemini-pro)")  # modello spesso più stabile
    ap.add_argument("--k", type=int, default=5, help="Candidati proposti come next command dell'attaccante")
    ap.add_argument("--context-len", type=int, default=5, help="Numero di comandi che rappresentano il contesto di attacco")
    ap.add_argument("--n", type=int, default=0, help="Numero di prediction da eseguire (0 = una prediction per ogni sessione del file di input)")
    
    args = ap.parse_args()
    if args.output is None:
        args.output = f"output/topk/gemini/gemini_topk_results_n{args.n}_ctx{args.context_len}_k{args.k}.jsonl"
    core_topk.prediction_evaluation(args, "gemini", query_model=query_gemini)

if __name__ == "__main__":
    main()