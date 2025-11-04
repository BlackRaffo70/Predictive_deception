<img width="1024" height="233" alt="image" src="https://github.com/user-attachments/assets/e210dcce-57f2-4470-a895-780896dbe45f" />

# 🍯 Predictive Deception — LLM-based Command Anticipation in SSH Honeypots

---

## 🎯 Obiettivo del progetto

Tradizionalmente, gli honeypot reagiscono ai comandi malevoli **dopo** la loro esecuzione.  
Questo progetto esplora un approccio innovativo: **Predictive Deception**, dove un **LLM (Large Language Model)** analizza in tempo reale la sequenza dei comandi inviati da un attaccante per **predire il prossimo comando probabile**.

Questo consente di:
- 🪤 Pre-posizionare file o artefatti falsi prima che l’attaccante li richieda.  
- 🧠 Attivare canary tokens o logging avanzato al momento dell’accesso.  
- 🕵️‍♂️ Aumentare l’engagement dell’attaccante e migliorare la qualità dell’intelligence raccolta.

---

## 📦 Contenuto tipico del progetto

**requirements.txt:**
```bash
requests
tqdm
difflib
argparse
```

⸻

## 📁 Struttura del repository

Predictive_deception/
│
├── analyze_cowrie_dataset.py         → Analizza dataset Cowrie e crea sessioni
├── build_predictive_pairs.py         → Crea coppie (context → next)
├── evaluate_ollama.py                → Valutazione modelli locali via Ollama
├── evaluate_LLM_OpenRouter.py        → Valutazione modelli via API OpenRouter
├── inspect_cowrie_json.py            → Ispeziona dataset grezzo
│
├── data/
│   └── cowrie_2020-02-29.json        → Dataset originale Cowrie
│
├── output/
│   ├── cowrie_sessions.jsonl         → Sessioni SSH estratte
│   ├── predictive_pairs.jsonl        → Coppie (context → next)
│   ├── ollama_results.jsonl          → Risultati modelli locali
│   ├── results.jsonl                 → Risultati modelli API
│   └── summary.json                  → Metriche riassuntive
│
├── requirements.txt
└── README.md


⸻
---

## 🧭 Workflow del progetto

| Step | Script | Input | Output | Descrizione |
|------|--------|--------|---------|-------------|
| 1️⃣ | `inspect_cowrie_json.py` | `data/cowrie_2020-02-29.json` | — | Ispeziona il file raw per verificare la struttura |
| 2️⃣ | `analyze_cowrie_dataset.py` | Cowrie JSON | `output/cowrie_sessions.jsonl` | Estrae eventi e comandi per sessione |
| 3️⃣ | `build_predictive_pairs.py` | `output/cowrie_sessions.jsonl` | `output/predictive_pairs.jsonl` | Genera coppie sliding-window *(context → next)* |
| 4️⃣ | `evaluate_ollama.py` | `output/predictive_pairs.jsonl` | `output/ollama_results.jsonl` | Valuta modelli locali via Ollama |
| 5️⃣ | `evaluate_LLM_OpenRouter.py` | `output/predictive_pairs.jsonl` | `output/results.jsonl`, `output/summary.json` | Valuta modelli cloud via API OpenRouter |



⸻

## 🚀 **Esempi di utilizzo rapido**

1️⃣ Analisi dataset Cowrie:
```bash
python analyze_cowrie_dataset.py --input data/cowrie_2020-02-29.json --output output/cowrie
```
2️⃣ Generare coppie di predizione (sliding window):
```bash
python build_predictive_pairs.py --input output/cowrie_sessions.jsonl --output output/predictive_pairs.jsonl --context-len 1
```
3️⃣ Valutare modello locale con Ollama:

```bash
ollama pull mistral:7b-instruct-q4_0
ollama serve &
python evaluate_ollama.py --data output/predictive_pairs.jsonl --model mistral:7b-instruct-q4_0 --n 200 --temp 0.1
```
4️⃣ Valutare modello via OpenRouter (API):

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
| <a href="https://github.com/BlackRaffo70"><img src="https://github.com/BlackRaffo70.png" width="110" alt="avatar Raffaele Neri"></a> | <a href="https://github.com/melottimatteo"><img src="https://github.com/melottimatteo.png" width="110" alt="avatar Matteo Melotti"></a> | <a href="https://github.com/enricoborsetti"><img src="https://github.com/enricoborsetti.png" width="110" alt="avatar Enrico Borsetti"></a> |
| **Raffaele Neri**<br/>[@BlackRaffo70](https://github.com/BlackRaffo70) | **Matteo Melotti**<br/>[@melottimatteo](https://github.com/melottimatteo) | **Enrico Borsetti**<br/>[@enricoborsetti](https://github.com/kikeeeee) |

---

📘 *Progetto di ricerca:*  
**🍯 Predictive Deception – LLM-based Command Anticipation in SSH Honeypots**  
Università di Bologna – Corso di Laurea Magistrale in Ingegneria Informatica  

👨‍🏫 *Docente referente:* **Prof. Michele Colajanni**
