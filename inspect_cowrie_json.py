import json

file_path = "data/cowrie_2020-02-29.json"

with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

print("=== Livello 1 ===")
print("Tipo:", type(data))
print("Lunghezza lista:", len(data))

first = data[0]
print("\n=== Livello 2 ===")
print("Tipo primo elemento:", type(first))
if isinstance(first, dict):
    print("Chiavi del primo elemento:", list(first.keys()))

    first_key = list(first.keys())[0]
    print("Prima chiave:", first_key)

    value = first[first_key]
    print("Tipo del valore:", type(value))
    if isinstance(value, list):
        print("Numero eventi nella sessione:", len(value))
        print("\n=== Livello 3 ===")
        print("Chiavi del primo evento:", list(value[0].keys()))
        print("\nEsempio evento:")
        for k, v in list(value[0].items())[:10]:
            print(f"  {k}: {v}")

