"""시트 탭을 CSV로 내려받아 실행: python aggregate_ahp.py 총괄표_agent.csv [사람응답.csv ...]
CR통과 응답만 골라, 같은 응답자(페르소나)의 반복 실행은 먼저 기하평균해 1명분으로 만든 뒤(Agent는 5회 중 3회 이상 통과한 페르소나만), 사람과 Agent를 따로(직무별도) 쌍대비교 값끼리 기하평균(AIJ)한 뒤 가중치를 다시 계산한다.
경제성 대안 점수는 기준안(PFA: B/C 비율 1.40/1.02 → A 0.72)과 민감도(단순 비례 0.58)를 함께 낸다.
제외된(CR 미통과) 응답 수와 통과율도 출력한다."""
import csv, sys, math, json, collections
BC=(1.40,1.02)
pf=lambda b: 5.11532*math.log(b)+1
r=pf(BC[0]/BC[1]); ECON={"PFA기준":(r/(1+r),1/(1+r)),"단순비례":(BC[0]/sum(BC),BC[1]/sum(BC))}
allrows=[r for f in sys.argv[1:] for r in csv.DictReader(open(f,encoding="utf-8-sig"))]   # 여러 CSV(사람 시트 + Agent 총괄표)를 한 번에 읽는다
C=[k[2:] for k in allrows[0] if k.startswith("w_")]; n=len(C)
ok=lambda r: str(r.get("CR통과","")).upper()=="TRUE" or (r.get("CR통과","")=="" and float(r["CR"])<0.1)
gm=lambda xs: math.exp(sum(map(math.log,xs))/len(xs))
def weights(M):
    g=[math.prod(row)**(1/n) for row in M]; s=sum(g); w=[x/s for x in g]
    lam=sum(sum(M[i][j]*w[j] for j in range(n))/w[i] for i in range(n))/n
    return w,((lam-n)/(n-1))/1.12
def norm(x):  # 키 방향 통일: "요인i|요인j"(i<j)와 "ALT|요인" 값만 남긴다
    d={}
    for i in range(n):
        for j in range(i+1,n):
            k=f"{C[i]}|{C[j]}"; d[k]=x[k] if k in x else 1/x[f"{C[j]}|{C[i]}"]
    for c in range(1,n): d[f"ALT|{C[c]}"]=x[f"ALT|{C[c]}"]
    return d
MIN_PASS=3   # Agent: 반복 5회 중 CR 통과가 3회 미만이면 판단이 흔들린다고 보고 그 페르소나를 뺀다
def per_person(rs):  # 같은 페르소나의 통과 회차를 먼저 기하평균해 1명분으로 합친다(평가자 수 부풀림 방지)
    by=collections.defaultdict(list)
    for r in rs: by[(r["source"],r["respondent_id"])].append(norm(json.loads(r["raw_json"])))
    keep={k:v for k,v in by.items() if not k[0].startswith("agent") or len(v)>=MIN_PASS}
    ids={(r["source"],r["respondent_id"]) for r in per_person.all}   # 0회 통과한 페르소나도 제외 목록에 넣는다
    per_person.dropped=sorted(f"{k[1]}({len(by.get(k,[]))}회 통과)" for k in ids if k[0].startswith("agent") and k not in keep)
    return [{k:gm([x[k] for x in xs]) for k in xs[0]} for xs in keep.values()]
def agg(rs):
    raws=per_person(rs); agg.dropped=per_person.dropped; M=[[1.0]*n for _ in range(n)]
    if not raws: return None
    for i in range(n):
        for j in range(i+1,n):
            v=gm([x[f"{C[i]}|{C[j]}"] if f"{C[i]}|{C[j]}" in x else 1/x[f"{C[j]}|{C[i]}"] for x in raws]); M[i][j]=v; M[j][i]=1/v
    w,cr=weights(M)
    agg.people=len(raws)
    loc=[None]+[(lambda a:(a/(1+a),1/(1+a)))(gm([x[f"ALT|{C[c]}"] for x in raws])) for c in range(1,n)]
    out={}
    for name,e in ECON.items():
        L=[e]+loc[1:]; out[name]=[sum(w[c]*L[c][k] for c in range(n)) for k in (0,1)]
    return w,cr,out
groups=collections.defaultdict(list); allg=collections.defaultdict(list); tot=collections.Counter()
for r in allrows:
    for g in (r["source"], r["source"]+"·"+r["role"]):
        tot[g]+=1; allg[g].append(r)
        if ok(r): groups[g].append(r)
print("집단 | 통과/전체(응답 수) | 집계 인원 | "+" | ".join(C)+" | 통합CR | 종합A/B(PFA기준) | 종합A/B(단순비례)")
for g in sorted(tot):
    rs=groups[g]; per_person.all=allg[g]
    if not rs: print(f"{g} | 0/{tot[g]} | 0 | 통과 응답 없음"); continue
    res=agg(rs)
    if res is None: print(f"{g} | {len(rs)}/{tot[g]} | 0 | 남은 응답자 없음 | 제외: {', '.join(agg.dropped)}"); continue
    w,cr,o=res
    print(f"{g} | {len(rs)}/{tot[g]} | {agg.people} | "+" | ".join(f"{x:.3f}" for x in w)+f" | {cr:.3f} | {o['PFA기준'][0]:.3f}/{o['PFA기준'][1]:.3f} | {o['단순비례'][0]:.3f}/{o['단순비례'][1]:.3f}"+(f" | 제외(3회 미만 통과): {', '.join(agg.dropped)}" if agg.dropped else ""))

# 장표용 페르소나별 표: 그대로 복사해 붙일 수 있게 CSV(엑셀용)와 탭 구분 텍스트로 낸다
def person_result(xs):   # 한 사람의 통과 회차를 기하평균한 뒤 가중치와 종합 점수를 낸다
    x={k:gm([d[k] for d in xs]) for k in xs[0]}; M=[[1.0]*n for _ in range(n)]
    for i in range(n):
        for j in range(i+1,n): M[i][j]=x[f"{C[i]}|{C[j]}"]; M[j][i]=1/M[i][j]
    w,_=weights(M); loc=[(lambda a:(a/(1+a),1/(1+a)))(x[f"ALT|{C[c]}"]) for c in range(1,n)]
    return {k:[sum(w[c]*([e]+loc)[c][t] for c in range(n)) for t in (0,1)] for k,e in ECON.items()}
pp=collections.OrderedDict()
for r in allrows:
    d=pp.setdefault((r["source"],r["respondent_id"]),{"r":r,"all":0,"ok":[]}); d["all"]+=1
    if ok(r): d["ok"].append(norm(json.loads(r["raw_json"])))
head=["source","페르소나ID","직업","감사원 역할","통과/전체","집계 포함","종합A(PFA기준)","종합B(PFA기준)","종합A(단순비례)","종합B(단순비례)"]
out=[]
for (src,pid),d in sorted(pp.items()):
    inc=len(d["ok"])>=(MIN_PASS if src.startswith("agent") else 1)
    res=person_result(d["ok"]) if d["ok"] else None
    f=lambda k,t: f"{res[k][t]:.3f}" if res else "-"
    out.append([src,pid,d["r"].get("occupation","") or "-",d["r"]["role"],f"{len(d['ok'])}/{d['all']}","포함" if inc else "제외",
                f("PFA기준",0),f("PFA기준",1),f("단순비례",0),f("단순비례",1)])
with open("페르소나별_결과.csv","w",newline="",encoding="utf-8-sig") as fo:
    wr=csv.writer(fo); wr.writerow(head); wr.writerows(out)
print("\n[페르소나별 결과] 아래는 탭 구분이라 엑셀·PPT 표에 그대로 붙여넣을 수 있다. 같은 내용을 페르소나별_결과.csv 에도 저장")
print("\t".join(head)); [print("\t".join(o)) for o in out]
