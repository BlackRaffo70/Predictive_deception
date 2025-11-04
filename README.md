# 🧠 Predictive Deception — LLM-based Command Anticipation in SSH Honeypots

> **Università di Bologna – Ingegneria Informatica (Magistrale)**  
> *Progetto di ricerca a cura di:*  
> [Raffaele Neri](mailto:raffaele.neri2@studio.unibo.it) · [Matteo Melotti](mailto:matteo.melotti5@studio.unibo.it) · [Enrico Borsetti](mailto:enrico.borsetti@studio.unibo.it)  
> **Docente referente:** Prof. Michele Colajanni  
> **Titolo:** Predictive Deception — LLM-based command anticipation in SSH honeypots

---

## 📘 Introduzione

Tradizionalmente, gli honeypot agiscono in modo **reattivo**: rispondono ai comandi dopo che l’attaccante li ha eseguiti.  
Questo progetto esplora un paradigma **proattivo**, denominato **Predictive Deception**, dove un modello linguistico (LLM) analizza la sequenza dei comandi di un attacco SSH in corso e **predice il prossimo comando**.

In base alla predizione, il sistema può **preparare in anticipo artefatti ingannevoli** (es. file falsi, canary tokens), rendendo l’ambiente più interattivo e migliorando la detection.

---

## 🎯 Obiettivi

- Valutare se un **LLM** (locale o cloud) può predire con accuratezza il prossimo comando in una sessione SSH malevola.  
- Confrontare prestazioni tra:
  - Modelli **locali (Ollama)** → *es. Mistral, Gemma, Llama*  
  - Modelli **cloud (API OpenRouter)** → *es. DeepSeek, Qwen, Llama 3.3, Mistral-small-24B*  
- Analizzare metriche di **accuratezza, similarità** e **robustezza semantica** della predizione.

---

## ⚙️ Requisiti

### 🧩 Software
- Python ≥ 3.9  
- `pip install -r requirements.txt`

### 📦 Librerie principali
```bash
requests
tqdm
difflib
argparse
