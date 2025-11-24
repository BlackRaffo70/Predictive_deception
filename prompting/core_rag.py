# -------------------------
# INTRODUCTION -> some utils informations about the Python script
# -------------------------


"""
Il file, che funge da libreria per i due file evaluate_GEMINI_RAG.py e evaluate_ollama_RAG.py, 
contiene la logica fondamentale per l'esecuzione del prompting, basato su RAG, nei due differenti modelli. All'interno di 
questa libreria sono presenti i seguenti elementi:

- Classe VectorContextRetriever:
    Questa rappresenta la classe fondamentale per l'esecuzione dell'approccio RAG (Retrieval-Augmented Generation), per 
    prevedere i comandi futuri sulla base di sessioni di attacco passate. Le sessioni di attacco (e anche delle finestre
    di dimensione minore) vengono trasformate in embeddings (vettori di numeri che rappresentano un qualsiasi oggetto 
    -> oggetti simili, presentano degli embedding simili) e salvate all'interno di un DB vettoriale. Ricercando all'interno
    del DB gli embedding simili a quelli di una sessione di attacco in corso, vengono restituiti contesti di attacco passati
    nonchè il successivo comando che era stato inserito. Questo elemento può essere utile per prevedere il successivo 
    comando inserito da un'attaccante. La classe presenta diverse funzioni:
    
    - __init__(self, persist_dir: str, collection_name="honeypot_attacks") -> configurazione del rag DB, con creazione del client e definizione del modello di embedding
    - index_file(self, jsonl_path: str, context_len: int) -> popolamento del DB vettoriale con la sessione di attacco e finestre scorrevoli di dimensione pari al context-length
    - retrieve(self, current_context_list: List[str], k: int = 3) -> funzione che, dato un contesto di attacco, restituisce i contesti simili ritrovati all'interno del DB

- Funzioni (utilizzate nei suddetti file):
    - hit_db(target_cmd: str, retrieved_examples_text: str) = funzione che serve per verificare se il comando obiettivo della prediction è stato indovinato attraverso la retrieve all'interno del DB vettoriale
    - clean_ollama_candidate(line: str) = funzione utilizzata per "pulire" la risposta di LLM ollama, fortemente indicizzata e verbosa (caratteristica del modello)
    - make_rag_prompt(context_list: List[str], rag_text: str, k: int)
    - prediction_evaluation(args) = funzione che viene chiamata dai suddenti file e che invia al LLM 
        il prompt, a seconda dei parametri specificati da utente
"""

# -------------------------
# IMPORT SECTION -> imports necessary for the Python script
# -------------------------

import os
import sys
import re
import json
import time
import random
import utils                            
from typing import List
from tqdm import tqdm
import chromadb
from chromadb.utils import embedding_functions

# -------------------------
# CLASS SECTION
# -------------------------

class VectorContextRetriever:
    # Inizializzazione RAG DB
    def __init__(self, persist_dir: str, collection_name="honeypot_attacks"):
        print(f"--- Inizializzazione RAG DB ({persist_dir}) ---")

        # Creazione client che gestisce un vector database ChromaDB, database contenente embeddings
        self.client = chromadb.PersistentClient(path=persist_dir)
        # Modello di embedding utile per eseguire ricerca all'interno di un db in quanto veloce e leggero -> ogni vettore è costituito da 384 elementi
        self.emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        # Creazione della tabella honeypot_attacks (parametro passato) all'interno del DB
        self.collection = self.client.get_or_create_collection(name=collection_name,embedding_function=self.emb_fn)

    # Indicizzazione sessioni di attacco
    def index_file(self, jsonl_path: str, context_len: int):
        if not os.path.exists(jsonl_path):
            print(f"[RAG ERROR] File non trovato: {jsonl_path}")
            return

        if self.collection.count() > 0:
            print(f"[RAG] DB già popolato ({self.collection.count()} vettori). Salto indicizzazione.")
            return

        print(f"[RAG] Indicizzazione vettoriale di {jsonl_path}...")
        documents, metadatas, ids = [], [], []

        with open(jsonl_path, "r", encoding="utf-8") as file_train: 
            lines = file_train.readlines()

        """
        Strategia di indicizzazione: oltre tutte le sessioni di attacco, vengono indicizzate anche le "finestre" scorrevoli.
        Se la sessione contiene i seguenti comandi: A -> B -> C -> D
        Indicizziamo:
          - Vettore("A") -> Target: "B"
          - Vettore("A B") -> Target: "C"
          - Vettore("A B C") -> Target: "D"
        """
    
        for line_idx, line in enumerate(tqdm(lines, desc="Indicizzazione DB", unit="line")):
            if not line.strip(): continue
            
            # Estrapolazione dei comandi contenuti all'interno della linea
            data = json.loads(line)
            cmds = data.get("commands", [])
            session_id = str(data.get("session", "unknown"))

            for i in range(len(cmds) - 1):                  # Si scorre fino al penultimo comando, in quanto l'ultimo è il target della prediction
                start = max(0, i - context_len + 1)         # Calcolo inizio della finestra scorrevole
                context_list = cmds[start:i+1]              # Lista comandi del contesto
                context_str = " || ".join(context_list)     # Storia dei comandi inseriti nella sessione d'attacco    
                target_cmd = cmds[i+1]                      # Comando obiettivo della prediction -> quello successivo alla finestra scorrevole
                
                documents.append(context_str)
                metadatas.append({
                    "next_command": target_cmd,
                    "session_id": session_id,
                    "original_line": line_idx
                })
                ids.append(f"sess_{line_idx}_step_{i}")
                
                # Aggiunta delle info nel DB -> per evitare accessi frequenti al DB
                if len(documents) >= 4000:
                    self.collection.add(documents=documents, metadatas=metadatas, ids=ids)
                    documents, metadatas, ids = [], [], []

        # Aggiunta delle info rimanenti nel DB -> necessario se non si era arrivato a 4000
        if documents: self.collection.add(documents=documents, metadatas=metadatas, ids=ids)
        
        print(f"[RAG] Indicizzazione completata. Totale vettori: {self.collection.count()}")

    # Ritrovamento all'interno del DB di attacchi simili
    def retrieve(self, current_context_list: List[str], k: int) -> str:
        
        # Sulla base del contesto attuale, viene eseguita una query al DB vettoriale, che restituisce i k più simili
        if not current_context_list: return ""
        query_text = " || ".join(current_context_list)
        results = self.collection.query(query_texts=[query_text], n_results=k)
        
        formatted_examples = ""
        if not results['ids']: return ""    # Se DB vuoto o contiene pochi vettori indicizzati

        # La query restituisce una lista di liste, perciò è necessario estrarre, per ogni campo, la lista contenuta all'interno
        ids = results['ids'][0]
        docs = results['documents'][0]
        metas = results['metadatas'][0]
        
        # Per ogni sessione di attacco simile, restituisce il contesto e il successivo comando inserito
        for i in range(len(ids)):
            hist_ctx = docs[i].replace(" || ", "\n")
            hist_next = metas[i]['next_command']
            formatted_examples += (
                f"--- SIMILAR PAST ATTACK (Example {i+1}) ---\n"
                f"Context:\n{hist_ctx}\n"
                f"Attacker Next Move:\n{hist_next}\n\n"
            )
        return formatted_examples
    
# -------------------------
# FUNCTION SECTION
# -------------------------
  
def hit_db(target_cmd: str, retrieved_examples_text: str) -> bool:
    target = target_cmd.strip()
    lines = retrieved_examples_text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("Attacker Next Move:") and i + 1 < len(lines):
            next_move = lines[i + 1].strip()
            if target == next_move:
                return True

    return False

def clean_ollama_candidate(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^\d+\.\s*", "", line)   # rimuove "1. "
    line = line.strip("`")                  # rimuove backticks
    return line.strip()

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

def prediction_evaluation(args, query_model):
    # Configurazione del DB vettoriale
    rag = VectorContextRetriever(persist_dir=args.persist_dir)
    source_for_index = args.index_file if args.index_file else args.sessions
    rag.index_file(source_for_index, context_len=args.context_len)

    # Preparazione sessioni di cui eseguire la prediction
    tasks = []
    print("--- Preparazione task di valutazione ---")
    try:
        # Lettura delle righe del file contenente le sessioni
        with open(args.sessions, "r", encoding="utf-8") as file: lines = [line for line in file if line.strip()]
        
        # Se il numero di prediction stabilito dall'utente è 0 = considera tutte le sessioni, altrimenti solo n sessioni random
        if args.n > 0: random_lines = random.sample(lines, min(args.n, len(lines)))

        for line in (random_lines if random_lines else lines):
            if not line.strip(): 
                continue
            try:
                obj = json.loads(line)
                cmds = obj.get("commands", [])
                sid = obj.get("session", "unk")

                # Dalla sessione random, si estra un comando random che funge da expected, i precedenti da contesto
                indice_expected= random.randint(0, len(cmds) - 1)
                expected = cmds[indice_expected]
                ctx_start = max(0, indice_expected - args.context_len)
                context = cmds[ctx_start:indice_expected]

                tasks.append({"session": sid, "context": context, "expected": expected})
            except: 
                continue
    except FileNotFoundError:
        sys.exit(f"Errore: Il file {args.sessions} non esiste.")

    print(f"Totale task da valutare: {len(tasks)}")
    if len(tasks) == 0: sys.exit("Nessun task trovato. Controlla il formato del file JSONL.")

    # Prompting al LLM e valutazione delle prediction eseguite
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    results = []
    top1_hits = 0
    topk_hits = 0
    empty_responses_count = 0
    
    print(f"--- Inizio Valutazione con Modello: {args.model} ---")
    
    with open(args.output, "w", encoding="utf-8") as fout:
        for task in tqdm(tasks, desc="Evaluating"):
            context = task["context"]
            expected = task["expected"]
            
            # Ritrovamento all'interno del DB di attacchi simili
            retrieved_text = rag.retrieve(context, args.rag_k)
            
            # Verifico se il comando expected è presente come campo Attacker Next Move all'interno della retrieve del DB vettoriale
            db_hit = hit_db(expected, retrieved_text)
            
            # Query LLM e ottenimento risposta
            prompt = make_rag_prompt(context, retrieved_text, args.k)
            raw_response = query_model(prompt, args.model)
            candidates = []
            if raw_response: 
                candidates = [clean_ollama_candidate(line) for line in raw_response.splitlines() if line.strip()]
            candidates = candidates[:args.k]
             
            if not candidates: 
                empty_responses_count += 1
            
            # Valutazione della prediction
            # Per ogni candidato prodotto, normalizzo il contenuto e verifico sia uguale al contenuto del comando expected
            hit = False
            hit_rank = 0
            norm_expected = utils.normalize_for_compare(expected)
            if not norm_expected: 
                sys.exit(f"Errore: Comando expected non trovato")

            for rnk, cand in enumerate(candidates, 1):
                norm_cand = utils.normalize_for_compare(cand)
                if len(norm_cand) == len(norm_expected):
                    i = 0
                    while i < len(norm_expected):
                        exp_name, exp_path = norm_expected[0]
                        cand_name, cand_path = norm_cand[0]
                        # Confronto prima il comando e poi l'eventuale path
                        if (exp_name == cand_name): 
                            if not exp_path or not cand_path or exp_path in cand_path or cand_path in exp_path:
                                hit = True
                                hit_rank = rnk
                                break
                        else: 
                            break
                        i+=1
                    # Un candidato corrisponde all'expected, esco dal ciclo
                    if hit:
                        topk_hits += 1
                        if hit_rank == 1: top1_hits += 1 
                        break 
            
            # Scrittura file
            rec = {
                "session": task["session"],
                "context": context,
                "expected": expected,
                "candidates": candidates,
                "hit": hit,
                "rank": hit_rank if hit else None,
                "db_hit": db_hit
            }
            fout.write(json.dumps(rec) + "\n")
            fout.flush()
            results.append(rec)
            time.sleep(0.5)

    # Stampa dei risultati
    total = len(results)
    if total == 0: 
        sys.exit("Nessun risultato generato.")
    
    print("\n=== RAG EVALUATION SUMMARY ===")
    print(f"Model: {args.model}")
    print(f"Total Tasks: {total}")
    print(f"Top-1 Accuracy: {top1_hits/total:.2%}")
    print(f"Top-{args.k} Accuracy: {topk_hits/total:.2%}")
    
    empty_rate = empty_responses_count / total if total else 0.0
    print(f"Empty Responses: {empty_responses_count}/{total} ({empty_rate:.2%})")
    
    db_hits = len([r for r in results if r['hit'] and r['db_hit']])
    clean_hits = len([r for r in results if r['hit'] and not r['db_hit']])
    print(f"Hits influenced by DB: {db_hits}")
    print(f"Hits NOT influenced by DB: {clean_hits}")
    print(f"Results saved to: {args.output}")

