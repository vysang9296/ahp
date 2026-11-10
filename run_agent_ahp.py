"""합성 페르소나 AHP 실행기. role은 HTML 직무와 같은 값(감사, 정보화, 보안·법무, 예산·기획, 기타)만 쓴다. personas_nemotron.jsonl(한 줄에 {"id","role","nemotron_uuid","persona"})을 읽어
OpenAI 호환 API(OpenCode/DeepSeek V4 Flash 등)에 쌍대비교를 묻고, CR·가중치를 코드로 계산해 시트로 보낸다.
환경변수: PERSONAS(기본 personas_nemotron.jsonl), FACTS(기본 1, 0이면 사실표 없이), LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, WEBAPP_URL(없으면 시트 전송 생략), OUT(기본 총괄표_agent.csv), RUNS(기본 5), TEMP(기본 0.7)"""
import os, json, random, math, datetime, requests
import re, html as _h
_H=open("ahp_survey.html",encoding="utf-8").read()   # 설문 HTML 하나가 기준(요인·정의·첫 화면 문구)
CFG=json.loads(re.search(r'<script id="config" type="application/json">(.*?)</script>',_H,re.S).group(1))
C=CFG["C"]; ALT=CFG["ALT"]; BC=CFG["BC"]; CDEF=CFG["CDEF"]; RI={5:1.12}
BASE=os.environ["LLM_BASE_URL"].rstrip("/"); KEY=os.environ["LLM_API_KEY"]; MODEL=os.environ["LLM_MODEL"]
HOOK=os.getenv("WEBAPP_URL",""); RUNS=int(os.getenv("RUNS",5)); TEMP=float(os.getenv("TEMP",0.7))
_intro=re.search(r'<div id="intro">(.*?)</div>`\);',_H,re.S).group(1)
_intro=re.sub(r'</(li|p|h1|h2|tr|div)>|<br>',"\n",_intro); _intro=re.sub(r'</t[dh]>'," | ",_intro)
CONTEXT=_h.unescape(re.sub(r'<[^>]+>',"",_intro)); CONTEXT=re.sub(r'\n\s*\n+',"\n",CONTEXT).strip()
USE_FACTS=os.getenv("FACTS","1")!="0"   # FACTS=0 이면 사실표를 빼고 돌린다(정보 제공 효과 점검용)
if USE_FACTS and CFG.get("FACTS"):
    CONTEXT+="\n요인별로 두 방식은 이렇게 다르다(사실만 적음)\n"+"\n".join(f"- {k}: {ALT[0]} = {v[0]} / {ALT[1]} = {v[1]}" for k,v in CFG["FACTS"].items())
CONTEXT+="\n평가 요인\n"+"\n".join(f"{i+1}. {c}: {d}" for i,(c,d) in enumerate(zip(C,CDEF)))  # 사람용 화면과 같은 문장
ALLOWED=["9","8","7","6","5","4","3","2","1","1/2","1/3","1/4","1/5","1/6","1/7","1/8","1/9"]
MAX_TRY=2  # 사람과 같게: 1회 응답 + CR 미통과 시 1회 수정
import hashlib
def seed_of(*a): return int(hashlib.md5("|".join(map(str,a)).encode()).hexdigest()[:8],16)  # 실행마다 같은 순서(재현성)
def pfa(bc): return 5.11532*math.log(bc)+1 if bc>=1 else 1/(5.11532*math.log(1/bc)+1)  # 교안 PFA B/C 표준점수
def bad_pairs(M,w,k=3):  # 가중치 비율에서 가장 많이 어긋난 쌍
    d=[(abs(math.log(M[i][j]/(w[i]/w[j]))),i,j) for i in range(5) for j in range(i+1,5)]
    return [f'"{C[i]}" vs "{C[j]}"' for _,i,j in sorted(d,reverse=True)[:k]]
pairs=[(i,j) for i in range(5) for j in range(i+1,5)]
def ask(persona, role, seed, extra=""):
    rnd=random.Random(seed); items=[]
    for i,j in pairs:
        a,b=(i,j) if rnd.random()<.5 else (j,i); items.append({"key":f"C|{a}|{b}","left":C[a],"right":C[b]})
    for c in range(1,5):
        a,b=(0,1) if rnd.random()<.5 else (1,0); items.append({"key":f"A|{c}|{a}|{b}","left":f"{ALT[a]} ({C[c]} 측면)","right":f"{ALT[b]} ({C[c]} 측면)"})
    rnd.shuffle(items)
    q="\n".join(f'- {it["key"]}: "{it["left"]}" vs "{it["right"]}"' for it in items)
    sys=f"당신은 다음 인물이다. 이 사람의 관점으로만 판단한다.\n{persona}\n맡은 역할: {role}\n상황: 감사원이 아래 두 방식 중 하나를 고른다. 경제성 칸의 대안 점수는 B/C로 정해지므로 묻지 않는다.\n\n"+CONTEXT
    usr=("각 항목에서 왼쪽이 오른쪽보다 얼마나 더 중요한지(또는 더 우수한지) Saaty 척도로 답하라. "
         "값은 반드시 다음 목록 중 하나의 문자열만 쓴다: "+", ".join(ALLOWED)+". "
         "왼쪽이 더 중요하면 2~9, 오른쪽이 더 중요하면 1/2~1/9, 같으면 1. "
         "답하기 전에 요인들의 중요도 순서를 머릿속으로 먼저 정하고, 모든 비교가 그 순서와 모순되지 않게(A>B, B>C이면 A>C) 답하라.\n"+q+extra+
         '\nJSON만 출력: {"answers":{"<key>":"<값>",...}}')
    r=requests.post(f"{BASE}/chat/completions",headers={"Authorization":f"Bearer {KEY}"},timeout=180,json={
        "model":MODEL,"temperature":TEMP,"response_format":{"type":"json_object"},
        "messages":[{"role":"system","content":sys},{"role":"user","content":usr}]}).json()
    return json.loads(r["choices"][0]["message"]["content"])["answers"]
def num(s):
    s=str(s).strip(); return float(s.split("/")[0])/float(s.split("/")[1]) if "/" in s else float(s)
def ahp(M):
    n=len(M); g=[math.prod(r)**(1/n) for r in M]; w=[x/sum(g) for x in g]
    lam=sum(sum(M[i][j]*w[j] for j in range(n))/w[i] for i in range(n))/n
    return w,((lam-n)/(n-1))/RI[n]
def parse(ans):
    M=[[1.0]*5 for _ in range(5)]; altW=[ECON_PFA]+[None]*4; raw={}
    for k,v in ans.items():
        if str(v).strip() not in ALLOWED: raise ValueError(f"허용되지 않은 값 {k}={v}")
        t=k.split("|"); x=num(v)
        if t[0]=="C": a,b=int(t[1]),int(t[2]); M[a][b]=x; M[b][a]=1/x; i,j=min(a,b),max(a,b); raw[f"{C[i]}|{C[j]}"]=M[i][j]
        else:
            c,a=int(t[1]),int(t[2]); xa=x if a==0 else 1/x; altW[c]=[xa/(1+xa),1/(1+xa)]; raw[f"ALT|{C[c]}"]=xa
    if len([k for k in raw if not k.startswith("ALT")])!=10 or any(x is None for x in altW): raise ValueError("빠진 문항")
    return M,altW,raw
def ask_valid(persona, role, seed, extra=""):
    err=""
    for _ in range(3):
        try:
            ans=ask(persona,role,seed=seed,extra=extra+err)
            return ans,*parse(ans)
        except Exception as e:
            err=f"\n(이전 응답 형식 오류: {e}. 허용된 17개 값과 JSON 형식을 지켜 모든 문항에 다시 답하라.)"
    raise RuntimeError(err)
ROLES={"감사","정보화","보안·법무","예산·기획","기타"}
r=pfa(BC[0]/BC[1])   # 기준안: B/C 비율(1.40/1.02=1.37)을 PFA 공식에 넣음 → 2.62 → A 0.72 : B 0.28
ECON_PFA=[r/(1+r),1/(1+r)]; ECON_SIMPLE=[BC[0]/sum(BC),BC[1]/sum(BC)]  # 민감도: 단순 비례 0.58:0.42
import csv
OUT=os.getenv("OUT","총괄표_agent.csv")   # 모든 시행을 한 줄씩 쌓는 총괄표(시트와 같은 열 + 페르소나 정보)
def log_row(q,p):
    head=(["timestamp","source","respondent_id","role","nemotron_uuid","occupation","model","run","CR","CR_처음"]
          +["w_"+c for c in C]+["A점수_"+c for c in C]+["종합_A(PFA기준)","종합_B(PFA기준)","종합_A_단순비례","종합_B_단순비례","attempts","CR통과","raw_json"])
    row=([q["timestamp"],q["source"],q["respondent_id"],q["role"],p.get("nemotron_uuid",""),p.get("occupation",""),q["model"],q["run"],
          round(q["cr"],4),round(q["cr_initial"],4)]+[round(x,4) for x in q["weights"]]+[round(a[0],4) for a in q["alt_local"]]
         +[round(x,4) for x in q["total"]+q["total_simple"]]+[q["attempts"],"TRUE" if q["cr_pass"] else "FALSE",json.dumps(q["raw"],ensure_ascii=False)])
    new=not os.path.exists(OUT)
    with open(OUT,"a",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f)
        if new: w.writerow(head)
        w.writerow(row)

PERSONAS=os.getenv("PERSONAS","personas_nemotron.jsonl")   # Nemotron에서 뽑은 8명
SOURCE="agent" if USE_FACTS else "agent_사실표없음"
for line in open(PERSONAS,encoding="utf-8"):
    p=json.loads(line)
    if p["role"] not in ROLES: print(p["id"],"직무 이름 불일치:",p["role"]); continue
    for run in range(1,RUNS+1):
        seed=seed_of(p["id"],run); extra=""; ok=False; got=False; cr0=None
        for attempt in range(1,MAX_TRY+1):
            try:
                ans,M,altW,raw=ask_valid(p["persona"],p["role"],seed=seed,extra=extra)
            except Exception as e:
                print(p["id"],run,"응답 실패:",e); break
            w,cr=ahp(M); got=True
            if cr0 is None: cr0=cr
            if cr<0.1: ok=True; break
            extra=(f"\n\n[1차 응답 일관성 점검 안내]\n당신의 1차 응답: {json.dumps(ans,ensure_ascii=False)}\n"
                   f"이 응답의 일관성 비율(CR)이 {cr:.3f}로 0.1을 넘었다. 특히 다음 비교가 서로 어긋난다: {', '.join(bad_pairs(M,w))}.\n"
                   f"본인의 관점은 유지하되 어긋난 비교를 조정하여 한 번만 수정해 전체 문항에 다시 답하라.")
        if not got: continue
        tot=[sum(altW[c][k]*w[c] for c in range(5)) for k in (0,1)]
        altS=[ECON_SIMPLE]+altW[1:]; totS=[sum(altS[c][k]*w[c] for c in range(5)) for k in (0,1)]
        payload={"timestamp":datetime.datetime.now().isoformat(),"source":SOURCE,"respondent_id":p["id"],"role":p["role"],
                 "model":MODEL,"run":run,"attempts":attempt,"cr_pass":ok,"criteria":C,"weights":w,"cr":cr,"cr_initial":cr0,"alt_names":ALT,
                 "alt_local":altW,"total":tot,"total_simple":totS,"raw":raw}
        if HOOK: requests.post(HOOK,data=json.dumps(payload,ensure_ascii=False).encode(),headers={"Content-Type":"text/plain"})
        log_row(payload,p)
        print(p["id"],p.get("nemotron_uuid","")[:8],run,f"시도{attempt}",f"CR={cr:.3f}","통과" if ok else "미통과",["%.3f"%x for x in w])
