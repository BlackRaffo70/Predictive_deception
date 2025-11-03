import json
import random
import openai
from difflib import SequenceMatcher
from tqdm import tqdm

# === CONFIG ===
MODEL = "gpt-4o-mini"   # puoi usare gpt-4o, gpt-4-turbo, ecc.
N_SAMPLES = 100          # numero di esempi da testare (riduci per debug)
DATA_FILE = "output/predictive_pairs.jsonl"
RESULTS_FILE = "output/llm_predictions.jsonl"

openai.api_key = "INSERISCI_LA_TUA_API_KEY_QUI"  # 🔐 metti la tua chiave OpenAI

# === FUNZIONI ===
def similarity(a, b):
    return SequenceMatcher(None, a.strip(), b.strip()).ratio()

def make_prompt(context):
    joined = "\n".join(context)
    return f"""Sei un analizzatore di attacchi SSH.
Ti fornisco i comandi che un attaccante ha eseguito finora.
Predici il prossimo comando che probabilmente eseguirà.

Comandi finora:
{joined}

Rispondi con un solo comando, senza spiegazioni.
"""

# === CARICA IL DATASET ===
pairs = []
with open(DATA_FILE, "r", encoding="utf-8") as f:
    for line in f:
        pairs.append(json.loads(line))

random.shuffle(pairs)
pairs = pairs[:N_SAMPLES]

print(f"🔍 Test su {len(pairs)} esempi usando {MODEL}")

results = []

# === LOOP DI VALUTAZIONE ===
for p in tqdm(pairs):
    context, expected = p["context"], p["next"]
    prompt = make_prompt(context)

    try:
        completion = openai.ChatCompletion.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        pred = completion.choices[0].message["content"].strip()
    except Exception as e:
        print("Errore:", e)
        continue

    sim = similarity(pred, expected)
    match = int(pred == expected)
    results.append({"context": context, "expected": expected, "predicted": pred, "similarity": sim, "match": match})

# === SALVA RISULTATI ===
with open(RESULTS_FILE, "w", encoding="utf-8") as out:
    for r in results:
        out.write(json.dumps(r) + "\n")

# === METRICHE FINALI ===
exact = sum(r["match"] for r in results) / len(results)
avg_sim = sum(r["similarity"] for r in results) / len(results)

print("\n📊 RISULTATI FINALI")
print("--------------------")
print(f"Modello: {MODEL}")
print(f"Esempi testati: {len(results)}")
print(f"Accuracy esatta: {exact*100:.2f}%")
print(f"Similarità media: {avg_sim*100:.2f}%")
print(f"💾 Risultati dettagliati salvati in: {RESULTS_FILE}")