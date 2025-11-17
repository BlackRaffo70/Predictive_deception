#!/usr/bin/env python3
"""
evaluate_gemini_topk.py — versione adattata per Google Gemini API

Funziona in due modalità:
 - sessioni (--sessions)
 - singolo comando (--single-cmd, --single-file)

Usa il modello Gemini tramite:
    pip install google-genai

Ricorda di esportare:
    export GOOGLE_API_KEY="LA_TUA_KEY"
"""

from __future__ import annotations
import argparse, json, os, re, time, random
from typing import List, Tuple
from tqdm import tqdm


# -------------------------
# Google Gemini API (nuova sintassi 2025)
# -------------------------
from google.genai import Client

if not os.getenv("GOOGLE_API_KEY"):
    raise RuntimeError("ERROR: manca GOOGLE_API_KEY. Usa: export GOOGLE_API_KEY=xxxxx")

client = Client(api_key=os.getenv("GOOGLE_API_KEY"))

def query_gemini(prompt: str, temp: float = 0.2) -> str:
    """
    Invia prompt a Gemini usando la nuova API:
    client.models.generate(...)
    """
    try:
        response = client.models.generate(
            model="gemini-1.5-flash",
            input=prompt,
            config={
                "temperature": temp
            }
        )

        # estrai testo dalla risposta
        if hasattr(response, "text"):
            return response.text.strip()

        if hasattr(response, "output_text"):
            return response.output_text.strip()

        return str(response)

    except Exception as e:
        return f"[GEMINI ERROR] {e}"

# -------------------------
# Regex helpers
# -------------------------
CMD_NAME_RE = re.compile(r"[a-zA-Z0-9._/\-]+")
PATH_RE = re.compile(r"(/[^ ]+|\.{1,2}/[^ ]+)")
PLACEHOLDER_RE = re.compile(r"<[^>]+>")
CODE_FENCE_RE = re.compile(r'```(?:bash|sh)?\s*(.*?)\s*```', re.S | re.I)

# -------------------------------------------------------------------
# CLEAN LLM OUTPUT (USANDO SOLO LE LINEE CHE SONO COMANDI VALIDi)
# -------------------------------------------------------------------
def clean_llm_response(resp: str, k: int) -> List[str]:
    if not resp:
        return []

    out = resp.strip()

    # estrai da code fence se presente
    m = CODE_FENCE_RE.search(out)
    if m:
        out = m.group(1).strip()

    lines = out.splitlines()
    cleaned = []

    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue

        # rimuovi numerazione e bullet
        ln = re.sub(r"^\d+[\.\)\-]\s*", "", ln)
        ln = re.sub(r"^[\-\*\•]\s*", "", ln)

        # ignora testo non-comando
        if ln.lower().startswith(("sorry", "i cannot", "i can’t","based", "the next", "i am unable",
                                  "i'm unable", "this is", "as an ai")):
            continue

        # deve sembrare un comando
        if not re.match(r"[a-zA-Z0-9./<]", ln):
            continue

        cleaned.append(ln)

        if len(cleaned) >= k:
            break

    return cleaned

# -------------------------------------------------------------------
# NORMALIZZAZIONE CON PIPELINE SUPPORT
# -------------------------------------------------------------------
def normalize_for_compare(cmd: str) -> List[Tuple[str, str]]:
    if not cmd:
        return []

    s = cmd.strip()
    s = re.sub(r'^```(?:bash|sh)?|```$', '', s, flags=re.I).strip()
    s = s.replace('`', '')

    s = re.sub(
        r'^(the next command( is|:)?|il prossimo comando( è|:)?|next command( is|:)?|predicted command( is|:)?)[\s:,-]*',
        '',
        s,
        flags=re.I
    ).strip()

    segments = re.split(r"\s*\|\s*", s)
    results = []

    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue

        seg_clean = PLACEHOLDER_RE.sub("", seg).strip()
        seg_clean = re.split(r"\s*>\s*|\s*2>\s*|\s*>>\s*", seg_clean)[0].strip()

        m = CMD_NAME_RE.match(seg_clean)
        name = m.group(0).lower() if m else ""

        path = ""
        pm = PATH_RE.search(seg_clean)
        if pm:
            path = pm.group(0)

        results.append((name, path))

    return results

# -------------------------------------------------------------------
# GEMINI CALL
# -------------------------------------------------------------------
def query_gemini(prompt: str, temp: float = 0.2) -> str:
    """Invia prompt a Google Gemini e restituisce il testo puro usando la nuova API."""
    try:
        response = client.models.generate(
            model="gemini-1.5-flash",
            input=prompt,
            config={"temperature": temp}
        )

        # Estrazione del testo
        if hasattr(response, "text"):
            return response.text.strip()

        if hasattr(response, "output_text"):
            return response.output_text.strip()

        return str(response)

    except Exception as e:
        return f"[GEMINI ERROR] {e}"

# -------------------------------------------------------------------
# WHITELISTS (le tue liste complete vengono mantenute)
# -------------------------------------------------------------------

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


# -------------------------------------------------------------------
# PROMPT BUILDER
# -------------------------------------------------------------------
def _whitelist_commands():
    return "ALLOWED COMMANDS:\n" + "\n".join(WHITELIST)

def _whitelist_files():
    return "ALLOWED FILES:\n" + "\n".join(WHITELISTFILES)

def _whitelist_folders():
    return "ALLOWED FOLDERS:\n" + "\n".join(WHITELISTFOLDERS)

def make_prompt_topk_from_context(context: List[str], k: int) -> str:
    ctx = "\n".join(context[-10:])
    return f"""
You must simulate attacker behavior in an SSH honeypot.
Predict the NEXT {k} commands.

RULES:
- Output EXACTLY {k} commands (one per line, no extra text).
- Commands MUST be built ONLY using:
  * ALLOWED COMMANDS
  * ALLOWED FILES
  * ALLOWED FOLDERS
- Placeholders allowed ONLY if wrapped in <...>
- Pipelines allowed ("|")
- Redirections allowed only to whitelisted files.

{_whitelist_commands()}

{_whitelist_files()}

{_whitelist_folders()}

CONTEXT:
{ctx}

Now output EXACTLY {k} commands.
"""

def make_prompt_topk_for_single(cmd: str, k: int) -> str:
    return f"""
Predict the next {k} commands.

RULES:
- EXACTLY {k} commands, one per line.
- Must use whitelist.

{_whitelist_commands()}

{_whitelist_files()}

{_whitelist_folders()}

LAST COMMAND:
{cmd}

Now output EXACTLY {k} commands.
"""

# -------------------------------------------------------------------
# MAIN EVALUATION LOOP
# -------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions")
    ap.add_argument("--single-cmd")
    ap.add_argument("--single-file")
    ap.add_argument("--out", default="output/gemini_results.jsonl")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--context-len", type=int, default=3)
    ap.add_argument("--n", type=int, default=0)
    ap.add_argument("--temp", type=float, default=0.2)
    args = ap.parse_args()

    tasks = []

    if args.sessions:
        if not os.path.exists(args.sessions):
            raise SystemExit(f"Sessions file not found: {args.sessions}")

        with open(args.sessions, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
                cmds = obj.get("commands")
                if not cmds or len(cmds) < 2:
                    continue

                # Sliding window
                for i in range(len(cmds) - 1):
                    start = max(0, i - (args.context_len - 1))
                    context = cmds[start:i + 1]
                    expected = cmds[i + 1]

                    tasks.append({
                        "session": obj.get("session"),
                        "index": i,
                        "context": context,
                        "expected": expected
                    })

    elif args.single_cmd:
        tasks.append({
            "session": "single",
            "index": 0,
            "context": [args.single_cmd],
            "expected": None
        })

    elif args.single_file:
        with open(args.single_file, "r") as f:
            for line in f:
                cmd = line.strip()
                if cmd:
                    tasks.append({
                        "session": "single",
                        "index": 0,
                        "context": [cmd],
                        "expected": None
                    })

    # ---------- LOOP ----------
    fout = open(args.out, "w")
    results = []

    for t in tqdm(tasks):
        context = t["context"]
        expected = t.get("expected")

        if len(context) == 1:
            prompt = make_prompt_topk_for_single(context[0], args.k)
        else:
            prompt = make_prompt_topk_from_context(context, args.k)

        raw = query_gemini(prompt, temp=args.temp)

        candidates = clean_llm_response(raw, args.k)

        rec = {
            "context": context,
            "expected": expected,
            "candidates": candidates
        }
        fout.write(json.dumps(rec) + "\n")
        results.append(rec)

    fout.close()
    print("Done.")

if __name__ == "__main__":
    main()