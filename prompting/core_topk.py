# -------------------------
# INTRODUCTION -> some utils informations about the Python script
# -------------------------

"""
Il file contiene funzioni e array necessari per gli script sviluppati.
All'inzio di ogni script che utilizza tali array e funzioni, viene eseguito l'import del seguente file. 
"""
# -------------------------
# IMPORT SECTION
# -------------------------

import json
import os
import random
import re
import time
from typing import List
from tqdm import tqdm
import utils

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

# -------------------------
# PROMPTING SECTION -> definition of the two functions (with and whitout context) containing the prompt
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

def prediction_evaluation(args, llm_type, query_model):
    # validate modes
    mode_sessions = bool(args.sessions)
    mode_single = bool(args.single_cmd or args.single_file)
    if not (mode_sessions or mode_single):
        raise SystemExit("Provide --sessions OR --single-cmd OR --single-file")

    # quick ping for Ollama
    if llm_type == "ollama":
        try:
            _ = query_model("Ping. Reply 'ok' only.", args.model, args.ollama_url, temp=0.0, timeout=10)
        except Exception as e:
            raise SystemExit(f"Unable to contact Ollama: {e}\nStart `ollama serve` and ensure model is pulled.")

    # build tasks
    tasks = []
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
        for sess in sessions:
            cmds = sess["commands"]
            for i in range(len(cmds) - 1):
                start = max(0, i - (args.context_len - 1))
                context = cmds[start:i+1]
                expected = cmds[i+1]
                tasks.append({"session": sess["session"], "index": i, "context": context, "expected": expected})
    else:
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

    # shuffle if requested
    if args.n and args.n > 0:
        random.seed(args.seed)
        random.shuffle(tasks)
        tasks = tasks[:args.n]

    print(f"Total prediction tasks: {len(tasks)}")
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

        # query LLM
        try:
            if llm_type == "gemini":
                raw = query_model(prompt, temp=args.temp)
            else:  # ollama
                raw = query_model(prompt, args.model, args.ollama_url, temp=args.temp, timeout=120)
            err = None
        except Exception as e:
            raw = ""
            err = str(e)

        # parse response
        if llm_type == "gemini":
            candidates = raw.splitlines()[:args.k]
            candidates_clean = [c.strip() for c in candidates if c.strip()]
        else:
            candidates = utils.clean_llm_response(raw, args.k)
            candidates_clean = [re.sub(r'^```|```$|`', '', c).strip() for c in candidates]

        # print
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

        # permissive comparison
        hit = False
        if expected and candidates_clean:
            exp_keys = utils.normalize_for_compare(expected)
            if exp_keys:
                exp_cmd = exp_keys[0]
                for rnk, cand in enumerate(candidates_clean, start=1):
                    cand_keys = utils.normalize_for_compare(cand)
                    if not cand_keys:
                        continue
                    cand_cmd = cand_keys[0]
                    name_match = (cand_cmd[0] == exp_cmd[0] and cand_cmd[0] != "")
                    if exp_cmd[1]:
                        path_match = (cand_cmd[1] == exp_cmd[1] or 
                                      (cand_cmd[1] and (exp_cmd[1].startswith(cand_cmd[1]) or cand_cmd[1].startswith(exp_cmd[1]))))
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
        "k": args.k,
        "context_len": args.context_len
    }
    if llm_type == "ollama":
        summary["model"] = args.model

    with open(args.out + ".summary.json", "w", encoding="utf-8") as s:
        json.dump(summary, s, indent=2)

    print("\n=== SUMMARY ===")
    print(f"Total tasks: {total_done}")
    print(f"Non-empty predictions: {non_empty}/{total_done} ({non_empty_rate*100:.2f}%)")
    print(f"Top-{args.k} hits: {topk_hits}/{total_done} -> {topk_rate*100:.2f}%")
    print(f"Top-1 hits: {top1_hits}/{total_done} -> {top1_rate*100:.2f}%")
    print(f"Detailed results: {args.out}")
    print(f"Summary: {args.out}.summary.json")

