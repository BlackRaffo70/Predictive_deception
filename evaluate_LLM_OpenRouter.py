# evaluate_openrouter_retry.py
import os, json, time, math, random, argparse, difflib
import requests
from datetime import datetime, timezone

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

def normalize_cmd(s: str) -> str:
    s = s.strip()
    # rimuovi fence e prefissi comuni
    s = s.replace("```bash", "").replace("```sh", "").replace("```", "")
    # prendi solo la prima linea non vuota
    first = next((ln for ln in s.splitlines() if ln.strip()), "")
    return " ".join(first.split())

def jaccard(a: str, b: str) -> float:
    A = set(a.split())
    B = set(b.split())
    if not A and not B: return 1.0
    if not A or not B: return 0.0
    return len(A & B) / len(A | B)

def ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()

def rate_limit_sleep(resp):
    # rispetta Retry-After oppure X-RateLimit-Reset (ms/epoch)
    retry_after = resp.headers.get("retry-after")
    if retry_after:
        try: return max(1.0, float(retry_after))
        except: pass
    reset_ms = resp.headers.get("X-RateLimit-Reset") or resp.headers.get("x-ratelimit-reset")
    if reset_ms:
        try:
            # alcuni provider usano epoch ms
            reset_s = float(reset_ms)
            if reset_s > 1e12: reset_s /= 1000.0
            now = time.time()
            return max(1.0, reset_s - now)
        except: pass
    # fallback: backoff breve
    return 15.0

def call_openrouter(api_key, model, messages, max_retries=6, rpm_limit=18, title="Predictive Deception Eval"):
    # rpm_limit: tieniti sotto 20 rpm sui :free
    t0 = time.time()
    for attempt in range(max_retries):
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/BlackRaffo70/Predictive_deception",
            "X-Title": title
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 64
        }
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=90)
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"], None
        elif resp.status_code in (429, 502, 408):
            sleep_s = rate_limit_sleep(resp)
            # cap rpm
            elapsed = time.time() - t0
            min_spacing = 60.0 / max(1, rpm_limit)
            if elapsed < min_spacing:
                sleep_s = max(sleep_s, min_spacing - elapsed)
            # jitter
            sleep_s += random.uniform(0, 1.5)
            time.sleep(min(120.0, sleep_s))
            t0 = time.time()
            continue
        else:
            try:
                return "", f"http_{resp.status_code}: {resp.json()}"
            except Exception:
                return "", f"http_{resp.status_code}: {resp.text[:300]}"

    # esauriti i tentativi
    try:
        return "", f"http_{resp.status_code}: {resp.json()}"
    except Exception:
        return "", f"http_{resp.status_code}: {resp.text[:300]}"

def make_prompt(context):
    # Istruzioni minimali per forzare una singola riga di output
    sys = "You predict the single next most likely shell command. Output ONLY the raw command on one line, no explanations."
    user = "History:\n" + "\n".join(context) + "\nNext command:"
    return [{"role":"system","content":sys}, {"role":"user","content":user}]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="dataset JSONL con campi: context(list[str]), expected(str)")
    ap.add_argument("--output", default="results.jsonl")
    ap.add_argument("--summary", default="summary.json")
    ap.add_argument("--model", default="deepseek/deepseek-r1-0528:free")
    ap.add_argument("--api_key", default=os.getenv("OPENROUTER_API_KEY"))
    ap.add_argument("--near_jaccard", type=float, default=0.8)
    ap.add_argument("--rpm_limit", type=int, default=18)
    args = ap.parse_args()

    if not args.api_key:
        raise SystemExit("Missing --api_key or OPENROUTER_API_KEY")

    # resume
    done = {}
    if os.path.exists(args.output):
        with open(args.output, "r") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    key = json.dumps(obj.get("_key", obj.get("context")), sort_keys=True)
                    done[key] = True
                except:
                    pass

    n, ok, near, errors = 0, 0, 0, 0
    with open(args.input, "r") as fin, open(args.output, "a") as fout:
        for line in fin:
            item = json.loads(line)
            key = json.dumps(item.get("context"), sort_keys=True)
            if key in done:  # skip se già valutato
                continue

            ctx = item["context"]
            expected = normalize_cmd(item["expected"])
            content, err = call_openrouter(
                args.api_key, args.model, make_prompt(ctx),
                rpm_limit=args.rpm_limit
            )

            predicted_raw = content or ""
            predicted = normalize_cmd(predicted_raw)
            ex = (predicted == expected) and bool(predicted)
            jac = jaccard(predicted, expected)
            rat = ratio(predicted, expected)

            rec = {
                "_key": item.get("_key", ctx),
                "context": ctx,
                "expected": expected,
                "predicted_raw": predicted_raw,
                "predicted": predicted,
                "exact": ex,
                "ratio": rat,
                "jaccard": jac,
                "model": args.model,
                "error": err
            }
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fout.flush()

            n += 1
            ok += int(ex)
            near += int((not ex) and jac >= args.near_jaccard)
            errors += int(err is not None)

    summary = {
        "total_new": n,
        "exact_acc": ok / n if n else 0.0,
        "near_matches_jaccard>=%.2f" % args.near_jaccard: near / n if n else 0.0,
        "error_rate": errors / n if n else 0.0,
        "model": args.model,
        "generated_at": datetime.now(timezone.utc).isoformat()
    }
    with open(args.summary, "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
