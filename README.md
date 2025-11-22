<img width="1024" height="233" alt="image" src="https://github.com/user-attachments/assets/e210dcce-57f2-4470-a895-780896dbe45f" />

# 🍯 Predictive Deception — LLM-based Command Anticipation in SSH Honeypots

---
## 🎯 Obiettivo del progetto: *Predictive Deception per Honeypot*

Gli honeypot tradizionali osservano e registrano ciò che l’attaccante fa **solo dopo** che un comando è stato eseguito.  
Il nostro progetto introduce un cambio di paradigma: usare un **LLM** per trasformare l’honeypot da sistema reattivo a **sistema predittivo**.

### 🚀 Idea chiave  
Un modello di linguaggio (es. CodeLlama o Gemini) analizza in tempo reale la sequenza di comandi digitati dall’attaccante e **predice il prossimo comando probabile** prima che venga effettivamente eseguito.

### 🔐 Perché è rivoluzionario  
Questa capacità permette all’honeypot di:

- 🪤 **Preparare deception mirate in anticipo**  
  Creare file fake, configurazioni fittizie, directory esca o output manipolati **prima** che l’attaccante le richieda.

- 🎯 **Attivare trigger intelligenti e invisibili**  
  Canary tokens, log ad alta granularità, honey-credentials, environment spoofing, tutto avviato *appena* la predizione indica un probabile step successivo.

- 🧠 **Aumentare l’ingaggio dell’attaccante**  
  Simulare sistemi realistici, far credere all’attaccante di essere nel posto giusto e catturare operazioni più avanzate.

- 📈 **Migliorare la qualità dell’intelligence**  
  Comprendere pattern, automatizzare il profiling di tool e campagne, generare dataset per threat research.

### 🧩 In sintesi  
Il progetto converte l’honeypot in un sistema attivo, capace di **anticipare** il comportamento dell’attaccante e adattarsi, invece di limitarsi a loggare passivamente quello che accade.


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

| Step | Script | Input | Output | Descrizione |
|------|--------|--------|---------|-------------|
| 1️⃣ | `download_zenodo.py` | — | `data/*.json` | Scarica dataset Cowrie da Zenodo (se non presenti) |
| 2️⃣ | `inspect_cowrie_json.py` | `data/*.json` | — | Ispeziona struttura JSON grezza (debug) |
| 3️⃣ | `merge_cowrie_datasets.py` | `data/*.json` | `output/merged_cowrie.jsonl` | Unisce più dataset Cowrie in un unico file |
| 4️⃣ | `analyze_and_clean.py` | `output/merged_cowrie.jsonl` | `output/cowrie_sessions.jsonl` | Estrae sessioni, comandi e normalizza i dati |
| 5️⃣ | `vector_research.py` | `output/cowrie_TEST.jsonl` | embedding temporanei | Analisi vettori & test embedding (debug RAG) |
| 6️⃣ | `convert_sessions_to_finetune.py` | `output/cowrie_sessions.jsonl` | `output/predictive_pairs.jsonl` | Crea coppie (context → next) per training LL |
| 7️⃣ | `core_topk.py` | `output/predictive_pairs.jsonl` | predizioni interne | Motore predittivo baseline top-k |
| 8️⃣ | `core_RAG.py` | `output/predictive_pairs.jsonl` + ChromaDB | predizioni RAG | Motore predittivo con Retrieval-Augmented |
| 9️⃣ | `evaluate_ollama_topk.py` | `output/predictive_pairs.jsonl` | `output/ollama_topk_results.jsonl` | Valuta modelli Ollama (solo top-k) |
| 🔟 | `evaluate_ollama_RAG.py` | `output/predictive_pairs.jsonl` | `output/ollama_rag_results.jsonl` | Valuta Ollama con RAG |
| 1️⃣1️⃣ | `evaluate_GEMINI_topk.py` | `output/predictive_pairs.jsonl` | `output/gemini_topk_results.jsonl` | Valuta Gemini API (top-k) |
| 1️⃣2️⃣ | `evaluate_GEMINI_RAG.py` | `output/predictive_pairs.jsonl` + ChromaDB | `output/gemini_rag_results.jsonl` | Valuta Gemini con RAG |
| 1️⃣3️⃣ | `utils.py` | — | — | Funzioni condivise (tokenizer, parsing, formatting) |


⸻

## 🚀 **Esempi di utilizzo rapido**

1️⃣ Analisi dataset Cowrie:
```bash
python analyze_cowrie_dataset.py --input data/cowrie_2020-02-29.json --output output/cowrie
```
2️⃣ Merge & Clean dei dataset Cowrie
```bash
python build_predictive_pairs.py --input output/cowrie_sessions.jsonl --output output/predictive_pairs.jsonl --context-len 1
```
3️⃣ Valutare modello locale con Ollama + RAG(opzionale):

```bash
ollama pull mistral:7b-instruct-q4_0
ollama serve &
python evaluate_ollama_topk.py --data output/predictive_pairs.jsonl --model mistral:7b-instruct-q4_0 --n 200 --temp 0.1
```
4️⃣ Valutare modello via Gemini (API):

```bash
export OPENROUTER_API_KEY="sk-or-xxxxxxxx"
python evaluate_LLM_OpenRouter.py --input output/predictive_pairs.jsonl --model deepseek/deepseek-r1:free --n 200
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

- Prompt **brevi** e in **inglese** migliorano la precisione del modello.  
- Estrarre **solo la prima riga valida** del comando previsto.  
- Testare diversi valori di **context length** (es. 1–5 comandi precedenti).  
- Misurare sia **Exact Match** che **similarità testuale** (Jaccard / SequenceMatcher).  
- Implementare **rate-limit** e **backoff** per l’uso di API gratuite.  
- Preferire **Ollama locale** o **GPU universitaria** per batch lunghi di test.  

---

## 🔧 Possibili estensioni future

- Fine-tuning su dataset SSH per migliorare la **precisione predittiva**.  
- Introduzione di **Top-k accuracy** (predizione di più comandi candidati).  
- Integrazione diretta con sistemi honeypot come **Cowrie** o **CanaryTokens**.  
- Analisi **semantica** dei pattern di attacco (ricognizione, persistence, privilege escalation, ecc.).  

---

## 📚 Riferimenti

- 🐍 **Cowrie Honeypot** → [github.com/cowrie/cowrie](https://github.com/cowrie/cowrie)  
- 🪤 **Canarytokens** → [canarytokens.org](https://canarytokens.org) / [github.com/thinkst/canarytokens](https://github.com/thinkst/canarytokens)  
- 💻 **Ollama** → [ollama.com](https://ollama.com) / [github.com/ollama/ollama](https://github.com/ollama/ollama)  
- 🌐 **OpenRouter API** → [openrouter.ai](https://openrouter.ai)  

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
