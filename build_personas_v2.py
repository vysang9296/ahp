"""Nemotron-Personas-Korea에서 직무별 페르소나를 '직업(occupation) 정확 일치'로 뽑는 스크립트.
- 원본 uuid를 남겨 재현할 수 있게 한다.
- 역할 문장은 모든 사람에게 같은 틀로 붙인다(선호·결론을 넣지 않는다).
사용법: pip install pyarrow pandas 후, 같은 폴더에 HF parquet(0~8.parquet)를 두고 python build_personas_v2.py
(parquet 주소: https://huggingface.co/api/datasets/nvidia/Nemotron-Personas-Korea/parquet)"""
import json, glob, pandas as pd

SEED = 42
PER_ROLE = 2
AGE_MIN, AGE_MAX = 30, 59
ROLE_OCC = {  # 'occupation' 값과 정확히 일치. '전직 …, 현재 구직중'은 뺀다.
    "감사": ["감사 사무원", "회계사"],
    "정보화": ["정보 시스템 운영자", "컴퓨터 시스템 감리 전문가", "정보 통신 컨설턴트", "컴퓨터 시스템 설계 및 분석가"],
    "보안·법무": ["정보 보안 전문가", "변호사", "법무사"],
    "예산·기획": ["공공행정 전문가", "중앙정부 고위 공무원", "국가행정 사무원"],
}
ROLE_DESC = {
 "감사": "일반 감사 업무(기관 정기감사, 재무·성과 감사, 감사보고서 작성)",
 "정보화": "정보화 업무(전산 시스템 운영, 정보화 사업 기획·관리)",
 "보안·법무": "보안·법무 업무(정보보안, 개인정보 보호, 법령·규정 검토)",
 "예산·기획": "예산·기획 업무(예산 편성, 사업 기획, 중복투자 심의 대응)"
}
ROLE_CARD = "위 배경의 경력을 가진 이 사람은 지금 감사원에서 {desc}를 맡고 있는 직원이다. 자신의 경력과 맡은 업무의 관점에서 판단한다."  # 감사원 직원 입장으로 통일(사람 응답자와 같은 입장)
COLS = ["uuid", "persona", "professional_persona", "occupation", "age", "sex", "province", "district"]

df = pd.concat([pd.read_parquet(f, columns=COLS) for f in sorted(glob.glob("[0-9].parquet"))], ignore_index=True)
df = df[(df.age >= AGE_MIN) & (df.age <= AGE_MAX)]
out, used, idx = [], set(), 1
for role, occs in ROLE_OCC.items():
    pool = df[df.occupation.isin(occs) & ~df.uuid.isin(used)].sort_values("uuid")
    picks = pool.sample(n=PER_ROLE, random_state=SEED)
    for _, r in picks.iterrows():
        used.add(r.uuid)
        bg = f"{r.age}세 {r.sex}, {r.province} {r.district} 거주. 직업: {r.occupation}. {r.persona} {r.professional_persona}"
        out.append({"id": f"P{idx:02d}", "role": role, "nemotron_uuid": r.uuid, "occupation": r.occupation,
                    "pool_size": int(len(pool)), "persona": bg + " " + ROLE_CARD.format(desc=ROLE_DESC[role])})
        idx += 1
with open("personas.jsonl", "w", encoding="utf-8") as f:
    for o in out: f.write(json.dumps(o, ensure_ascii=False) + "\n")
print(f"{len(out)}명 저장")
