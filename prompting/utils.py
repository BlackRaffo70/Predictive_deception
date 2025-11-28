# -------------------------
# INTRODUCTION -> some utils informations about the Python script
# -------------------------

"""
Il file contiene due funzoni di utilità che vengono utilizzate nei diversi script progettati.
Le funzioni presenti sono:

- normalize_for_compare(cmd: str) -> List[Tuple[str, str]] = normalizzazione dei comandi, con supporto del pipelining.
- clean_ollama_candidate(line: str) = funzione utilizzata per "pulire" la risposta di LLM ollama, fortemente indicizzata e verbosa (caratteristica del modello)
"""

# -------------------------
# IMPORT SECTION -> imports necessary for the Python script
# -------------------------

import re
from typing import List, Tuple

# -------------------------
# FUNCTION SECTION
# -------------------------

CMD_NAME_RE = re.compile(r"[a-zA-Z0-9._/\-]+")     # nome comando
PATH_RE = re.compile(r"(/[^ ]+|\.{1,2}/[^ ]+)")    # path-like
PLACEHOLDER_RE = re.compile(r"<[^>]+>")  # qualunque <...>
CODE_FENCE_RE = re.compile(r'```(?:bash|sh)?\s*(.*?)\s*```', re.S | re.I)

def normalize_for_compare(cmd: str) -> List[Tuple[str, str]]:
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

def clean_ollama_candidate(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^\d+\.\s*", "", line)   # rimuove "1. "
    line = line.strip("`")                  # rimuove backticks
    return line.strip()