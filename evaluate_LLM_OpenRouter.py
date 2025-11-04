# evaluate_LLM_OpenRouter.py — versione con progress bar (tqdm)
import os, json, time, random, argparse, difflib, requests
from datetime import datetime, timezone
from tqdm import tqdm  # ✅ barra di progresso

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# ========================
# Utility
# ========================

def normalize_cmd(s: str) -> str:
    if not s:
        return ""
    s = s.strip()
    s = s.replace("```bash", "").replace("```sh", "").replace("```", "")
    first = next((ln for ln in s.splitlines() if ln.strip()), "")
    return " ".join(first.split())

def jaccard(a: str, b: str) -> float:
    A, B = set(a.split()), set(b.split())
    if not A and not B:
        return 1.0
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)

def ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()

def rate_limit_sleep(resp):
    retry_after = resp.headers.get("retry-after")
    if retry_after:
        try:
            return max(1.0, float(retry_after))
        except:
            pass
    reset_ms = resp.headers.get("X-RateLimit-Reset") or resp.headers.get("x-ratelimit-reset")
    if reset_ms:
        try:
            reset_s = float(reset_ms)
            if reset_s > 1e12:
                reset_s /= 1000.0
            now = time.time()
            return max(1.0, reset_s - now)
        except:
            pass
    return 15.0

# ========================
# OpenRouter API
# ========================

def call_openrouter(api_key, model, messages, max_retries=6, rpm_limit=18, title="Predictive Deception Eval"):
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

        try:
            resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=90)
        except requests.RequestException as e:
            if attempt == max_retries - 1:
                return "", f"network_error: {e}"
            time.sleep(5)
            continue

        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"], None
        elif resp.status_code in (429, 502, 408, 503):
            sleep_s = rate_limit_sleep(resp)
            elapsed = time.time() - t0
            min_spacing = 60.0 / max(1, rpm_limit)
            if elapsed < min_spacing:
                sleep_s = max(sleep_s, min_spacing - elapsed)
            sleep_s += random.uniform(0, 1.5)
            time.sleep(min(120.0, sleep_s))
            t0 = time.time()
            continue
        else:
            try:
                return "", f"http_{resp.status_code}: {resp.json()}"
            except Exception:
                return "", f"http_{resp.status_code}: {resp.text[:200]}"

    return "", "max_retries_exceeded"

# ========================
# Prompt builder
# ========================

def make_prompt(context):
    sys_msg = (
        "You are a predictive model for SSH attackers' next command.\n"
        "Given the previous shell commands, output ONLY the next raw command on one line.\n"
        "Do NOT add explanations, text, or formatting."
    )
    user_msg = "Command history:\n" + "\n".join(context) + "\nNext command:"
    return [{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}]

# ========================
# Main
# ========================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Dataset JSONL con campi: context(list[str]) e next/expected(str)")
    ap.add_argument("--output", default="results.jsonl")
    ap.add_argument("--summary", default="summary.json")
    ap.add_argument("--model", default="deepseek/deepseek-r1-0528:free")
    ap.add_argument("--api_key", default=os.getenv("OPENROUTER_API_KEY"))
    ap.add_argument("--near_jaccard", type=float, default=0.8)
    ap.add_argument("--rpm_limit", type=int, default=18)
    args = ap.parse_args()

    if not args.api_key:
        raise SystemExit("❌ Missing --api_key or OPENROUTER_API_KEY")

    # Resume: skip già valutati
    done = {}
    if os.path.exists(args.output):
        with open(args.output, "r") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    done[json.dumps(obj.get("_key", obj.get("context")), sort_keys=True)] = True
                except:
                    pass

    n, ok, near, errors = 0, 0, 0, 0

    # ✅ Conta righe per mostrare barra proporzionale
    with open(args.input, "r") as fin:
        lines = [json.loads(line) for line in fin if line.strip()]
    total = len(lines)

    with open(args.output, "a") as fout, tqdm(total=total, desc="🔍 Valutazione progress", unit="pair") as pbar:
        for item in lines:
            ctx = item.get("context") or item.get("input") or item.get("commands") or []
            expected = item.get("next") or item.get("expected") or item.get("target") or ""
            if not ctx or not expected:
                pbar.update(1)
                continue

            expected = normalize_cmd(expected)
            key = json.dumps(ctx, sort_keys=True)
            if key in done:
                pbar.update(1)
                continue

            content, err = call_openrouter(
                args.api_key, args.model, make_prompt(ctx), rpm_limit=args.rpm_limit
            )

            predicted_raw = content or ""
            predicted = normalize_cmd(predicted_raw)
            ex = (predicted == expected) and bool(predicted)
            jac = jaccard(predicted, expected)
            rat = ratio(predicted, expected)

            rec = {
                "_key": ctx,
                "context": ctx,
                "expected": expected,
                "predicted_raw": predicted_raw,
                "predicted": predicted,
                "exact": ex,
                "ratio": round(rat, 4),
                "jaccard": round(jac, 4),
                "model": args.model,
                "error": err,
            }

            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fout.flush()

            n += 1
            ok += int(ex)
            near += int((not ex) and jac >= args.near_jaccard)
            errors += int(err is not None)
            pbar.update(1)

    summary = {
        "total_evaluated": n,
        "exact_acc": ok / n if n else 0.0,
        f"near_matches_jaccard>={args.near_jaccard:.2f}": near / n if n else 0.0,
        "error_rate": errors / n if n else 0.0,
        "model": args.model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(args.summary, "w") as f:
        json.dump(summary, f, indent=2)
    print("\n📊 RISULTATI FINALI:")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()