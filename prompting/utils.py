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