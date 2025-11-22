<img width="1024" height="233" alt="image" src="https://github.com/user-attachments/assets/e210dcce-57f2-4470-a895-780896dbe45f" />

# 🍯 Predictive Deception — LLM-based Command Anticipation in SSH Honeypots

---

## 🎯 Obiettivo del progetto: *Predictive Deception per Honeypot*

Gli honeypot tradizionali osservano e registrano ciò che l’attaccante fa **solo dopo** l’esecuzione di un comando.  
Questo progetto introduce un nuovo paradigma: sfruttare un **LLM** per trasformare l’honeypot da sistema passivo a **sistema predittivo**.

### 🚀 Idea chiave  
Un modello di linguaggio (es. CodeLlama, Llama 3, Gemini, Mistral) analizza la sequenza dei comandi dell'attaccante e **predice il prossimo comando** con alta accuratezza, *prima* che venga digitato.

### 🔐 Perché è rivoluzionario  
Grazie alla predizione dei comandi, l’honeypot può:

- 🪤 **Preparare deception mirate in anticipo**  
  Creare file fake, directory esca, configurazioni fittizie, output manipolati **prima** che l’attaccante tenti di accedervi.

- 🎯 **Attivare trigger intelligenti e invisibili**  
  Canary tokens, logging avanzato, honey-credentials, environment spoofing… tutto al momento giusto.

- 🧠 **Aumentare l’ingaggio dell’attaccante**  
  Il sistema diventa più realistico, più coerente e più credibile, favorendo l’emergere di comportamenti complessi e tecniche avanzate.

- 📈 **Potenziare la threat intelligence**  
  Analisi predittiva delle campagne, riconoscimento di tool automatizzati, profilo comportamentale degli attaccanti e dataset di alto valore.

### 🧩 In sintesi  
Il progetto trasforma l’honeypot in un sistema **proattivo**, capace non solo di osservare ma di **anticipare**, manipolare e studiare il comportamento dell’attaccante con un livello di controllo mai visto prima.

---

## 📦 Requirements

Il progetto utilizza LLM, RAG e dataset generati da honeypot Cowrie.  
Questi sono i requisiti minimi e completi per eseguire preprocessing, predizione e fine-tuning.

### 🔧 Core Dependencies
- `python-dotenv`
- `tqdm`
- `requests`
- `jsonlines`
- `pandas`

### 🧠 RAG & Embeddings
- `chromadb`
- `sentence-transformers`

### 🤖 LLM APIs (Gemini / OpenAI / HF)
- `openai`
- `google-genai`
- `transformers`
- `tokenizers`
- `safetensors`

### 🧪 Fine-Tuning (CodeLlama / PEFT)
- `torch`
- `accelerate`
- `datasets`
- `peft`
- `bitsandbytes`

### 📊 Machine Learning Utilities
- `scikit-learn`
- `numpy`

---

## 📁 Struttura del repository
```bash
## 📁 Struttura del repository

```bash
Predictive_deception/
│
├── chroma_storage/                     # Storage locale per ChromaDB (RAG)
│
├── data/                               # Dataset Cowrie grezzi o scaricati
│
├── fine_tuning/                        # Script per preparazione e training modelli
│   └── convert_sessions_to_finetune.py # Converte sessioni SSH in dataset per LLM
│
├── google-cloud-sdk/                   # SDK Google (opzionale, per storage/compute)
│
├── inspectDataset/                     # Analisi e pulizia dataset Cowrie
│   ├── analyze_and_clean.py            # Pulizia e normalizzazione eventi
│   └── merge_cowrie_datasets.py        # Merge file Cowrie multipli
│
├── output/                             # File prodotti dal progetto (dataset, risultati)
│
├── prompting/                          # Modulo per valutazione predittiva LLM
│   ├── core_RAG.py                     # Motore RAG locale
│   ├── core_topk.py                    # Motore top-k senza RAG
│   ├── evaluate_GEMINI_RAG.py          # Valutazione Gemini con RAG
│   ├── evaluate_GEMINI_topk.py         # Valutazione Gemini top-k
│   ├── evaluate_ollama_RAG.py          # Valutazione modelli locali (Ollama) con RAG
│   ├── evaluate_ollama_topk.py         # Valutazione Ollama top-k
│   └── utils.py                        # Funzioni condivise (tokenizzazione, parsing, ecc.)
│
├── utilities_script/                   # Script di utilità e preprocessing
│   ├── download_zenodo.py              # Download dataset pubblici da Zenodo
│   ├── inspect_cowrie_json.py          # Ispezione JSON Cowrie per debugging
│   └── vector_research.py              # Analisi vettori, embedding e RAG debugging
│
├── venv/                               # Ambiente virtuale Python (non va pushato)
│
├── .gitignore
├── google-cloud-cli-darwin-x86_64.tar.gz
├── README.md
├── requirements.txt
└── todo.txt


```

⸻
---

## 🧭 Workflow del progetto

## 🧭 Workflow del progetto

| Step | Script | Input | Output | Descrizione |
|------|--------|--------|---------|-------------|
| 1️⃣ | `download_zenodo.py` | — | `data/*.json` | Scarica automaticamente i file Cowrie dal dataset Zenodo (record 3687527) |
| 2️⃣ | `inspect_cowrie_json.py` | `data/*.json` | — | Ispezione e validazione della struttura dei file JSON grezzi |
| 3️⃣ | `analyze_and_clean.py` | `data/*.json` | `output/cowrie_{RAW,CLEAN}.jsonl` | Analizza singoli file, estrae sessioni e normalizza comandi |
| 4️⃣ | `merge_cowrie_datasets.py` | `data/*.json` | `output/cowrie_ALL_RAW.jsonl` / `output/cowrie_ALL_CLEAN.jsonl` | Unisce tutti i file, produce RAW e CLEAN globali, genera statistiche, split train/test |
| 5️⃣ | `filter_short_sessions.py` | `output/cowrie_ALL_CLEAN.jsonl` | `output/cowrie_ALL_CLEAN_filtered.jsonl` | Rimuove sessioni troppo brevi (min-len configurabile) |
| 6️⃣ | `core_topk.py` | — | — | Motore predittivo TOP-K (logica comune a Ollama e Gemini) |
| 7️⃣ | `core_RAG.py` | — + ChromaDB | — | Motore RAG: embedding, indicizzazione, ricerca vettoriale e few-shot dinamico |
| 8️⃣ | `evaluate_ollama_topk.py` | `output/cowrie_TEST.jsonl` | `output/ollama_topk_results.jsonl` | Valutazione modelli locali Ollama (modalità TOP-K) |
| 9️⃣ | `evaluate_ollama_RAG.py` | `output/cowrie_TEST.jsonl` + ChromaDB | `output/ollama_rag_results.jsonl` | Valutazione modelli Ollama con RAG |
| 🔟 | `evaluate_GEMINI_topk.py` | `output/cowrie_TEST.jsonl` | `output/gemini_topk_results.jsonl` | Valutazione Gemini API (TOP-K) |
| 1️⃣1️⃣ | `evaluate_GEMINI_RAG.py` | `output/cowrie_TEST.jsonl` + ChromaDB | `output/gemini_rag_results.jsonl` | Valutazione Gemini API con RAG |
| 1️⃣2️⃣ | `vector_research.py` | qualsiasi JSONL | output debug | Strumento di debug per test embedding, query e qualità del vector search |
| 1️⃣3️⃣ | `utils.py` | — | — | Funzioni condivise: normalizzazione comandi, pulizia, confronto, parsing |
⸻

## 🚀 **Esempi di utilizzo rapido**

1️⃣ Merge, Clean e Split del dataset Cowrie:
```bash
python inspectDataset/merge_cowrie_datasets.py --input data --output output/cowrie --want clean
```
2️⃣ Generare coppie di predizione (sliding window) per il fine-tuning:
```bash
python build_predictive_pairs.py --input output/cowrie_sessions.jsonl --output output/predictive_pairs.jsonl --context-len 1
```
3️⃣ Valutare un modello locale con Ollama (solo TOP-K):
```bash
ollama pull mistral:7b-instruct-q4_0
ollama serve &
python prompting/evaluate_ollama_topk.py --sessions output/cowrie_TEST.jsonl --model mistral:7b-instruct-q4_0 --k 5 --n 200 --context-len 5
```
4️⃣ Valutare un modello locale con Ollama + RAG (opzionale):

```bash
python prompting/evaluate_ollama_RAG.py --sessions output/cowrie_TEST.jsonl --index-file output/cowrie_TRAIN.jsonl --model codellama --k 5 --rag-k 3 --context-len 5 --n 200
```
5️⃣ Valutare un modello via Gemini (API) – modalità TOP-K:

```bash
export GOOGLE_API_KEY="AIza-xxxxxxxx"
python prompting/evaluate_GEMINI_topk.py --sessions output/cowrie_TEST.jsonl --k 5 --n 200 --model gemini-1.5-flash-latest
```
6️⃣ Valutare un modello via Gemini (API) + RAG:
```bash
python prompting/evaluate_GEMINI_RAG.py --sessions output/cowrie_TEST.jsonl --index-file output/cowrie_TRAIN.jsonl --k 5 --rag-k 3 --context-len 5 --n 200 --model gemini-1.5-flash-latest
```
⸻

## 📊 Output di esempio

Esempio di riga in ollama_results.jsonl:
```bash
{"context": ["whoami", "uname -a"], "expected": "cat /etc/passwd", "predicted": "cat /etc/shadow", "similarity": 0.85, "match": 0, "raw_response": "cat /etc/shadow"}
```
Esempio di file summary.json:
```bash
{
  "total_new": 200,
  "exact_acc": 0.12,
  "near_matches_jaccard>=0.80": 0.35,
  "error_rate": 0.05,
  "model": "mistral:7b-instruct-q4_0",
  "generated_at": "2025-11-04T10:00:00Z"
}
```

⸻

---

## 🧠 Note metodologiche

- I modelli funzionano meglio con **prompt brevi** e **in inglese**, come quelli costruiti in  
  `core_topk.py` e `core_RAG.py`.
- Le predizioni devono sempre essere pulite: estrarre **solo la prima riga valida**, usando le funzioni
  di parsing e normalizzazione in `utils.py`.
- Testare diversi valori di **context length** (`--context-len`), soprattutto con:  
  - `evaluate_ollama_topk.py`  
  - `evaluate_GEMINI_topk.py`  
  - `evaluate_ollama_RAG.py`  
  - `evaluate_GEMINI_RAG.py`
- Per valutare correttamente i modelli, utilizzare sia:
  - **Exact Match** (già implementato nel tuo codice)
  - **Confronto normalizzato** tramite `utils.normalize_for_compare()`
- Quando si usano API come Gemini, mantenere attivo **rate limit** + **sleep** (già presente nei tuoi script).
- Preferire modelli locali via **Ollama** (`codellama`, `llama3`, `mistral`, `gemma:2b`) per test massivi,
  perché gli script `evaluate_ollama_*` sono ottimizzati per esecuzioni lunghe.
- Usare dataset puliti generati da:
  - `merge_cowrie_datasets.py`
  - `analyze_and_clean.py`
  - `convert_sessions_to_finetune.py`  
  per ridurre rumore e comandi non utili all’LLM.
- Per RAG, evitare di reinizializzare il DB: `VectorContextRetriever` verifica già se la collezione esiste.

---

## 🔧 Possibili estensioni future

- Addestrare un modello locale tramite **fine-tuning** su `convert_sessions_to_finetune.py`
  (formato già pronto per supervised next-command prediction).
- Implementare metriche avanzate come:
  - **Top-k Accuracy**
  - **Recall@k**
  - **Confidence Distribution** dei candidati prodotti dal modello
- Integrare direttamente il motore predittivo (top-k o RAG) dentro Cowrie tramite:
  - hook sugli eventi `cowrie.command.input`  
  - API locale che richiama `evaluate_ollama_topk.py`
- Utilizzare `core_RAG.py` per creare un **Honeypot con memoria storica** degli attacchi,
  aggiornando dinamicamente ChromaDB con nuove sessioni.
- Aggiungere una pipeline di:
  - **Command Semantics Classification** per etichettare automaticamente i pattern:
    ricognizione, file exfiltration, credential harvesting, persistence, ecc.
- Costruire dashboard real-time usando i file JSONL prodotti da:
  - `evaluate_ollama_topk.py`
  - `evaluate_ollama_RAG.py`
  - `evaluate_GEMINI_RAG.py`
- Estendere il dataset includendo altri dataset pubblici (Zenodo 3759652, SIHD, HoneySELK)
  già compatibili con i tuoi script di merge e normalizzazione.

---

## 📚 Riferimenti

- 🐍 **Cowrie Honeypot** → https://github.com/cowrie/cowrie
- 🪤 **Canarytokens** → https://canarytokens.org / https://github.com/thinkst/canarytokens
- 💻 **Ollama** → https://ollama.com / https://github.com/ollama/ollama
- 🌐 **OpenRouter API** → https://openrouter.ai
- 🧪 **CyberLab Honeynet Dataset (Zenodo)** → https://zenodo.org/records/3687527
- 🐼 **PANDAcap SSH Dataset** → https://zenodo.org/records/3759652
- 🏭 **SIHD – Smart Industrial Honeypot Dataset (IEEE)** → https://ieee-dataport.org/documents/sihd-smart-industrial-honeypot-dataset
- 🕵️ **HoneySELK Cyber Attacks Dataset (IEEE)** → https://ieee-dataport.org/open-access/dataset-cyber-attacks-honeyselk

### 📘 Key Papers
- 📄 Nawrocki et al. (2016) — "A Survey on Honeypot Software and Data Analysis"  
- 🤖 Deng et al. (2023) — "PentestGPT: Evaluating LLMs for Automated Penetration Testing"  
- 🛡️ Alata et al. — "Lessons Learned from High-Interaction Honeypot Deployment"  
- 🐦 Whitham — "Canary Tokens and Deception"  

---

## 👥 Autori

| | | |
|:--:|:--:|:--:|
| <a href="https://github.com/BlackRaffo70"><img src="https://github.com/BlackRaffo70.png" width="110" alt="avatar Raffaele Neri"></a> | <a href="https://github.com/melomatte"><img src="https://github.com/melomatte.png" width="110" alt="avatar Matteo Melotti"></a> | <a href="https://github.com/kikeeeee"><img src="https://github.com/kikeeeee.png" width="110" alt="avatar Enrico Borsetti"></a> |
| **Raffaele Neri**<br/>[@BlackRaffo70](https://github.com/BlackRaffo70) | **Matteo Melotti**<br/>[@melottimatteo](https://github.com/melomatte) | **Enrico Borsetti**<br/>[@enricoborsetti](https://github.com/kikeeeee) |

---

📘 *Progetto di ricerca:*  
**🍯 Predictive Deception – LLM-based Command Anticipation in SSH Honeypots**  
Università di Bologna – Corso di Laurea Magistrale in Ingegneria Informatica  

👨‍🏫 *Docente referente:* **Prof. Michele Colajanni**
