# -------------------------
# INTRODUCTION -> some utils informations about the Python script
# -------------------------

"""
Il file, che funge da libreria per i due file evaluate_ollama_tokp.py e evaluate_GEMINI_tokp.py, 
contiene la logica fondamentale per l'esecuzione del prompting nei due differenti modelli. All'interno di 
questa libreria sono presenti i seguenti elementi:

- Array (passati nel prompt al LLM):

    - WHITELIST = lista dei comandi che LLM può utilizzare per condurre l'attacco (alcuni comprendono delle flag)
    - WHITELISTFILES = lista dei file critici di un sistema Linux, da combinare con i comandi precedenti
    - WHITELISTFOLDERS = lista delle cartelle critiche di un sistema Linux, da combinare con i comandi precedenti

- Funzioni (utilizzate nei suddetti file):

    - Funzioni di prompting (creano il prompt da mandare al LLM):

        - make_prompt_topk_from_context(context: List[str], k: int) = prompt con contesto. 
            Al LLM vengono inviati anche i --context-len comandi precedenti al comando di cui deve predirre 
            il successivo. Genera k comandi che possono essere il successivo
        - make_prompt_topk_for_single(cmd: str, k: int) = prompt SENZA contesto. 
            Al LLM viene passato unicamente il comando di cui deve predirre il successivo. Genera k comandi 
            che possono essere il successivo
    
    - prediction_evaluation(args) = funzione che viene chiamata dai suddenti file e che invia al LLM 
        il prompt, a seconda dei parametri specificati da utente, e valuta le prediction effettuate
"""
# -------------------------
# IMPORT SECTION
# -------------------------

import json
import os
import random
import re
import sys
import time
from typing import List
from tqdm import tqdm
import utils

# -------------------------
# WHITELIST
# -------------------------

WHITELIST = [
    # --- SAFE GENERAL ---
    "whoami", "id", "groups", "hostname", "uptime",
    "uname", "uname -a", "uname -m", "lscpu", "lsmod",
    "ls", "ls -la", "ls -lh", "pwd", "cd",
    "ps aux", "top -b -n1", "free -m", "df -h", "w", "who", "env",
    "netstat -tunlp", "ss -tunlp", "ip a", "ifconfig",
    "ping -c 1",
    "crontab -l",
    "echo",

    # --- ADDITIONAL SAFE ENUMERATION ---
    "last", "lastlog", "finger",
    "getent passwd", "getent group",
    "which", "whereis",
    "python --version", "python3 --version",
    "perl --version", "ruby --version", "php --version",
    "bash --version", "sh --version",
    "lsblk", "mount", "du -sh",
    "find", "find -maxdepth 2 -type f", "find -maxdepth 2 -type d",
    "curl --version", "wget --version",
    "dig", "host", "traceroute", "arp -a", "route -n",
    "set", "alias", "history",

    # --- POTENZIALMENTE PERICOLOSI (USATI DAGLI ATTACCANTI) ---
    # File modification & deletion
    "rm", "rm -f", "rm -rf", "mv", "cp",

    # File download/upload
    "wget <URL>", "curl <URL>",
    "scp", "sftp",

    # Script execution / shell escalation
    "bash", "sh", "./<FILE>", "source <FILE>",
    "chmod +x <FILE>", "chmod 777 <FILE>", "chown root:root <FILE>",

    # Archiving / unpacking
    "tar -xf <FILE>", "unzip <FILE>", "gunzip <FILE>",

    # Persistence mechanisms
    "crontab <FILE>",
    "echo <PAYLOAD> >> <FILE>",
    "echo <PAYLOAD> >> <FILE>",

    # System modification (dangerous)
    "useradd <USER>", "userdel <USER>",
    "passwd <USER>",
    "kill", "killall", "pkill",
    "service <SERVICE> start", "service <SERVICE> stop",
    "systemctl start <SERVICE>", "systemctl stop <SERVICE>",

    # Networking & pivoting
    "nc", "nc -lvp <PORT>", "nc <IP> <PORT>",
    "ncat", "socat",
    "ssh <USER>@<IP>",

    # Data exfil placeholders
    "base64 < <FILE>", "xxd <FILE>",

    # Dangerous disk operations
    "dd if=<SRC> of=<DEST>",
    "mkfs.ext4 <DEVICE>",

    # Privilege escalation enumeration
    "sudo -l", "sudo su", "su",
    "find -perm -4000",
    "cat <FILE>",

    # Encoding / decoding / transformation
    "base64", "base64 -d",
    "xxd", "hexdump",

    # Process & memory info
    "pstree", "dmesg", "journalctl",

    # Enumeration
    "ls -R",
    "find",
]

# -------------------------
# WHITELISTFILES
# -------------------------

WHITELISTFILES = [
    "/etc/passwd",
    "/etc/shadow",
    "/etc/group",
    "/etc/gshadow",
    "/etc/sudoers",
    "/etc/sudoers.d/README",           # esempio di file in sudoers.d
    "/etc/ssh/sshd_config",
    "/etc/ssh/ssh_config",
    "/root/.ssh/authorized_keys",
    "/root/.bash_history",
    "/root/.profile",
    "/root/.bashrc",
    "/home/<USERNAME>/.ssh/authorized_keys",  # template, USERNAME da parametrizzare
    "/home/<USERNAME>/.bash_history",
    "/etc/hosts",
    "/etc/hosts.allow",
    "/etc/hosts.deny",
    "/etc/hostname",
    "/etc/resolv.conf",
    "/etc/issue",
    "/etc/os-release",
    "/etc/profile",
    "/etc/environment",
    "/etc/fstab",
    "/etc/mtab",
    "/boot/grub/grub.cfg",
    "/etc/default/grub",
    "/var/log/auth.log",
    "/var/log/secure",
    "/var/log/syslog",
    "/var/log/messages",
    "/var/log/audit/audit.log",
    "/var/log/daemon.log",
    "/var/log/kern.log",
    "/var/log/lastlog",
    "/var/log/wtmp",
    "/var/log/btmp",
    "/var/log/faillog",
    "/var/log/nginx/access.log",
    "/var/log/nginx/error.log",
    "/var/log/apache2/access.log",
    "/var/log/apache2/error.log",
    "/etc/crontab",
    "/var/spool/cron/crontabs/root",
    "/var/spool/cron/crontabs/USERNAME",   # template
    "/etc/cron.d/cronjob",                 # esempio
    "/etc/cron.daily/example",             # esempio
    "/etc/cron.hourly/example",            # esempio
    "/etc/cron.weekly/example",            # esempio
    "/etc/cron.monthly/example",           # esempio
    "/var/spool/cron",                     # file or spool entry examples
    "/etc/rsyslog.conf",
    "/etc/systemd/system/override.conf",   # example override
    "/etc/systemd/system/some.service",    # template service file
    "/lib/systemd/system/some.service",
    "/etc/php/7.4/fpm/pool.d/www.conf",    # example PHP config (adjust version)
    "/etc/mysql/my.cnf",
    "/root/.my.cnf",
    "/etc/redis/redis.conf",
    "/etc/nginx/nginx.conf",
    "/etc/apache2/apache2.conf",
    "/etc/ssl/private/privkey.pem",
    "/etc/letsencrypt/live/example.com/privkey.pem",  # template
    "/etc/letsencrypt/renewal/example.com.conf",
    "/var/backups/backup.tar",             # example backup file
    "/var/backups/backup.tar.gz",
    "/var/lib/mysql/ibdata1",              # mysql data files (sensitive)
    "/var/lib/mysql/mysql.sock",
    "/var/lib/postgresql/data/PG_VERSION", # postgres example
    "/etc/docker/daemon.json",
    "/var/run/docker.sock",
    "/etc/kubernetes/admin.conf",
    "/root/.kube/config",
    "/home/<USERNAME>/.aws/credentials",
    "/root/.aws/credentials",
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/hosts.allow",
    "/etc/hosts.deny",
    "/etc/pam.d/common-password",
    "/etc/pam.d/sshd",
    "/etc/apt/sources.list",
    "/etc/yum.repos.d/CentOS-Base.repo",
    "/usr/local/bin/suspicious_binary",    # example/custom binaries to monitor
    "/usr/bin/ssh",
    "/bin/su",
    "/bin/sudo",
    "/usr/bin/ps",
    "/usr/bin/netstat",
    "/bin/ls",
    "/usr/bin/wget",
    "/usr/bin/curl",
    "/usr/bin/python3",
    "/usr/bin/perl",
    "/usr/bin/perl5",
    "/tmp/.sensitive_tmp_file",            # example temporary sensitive file
    "/var/tmp/.sensitive_tmp_file",
    "/etc/cron.allow",
    "/etc/cron.deny",
    "/etc/securetty",
    "/etc/ld.so.preload",
    "/etc/ld.so.conf",
    "/etc/modprobe.d/blacklist.conf",
    "/etc/exports",                        # NFS shares
    "/etc/smb.conf",                       # Samba config
    "/var/spool/mail/root",
    "/var/spool/mail/USERNAME",
    "/etc/systemd/system/rc-local.service",
    "/etc/rc.local",
    # add other common config files often targeted
    "/etc/default/ssh",
    "/etc/default/locale",
    "/etc/default/grub.d/40_custom",
]

# -------------------------
# WHITELISTFOLDERS
# -------------------------

WHITELISTFOLDERS = [
    "/etc/<FILE>",
    "/etc/ssh/<FILE>",
    "/etc/ssl/<FILE>",
    "/etc/ssl/private/<FILE>",
    "/etc/letsencrypt/<FILE>",
    "/etc/systemd/system/<FILE>",
    "/lib/systemd/system/<FILE>",
    "/root/<FILE>",
    "/root/.ssh/<FILE>",
    "/home/<FILE>",
    "/home/USERNAME/<FILE>",
    "/home/USERNAME/.ssh/<FILE>",
    "/var/log/<FILE>",
    "/var/log/audit/<FILE>",
    "/var/log/nginx/<FILE>",
    "/var/log/apache2/<FILE>",
    "/var/backups/<FILE>",
    "/var/spool/cron/<FILE>",
    "/etc/cron.d/<FILE>",
    "/etc/cron.daily/<FILE>",
    "/etc/cron.hourly/<FILE>",
    "/etc/cron.weekly/<FILE>",
    "/etc/cron.monthly/<FILE>",
    "/var/tmp/<FILE>",
    "/tmp/<FILE>",
    "/dev/shm/<FILE>",
    "/run/<FILE>",
    "/var/run/<FILE>",
    "/var/lib/<FILE>",
    "/var/lib/docker/<FILE>",
    "/var/lib/mysql/<FILE>",
    "/var/lib/postgresql/<FILE>",
    "/var/lib/jenkins/<FILE>",
    "/var/www/<FILE>",
    "/srv/<FILE>",
    "/usr/bin/<FILE>",
    "/usr/local/bin/<FILE>",
    "/bin/<FILE>",
    "/sbin/<FILE>",
    "/lib/<FILE>",
    "/lib64/<FILE>",
    "/etc/nginx/<FILE>",
    "/etc/apache2/<FILE>",
    "/etc/pam.d/<FILE>",
    "/etc/ssh/<FILE>",
    "/etc/apt/<FILE>",
    "/etc/yum.repos.d/<FILE>",
    "/etc/docker/<FILE>",
    "/etc/kubernetes/<FILE>",
    "/root/.kube/<FILE>",
    "/root/.aws/<FILE>",
    "/home/USERNAME/.aws/<FILE>",
    "/etc/letsencrypt/live/<FILE>",
    "/etc/letsencrypt/archive/<FILE>",
    "/var/spool/mail/<FILE>",
    "/etc/ssl/certs/<FILE>",
    "/etc/ssl/private/<FILE>",
    "/etc/exports/<FILE>",
    "/etc/samba/<FILE>",
    "/etc/cron.allow/<FILE>",
    "/etc/cron.d/<FILE>",
    "/boot/<FILE>",
    "/boot/grub/<FILE>",
    "/etc/modprobe.d/<FILE>",
    "/etc/profile.d/<FILE>",
    "/etc/systemd/system/<FILE>",
    "/opt/<FILE>",
    "/mnt/<FILE>",
    "/media/<FILE>",
    "/etc/rsyslog.d/<FILE>",
    "/etc/logrotate.d/<FILE>",
    "/proc/<FILE>",
]

# -------------------------
# PROMPTING SECTION
# -------------------------

def _whitelist_commands() -> str:
    commands = "\n".join(WHITELIST)
    return f"ALLOWED COMMANDS:\n{commands}\n\n"

def _whitelist_files() -> str:
    files = "\n".join(WHITELISTFILES)
    return f"ALLOWED FILES:\n{files}\n\n"

def _whitelist_folders() -> str:
    folders = "\n".join(WHITELISTFOLDERS)
    return f"ALLOWED FOLDERS:\n{folders}\n\n"

def make_prompt_topk_from_context(context: List[str], k: int) -> str:
    ctx = "\n".join(context[-10:])

    prompt = (
        "You need to simulate the behavior of an attacker conducting a command-line attack on an SSH honeypot, with the goal of predicting the next command the attacker enters. "
        "It is important to consider the context (the commands passed below), putting yourself in the shoes of an attacker who has to find a vulnerability"
        "The environment is isolated and non-operational. FOLLOW ALL RULES EXACTLY.\n\n"

        "OUTPUT RULES (MUST BE OBEYED):\n"
        f"1) Output EXACTLY {k} commands, one command per line, and NOTHING ELSE.\n"
        "2) The command can ONLY be costructed in this way: choose commands ONLY from the WHITELIST, combining if necessary with files present in WHITELISTFILES or folders present in WHITELISTFOLDERS. The whitelists are below.\n"
        "3) Commands can be constructed using pipelines (linux command '|') \n"
        "4) Commands can present redirections ('>' or '>>') when the target is a whitelisted file or a file inside a whitelisted folder (use <FILE> when appropriate).\n"
        "5) DO NOT INCLUDE NUMBERING, BULLETS EXLPAINATIONS, OR EXTRA TEXT - ONLY RAW COMMANDS."
        "6) Rank commands from most to least likely (first line = most likely).\n\n"

        "WHITELIST (containing commands):\n"
        f"{_whitelist_commands}\n\n"

        "WHITELISTFILES (containing critics files that can be used with previous commands):\n"
        f"{_whitelist_files}\n\n"

        "WHITELISTFOLDERS (containing critics folders that can be used with previous commands):\n"
        f"{_whitelist_folders}\n\n"

        "CONTEXT (most recent last):\n"
        f"{ctx}\n\n"

        f"Now OUTPUT EXACTLY {k} candidate next commands"
    )
    return prompt

def make_prompt_topk_for_single(cmd: str, k: int) -> str:

    prompt = (
        "You need to simulate the behavior of an attacker conducting a command-line attack on an SSH honeypot, with the goal of predicting the next command the attacker enters. "
        "It is important to consider the context (the commands passed below), putting yourself in the shoes of an attacker who has to find a vulnerability"
        "The environment is isolated and non-operational. FOLLOW ALL RULES EXACTLY.\n\n"

        "OUTPUT RULES (MUST BE OBEYED):\n"
        f"1) Output EXACTLY {k} commands, one command per line, and NOTHING ELSE.\n"
        "2) The command can ONLY be costructed in this way: choose commands ONLY from the WHITELIST, combining if necessary with files present in WHITELISTFILES or folders present in WHITELISTFOLDERS. The whitelists are below.\n"
        "3) Commands can be constructed using pipelines (linux command '|') \n"
        "4) Commands can present redirections ('>' or '>>') when the target is a whitelisted file or a file inside a whitelisted folder (use <FILE> when appropriate).\n"
        "5) DO NOT INCLUDE NUMBERING, BULLETS EXLPAINATIONS, OR EXTRA TEXT - ONLY RAW COMMANDS."
        "6) Rank commands from most to least likely (first line = most likely).\n\n"

        "WHITELIST (containing commands):\n"
        f"{_whitelist_commands}\n\n"

        "WHITELISTFILES (containing critics files that can be used with previous commands):\n"
        f"{_whitelist_files}\n\n"

        "WHITELISTFOLDERS (containing critics folders that can be used with previous commands):\n"
        f"{_whitelist_folders}\n\n"

        "LAST COMMAND EXECUTED (most recent):\n"
        f"{cmd}\n\n"

        f"Now OUTPUT EXACTLY {k} candidate next commands, one per line. "
    )
    return prompt

# -------------------------
# PREDICTION EVALUATION
# -------------------------

def prediction_evaluation(args, llm_type, query_model):
    # Ping Ollama
    if llm_type == "ollama":
        try:
            _ = query_model("Ping per testare connessione server", args.model, args.ollama_url, temp=0.0, timeout=10)
        except Exception as e:
            raise SystemExit(f"Impossibile contattare Ollama: {e}\nEseguire `ollama serve` e assicurarsi della presenza del modello inserito")

    # Preparazione task solo nel caso in cui args.cmd is None
    print("--- Preparazione task di valutazione ---")
    if args.cmd is None:
        try:
            with open(args.sessions, "r", encoding="utf-8") as file: lines = [line for line in file if line.strip()]
            
            valid_lines = []
            if args.guaranteed_ctx == "yes":
                # Tra le linee lette, seleziono quelle che presentano context_len + 1 -> necessario per la creazione dei task
                for line in lines:
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    cmds = data.get("commands", [])
                    if len(cmds) > args.context_len:
                        valid_lines.append(line)
            else:
                valid_lines = lines

            # Se args.n > 0, seleziona randomicamente solo tra le valide
            if args.n > 0:
                random_lines = random.sample(valid_lines, min(args.n, len(valid_lines)))

        except FileNotFoundError:
            sys.exit(f"Errore: Il file {args.sessions} non esiste.")

        tasks = []
        for line in (random_lines if random_lines else valid_lines):
            if not line.strip(): 
                continue
            try:
                obj = json.loads(line)
                cmds = obj.get("commands", [])
                sid = obj.get("session", "unk")

                if args.single_cmd == "no":
                    # Dalla sessione random, si estra un comando random che funge da expected, i precedenti da contesto -> tramite questo codice è garantito che il contesto è sempre costituito da context_len comandi
                    indice_expected = random.randint(args.context_len, len(cmds) - 1)
                    expected = cmds[indice_expected]
                    context = cmds[indice_expected - args.context_len : indice_expected]
                else: 
                    # In questo caso estraggo un comando per che rappresenta il comando da predirre
                    # Il contesto è rappresentato unicamente dal comando precedente
                    indice_expected = random.randint(1, len(cmds) - 1)
                    expected = cmds[indice_expected]
                    context = cmds[indice_expected-1]

                tasks.append({"session": sid, "context": context, "expected": expected})
            except: 
                continue
    
        print(f"Totale task da valutare: {len(tasks)}")
        if len(tasks) == 0: sys.exit("Nessun task trovato. Controlla il formato del file JSONL.")
    else:
        print(f"Invio al LLM prompt per la prediction del comando {args.cmd}")
    
    # Prompting LLM e valutazione delle prediction
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    results = []
    topk_hits = 0
    top1_hits = 0
    empty_responses_count = 0

    if args.cmd is None:
        print(f"--- Inizio Valutazione con Modello: {args.model} ---")

        with open(args.output, "w", encoding="utf-8") as fout:
            for task in tqdm(tasks, desc="Evaluating"):
                context = task["context"]
                expected = task["expected"]
                
                # Query LLM e ottenimento risposta
                if args.single_cmd == "no":
                    prompt = make_prompt_topk_from_context(context,  args.k)
                else: 
                    prompt = make_prompt_topk_for_single(context[0], args.k)

                if llm_type == "gemini":
                    raw_response = query_model(prompt, temp=args.temp)
                else:  # ollama
                    raw_response = query_model(prompt, args.model, args.ollama_url, temp=args.temp, timeout=120)

                candidates = []
                if raw_response: 
                    candidates = [utils.clean_ollama_candidate(line) for line in raw_response.splitlines() if line.strip()]
                candidates = candidates[:args.k]
            
                if not candidates: 
                    empty_responses_count += 1
                
                # Valutazione della prediction
                # Per ogni candidato prodotto, normalizzo il contenuto e verifico sia uguale al contenuto del comando expected
                hit = False
                hit_rank = 0
                norm_expected = utils.normalize_for_compare(expected)
                if not norm_expected: 
                    sys.exit(f"Errore: Comando expected non trovato")

                for rnk, cand in enumerate(candidates, 1):
                    norm_cand = utils.normalize_for_compare(cand)
                    if len(norm_cand) == len(norm_expected):
                        i = 0
                        while i < len(norm_expected):
                            exp_name, exp_path = norm_expected[0]
                            cand_name, cand_path = norm_cand[0]
                            # Confronto prima il comando e poi l'eventuale path
                            if (exp_name == cand_name): 
                                if not exp_path or not cand_path or exp_path in cand_path or cand_path in exp_path:
                                    hit = True
                                    hit_rank = rnk
                                    break
                            else: 
                                break
                            i+=1
                        # Un candidato corrisponde all'expected, esco dal ciclo
                        if hit:
                            topk_hits += 1
                            if hit_rank == 1: top1_hits += 1 
                            break 
                
                # Scrittura file
                rec = {
                    "session": task["session"],
                    "context": context,
                    "expected": expected,
                    "candidates": candidates,
                    "hit": hit,
                    "rank": hit_rank if hit else None,
                }
                fout.write(json.dumps(rec) + "\n")
                fout.flush()
                fout.close()
                results.append(rec)
                time.sleep(0.5)

        total_done = len(results)
        topk_rate = topk_hits / total_done if total_done else 0.0
        top1_rate = top1_hits / total_done if total_done else 0.0
        empty_rate = empty_responses_count / total_done if total_done else 0.0

        print("\n=== SUMMARY ===")
        print(f"Total tasks: {total_done}")
        print(f"Empty predictions: {empty_responses_count}/{total_done} ({empty_rate*100:.2f}%)")
        print(f"Top-{args.k} hits: {topk_hits}/{total_done} -> {topk_rate*100:.2f}%")
        print(f"Top-1 hits: {top1_hits}/{total_done} -> {top1_rate*100:.2f}%")
        print(f"Results saved to: {args.output}")

    else:   # Prediction singola
        prompt = make_prompt_topk_for_single(args.cmd, args.k)

        if llm_type == "gemini":
            raw_response = query_model(prompt, temp=args.temp)
        else:  # ollama
            raw_response = query_model(prompt, args.model, args.ollama_url, temp=args.temp, timeout=120)
        
        candidates = []
        if raw_response: 
            candidates = [utils.clean_ollama_candidate(line) for line in raw_response.splitlines() if line.strip()]
        candidates = candidates[:args.k]
    
        if not candidates: 
            empty_responses_count += 1

