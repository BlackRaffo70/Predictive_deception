# -------------------------
# IMPORT SECTION
# -------------------------

import os
import subprocess
import requests
from tqdm import tqdm
import shutil

# -------------------------
# CONFIGURATION and UTILS
# -------------------------

RECORD_ID = "3687527"                                               # record del dataset Zenodo considerato
DEVICE_PATH = "/media/matteo/BNKRBL"                                # path del dispositivo di archiviazione esterno
OUTPUT_DIR = f"{DEVICE_PATH}/DatasetZenodo"                          # cartella dove vengono scaricati e decompressi i file   
os.makedirs(OUTPUT_DIR, exist_ok=True)

def to_gb(bytes_value): return round(bytes_value / (1024**3), 3)    # Funzione per convertire bytes in GB

# -------------------------
# DOWNLOADING DATASET ZENODO
# -------------------------

# Ottenimento della lista di file Cyberlab all'interno del dataset Zenodo
api_url = f"https://zenodo.org/api/records/{RECORD_ID}"
response = requests.get(api_url)
response.raise_for_status()
meta_record = response.json()

files = meta_record.get("files", [])
gz_files = [f for f in files if f.get("key", "").endswith(".gz")]

print(f"Trovati {len(gz_files)} file .gz\n")

# Calcolo dimensione totale dei file .gz da scaricare
total_gz_size = 0
for file in gz_files:
    total_gz_size += file.get("size")

print(f"Dimensione totale dei file da .gz scaricare: {to_gb(total_gz_size)} GB")

# Controllo dello spazio disponibile sul dispositivo di archiviazione esterno specificato da DEVICE_PATH
free_space_device = shutil.disk_usage(OUTPUT_DIR).free

print(f"Spazio libero sul dispositivo di archiviazione specificato (path = {DEVICE_PATH}): {to_gb(free_space_device)} GB")

if free_space_device < total_gz_size:
    print("\n❌ ERRORE: Spazio insufficiente nel dispositivo {DEVICE_PATH}")
    print(f"Spazio necessario: {to_gb(total_gz_size)} GB")
    print(f"Spazio disponibile:   {to_gb(free_space_device)} GB")
    exit(1)

print("\n✔ Spazio sufficiente. Inizio download e decompressione...\n")

# Download dei file .gz e decompressione
total_downloaded_bytes = 0
total_gz_downloaded = 0
total_gz_decompressed = 0
total_json_bytes = 0

for file in tqdm(gz_files, desc="Processo file", unit="file"):
    fname = file["key"]
    download_url = file.get("links", {}).get("self")

    path_file = os.path.join(OUTPUT_DIR, fname)

    file_size = file.get("size", 0)

    # Fase di download: prima si controlla che il file non sia già stato scaricato e successivamente lo si scarica nella cartella specificata da OUTPUT_DIR
    if not os.path.exists(path_file):
        resp = requests.get(download_url, stream=True)
        resp.raise_for_status()

        chunk_size = 8192

        with open(path_file, "wb") as out, tqdm(
            total=file_size,
            unit="B",
            unit_scale=True,
            desc=f"Download {fname}",
            leave=False
        ) as pbar:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                out.write(chunk)
                pbar.update(len(chunk))

        total_downloaded_bytes += file_size
        total_gz_downloaded+=1
    else:
        tqdm.write(f"[SKIP] Già scaricato: {fname}")

    # Fase di decompressione: prima si esegue il comando, se il file esiste ancora, vuol dire che il file è corrotto, di conseguenza si scarta
    try:
        tqdm.write(f"[WAIT] Decompressione del file {path_file}")
        subprocess.run(["gzip", "-df", path_file], check=True)
        path_json = f"{path_file[:-3]}"
        # aggiungi dimensione del json
        total_json_bytes += os.path.getsize(path_json)
        total_gz_decompressed += 1
        tqdm.write(f"[OK] {os.path.basename(path_json)} generato e .gz eliminato.")

    except subprocess.CalledProcessError:
        tqdm.write(f"[ERRORE] File corrotto: {fname} (saltato)")

print("\n\n===== RISULTATI FINALI =====")
print(f"Totale .gz scaricati:               {total_gz_downloaded}")
print(f"Dimensione .gz scaricati:           {to_gb(total_downloaded_bytes)} GB")
print(f"Totale .json decompressi:           {total_gz_decompressed}")
print(f"Dimensione .json decompressi:       {to_gb(total_json_bytes)} GB")
print("\n✔ Operazione completata con successo! 🚀")
