<img width="1024" height="233" alt="image" src="https://github.com/user-attachments/assets/e210dcce-57f2-4470-a895-780896dbe45f" />

# 🍯 Predictive Deception — LLM-based Command Anticipation in SSH Honeypots

---

## 🎯 Obiettivo del progetto — *Predictive Deception per Honeypot*

Gli honeypot tradizionali osservano e registrano ciò che l’attaccante fa **solo dopo** l’esecuzione di un comando.  
Questo progetto introduce un nuovo paradigma: sfruttare un **LLM** per trasformare l’honeypot da sistema passivo a **sistema predittivo e adattivo**.

---

## 🚀 Idea chiave  
Un modello di linguaggio (CodeLlama, Llama 3, Gemini, Mistral) analizza in tempo reale la sequenza dei comandi dell’attaccante e **predice il prossimo comando** con elevata accuratezza — *prima che venga digitato*.

Questa predizione permette al sistema di costruire sul filesystem una *realtà manipolata* che l’attaccante non può distinguere da quella autentica.

---

## 🪤 Core Concept: Predictive Deception

La **deception** in questo progetto non è statica, ma *dinamica e reattiva*.  
Si basa su tre principi fondamentali:

### 1️⃣ *Preparazione anticipata*  
Prima che l’attaccante esegua il comando previsto, il sistema crea:

- file fake ma plausibili  
- directory esca  
- script o configurazioni manipolate  
- log fittizi  
- output alterati

Il tutto generato automaticamente dal modello LLM, a seconda del comando predetto.

Esempio:  
se il modello predice `cat /etc/passwd`, il sistema può generare una versione *decoy*, coerente ma falsificata.

---

### 2️⃣ *Branching e pruning*  
Per ogni comando vengono predetti **5 possibili next-steps**.

Per ciascuno viene generata una *branch* di deception:

- branch A → file X  
- branch B → directory Y  
- branch C → canary token Z  
- …

Quando l’attaccante esegue realmente un comando, il sistema:

- mantiene **solo la branch corretta**  
- elimina le altre 4 con cleanup automatico  
- conserva coerenza assoluta nel filesystem

Questo crea la sensazione di un sistema vivo e coerente, impossibile da sgamare.

---

### 3️⃣ *Deception adattiva basata su RAG*  
L'LLM non predice "a caso".  
Combina:

- history della sessione  
- sequenze di attacchi precedenti conservate via **ChromaDB RAG**

In questo modo la deception diventa *personalizzata*:

- se l’attaccante mostra pattern simili a botnet → deception tecnica  
- se mostra pattern umani → deception narrativa e coerente  
- se usa tool come Mirai, Tsunami, zmap → deception su file system e servizi

---

## 🔐 Perché è rivoluzionario

- 🪤 **Deception mirata e contestuale**  
  Non è la solita deception statica: il sistema modifica l’ambiente *in tempo reale* in base al comportamento.

- 🎯 **Trigger nascosti intelligenti**  
  Canary tokens, honey-credentials e file monitoring attivati solo quando utili.

- 🧠 **Ingaggio dell’attaccante aumentato**  
  L’ambiente sembra perfettamente reale, con struttura coerente e reattiva.

- 📡 **Threat intelligence potenziata**  
  La correlazione via RAG tra comandi vecchi e nuovi permette un profiling comportamentale avanzato.

- 🎛 **Riduzione dei falsi positivi**  
  La predizione contestuale evita di generare deception non rilevanti.

---

## 🧩 In sintesi  
Il progetto trasforma l’honeypot in un sistema **proattivo**, capace non solo di osservare ma di:

- **anticipare** l’attaccante  
- **modellare** l’ambiente in base al suo comportamento  
- **manipolare** la percezione dell’host  
- **studiare** tecniche emergenti tramite dataset predittivi

Si passa così da un honeypot statico a un sistema **intelligente, adattivo e realmente interattivo**, in grado di raccogliere informazioni impossibili da ottenere con soluzioni tradizionali.

---

## 📦 Requirements

Il progetto utilizza LLM, RAG e dataset da honeypot (Cowrie) per analisi predittiva, deception adattiva e fine-tuning dei modelli.  
Di seguito l’elenco completo e organizzato delle dipendenze necessarie.

---

## 🔧 Core Dependencies
Librerie principali per gestione ambiente, logging, preprocessing e networking.

- `python-dotenv` — gestione variabili d’ambiente
- `tqdm` — progress bar e logging
- `requests` — API e download dataset
- `jsonlines` — lettura/scrittura JSONL
- `pandas` — preprocess e analisi dataset

---

## 🧠 RAG & Embeddings  
Moduli necessari per creare e interrogare il database vettoriale basato su ChromaDB.

- `chromadb`
- `sentence-transformers`  
  (utilizzato per MiniLM-L6-v2 nei retrieval)

---

## 🤖 LLM APIs (Gemini / OpenAI / HF)
Integrazione con i principali modelli LLM utilizzati nel progetto per predizione e generazione degli artefatti di deception.

- `openai`
- `google-genai`
- `transformers`
- `tokenizers`
- `safetensors`

---

## 🧪 Fine-Tuning (CodeLlama / LoRA / PEFT)
Dipendenze necessarie per addestramento leggero (LoRA) su dataset Cowrie + sequenze attaccante.

- `torch`
- `accelerate`
- `datasets`
- `peft`
- `bitsandbytes`  
  (quantizzazione 4/8-bit per GPU poco potenti)

---

## 📊 Machine Learning Utilities
Strumenti usati per normalizzazione, feature engineering, clustering comportamentale.

- `scikit-learn`
- `numpy`

---

## 🔍 Nota
Tutte le librerie sono compatibili con Python **3.10+** e con ambienti virtuali standard (`venv`/`conda`).  
Per l’ecosistema LLM è consigliata una GPU NVIDIA con supporto CUDA, ma il sistema funziona anche in CPU per test, predizione e RAG.

## 📁 Struttura del repository

```bash
Predictive_deception/
│
├── chroma_storage/                     # Database vettoriale ChromaDB
│   ├── chroma.sqlite3
│   └── DB_checkpoint.txt
│
├── deception/                          # Motore di deception + defender runtime
│   ├── scenarios/
│   ├── brain.py
│   ├── config.py
│   ├── defender.py
│   ├── host.key
│   ├── main.py
│   ├── session_handler.py
│   └── ssh_server.py
│
├── Honeypot/                           # Ambiente honeypot (Vagrant + Ansible)
│   ├── Vagrantfile
│   ├── playbook.yml
│   ├── readme.txt
│   └── roles/
│       ├── db_vettoriale/
│       │   └── tasks/
│       ├── defender/
│       │   ├── files/
│       │   │   └── defender2.py
│       │   ├── tasks/
│       │   └── vars/
│       ├── env_python/
│       │   ├── tasks/
│       │   └── vars/
│       └── fakeshell_v2/
│           ├── files/
│           │   ├── fakeshell.py
│           │   └── fakeshell_easy.py
│           ├── handlers/
│           └── tasks/
│
├── inspectDataset/                     # Analisi e pulizia dataset Cowrie
│   ├── analyze_and_clean.py
│   ├── download_zenodo.py
│   └── merge_cowrie_datasets.py
│
├── prompting/                          # Motore predittivo LLM
│   ├── core_rag.py
│   ├── core_topk.py
│   ├── evaluate_gemini_rag.py
│   ├── evaluate_gemini_topk.py
│   ├── evaluate_ollama_rag.py
│   ├── evaluate_ollama_topk.py
│   └── utils.py
│
├── requirements.txt
├── .gitignore
└── README.md

```

⸻
---
## 🧭 Workflow del progetto (script principali)

| Step | Script / File                                                | Input                               | Output                                      | Descrizione |
|------|--------------------------------------------------------------|-------------------------------------|---------------------------------------------|-------------|
| 1️⃣  | `inspectDataset/download_zenodo.py`                          | —                                   | `data/*.tar.gz`, `data/*.json`              | Scarica automaticamente i dataset Cowrie da Zenodo e li salva nella cartella dati locale. |
| 2️⃣  | `inspectDataset/analyze_and_clean.py`                        | `data/*.json`                       | `*_RAW.jsonl`, `*_CLEAN.jsonl`, statistiche | Analizza i log Cowrie, normalizza i comandi, pulisce rumore/duplicati e produce versioni RAW/CLEAN in JSONL. |
| 3️⃣  | `inspectDataset/merge_cowrie_datasets.py`                    | `*_CLEAN.jsonl`                     | `cowrie_ALL_*.jsonl`, `cowrie_TRAIN/TEST`   | Unisce più file puliti, crea un dataset unico e lo split train/test per gli esperimenti. |
| 4️⃣  | `prompting/core_rag.py`                                      | `cowrie_TRAIN.jsonl`, `chroma_storage/` | `chroma_storage/*`                          | Costruisce e interroga il database vettoriale ChromaDB (embedding + retrieval) per il RAG. |
| 5️⃣  | `prompting/core_topk.py`                                     | Sessioni JSONL                      | —                                           | Motore generico di predizione Top-k (senza RAG), riusato dai vari script di valutazione. |
| 6️⃣  | `prompting/evaluate_gemini_topk.py`                          | `cowrie_TEST.jsonl`                | `output/gemini_topk_results.jsonl`          | Valuta l’API Gemini in modalità Top-k, misurando Top-1/Top-5 sulle sessioni di test. |
| 7️⃣  | `prompting/evaluate_gemini_rag.py`                           | `cowrie_TEST.jsonl`, `chroma_storage/` | `output/gemini_rag_results.jsonl`       | Valuta Gemini integrato con RAG (ChromaDB), usando contesto + retrieval per predire il prossimo comando. |
| 8️⃣  | `prompting/evaluate_ollama_topk.py`                          | `cowrie_TEST.jsonl`                | `output/ollama_topk_results.jsonl`          | Valuta modelli locali (es. CodeLlama via Ollama) in modalità Top-k senza RAG. |
| 9️⃣  | `prompting/evaluate_ollama_rag.py`                           | `cowrie_TEST.jsonl`, `chroma_storage/` | `output/ollama_rag_results.jsonl`       | Valuta modelli locali con RAG (vector search + LLM) sulle stesse sessioni di test. |
| 🔟  | `Honeypot/Vagrantfile` + `Honeypot/playbook.yml`              | —                                   | VM di test configurata                      | Crea l’ambiente honeypot con Vagrant + Ansible (rete, pacchetti, utenti, Python, log, ecc.). |
| 1️⃣1️⃣ | `Honeypot/roles/fakeshell_v2/files/fakeshell.py`             | Input interattivo SSH nella VM      | `/var/log/fakeshell.json`                   | Fake shell avanzata: esegue comandi reali, mostra prompt realistico e logga ogni comando in formato JSONL. |
| 1️⃣2️⃣ | `Honeypot/roles/defender/files/defender2.py`                 | `/var/log/fakeshell.json`, ChromaDB | File di deception nel FS della VM           | Versione deployabile del Defender: segue il log, usa RAG+Gemini per predire i prossimi comandi e crea artefatti di deception. |
| 1️⃣3️⃣ | `deception/main.py` + `deception/ssh_server.py` + `session_handler.py` | Connessioni SSH reali               | Sessioni honeypot instradate verso il “brain” | Avvia il server SSH honeypot, accetta connessioni, gestisce le sessioni e inoltra i comandi al motore di deception. |
| 1️⃣4️⃣ | `deception/defender.py`                                      | Log honeypot (es. `fakeshell.json`), ChromaDB, LLM | Artefatti reali + log difese      | Defender runtime principale: legge i comandi in tempo reale, predice i prossimi passi con RAG+LLM e crea file/configurazioni esca. |
| 1️⃣5️⃣ | `deception/brain.py`                                         | Stato sessioni + log + predizioni   | Decisioni di deception / strategie           | Coordina a livello alto la strategia di deception (scenari, livelli di ingaggio, tipo di artefatti da generare). |
| 1️⃣6️⃣ | `deception/config.py`                                        | —                                   | Parametri di configurazione condivisi        | Centralizza porte, path, chiavi API, location del log, del DB vettoriale e degli scenari di deception. |
---


## 🧠 Note metodologiche

- I modelli lavorano meglio con **prompt compatti** e **in inglese**, come quelli costruiti in  
  `prompting/core_topk.py` e `prompting/core_rag.py`.

- Le predizioni vanno sempre **pulite e normalizzate**:  
  usa le funzioni di parsing e confronto in `prompting/utils.py`  
  (es. normalizzazione comandi, split per riga, gestione spazi).

- È utile testare diversi valori di **context length** (`CONTEXT_LEN`), in particolare con:
  - `prompting/evaluate_gemini_topk.py`
  - `prompting/evaluate_gemini_rag.py`
  - `prompting/evaluate_ollama_topk.py`
  - `prompting/evaluate_ollama_rag.py`
  - e nel runtime del defender (`deception/defender.py`), dove `CONTEXT_LEN` controlla quanto “passato” vede il modello.

- Per valutare correttamente i modelli conviene combinare:
  - **Exact Match** (già calcolato negli script di valutazione)
  - **Confronto normalizzato**, usando le utility di `prompting/utils.py`
    per ridurre l’effetto di differenze minori (spazi, quote, ecc.).

- Quando usi API esterne come **Gemini** (`evaluate_gemini_*.py`, `deception/defender.py`):
  - tieni conto di **rate limit** e possibili errori temporanei;
  - mantieni una logica di retry/sleep leggera, così da non bloccare gli esperimenti o il defender.

- Per esperimenti su larga scala è preferibile usare modelli locali via **Ollama**:
  - `prompting/evaluate_ollama_topk.py`
  - `prompting/evaluate_ollama_rag.py`  
  sono pensati per girare a lungo, con loop su centinaia/migliaia di sessioni.

- Usa sempre dataset **puliti e coerenti**, generati dalla pipeline:
  - `inspectDataset/download_zenodo.py` → download dei log Cowrie
  - `inspectDataset/analyze_and_clean.py` → pulizia, normalizzazione e statistiche
  - `inspectDataset/merge_cowrie_datasets.py` → merge e split train/test  
  in modo da ridurre rumore, comandi rari inutili e formati incoerenti.

- Per il **RAG**:
  - indicizza una sola volta in `chroma_storage/` usando la logica di `prompting/core_rag.py`;
  - riutilizza lo stesso DB vettoriale sia negli script di valutazione (`evaluate_*_rag.py`)  
    sia nel defender (`deception/defender.py`) tramite `VectorContextRetriever`;
  - evita di ricreare la collection a ogni esecuzione: il retriever è già pensato per lavorare su un DB esistente.
---

## 🔧 Possibili estensioni future

- Addestrare un modello locale tramite **fine-tuning** sui dataset puliti generati da  
  `inspectDataset/analyze_and_clean.py` e `inspectDataset/merge_cowrie_datasets.py`  
  (esportando le sessioni in formato input→next-command per supervised prediction).

- Estendere il set di metriche nelle valutazioni di:
  - `prompting/evaluate_gemini_topk.py`
  - `prompting/evaluate_gemini_rag.py`
  - `prompting/evaluate_ollama_topk.py`
  - `prompting/evaluate_ollama_rag.py`  
  includendo, oltre alla Top-k Accuracy:
  - **Recall@k**
  - distribuzione di confidenza / ranking dei candidati (es. punteggi normalizzati).

- Integrare in modo ancora più stretto il motore predittivo nel flusso dell’honeypot:
  - richiamare la logica di `prompting/core_topk.py` o `prompting/core_rag.py`  
    direttamente da `deception/session_handler.py` o `deception/ssh_server.py`;
  - orchestrare le risposte di deception tramite `deception/brain.py` e `deception/defender.py`
    per adattare gli artefatti al profilo dell’attaccante.

- Usare `prompting/core_rag.py` insieme al DB in `chroma_storage/` per costruire  
  un **honeypot con memoria storica**:
  - aggiornare periodicamente ChromaDB con nuove sessioni acquisite dall’ambiente Vagrant (`Honeypot/`);
  - permettere al defender (`deception/defender.py`) di sfruttare anche gli attacchi più recenti.

- Aggiungere una pipeline di **Command Semantics Classification** nel motore di prompting:
  - estendere `prompting/utils.py` con etichette di classe (ricognizione, lateral movement, credential harvesting, persistence, ecc.);
  - usare queste etichette in `deception/brain.py` per scegliere strategie di deception diverse per ogni tipologia di comando.

- Costruire dashboard real-time a partire dai log JSONL prodotti da:
  - honeypot fake shell (`/var/log/fakeshell.json`, generato da `fakeshell.py` / `fakeshell_easy.py` in `Honeypot/roles/fakeshell_v2/files/`);
  - output del defender (`output_deception/runtime/*.json` gestiti da `deception/defender.py`);
  - risultati sperimentali in JSONL generati dagli script di valutazione nella cartella `prompting/`.  
  Questi possono essere visualizzati con stack tipo ELK/Grafana.

- Estendere il dataset includendo altri sorgenti pubblici (es. nuovi dump Cowrie o honeypot simili)  
  e normalizzarli tramite:
  - `inspectDataset/download_zenodo.py` (per download automatici),
  - `inspectDataset/analyze_and_clean.py`,
  - `inspectDataset/merge_cowrie_datasets.py`,  
  mantenendo un formato uniforme per addestramento, RAG e valutazione.
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
