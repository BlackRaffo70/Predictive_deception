<img width="1024" height="233" alt="image" src="https://github.com/user-attachments/assets/e210dcce-57f2-4470-a895-780896dbe45f" />

# 🍯 Predictive Deception — LLM-based Command Anticipation in SSH Honeypots

---

## 🎯 Obiettivo del progetto — *Predictive Deception per Honeypot*

Gli honeypot tradizionali osservano e registrano ciò che l’attaccante fa **solo dopo** l’esecuzione di un comando.  
Questo progetto introduce un nuovo paradigma: sfruttare un **LLM** per trasformare l’honeypot da sistema passivo a **sistema predittivo e adattivo**.

---

## 🚀 Idea chiave  
Un modello di linguaggio (CodeLlama, Llama 3, Gemini, Mistral) analizza in tempo reale la sequenza dei comandi dell’attaccante e **predice il prossimo comando** con elevata accuratezza — *prima che venga digitato*.

Questa predizione permette al sistema di costruire sul filesystem una *realtà manipolata* che l’attaccante non deve essere in grado di distinguere da quella autentica.

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
- branch B → file Y  
- …

Quando l’attaccante esegue realmente uno dei comandi predetti, il sistema:

- mantiene **solo la branch corretta**  
- elimina le altre 4 con cleanup automatico  
- conserva coerenza assoluta nel filesystem

Questo crea la sensazione di un sistema vivo e coerente, difficilmente roconoscibile.

---

### 3️⃣ *Deception adattiva basata su RAG*  
L'LLM non predice "a caso".  
Combina:

- history della sessione  
- sequenze di attacchi precedenti conservate via **ChromaDB RAG**

---

## 🔐 Perché è rivoluzionario

- 🪤 **Deception mirata e contestuale**  
  Non è la solita deception statica: il sistema modifica l’ambiente *in tempo reale* in base al comportamento.

- 🧠 **Ingaggio dell’attaccante aumentato**  
  L’ambiente sembra perfettamente reale, con struttura coerente e reattiva.

- 🎛 **Riduzione dei falsi positivi**  
  La predizione contestuale evita di generare deception non rilevanti.

---

## 🧩 In sintesi  
Il progetto trasforma l’honeypot in un sistema **proattivo**, capace non solo di osservare ma di:

- **anticipare** l’attaccante  
- **modellare** l’ambiente in base al suo comportamento  
- **manipolare** la percezione dell’host
- 
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
│       │   │   └── defender.py
│       │   ├── tasks/
│       │   └── vars/
│       ├── env_python/
│       │   ├── tasks/
│       │   └── vars/
│       └── fakeshell/
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
## 🧭 Workflow del progetto (script principali)

| Step | Script / File                                                | Descrizione |
|------|--------------------------------------------------------------|-------------|
| 1️⃣  | `inspectDataset/download_zenodo.py`                          | Scarica automaticamente i dataset Cowrie da Zenodo e li salva nella cartella `data/` per l’analisi successiva. |
| 2️⃣  | `inspectDataset/analyze_and_clean.py`                        | Analizza i log Cowrie, normalizza i comandi, rimuove rumore/duplicati e genera versioni RAW/CLEAN in formato JSONL con statistiche. |
| 3️⃣  | `inspectDataset/merge_cowrie_datasets.py`                    | Unisce più file puliti in un unico dataset e produce lo split train/test (es. `cowrie_TRAIN.jsonl`, `cowrie_TEST.jsonl`) per gli esperimenti. |
| 4️⃣  | `prompting/core_rag.py`                                      | Implementa il motore RAG: crea/usa il database vettoriale in `chroma_storage/` e fornisce funzioni di retrieval contestuale per le predizioni. |
| 5️⃣  | `prompting/core_topk.py`                                     | Fornisce la logica generica di predizione Top-k (senza RAG), riutilizzabile da Gemini e modelli locali. |
| 6️⃣  | `prompting/evaluate_gemini_topk.py`                          | Valuta il modello Gemini in modalità Top-k pura, calcolando accuratezza Top-1/Top-5 sulle sessioni di test. |
| 7️⃣  | `prompting/evaluate_gemini_rag.py`                           | Valuta Gemini integrato con RAG (ChromaDB), usando contesto + retrieval per migliorare la predizione del prossimo comando. |
| 8️⃣  | `prompting/evaluate_ollama_topk.py`                          | Esegue test su modelli locali (es. CodeLlama via Ollama) in modalità Top-k senza RAG, per confrontarli con Gemini. |
| 9️⃣  | `prompting/evaluate_ollama_rag.py`                           | Valuta modelli locali integrati con RAG, combinando vector search + LLM per la next-command prediction. |
| 🔟  | `Honeypot/Vagrantfile` + `Honeypot/playbook.yml`              | Definisce e configura l’ambiente honeypot tramite Vagrant + Ansible (VM, utenti, Python, log, ruoli Ansible, ecc.). |
| 1️⃣1️⃣ | `Honeypot/roles/fakeshell/files/fakeshell.py`             | Implementa una fake shell avanzata nella VM: prompt realistico, esecuzione comandi e logging di ogni comando in `/var/log/fakeshell.json`. |
| 1️⃣2️⃣ | `Honeypot/roles/defender/files/defender.py`                 | Versione deployabile del Defender: segue il log della fake shell, usa RAG+Gemini per predire i prossimi comandi e crea artefatti di deception nel filesystem della VM. |
| 1️⃣3️⃣ | `deception/main.py` + `deception/ssh_server.py` + `deception/session_handler.py` | Avvia il server SSH honeypot, utile se si vuole testare l'ambiente in locale senza VM. |
| 1️⃣4️⃣ | `deception/defender.py`                                      | Defender runtime principale: legge i comandi in tempo reale, interroga RAG+LLM e genera file/configurazioni esca in base alle predizioni. |
| 1️⃣5️⃣ | `deception/brain.py`                                         | Coordina l’intelligenza di alto livello della deception (strategie, scenari, logica su quando/come creare artefatti). |
| 1️⃣6️⃣ | `deception/config.py`                                        | Centralizza configurazioni condivise: path del log, posizione del DB vettoriale, porte, chiavi API e selezione dello scenario di deception. |


## 🧠 Note metodologiche

- I modelli lavorano meglio con **prompt compatti** e **in inglese**, come quelli costruiti in  
  `prompting/core_topk.py` e `prompting/core_rag.py`.

- Le predizioni in alcuni casi vanno  **pulite e normalizzate**:  
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

## 🔮 Lavori futuri

### Fine-tuning specializzato dei modelli LLM
- Passare dall’uso zero-/few-shot a un **fine-tuning supervisionato** di un modello locale (es. CodeLlama via Ollama).
- Usare come dati:
  - sequenze di comandi dai log Cowrie (`TRAIN/TEST`);
  - log Vagrant (`fakeshell.json`);
  - sessioni da honeypot reali in produzione.
- Obiettivo: adattare il modello alla distribuzione reale dei comandi SSH, ridurre hallucination e migliorare la coerenza delle sequenze multi-step.  
  Gemini rimane il riferimento “cloud”, il CodeLlama fine-tunato il motore locale per la predizione *next-command*.

### Predizione multi-step e pianificazione della deception
- Estendere la predizione dal singolo comando Top-k a **brevi traiettorie di comandi** (2–5 step).
- Questo permette di:
  - pre-caricare catene di artefatti lungo possibili percorsi dell’attaccante (ricognizione → config → esfiltrazione);
  - stimare l’intenzione probabile (es. credential harvesting vs. lateral movement);
  - orchestrare strategie di deception a livello di **sessione**, non solo di singolo comando.
- Particolarmente utile contro script automatizzati e tool di brute forcing con sequenze deterministiche.

### Deception dinamica guidata dal modello
- Evolvere dalla creazione di pochi file isolati a una **deception dinamica** in cui il modello:
  - suggerisce insiemi coerenti di directory, log, chiavi e configurazioni fittizie;
  - contribuisce a simulare interi scenari di sistema (es. server applicativo con database “fantasma”);
  - adatta la profondità dell’ingaggio in base al profilo dell’attaccante osservato.
- In questa visione, `brain.py` diventa un **orchestratore di scenari**, che combina:
  - predizioni LLM,
  - knowledge storico dal RAG,
  - policy di deception definite dall’analista.

### Apprendimento continuo dai log dell’honeypot
- Passare da un ChromaDB statico a un **RAG aggiornato continuamente**, in cui:
  - le nuove sessioni loggate da `fakeshell.py` e dal server SSH vengono periodicamente normalizzate e indicizzate;
  - il knowledge base si arricchisce con attacchi recenti, seguendo l’evoluzione delle tecniche offensive.
- Integrare una pipeline automatica per:
  - il retraining o fine-tuning incrementale del modello locale;
  - l’aggiornamento del RAG con i nuovi log.
- L’honeypot diventa così una sorgente continua di dati per migliorare il motore predittivo, non solo un consumatore di knowledge storico.

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
