#!/usr/bin/env python3

# -------------------------
# INTRODUCTION -> some utils informations about the Python script
# -------------------------


"""
- MODALITÀ:


- PRE-REQUISITI (comandi da eseguire da riga di comando):

    export GOOGLE_API_KEY=CHIAVE API    -> comando per esportare in locale la chiave per eseguire API Gemini (da rifare ogni volta che si chiude il terminale)
    source .env/bin/activate            -> comando per attivare enviroment virtuale
    pip install chromedb                -> comando per scaricare 
    pip install sentence-transformers   -> comando per scaricare 

- COMANDO PER ESECUZIONE (ATTENZIONE -> è necessario eseguire la prima riga di pre-requisiti ogni volta che si chiude il terminale):
    
    python3 prompting/evaluate_GEMINI_RAG.py --sessions output/cowrie_TEST.jsonl --index-file output/cowrie_TRAIN.jsonl --k 5 --rag-k 3 --context-len 5 --n 10
    
"""

# -------------------------
# IMPORT SECTION -> imports necessary for the Python script
# -------------------------

from __future__ import annotations
import argparse
import json
import os
import re
import time
import random
import sys
import utils
from typing import List, Tuple
from tqdm import tqdm
from google.genai.types import HarmCategory, HarmBlockThreshold

# --- LIBRERIE RAG & AI ---
try:
    import chromadb
    from chromadb.utils import embedding_functions
    from google.genai import Client
except ImportError:
    sys.exit("ERRORE: Librerie mancanti. Esegui: pip install chromadb sentence-transformers google-genai tqdm")

# =============================================================================
# 1. CONFIGURAZIONE & UTILS
# =============================================================================


def check_contamination(target_cmd: str, retrieved_examples_text: str) -> bool:
    target = target_cmd.strip()
    if len(target) < 4: return False
    return target in retrieved_examples_text

# =============================================================================
# 2. MOTORE RAG (VECTOR SEARCH)
# =============================================================================

class VectorContextRetriever:
    def __init__(self, collection_name="honeypot_attacks", persist_dir="./chroma_storage"):
        print(f"--- Inizializzazione RAG DB ({persist_dir}) ---")
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.emb_fn
        )

    def index_file(self, jsonl_path: str, context_len: int = 5):
        # Se la cartella esiste ed è piena, non ricreare il DB
        if os.path.exists(self.client._path) and \
                os.path.isdir(self.client._path) and \
                len(os.listdir(self.client._path)) > 0:
            print(f"[RAG] DB già esistente e non vuoto ({self.collection.count()} vettori). Skip indicizzazione.")
            return

        if self.collection.count() > 0:
            print(f"[RAG] DB già popolato ({self.collection.count()} vettori). Salto indicizzazione.")
            return

        print(f"[RAG] Indicizzazione vettoriale di {jsonl_path}...")
        documents, metadatas, ids = [], [], []
        
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line_idx, line in enumerate(tqdm(f, desc="Indexing")):
                if not line.strip(): continue
                try:
                    data = json.loads(line)
                    cmds = data.get("commands", []) or data.get("cmds", [])
                    if len(cmds) < 2: continue

                    for i in range(len(cmds) - 1):
                        start = max(0, i - context_len + 1)
                        context_list = cmds[start:i+1]
                        context_str = " || ".join(context_list)
                        target_cmd = cmds[i+1]
                        
                        documents.append(context_str)
                        metadatas.append({
                            "next_command": target_cmd,
                            "session_id": str(data.get("session", "unknown")),
                            "original_line": line_idx
                        })
                        ids.append(f"sess_{line_idx}_step_{i}")
                        
                        if len(documents) >= 5000:
                            self.collection.add(documents=documents, metadatas=metadatas, ids=ids)
                            documents, metadatas, ids = [], [], []

                except Exception:
                    continue
        
        if documents:
            self.collection.add(documents=documents, metadatas=metadatas, ids=ids)
        print(f"[RAG] Indicizzazione completata. Totale vettori: {self.collection.count()}")

    def retrieve(self, current_context_list: List[str], k: int = 3) -> str:
        if not current_context_list: return ""
        query_text = " || ".join(current_context_list)
        results = self.collection.query(query_texts=[query_text], n_results=k)
        
        formatted_examples = ""
        if not results['ids']: return ""

        ids = results['ids'][0]
        docs = results['documents'][0]
        metas = results['metadatas'][0]
        
        for i in range(len(ids)):
            hist_ctx = docs[i].replace(" || ", "\n")
            hist_next = metas[i]['next_command']
            formatted_examples += (
                f"--- SIMILAR PAST ATTACK (Example {i+1}) ---\n"
                f"Context:\n{hist_ctx}\n"
                f"Attacker Next Move:\n{hist_next}\n\n"
            )
        return formatted_examples

# =============================================================================
# 3. INTERAZIONE GEMINI (Gestione Errori Avanzata)
# =============================================================================

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    sys.exit("ERRORE CRITICO: La variabile d'ambiente GOOGLE_API_KEY non è impostata.")

client_gemini = Client(api_key=api_key)

def list_available_models():
    """Elenca i modelli disponibili per aiutare l'utente a scegliere quello giusto."""
    print("\n--- CHECK MODELLI DISPONIBILI ---")
    print("Sto interrogando l'API per vedere quali modelli supportano 'generateContent'...")
    try:
        # Nota: La sintassi esatta per listare modelli dipende dalla versione SDK.
        # Questa è una chiamata standard per l'SDK google-genai v1beta
        for m in client_gemini.models.list_models():
            if "generateContent" in m.supported_generation_methods:
                print(f" - {m.name}")
        print("---------------------------------\n")
    except Exception as e:
        print(f"Impossibile listare i modelli: {e}")

def query_gemini(prompt: str, model_name: str, temp: float = 0.0) -> str:
    """
    Chiama l'API con i filtri di sicurezza DISABILITATI per permettere la simulazione.
    """
    try:
        # Configurazione per disabilitare i blocchi di sicurezza
        # Necessario perché stiamo simulando comandi di attacco
        safety_config = [
            {"category": HarmCategory.HARM_CATEGORY_HATE_SPEECH, "threshold": HarmBlockThreshold.BLOCK_NONE},
            {"category": HarmCategory.HARM_CATEGORY_HARASSMENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
            {"category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, "threshold": HarmBlockThreshold.BLOCK_NONE},
            {"category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
        ]

        response = client_gemini.models.generate_content(
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
        if not response or not response.text:
            return "" 
            
        return response.text

    except Exception as e:
        # Gestione specifica per errori 404 o blocchi
        err_str = str(e)
        if "404" in err_str:
            print(f"\n[ERRORE FATALE] Modello '{model_name}' non trovato.")
            sys.exit(1)
        
        # Ritorna stringa vuota in caso di errore generico per non rompere il loop
        return f""

def make_rag_prompt(context_list: List[str], rag_text: str, k: int) -> str:
    current_history = "\n".join(context_list[-10:])
    return f"""
You are an AI simulating a cyber-attacker inside an SSH honeypot.
Your task is to predict the EXACT next command the attacker will type.

INSTRUCTIONS:
1. Analyze the 'CURRENT SESSION' below.
2. Look at the 'SIMILAR PAST ATTACKS' provided (Retrieval Augmented Generation) to understand attacker patterns.
3. Output the {k} most likely next commands.
4. Output ONLY raw commands, one per line. No explanations.

========================================
{rag_text}
========================================

CURRENT SESSION HISTORY:
{current_history}

PREDICT NEXT {k} COMMANDS (Raw text only):
""".strip()

# =============================================================================
# 4. MAIN LOOP
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Evaluate Gemini with RAG Vector Search")
    parser.add_argument("--sessions", required=True, help="File JSONL con le sessioni di test")
    parser.add_argument("--index-file", help="File JSONL per DB vettoriale (se diverso da sessions)")
    parser.add_argument("--out", default="output/gemini_rag_results.jsonl")
    # MODIFICA: Default cambiato a 'gemini-1.5-flash-latest' che è spesso più stabile
    parser.add_argument("--model", default="gemini-flash-latest", help="Nome modello (es. gemini-1.5-pro-latest, gemini-pro)")
    parser.add_argument("--k", type=int, default=5, help="Numero di predizioni")
    parser.add_argument("--rag-k", type=int, default=3, help="Esempi storici da recuperare")
    parser.add_argument("--context-len", type=int, default=5, help="Lunghezza contesto")
    parser.add_argument("--n", type=int, default=0, help="Max test (0=tutti)")
    
    args = parser.parse_args()

    # 1. Setup RAG
    rag = VectorContextRetriever(persist_dir="./chroma_storage")
    source_for_index = args.index_file if args.index_file else args.sessions
    rag.index_file(source_for_index, context_len=args.context_len)

    # 2. Caricamento Tasks
    tasks = []
    print("--- Preparazione task di valutazione ---")
    try:
        with open(args.sessions, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                try:
                    obj = json.loads(line)
                    cmds = obj.get("commands", [])
                    sid = obj.get("session", "unk")
                    if len(cmds) < 2: continue
                    
                    for i in range(len(cmds) - 1):
                        ctx_start = max(0, i - args.context_len + 1)
                        context = cmds[ctx_start:i+1]
                        expected = cmds[i+1]
                        tasks.append({"session": sid, "context": context, "expected": expected})
                except: continue
    except FileNotFoundError:
        sys.exit(f"Errore: Il file {args.sessions} non esiste.")

    if args.n > 0:
        random.seed(42)
        random.shuffle(tasks)
        tasks = tasks[:args.n]

    print(f"Totale task da valutare: {len(tasks)}")
    if len(tasks) == 0:
        sys.exit("Nessun task trovato. Controlla il formato del file JSONL.")

    # 3. Execution Loop
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    results = []
    top1_hits = 0
    topk_hits = 0
    empty_responses_count = 0  # --- NUOVO CONTATORE ---
    
    print(f"--- Inizio Valutazione con Modello: {args.model} ---")
    
    with open(args.out, "w", encoding="utf-8") as fout:
        for t in tqdm(tasks, desc="Evaluating"):
            context = t["context"]
            expected = t["expected"]
            
            # A. RAG RETRIEVAL
            retrieved_text = rag.retrieve(context, k=args.rag_k)
            
            # B. CHECK CONTAMINATION
            is_contaminated = check_contamination(expected, retrieved_text)
            
           # C. QUERY GEMINI
            prompt = make_rag_prompt(context, retrieved_text, args.k)
            raw_response = query_gemini(prompt, args.model)
            
            # D. PARSING
            # --- CODICE VECCHIO CHE DAVA ERRORE ---
            # candidates = [line.strip() for line in raw_response.splitlines() if line.strip()]
            
            # --- CODICE NUOVO CORRETTO ---
            candidates = []
            if raw_response:  # Verifica che non sia None o vuoto
                candidates = [line.strip() for line in raw_response.splitlines() if line.strip()]
            
            candidates = candidates[:args.k]
            
            # --- NUOVO CONTROLLO RISPOSTE VUOTE ---
            if not candidates:
                empty_responses_count += 1
            
            # E. EVALUATION
            hit = False
            hit_rank = 0
            
            norm_expected = utils.normalize_for_compare(expected)
            if norm_expected:
                exp_name, exp_path = norm_expected[0]
                
                for rnk, cand in enumerate(candidates, 1):
                    norm_cand = utils.normalize_for_compare(cand)
                    if not norm_cand: continue
                    cand_name, cand_path = norm_cand[0]
                    
                    if cand_name == exp_name:
                        if not exp_path or not cand_path or exp_path in cand_path or cand_path in exp_path:
                            hit = True
                            hit_rank = rnk
                            break
            
            if hit:
                topk_hits += 1
                if hit_rank == 1: top1_hits += 1
            
            # F. SALVATAGGIO
            rec = {
                "session": t["session"],
                "context": context,
                "expected": expected,
                "candidates": candidates,
                "hit": hit,
                "rank": hit_rank if hit else None,
                "contamination": is_contaminated
            }
            fout.write(json.dumps(rec) + "\n")
            fout.flush()
            results.append(rec)
            
            time.sleep(0.5) # Rate limit safety

    # 4. SUMMARY
    total = len(results)
    if total == 0: sys.exit("Nessun risultato generato.")
    
    print("\n=== RAG EVALUATION SUMMARY ===")
    print(f"Model: {args.model}")
    print(f"Total Tasks: {total}")
    print(f"Top-1 Accuracy: {top1_hits/total:.2%}")
    print(f"Top-{args.k} Accuracy: {topk_hits/total:.2%}")
    
    # --- NUOVA STAMPA PERCENTUALE VUOTE ---
    empty_rate = empty_responses_count / total if total else 0.0
    print(f"Empty Responses: {empty_responses_count}/{total} ({empty_rate:.2%})")
    
    contaminated_hits = len([r for r in results if r['hit'] and r['contamination']])
    clean_hits = len([r for r in results if r['hit'] and not r['contamination']])
    print(f"Hits on Contaminated Data (Memory): {contaminated_hits}")
    print(f"Hits on Clean Data (Generalization): {clean_hits}")
    print(f"Results saved to: {args.out}")

if __name__ == "__main__":
    main()