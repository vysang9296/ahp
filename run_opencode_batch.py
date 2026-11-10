# -*- coding: utf-8 -*-
"""8 personas x 5 fresh OpenCode Go sessions, DeepSeek v4.1 Flash.

Each trial is a new session. A CR revision stays in that same session.
The coding default agent is not used: OPENCODE_CONFIG_DIR points at a
survey-only agent with tools denied.
"""
import csv, datetime, hashlib, json, math, os, random, re, subprocess, sys, time
import html as html_lib

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "results", "main-facts-2026-11-10")
CFG = r"C:\Users\user\AppData\Local\Temp\ahp-batch"
WORK = os.path.join(CFG, "work")
EXE = r"C:\Users\user\AppData\Roaming\npm\node_modules\opencode-ai\bin\opencode.exe"
PILOT = os.path.join(ROOT, "results", "pilot-P01-run1")
JSONL = os.path.join(OUT, "trials.jsonl")
LOG = os.path.join(OUT, "run.log")
MODEL = "opencode-go/deepseek-v4.1-flash"
EXPERIMENT = "dsv41flash-facts-2026-11-10"
ALLOWED = {"9","8","7","6","5","4","3","2","1","1/2","1/3","1/4","1/5","1/6","1/7","1/8","1/9"}
RI = 1.12
TIMEOUT = 240

def log(msg):
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def seed_of(*parts):
    return int(hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)

def num(s):
    s = str(s).strip()
    if "/" in s:
        a, b = s.split("/")
        return float(a) / float(b)
    return float(s)

def ahp(M):
    n = len(M)
    g = [math.prod(row) ** (1 / n) for row in M]
    w = [x / sum(g) for x in g]
    lam = sum(sum(M[i][j] * w[j] for j in range(n)) / w[i] for i in range(n)) / n
    return w, ((lam - n) / (n - 1)) / RI

def bad_pairs(M, w, C, k=3):
    d = [(abs(math.log(M[i][j] / (w[i] / w[j]))), i, j) for i in range(5) for j in range(i + 1, 5)]
    return [f'"{C[i]}" vs "{C[j]}"' for _, i, j in sorted(d, reverse=True)[:k]]

def load_survey():
    html = open(os.path.join(ROOT, "ahp_survey.html"), encoding="utf-8").read()
    cfg = json.loads(re.search(r'<script id="config" type="application/json">(.*?)</script>', html, re.S).group(1))
    intro = re.search(r'<div id="intro">(.*?)</div>`\);', html, re.S).group(1)
    intro = re.sub(r"</(li|p|h1|h2|tr|div)>|<br>", "\n", intro)
    intro = re.sub(r"</t[dh]>", " | ", intro)
    context = html_lib.unescape(re.sub(r"<[^>]+>", "", intro))
    context = re.sub(r"\n\s*\n+", "\n", context).strip()
    alt = cfg["ALT"]
    context += "\n요인별로 두 방식은 이렇게 다르다(사실만 적음)\n" + "\n".join(
        f"- {k}: {alt[0]} = {v[0]} / {alt[1]} = {v[1]}" for k, v in cfg["FACTS"].items()
    )
    context += "\n평가 요인\n" + "\n".join(
        f"{i+1}. {c}: {d}" for i, (c, d) in enumerate(zip(cfg["C"], cfg["CDEF"]))
    )
    return cfg, context, sha(json.dumps(cfg, ensure_ascii=False, sort_keys=True))

def load_personas():
    path = os.path.join(ROOT, "personas_nemotron.jsonl")
    rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    if len(rows) != 8:
        raise SystemExit(f"persona count {len(rows)}")
    return rows, sha(open(path, encoding="utf-8").read())

def split_persona(text):
    m = re.match(r"^(\d+)세 (여자|남자), (\S+) (.+?) 거주\. 직업: ([^.]+)\. (.*)$", text)
    out = {"age": "", "sex": "", "province": "", "district": "", "narrative": "", "role_card": ""}
    if not m:
        out["narrative"] = text
        return out
    out["age"] = int(m.group(1))
    out["sex"] = m.group(2)
    out["province"] = m.group(3)
    out["district"] = m.group(4)
    rest = m.group(6)
    mark = "위 배경의 경력을 가진"
    if mark in rest:
        narrative, card = rest.split(mark, 1)
        out["narrative"] = narrative.strip()
        out["role_card"] = (mark + card).strip()
    else:
        out["narrative"] = rest.strip()
    return out

def make_items(pid, run, C, ALT):
    rnd = random.Random(seed_of(pid, run))
    items = []
    for i, j in [(i, j) for i in range(5) for j in range(i + 1, 5)]:
        a, b = (i, j) if rnd.random() < 0.5 else (j, i)
        items.append({"key": f"C|{a}|{b}", "left": C[a], "right": C[b], "kind": "criterion"})
    for c in range(1, 5):
        a, b = (0, 1) if rnd.random() < 0.5 else (1, 0)
        items.append({
            "key": f"A|{c}|{a}|{b}",
            "left": f"{ALT[a]} ({C[c]} 측면)",
            "right": f"{ALT[b]} ({C[c]} 측면)",
            "kind": "alternative",
        })
    rnd.shuffle(items)
    return items

def prompts(persona, role, context, items):
    allowed = ", ".join(["9","8","7","6","5","4","3","2","1","1/2","1/3","1/4","1/5","1/6","1/7","1/8","1/9"])
    q = "\n".join(f'- {it["key"]}: "{it["left"]}" vs "{it["right"]}"' for it in items)
    system = (
        f"당신은 다음 인물이다. 이 사람의 관점으로만 판단한다.\n{persona}\n맡은 역할: {role}\n"
        "상황: 감사원이 아래 두 방식 중 하나를 고른다. 경제성 칸의 대안 점수는 B/C로 정해지므로 묻지 않는다.\n\n"
        + context
    )
    user = (
        "각 항목에서 왼쪽이 오른쪽보다 얼마나 더 중요한지(또는 더 우수한지) Saaty 척도로 답하라. "
        f"값은 반드시 다음 목록 중 하나의 문자열만 쓴다: {allowed}. "
        "왼쪽이 더 중요하면 2~9, 오른쪽이 더 중요하면 1/2~1/9, 같으면 1. "
        "답하기 전에 요인들의 중요도 순서를 머릿속으로 먼저 정하고, 모든 비교가 그 순서와 모순되지 않게(A>B, B>C이면 A>C) 답하라.\n"
        + q
        + '\nJSON만 출력: {"answers":{"<key>":"<값>",...}}'
    )
    return system, user

def write_agent(system):
    os.makedirs(os.path.join(CFG, "agents"), exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    open(os.path.join(CFG, "opencode.json"), "w", encoding="utf-8").write(json.dumps({
        "$schema": "https://opencode.ai/config.json",
        "default_agent": "ahp-respondent",
        "share": "disabled",
        "compaction": {"auto": False},
        "instructions": [],
    }, ensure_ascii=False, indent=2))
    body = (
        "---\n"
        "description: AHP pairwise respondent for one fresh session\n"
        "mode: primary\n"
        f"model: {MODEL}\n"
        "temperature: 0.7\n"
        "steps: 2\n"
        "permission:\n"
        "  edit: deny\n  read: deny\n  glob: deny\n  grep: deny\n  list: deny\n"
        "  bash: deny\n  task: deny\n  skill: deny\n  webfetch: deny\n"
        "  websearch: deny\n  lsp: deny\n  todowrite: deny\n  question: deny\n"
        "  external_directory: deny\n"
        "---\n\n"
        + system + "\n"
    )
    open(os.path.join(CFG, "agents", "ahp-respondent.md"), "w", encoding="utf-8").write(body)

def find_answers(text):
    dec = json.JSONDecoder()
    found = None
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = dec.raw_decode(text[i:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("answers"), dict):
            found = obj["answers"]
    return found

def parse(ans, C):
    M = [[1.0] * 5 for _ in range(5)]
    alt = [None] * 5
    raw = {}
    for k, v in ans.items():
        if str(v).strip() not in ALLOWED:
            raise ValueError(f"bad value {k}={v}")
        t = k.split("|")
        x = num(v)
        if t[0] == "C":
            a, b = int(t[1]), int(t[2])
            M[a][b] = x
            M[b][a] = 1 / x
            i, j = min(a, b), max(a, b)
            raw[f"{C[i]}|{C[j]}"] = M[i][j]
        else:
            c, a = int(t[1]), int(t[2])
            xa = x if a == 0 else 1 / x
            alt[c] = xa
            raw[f"ALT|{C[c]}"] = xa
    if len([k for k in raw if not k.startswith("ALT")]) != 10 or any(x is None for x in alt[1:]):
        raise ValueError("missing items")
    return M, alt, raw

def redact(s):
    s = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-REDACTED", s or "")
    s = re.sub(r"Bearer\s+[A-Za-z0-9_\-\.]+", "Bearer REDACTED", s)
    return s[:800]

def parse_events(stdout):
    texts, sessions, errors = [], [], []
    tokens, cost = None, None
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("sessionID"):
            sessions.append(ev["sessionID"])
        part = ev.get("part") or {}
        if ev.get("type") == "text" and isinstance(part.get("text"), str):
            texts.append(part["text"])
        if ev.get("type") == "error":
            errors.append(redact(json.dumps(ev.get("error"), ensure_ascii=False)))
        if part.get("type") == "step-finish":
            tokens = part.get("tokens")
            cost = part.get("cost")
    return "".join(texts), (sessions[-1] if sessions else ""), tokens, cost, errors

def call_model(message, title, session, dest):
    cmd = [EXE, "run", "--pure", "--format", "json", "--model", MODEL,
           "--agent", "ahp-respondent", "--title", title, "--dir", WORK]
    if session:
        cmd += ["--session", session]
    cmd.append(message)
    env = os.environ.copy()
    env["OPENCODE_CONFIG_DIR"] = CFG
    env["OPENCODE_DISABLE_PROJECT_CONFIG"] = "1"
    t0 = time.time()
    started = datetime.datetime.now().isoformat(timespec="seconds")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env=env, timeout=TIMEOUT)
        rc, out, err = proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired as e:
        rc, out, err = -1, e.stdout or "", (e.stderr or "") + "\nTIMEOUT"
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        if isinstance(err, bytes):
            err = err.decode("utf-8", "replace")
    os.makedirs(dest, exist_ok=True)
    open(os.path.join(dest, "events.jsonl"), "w", encoding="utf-8").write(out)
    open(os.path.join(dest, "stderr.txt"), "w", encoding="utf-8").write(redact(err))
    text, sid, tokens, cost, errors = parse_events(out)
    open(os.path.join(dest, "text.txt"), "w", encoding="utf-8").write(text)
    return {
        "returncode": rc, "started": started, "elapsed_s": round(time.time() - t0, 2),
        "session": sid or session or "", "text": text, "tokens": tokens, "cost": cost,
        "errors": errors, "stderr": redact(err),
    }

def accept(text, C):
    ans = find_answers(text)
    if ans is None:
        return None
    try:
        M, alt, raw = parse(ans, C)
    except Exception:
        return None
    w, cr = ahp(M)
    return ans, M, alt, raw, w, cr

def score_row(C, ALT, BC, w, alt):
    pfa = 5.11532 * math.log(BC[0] / BC[1]) + 1
    econ = pfa / (1 + pfa)
    simple = BC[0] / (BC[0] + BC[1])
    local = [econ]
    a_scores = {C[0]: econ}
    for c in range(1, 5):
        share = alt[c] / (1 + alt[c])
        local.append(share)
        a_scores[C[c]] = share
    simple_local = [simple] + local[1:]
    return {
        "weights": {C[i]: w[i] for i in range(5)},
        "a_scores": a_scores,
        "total_pfa": [sum(w[i] * local[i] for i in range(5)), sum(w[i] * (1 - local[i]) for i in range(5))],
        "total_simple": [sum(w[i] * simple_local[i] for i in range(5)), sum(w[i] * (1 - simple_local[i]) for i in range(5))],
    }

def add_tokens(bucket, call):
    tok = call.get("tokens") or {}
    for k in ("input", "output", "reasoning", "total"):
        bucket[k] = bucket.get(k, 0) + (tok.get(k) or 0)
    bucket["cost"] = bucket.get("cost", 0) + (call.get("cost") or 0)
    bucket["elapsed_s"] = bucket.get("elapsed_s", 0) + call.get("elapsed_s", 0)

def run_trial(p, run, cfg, context, persona_file_sha):
    C, ALT, BC = cfg["C"], cfg["ALT"], cfg["BC"]
    items = make_items(p["id"], run, C, ALT)
    system, user = prompts(p["persona"], p["role"], context, items)
    write_agent(system)
    trial_id = f"{p['id']}-run{run}"
    dest_root = os.path.join(OUT, "sessions", trial_id)
    os.makedirs(dest_root, exist_ok=True)
    open(os.path.join(dest_root, "prompt_system.txt"), "w", encoding="utf-8").write(system)
    open(os.path.join(dest_root, "prompt_user.txt"), "w", encoding="utf-8").write(user)
    open(os.path.join(dest_root, "items_order.json"), "w", encoding="utf-8").write(json.dumps(items, ensure_ascii=False, indent=2))
    parts = split_persona(p["persona"])
    usage = {}
    calls = []
    title = f"AHP {p['id']} run{run}"

    def once(message, session, tag):
        log(f"WAITING {trial_id} {tag}")
        result = call_model(message, title, session, os.path.join(dest_root, tag))
        calls.append({"tag": tag, "returncode": result["returncode"], "elapsed_s": result["elapsed_s"], "session": result["session"]})
        add_tokens(usage, result)
        log(f"CALL {trial_id} {tag} rc={result['returncode']} chars={len(result['text'])} elapsed={result['elapsed_s']}")
        return result

    harness_retries = 0
    first = None
    for attempt in range(3):
        tag = "attempt1" if attempt == 0 else f"harness{attempt+1}"
        first = once(user, None, tag)
        if first["text"].strip() and (first["returncode"] == 0 or find_answers(first["text"])):
            break
        harness_retries += 1
        if attempt < 2:
            time.sleep(15 * (attempt + 1))
    session = first["session"]
    parsed = accept(first["text"], C) if first["text"] else None
    if parsed is None and session and first["returncode"] == 0:
        fmt = user + "\n이전 응답에서 허용된 17개 값의 JSON을 읽지 못했다. 다른 문장 없이 {\"answers\":{...}} 만 다시 출력하라."
        second = once(fmt, session, "attempt_format")
        parsed = accept(second["text"], C)
    if parsed is None:
        return base_record(p, run, parts, persona_file_sha, system, user, items, session, "session_failure" if first["returncode"] != 0 or not first["text"].strip() else "invalid_response", usage, calls, harness_retries)
    ans, M, alt, raw, w, cr = parsed
    answers_by_attempt = [{"attempt": 1, "kind": "initial", "answers": ans, "cr": cr}]
    final = parsed
    if cr >= 0.1 and session:
        extra = (
            f"\n\n[1차 응답 일관성 점검 안내]\n당신의 1차 응답: {json.dumps(ans, ensure_ascii=False)}\n"
            f"이 응답의 일관성 비율(CR)이 {cr:.3f}로 0.1을 넘었다. 특히 다음 비교가 서로 어긋난다: {', '.join(bad_pairs(M, w, C))}.\n"
            "본인의 관점은 유지하되 어긋난 비교를 조정하여 한 번만 수정해 전체 문항에 다시 답하라.\n"
            + user
        )
        rev = once(extra, session, "attempt2")
        parsed2 = accept(rev["text"], C)
        if parsed2 is None:
            rev2 = once(user + "\n수정 응답의 JSON을 읽지 못했다. 전체 문항을 허용된 값으로만, JSON만 다시 출력하라.", session, "attempt2_format")
            parsed2 = accept(rev2["text"], C)
        if parsed2 is not None:
            final = parsed2
            answers_by_attempt.append({"attempt": 2, "kind": "revision", "answers": parsed2[0], "cr": parsed2[5]})
    ans, M, alt, raw, w, cr_final = final
    scored = score_row(C, ALT, BC, w, alt)
    rec = base_record(p, run, parts, persona_file_sha, system, user, items, session, "completed", usage, calls, harness_retries)
    rec.update({
        "cr_initial": answers_by_attempt[0]["cr"],
        "cr": cr_final,
        "cr_pass": cr_final < 0.1,
        "attempts": len(answers_by_attempt),
        "weights": scored["weights"],
        "a_scores": scored["a_scores"],
        "total_pfa": scored["total_pfa"],
        "total_simple": scored["total_simple"],
        "raw": raw,
        "answers_by_attempt": answers_by_attempt,
        "origin": "batch",
    })
    return rec

def base_record(p, run, parts, persona_file_sha, system, user, items, session, status, usage, calls, harness_retries):
    return {
        "experiment_id": EXPERIMENT,
        "trial_id": f"{p['id']}-run{run}",
        "session_id": session or "",
        "finished_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "model": MODEL,
        "temperature": 0.7,
        "questionnaire": "AHP_설문_v8",
        "facts": 1,
        "respondent_id": p["id"],
        "role": p["role"],
        "occupation": p["occupation"],
        "nemotron_uuid": p["nemotron_uuid"],
        "pool_size": p["pool_size"],
        "age": parts["age"],
        "sex": parts["sex"],
        "province": parts["province"],
        "district": parts["district"],
        "narrative": parts["narrative"],
        "role_card": parts["role_card"],
        "dataset": "nvidia/Nemotron-Personas-Korea",
        "dataset_revision": "",
        "persona_file_sha256": persona_file_sha,
        "persona_text": p["persona"],
        "persona_sha256": sha(p["persona"]),
        "system_sha256": sha(system),
        "user_sha256": sha(user),
        "run": run,
        "seed": seed_of(p["id"], run),
        "selection_seed": 42,
        "age_min": 30,
        "age_max": 59,
        "status": status,
        "attempts": 0,
        "harness_retries": harness_retries,
        "cr_initial": "",
        "cr": "",
        "cr_pass": False,
        "weights": {},
        "a_scores": {},
        "total_pfa": ["", ""],
        "total_simple": ["", ""],
        "raw": {},
        "answers_by_attempt": [],
        "items": items,
        "tokens_input": usage.get("input", 0),
        "tokens_output": usage.get("output", 0),
        "tokens_reasoning": usage.get("reasoning", 0),
        "cost_usd": round(usage.get("cost", 0), 6),
        "elapsed_s": round(usage.get("elapsed_s", 0), 2),
        "calls": calls,
        "origin": "batch",
        "provenance_note": "age, sex, province, district, narrative, role_card are parsed from the composed persona string that was placed in the prompt. persona and professional_persona were already joined in personas_nemotron.jsonl, so they are kept together as narrative.",
    }

def append(rec):
    with open(JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())

def load_latest():
    latest = {}
    if not os.path.exists(JSONL):
        return latest
    for line in open(JSONL, encoding="utf-8"):
        if line.strip():
            rec = json.loads(line)
            latest[rec["trial_id"]] = rec
    return latest

def import_pilot(personas, context, persona_file_sha, cfg):
    meta_path = os.path.join(PILOT, "prompt_meta.json")
    trial_path = os.path.join(PILOT, "trial.json")
    if not (os.path.exists(meta_path) and os.path.exists(trial_path)):
        return False
    p = personas[0]
    items = make_items(p["id"], 1, cfg["C"], cfg["ALT"])
    system, user = prompts(p["persona"], p["role"], context, items)
    meta = json.load(open(meta_path, encoding="utf-8"))
    if sha(system) != meta["system_sha256"] or sha(user) != meta["user_sha256"] or seed_of("P01", 1) != meta["seed"]:
        log("PILOT hash mismatch; P01-run1 will be rerun")
        return False
    pilot = json.load(open(trial_path, encoding="utf-8"))
    ans = json.loads(pilot["row"]["answers_json"])
    parsed = accept(json.dumps({"answers": ans}, ensure_ascii=False), cfg["C"])
    if parsed is None:
        log("PILOT answers did not parse; P01-run1 will be rerun")
        return False
    ans, M, alt, raw, w, cr = parsed
    scored = score_row(cfg["C"], cfg["ALT"], cfg["BC"], w, alt)
    parts = split_persona(p["persona"])
    usage = {"input": 2273, "output": 135, "reasoning": 8903, "cost": 0.00576375, "elapsed_s": 66.01}
    rec = base_record(p, 1, parts, persona_file_sha, system, user, items, pilot["row"]["session_id"], "completed", usage, [{"tag": "attempt1", "returncode": 0, "elapsed_s": 66.01, "session": pilot["row"]["session_id"]}], 0)
    rec.update({
        "cr_initial": cr, "cr": cr, "cr_pass": cr < 0.1, "attempts": 1,
        "weights": scored["weights"], "a_scores": scored["a_scores"],
        "total_pfa": scored["total_pfa"], "total_simple": scored["total_simple"],
        "raw": raw, "answers_by_attempt": [{"attempt": 1, "kind": "initial", "answers": ans, "cr": cr}],
        "origin": "pilot", "finished_at": pilot["row"]["started_at"],
    })
    append(rec)
    log(f"PILOT imported P01-run1 CR={cr:.4f}")
    return True

def write_tables(latest, C):
    rows = [latest[k] for k in sorted(latest, key=lambda s: (s.split("-")[0], int(s.split("run")[1])))]
    # trials.csv
    flat_fields = ["experiment_id","trial_id","session_id","finished_at","model","temperature","facts","respondent_id","role","occupation","nemotron_uuid","pool_size","age","sex","province","district","run","seed","status","attempts","harness_retries","cr_initial","cr","cr_pass","tokens_input","tokens_output","tokens_reasoning","cost_usd","elapsed_s","origin","persona_sha256","system_sha256","user_sha256","dataset","persona_file_sha256"]
    for c in C:
        flat_fields.append("w_" + c)
    for c in C:
        flat_fields.append("A_" + c)
    flat_fields += ["total_A_pfa","total_B_pfa","total_A_simple","total_B_simple","persona_text","narrative","role_card"]
    with open(os.path.join(OUT, "trials.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=flat_fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            flat = dict(r)
            for c in C:
                flat["w_" + c] = "" if c not in r["weights"] else round(r["weights"][c], 6)
                flat["A_" + c] = "" if c not in r["a_scores"] else round(r["a_scores"][c], 6)
            flat["total_A_pfa"] = "" if r["total_pfa"][0] == "" else round(r["total_pfa"][0], 6)
            flat["total_B_pfa"] = "" if r["total_pfa"][0] == "" else round(r["total_pfa"][1], 6)
            flat["total_A_simple"] = "" if r["total_simple"][0] == "" else round(r["total_simple"][0], 6)
            flat["total_B_simple"] = "" if r["total_simple"][0] == "" else round(r["total_simple"][1], 6)
            flat["cr_initial"] = "" if r["cr_initial"] == "" else round(r["cr_initial"], 6)
            flat["cr"] = "" if r["cr"] == "" else round(r["cr"], 6)
            w.writerow(flat)
    with open(os.path.join(OUT, "items.csv"), "w", newline="", encoding="utf-8-sig") as f:
        fields = ["trial_id","session_id","respondent_id","run","attempt","kind","item_index","item_key","item_kind","left","right","answer"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            order = {it["key"]: (i, it) for i, it in enumerate(r["items"], 1)}
            for block in r["answers_by_attempt"]:
                for key, val in block["answers"].items():
                    if key not in order:
                        continue
                    i, it = order[key]
                    w.writerow({
                        "trial_id": r["trial_id"], "session_id": r["session_id"], "respondent_id": r["respondent_id"],
                        "run": r["run"], "attempt": block["attempt"], "kind": block["kind"], "item_index": i,
                        "item_key": key, "item_kind": it["kind"], "left": it["left"], "right": it["right"], "answer": val,
                    })
    # compatible sheet for aggregate_ahp.py
    head = ["timestamp","source","respondent_id","role","nemotron_uuid","occupation","model","run","CR","CR_처음"]
    head += ["w_" + c for c in C] + ["A점수_" + c for c in C]
    head += ["종합_A(PFA기준)","종합_B(PFA기준)","종합_A_단순비례","종합_B_단순비례","attempts","CR통과","raw_json"]
    with open(os.path.join(OUT, "총괄표_agent.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=head)
        w.writeheader()
        for r in rows:
            row = {
                "timestamp": r["finished_at"], "source": "agent", "respondent_id": r["respondent_id"],
                "role": r["role"], "nemotron_uuid": r["nemotron_uuid"], "occupation": r["occupation"],
                "model": r["model"], "run": r["run"],
                "CR": "" if r["cr"] == "" else r["cr"], "CR_처음": "" if r["cr_initial"] == "" else r["cr_initial"],
                "attempts": r["attempts"], "CR통과": "TRUE" if r["cr_pass"] else "FALSE",
                "raw_json": json.dumps(r["raw"], ensure_ascii=False) if r["raw"] else "{}",
            }
            for c in C:
                row["w_" + c] = "" if c not in r["weights"] else r["weights"][c]
                row["A점수_" + c] = "" if c not in r["a_scores"] else r["a_scores"][c]
            row["종합_A(PFA기준)"] = "" if r["total_pfa"][0] == "" else r["total_pfa"][0]
            row["종합_B(PFA기준)"] = "" if r["total_pfa"][0] == "" else r["total_pfa"][1]
            row["종합_A_단순비례"] = "" if r["total_simple"][0] == "" else r["total_simple"][0]
            row["종합_B_단순비례"] = "" if r["total_simple"][0] == "" else r["total_simple"][1]
            w.writerow(row)

def gm(vals):
    return math.exp(sum(math.log(v) for v in vals) / len(vals))

def aggregate(latest, C, BC):
    people = {}
    for r in latest.values():
        people.setdefault(r["respondent_id"], []).append(r)
    per = {}
    for pid, rs in people.items():
        ok = [r for r in rs if r["cr_pass"] and r["raw"]]
        info = rs[0]
        entry = {"id": pid, "role": info["role"], "occupation": info["occupation"], "uuid": info["nemotron_uuid"],
                 "age": info["age"], "sex": info["sex"], "province": info["province"], "district": info["district"],
                 "n_ok": len(ok), "n_all": len(rs), "include": len(ok) >= 3}
        if ok:
            raw = {k: gm([r["raw"][k] for r in ok]) for k in ok[0]["raw"]}
            M = [[1.0]*5 for _ in range(5)]
            for i in range(5):
                for j in range(i+1, 5):
                    M[i][j] = raw[f"{C[i]}|{C[j]}"]
                    M[j][i] = 1 / M[i][j]
            w, cr = ahp(M)
            alt = [None]*5
            for c in range(1, 5):
                alt[c] = raw[f"ALT|{C[c]}"]
            scored = score_row(C, ["A","B"], BC, w, alt)
            entry.update({"cr": cr, "weights": scored["weights"], "a_scores": scored["a_scores"],
                          "total_pfa": scored["total_pfa"], "total_simple": scored["total_simple"], "raw": raw})
        per[pid] = entry
    def pool(entries):
        used = [e for e in entries if e["include"] and e.get("raw")]
        if not used:
            return None
        raw = {k: gm([e["raw"][k] for e in used]) for k in used[0]["raw"]}
        M = [[1.0]*5 for _ in range(5)]
        for i in range(5):
            for j in range(i+1, 5):
                M[i][j] = raw[f"{C[i]}|{C[j]}"]
                M[j][i] = 1 / M[i][j]
        w, cr = ahp(M)
        alt = [None]*5
        for c in range(1, 5):
            alt[c] = raw[f"ALT|{C[c]}"]
        scored = score_row(C, ["A","B"], BC, w, alt)
        return {"n": len(used), "ids": [e["id"] for e in used], "cr": cr, "raw": raw, **scored}
    groups = {"agent": pool(list(per.values()))}
    for role in ["감사", "정보화", "보안·법무", "예산·기획"]:
        groups["agent·" + role] = pool([e for e in per.values() if e["role"] == role])
    # write persona table
    pfields = ["respondent_id","role","occupation","nemotron_uuid","age","sex","province","district","pass","all","include","cr"]
    pfields += ["w_" + c for c in C] + ["A_" + c for c in C] + ["total_A_pfa","total_B_pfa","total_A_simple","total_B_simple"]
    with open(os.path.join(OUT, "페르소나별_결과.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=pfields)
        w.writeheader()
        for pid in sorted(per):
            e = per[pid]
            row = {"respondent_id": pid, "role": e["role"], "occupation": e["occupation"], "nemotron_uuid": e["uuid"],
                   "age": e["age"], "sex": e["sex"], "province": e["province"], "district": e["district"],
                   "pass": e["n_ok"], "all": e["n_all"], "include": "포함" if e["include"] else "제외",
                   "cr": "" if "cr" not in e else round(e["cr"], 6)}
            for c in C:
                row["w_" + c] = "" if "weights" not in e else round(e["weights"][c], 6)
                row["A_" + c] = "" if "a_scores" not in e else round(e["a_scores"][c], 6)
            if "total_pfa" in e:
                row["total_A_pfa"] = round(e["total_pfa"][0], 6)
                row["total_B_pfa"] = round(e["total_pfa"][1], 6)
                row["total_A_simple"] = round(e["total_simple"][0], 6)
                row["total_B_simple"] = round(e["total_simple"][1], 6)
            w.writerow(row)
    gfields = ["group","n_included","ids","cr"] + ["w_" + c for c in C] + ["A_" + c for c in C] + ["total_A_pfa","total_B_pfa","total_A_simple","total_B_simple"]
    with open(os.path.join(OUT, "집단_집계.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=gfields)
        w.writeheader()
        lines = []
        for name, g in groups.items():
            if not g:
                w.writerow({"group": name, "n_included": 0})
                lines.append(f"{name}\t집계 인원 0")
                continue
            row = {"group": name, "n_included": g["n"], "ids": " ".join(g["ids"]), "cr": round(g["cr"], 6)}
            for c in C:
                row["w_" + c] = round(g["weights"][c], 6)
                row["A_" + c] = round(g["a_scores"][c], 6)
            row["total_A_pfa"] = round(g["total_pfa"][0], 6)
            row["total_B_pfa"] = round(g["total_pfa"][1], 6)
            row["total_A_simple"] = round(g["total_simple"][0], 6)
            row["total_B_simple"] = round(g["total_simple"][1], 6)
            w.writerow(row)
            lines.append(
                f"{name}\t인원 {g['n']} ({' '.join(g['ids'])})\tCR {g['cr']:.4f}\t"
                f"A {g['total_pfa'][0]:.4f} / B {g['total_pfa'][1]:.4f} (PFA)\t"
                f"A {g['total_simple'][0]:.4f} / B {g['total_simple'][1]:.4f} (단순비례)"
            )
    dropped = [e["id"] for e in per.values() if not e["include"]]
    text = []
    text.append(f"실험 {EXPERIMENT}")
    text.append(f"모델 {MODEL}  온도 0.7  사실표 사용  설문 AHP_설문_v8")
    text.append("세션: 페르소나 1명 x 회차 1번마다 OpenCode 세션을 새로 열었다. CR 0.1 이상이면 그 세션에서 한 번 수정했다.")
    text.append("집계: CR 0.1 미만만 사용. 같은 사람의 통과 회차를 기하평균해 1명으로 만든 뒤, 5회 중 3회 미만은 제외하고 남은 사람을 다시 기하평균했다.")
    text.append("제외: " + (", ".join(dropped) if dropped else "없음"))
    text.append("")
    text.extend(lines)
    text.append("")
    text.append("페르소나별")
    for pid in sorted(per):
        e = per[pid]
        if "total_pfa" in e:
            text.append(f"{pid} {e['role']} {e['occupation']} {e['n_ok']}/{e['n_all']} {'포함' if e['include'] else '제외'} A {e['total_pfa'][0]:.4f} B {e['total_pfa'][1]:.4f}")
        else:
            text.append(f"{pid} {e['role']} {e['occupation']} {e['n_ok']}/{e['n_all']} 제외")
    open(os.path.join(OUT, "요약.txt"), "w", encoding="utf-8").write("\n".join(text) + "\n")
    return "\n".join(text)

def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True

def main():
    os.makedirs(OUT, exist_ok=True)
    if not os.environ.get("OPENCODE_API_KEY"):
        log("FAILED missing OPENCODE_API_KEY")
        sys.exit(2)
    pid_path = os.path.join(OUT, "runner.pid")
    if os.path.exists(pid_path):
        old = int(open(pid_path, encoding="utf-8").read().strip() or "0")
        if old and old != os.getpid() and pid_alive(old):
            log(f"FAILED another runner is alive pid {old}")
            sys.exit(2)
    open(pid_path, "w", encoding="utf-8").write(str(os.getpid()))
    cfg, context, config_sha = load_survey()
    personas, persona_file_sha = load_personas()
    open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8").write(json.dumps({
        "experiment_id": EXPERIMENT, "model": MODEL, "temperature": 0.7, "facts": 1,
        "questionnaire": "AHP_설문_v8", "config_sha256": config_sha,
        "persona_file_sha256": persona_file_sha, "dataset": "nvidia/Nemotron-Personas-Korea",
        "selection_seed": 42, "age_min": 30, "age_max": 59,
        "agent": "ahp-respondent", "tools": "denied", "session": "fresh per trial",
        "revision": "same session, once, if CR>=0.1",
    }, ensure_ascii=False, indent=2))
    latest = load_latest()
    if "P01-run1" not in latest:
        import_pilot(personas, context, persona_file_sha, cfg)
        latest = load_latest()
    expected = [f"{p['id']}-run{run}" for p in personas for run in range(1, 6)]
    streak = 0
    done_n = 0
    for p in personas:
        for run in range(1, 6):
            tid = f"{p['id']}-run{run}"
            prev = latest.get(tid)
            if prev and prev["status"] != "session_failure":
                done_n += 1
                log(f"SKIP {tid} status={prev['status']}")
                continue
            log(f"START {tid}")
            try:
                rec = run_trial(p, run, cfg, context, persona_file_sha)
            except Exception as e:
                log(f"FAILED exception {tid} {type(e).__name__}: {e}")
                streak += 1
                if streak >= 4:
                    log("FAILED four exceptions in a row")
                    sys.exit(1)
                continue
            append(rec)
            latest[tid] = rec
            write_tables(latest, cfg["C"])
            done_n = sum(1 for k in expected if k in latest and latest[k]["status"] != "session_failure")
            cr = rec["cr"] if rec["cr"] != "" else ""
            cr_s = f"{cr:.4f}" if isinstance(cr, float) else "-"
            log(f"PROGRESS {done_n}/40 {tid} status={rec['status']} CR={cr_s} pass={rec['cr_pass']}")
            if rec["status"] == "session_failure":
                streak += 1
                if streak >= 4:
                    log("FAILED four session failures in a row")
                    write_tables(latest, cfg["C"])
                    sys.exit(1)
            else:
                streak = 0
            time.sleep(2)
    latest = load_latest()
    write_tables(latest, cfg["C"])
    missing = [k for k in expected if k not in latest or latest[k]["status"] == "session_failure"]
    summary = aggregate(latest, cfg["C"], cfg["BC"])
    log(summary)
    if missing:
        log("FAILED missing " + " ".join(missing))
        sys.exit(1)
    log("DONE 40/40")

if __name__ == "__main__":
    main()
