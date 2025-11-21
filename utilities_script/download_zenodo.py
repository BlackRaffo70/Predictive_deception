# -------------------------
# INTRODUCTION
# -------------------------

"""
- MODALITÀ:
    Lo script serve per scaricare un numero di file specificato (in caso contrario tutti) del record {RECORD_ID} del
    dataset Zenodo. 

- COMANDO PER L'ESECUZIONE:

    - Intero dataset su dispositivo esterno:

        python utilities_script/download_zenodo.py --dst ext --dst-path /media/matteo/BNKRBL/DatasetZenodo
    
    - Qualche file random in locale

        python utilities_script/download_zenodo.py --dst local --dst-path data --n 1 

    le flag sono:
    - dst = può assumere solo due valori: local, ext. Serve per specificare il dispositivo di archivizione dove verranno scaricati i file
    - dst-path = specifica la cartella dove verranno salvati i file .json
    - n = specifica il numero di file da scaricare. Se non viene utilizzata questa flag, viene scaricato tutto il dataset (in questo caso meglio utilizzare --dst ext)
    
"""

# -------------------------
# IMPORT SECTION
# -------------------------

import argparse
import os
import random
import subprocess
import requests
from tqdm import tqdm
import shutil

# -------------------------
# CONFIGURATION and UTILS
# -------------------------

RECORD_ID = "3687527"                                               # record del dataset Zenodo considerato
TMP_ROOT_PATH = os.path.expanduser("~/Downloads")  

def to_gb(bytes_value): return round(bytes_value / (1024**3), 3)    # Funzione per convertire bytes in GB

# -------------------------
# DOWNLOADING DATASET ZENODO
# -------------------------

def downloading_and_decompression(args):  

    os.makedirs(args.dst_path, exist_ok=True)
    os.makedirs(TMP_ROOT_PATH, exist_ok=True)

    # Ottenimento della lista di file Cyberlab all'interno del dataset Zenodo
    api_url = f"https://zenodo.org/api/records/{RECORD_ID}"
    response = requests.get(api_url)
    response.raise_for_status()
    meta_record = response.json()

    files = meta_record.get("files", [])
    gz_files = [f for f in files if f.get("key", "").endswith(".gz")]

    # Se l'utente ha specificato n>0, prende una selezione random di n file, altrimenti tutti
    if args.n and args.n > 0:
        numero_file = min(args.n, len(gz_files))
        selected_files = random.sample(gz_files, numero_file)
        print(f"Trovati {len(gz_files)} file .gz — selezionati {numero_file} file (random).")
    else:
        selected_files = gz_files
        print(f"Trovati {len(gz_files)} file .gz — verranno scaricati tutti.")

    # Calcolo dimensione totale dei file .gz da scaricare
    total_gz_size = 0
    for file in selected_files:
        total_gz_size += file.get("size")

    print(f"Dimensione totale dei file da .gz scaricare: {to_gb(total_gz_size)} GB")

    # Controllo dello spazio disponibile in locale/dispositivo di archiviazione
    free_space_device = shutil.disk_usage(args.dst_path).free
    if args.dst == "local":
        print(f"Spazio libero in locale: {to_gb(free_space_device)} GB")
    else:
        print(f"Spazio libero sul dispositivo di archiviazione esterno specificato: {to_gb(free_space_device)} GB")

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

    for file in tqdm(selected_files, desc="Processo file", unit="file"):
        fname = file["key"]
        download_url = file.get("links", {}).get("self")

        # Controllo unico per download dispositivo esterno -> passaggio da cartella Downloads in locale per decompressione più rapida
        if args.dst == "ext":
            path_file = os.path.join(TMP_ROOT_PATH, fname) 
            path_json = f"{path_file[:-3]}"
            perm_path_file = os.path.join(args.dst_path, fname[:-3])
        else: 
            path_file = os.path.join(args.dst_path, fname)
            path_json = f"{path_file[:-3]}" 
            perm_path_file = path_json
    
        file_size = file.get("size", 0)
        # Prima controllo se il file non è già stato scaricato e decompresso
        if not os.path.exists(perm_path_file):
            # Prima di eseguire il download, controllo che il file .gz non sia già stato scaricato e successivamente lo si scarica
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

                if args.dst == "ext":
                    tqdm.write(f"[MOVE] Spostamento del file {path_json} in {perm_path_file}")
                    shutil.move(path_json, perm_path_file)
            
                # aggiungi dimensione del json
                total_json_bytes += os.path.getsize(perm_path_file)
                total_gz_decompressed += 1
                tqdm.write(f"[OK] {os.path.basename(perm_path_file)} generato e .gz eliminato.")

            except subprocess.CalledProcessError:
                tqdm.write(f"[ERRORE] File corrotto: {fname} (saltato)")
        else:
            tqdm.write(f"[SKIP] Già scaricato nella destinazione: {perm_path_file}")
            
    # Stampe finali
    print("\n\n===== RISULTATI FINALI =====")
    print(f"Totale .gz scaricati:               {total_gz_downloaded}")
    print(f"Dimensione .gz scaricati:           {to_gb(total_downloaded_bytes)} GB")
    print(f"Totale .json decompressi:           {total_gz_decompressed}")
    print(f"Dimensione .json decompressi:       {to_gb(total_json_bytes)} GB")
    print("\n✔ Operazione completata con successo! 🚀")

def main():
    parser = argparse.ArgumentParser(description="Downloading file form Zenodo Dataset")
    parser.add_argument("--dst", required=True, choices=["local", "ext"], help="Per sapere se i file vengono scaricati in locale o su supporto esterno")
    parser.add_argument("--dst-path", required=True, help="Path della cartella dove verranno salvati tutti i file .json decompressi")
    parser.add_argument("--n", type=int, default=0, help="Max test (0=tutti)")

    args = parser.parse_args()
    downloading_and_decompression(args)

if __name__ == "__main__":
    main()
