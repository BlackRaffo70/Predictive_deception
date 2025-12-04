La VM utilizza 4 gb di RAM e un disco da 25GB (5 in più rispetto allo standard Vagrant). Queste modifiche si riscontrano nel Vagrantfile.
Per quanto riguarda la memoria, per aggiungere i 5 GB in più è necessario:
- Da riga di comando eseguire:

    vagrant plugin install vagrant-disksize

- Aggiornare il provisioning della VM con comando:

    vagrant reload --provision

- Una volta terminato, loggare con:

    vagrant ssh

- La VM avrà un disco virtuale più grande, ma il sistema operativo al suo interno vedrà ancora la partizione con la vecchia dimensione. Lo spazio aggiuntivo sarà "non allocato".
  Per rendere utilizzabili i 5GB aggiuntivi, bisogna estendere il filesystem in questo modo:

    # Installa gli strumenti necessari se non ci sono
    sudo apt update && sudo apt install cloud-guest-utils -y

    # Estendi la partizione 1 del primo disco (sdX1, potrebbe anche essere vdX1)
    # Controlla prima con 'lsblk' qual è il nome corretto del tuo disco (es. sda o vda)
    # Esempio per sda1:
    sudo growpart /dev/sda 1

    # Estendi il filesystem (per ext4, il più comune)
    sudo resize2fs /dev/sda1

    # Verifica lo spazio (dovresti vedere la nuova dimensione)
    df -h
