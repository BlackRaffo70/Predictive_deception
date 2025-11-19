# -------------------------
# INTRODUCTION -> some utils informations about the Python script
# -------------------------

"""
Il file contiene funzioni e array necessari per gli script sviluppati.
All'inzio di ogni script che utilizza tali array e funzioni, viene eseguito l'import del seguente file. 
"""

# -------------------------
# FUNCTION SECTION
# -------------------------

import re
from typing import List, Tuple

CMD_NAME_RE = re.compile(r"[a-zA-Z0-9._/\-]+")     # nome comando
PATH_RE = re.compile(r"(/[^ ]+|\.{1,2}/[^ ]+)")    # path-like
PLACEHOLDER_RE = re.compile(r"<[^>]+>")  # qualunque <...>
CODE_FENCE_RE = re.compile(r'```(?:bash|sh)?\s*(.*?)\s*```', re.S | re.I)

def clean_llm_response(resp: str, k: int) -> List[str]:
    """
    Estrae SOLO i comandi generati dall'LLM.
    - Rimuove testo descrittivo
    - Rimuove numerazione / bullet
    - Supporta code fences
    - Supporta pipeline e redirections
    - Restituisce max k righe interpretabili come comandi
    """

    if not resp:
        return []

    out = resp.strip()

    # 1) estrai contenuto dentro eventuale code block
    m = re.search(r"```(?:bash|sh)?\s*(.*?)\s*```", out, flags=re.S)
    if m:
        out = m.group(1).strip()

    lines = out.splitlines()
    cleaned = []

    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue

        # 2) rimuovi numerazione e bullet
        ln = re.sub(r"^\d+[\.\)\-]\s*", "", ln)       # 1. cmd
        ln = re.sub(r"^[\-\*\•]\s*", "", ln)          # - cmd

        # 3) elimina frasi non comando
        if ln.lower().startswith(("sorry", "i cannot", "i can’t","based", "the next", "i am unable",
                                  "i'm unable", "this is", "as an ai")):
            continue

        # 4) tieni solo linee plausibili come comandi
        if not re.match(r"[a-zA-Z0-9./<]", ln):
            continue  # scarta righe che non iniziano come comandi

        cleaned.append(ln)

        if len(cleaned) >= k:
            break

    return cleaned

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

# -------------------------
# WHITELIST = list of commands that can be used by an attacker (some commands includes util flags)
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
# WHITELISTFILES = Critics files in Linux systems that should be monitored
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
# WHITELISTFOLDERS = Critics folders in Linux systems that contains files that can be used by an attacker (the name of these files can change and is not unique across all systems, which is why the placeholder <FILE> is used.)
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