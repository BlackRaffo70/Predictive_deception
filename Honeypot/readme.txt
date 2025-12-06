La VM utilizza 4 GB di RAM e un disco da 25GB (5 in più rispetto allo standard Vagrant). 
Queste impostazioni si riscontrano all'interno del Vagrantfile.
Il provisioning della macchina virtuale viene eseguito in modo automatico tramite l'esecuzione di task Ansible. Nonostante ciò,
sono presenti alcuni punti non gestiti direttamente dal provisioning:

- Role DB_vettoriale = in questo ruolo all'interno della cartella file, deve essere presente la cartella nominata chroma_storage_ctx5,
non presente direttamente all'interno del progetto in quanto troppo pesante (2GB)

- Role DB_vettoriale = nella cartella vars di questo role è necessario modificare la variabile gemini_api_key, inserendo la 
propria chiave gemini

- Aggiunta di memoria del disco fisso = come anticipato nell'introduzione, il disco della VM è da 25 GB, 5 GB in più rispetto
al disco creato da Vagrant durante la normale creazione della VM. Per rendere effettiva questa modifica sono necessari una serie di passaggi:

    - Prima di eseguire il provisioning della VM è necessario installare un plugin tramite comando:

        vagrant plugin install vagrant-disksize

    - La VM avrà un disco virtuale più grande, ma il sistema operativo al suo interno vedrà ancora la partizione con la vecchia dimensione. Lo spazio aggiuntivo sarà "non allocato".
    Per rendere utilizzabili i 5GB aggiuntivi, bisogna estendere il filesystem attraverso l'esecuzione di questi comandi:

        # Installa gli strumenti necessari se non ci sono
        sudo apt update && sudo apt install cloud-guest-utils -y

        # Estendi la partizione 1 del primo disco (sdX1, potrebbe anche essere vdX1)
        sudo growpart /dev/sda 1

        # Estendi il filesystem (per ext4, il più comune)
        sudo resize2fs /dev/sda1

        # Verifica lo spazio (dovresti vedere la nuova dimensione)
        df -h

- import di sentence-transformers = questo import deve essere realizzato all'interno del venv python creato durante il 
provisionin. Il task Ansible relativo a questo import fallisce a seguito del tempo impiegato per il download 
(triggera il timeout task Ansible). Di conseguenza è necessario omettere questo task, ma è necessario installare il 
pacchetto manualmente all'interno della vm tramite comandi:
    
    cd defender/
    source .venv/bin/activate
    pip install sentence-transformers