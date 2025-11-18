import chromadb
from chromadb.utils import embedding_functions
import json
import uuid

class VectorContextRetriever:
    def __init__(self, collection_name="attacker_sessions"):
        """
        Inizializza il database vettoriale locale (in memoria o su disco).
        Usa 'sentence-transformers' per creare gli embedding (gratuito e locale).
        """
        self.client = chromadb.Client() # O chromadb.PersistentClient(path="./db") per salvare su disco
        
        # Funzione di embedding standard (trasforma testo -> numeri)
        self.emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2" 
        )
        
        # Crea o ottieni la collezione (come una tabella SQL ma per vettori)
        self.collection = self.client.get_or_create_co9llection(
            name=collection_name,
            embedding_function=self.emb_fn
        )

    def index_sessions_from_jsonl(self, jsonl_path, context_len=5):
        """
        FASE 1: PREPARAZIONE / INDICIZZAZIONE
        Legge il file delle sessioni passate e le trasforma in vettori.
        
        Strategia: Non indicizziamo solo l'intera sessione, ma le "finestre" scorrevoli.
        Se la sessione è: A -> B -> C -> D
        Indicizziamo:
          - Vettore("A") -> Target: "B"
          - Vettore("A B") -> Target: "C"
          - Vettore("A B C") -> Target: "D"
        Questo permette di trovare match parziali precisi.
        """
        print(f"--- Indicizzazione vettoriale di {jsonl_path} in corso... ---")
        documents = []
        metadatas = []
        ids = []

        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f):
                if not line.strip(): continue
                try:
                    data = json.loads(line)
                    cmds = data.get("commands", [])
                    
                    # Sliding window indexing
                    for i in range(len(cmds) - 1):
                        # Prendiamo gli N comandi precedenti come "Contesto"
                        start = max(0, i - context_len + 1)
                        context_cmds = cmds[start:i+1]
                        target_cmd = cmds[i+1]
                        
                        # Creiamo la stringa che rappresenta la storia
                        context_str = " || ".join(context_cmds)
                        
                        documents.append(context_str)
                        metadatas.append({
                            "next_command": target_cmd, 
                            "session_id": str(data.get("session", "unknown")),
                            "step": i
                        })
                        ids.append(f"sess_{line_num}_step_{i}")
                        
                except Exception as e:
                    continue

        # Caricamento in blocco nel DB (trasforma testo in vettori automaticamente)
        if documents:
            # Chroma gestisce batching, ma per grandi dataset meglio farlo a blocchi di 5000
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
        print(f"--- Indicizzazione completata: {len(documents)} contesti vettorializzati. ---")

    def retrieve_similar_examples(self, current_context: list, k=5) -> str:
        """
        FASE 2: RICERCA
        Prende i comandi attuali, li trasforma in vettore, cerca i vicini nel DB.
        Ritorna una stringa formattata pronta per il prompt.
        """
        # Prepara la query nello stesso formato dell'indice
        query_text = " || ".join(current_context)
        
        # Esegue la ricerca dei 'k' vettori più vicini
        results = self.collection.query(
            query_texts=[query_text],
            n_results=k
        )
        
        # Costruzione del testo per il prompt (Few-Shot dinamico)
        examples_text = ""
        
        # results è un dizionario di liste. Iteriamo sui risultati trovati.
        for i in range(len(results['documents'][0])):
            # Il contesto storico trovato (simile al nostro)
            found_context = results['documents'][0][i].replace(" || ", "\n")
            # Il comando che seguiva in quella sessione storica
            found_next = results['metadatas'][0][i]['next_command']
            
            examples_text += f"--- Example (Similar Situation) ---\n"
            examples_text += f"Context:\n{found_context}\n"
            examples_text += f"Next Command:\n{found_next}\n\n"
            
        return examples_text