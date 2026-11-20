"""Build an offline paper walkthrough and experiment presentation from saved evidence."""
from pathlib import Path
import base64
import json
import html
import re
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "presentation" / "PAM_논문리뷰_실험발표.html"
RUN = ROOT / "artifacts/stage3_morning_reflection_reduced"

def asset(relative):
    p = ROOT / relative
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()

report = json.loads((RUN / "report.json").read_text(encoding="utf-8"))
stages = {s["id"]: s for s in report["stages"]}
updated_memory = json.loads((RUN / "memory_store/versions/001_2026-10-25.json").read_text(encoding="utf-8"))
morning_state = next(s for s in updated_memory["states"] if s["id"] == "morning_started")
cases = [("seated_without_milk", "식탁 착석 · 우유 없음", 0),
         ("seated_with_milk", "식탁 착석 · 우유 있음", -1)]
labels = {-1: "대기", 0: "우유 가져오기"}
rows = []
for case, name, expected in cases:
    actual = stages["after_" + case]["task_index"]
    correct = actual == expected
    rows.append(f'<tr><th>{name}</th><td>{labels[expected]}</td><td>{labels[actual]}</td><td class="{"good" if correct else "bad"}">{"성공 ✓" if correct else "실패 ✕"}</td></tr>')

tokens = {
    "OVERVIEW": asset("reference/PAM/docs/static/images/fig2_overview.png"),
    "FSM": asset("reference/PAM/docs/static/images/fig3_pam.png"),
    "NO_MILK": asset("data/morning_3d_v1/camera_frames/seated_without_milk/0008_right.png"),
    "MILK": asset("data/morning_3d_v1/camera_frames/seated_with_milk/0008_right.png"),
    "ROWS": "".join(rows),
    "MEMORY_EXAMPLE": html.escape(json.dumps({"rules": morning_state["rules"], "next": morning_state["next"]}, ensure_ascii=False, indent=2)),
}
for index in range(5):
    tokens[f"FRAME{index}"] = asset(f"artifacts/stage3_morning_reflection_reduced/after_seated_without_milk/prepared/frames/frame_{index:03d}.png")

document = r'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PAM 논문 리뷰와 아침 습관 실험</title>
<style>
:root{--ink:#182d3e;--muted:#667985;--paper:#f4f5f0;--teal:#087f78;--pale:#e4f3ef;--red:#b3473b;--line:#dbe2df;--white:#fff;--gold:#ca9137}
*{box-sizing:border-box}body{margin:0;font-family:"Malgun Gothic","Segoe UI",sans-serif;background:var(--paper);color:var(--ink)}
button,a{touch-action:manipulation}button{font:inherit;cursor:pointer}button:focus-visible,a:focus-visible{outline:3px solid var(--gold);outline-offset:4px}
.app{height:100dvh;display:grid;grid-template-rows:54px minmax(0,1fr) auto 54px;max-width:1600px;margin:auto}
header{display:flex;align-items:center;justify-content:space-between;padding:0 42px;border-bottom:1px solid var(--line);font-size:12px;letter-spacing:.1em}header strong{color:var(--teal)}
.top-meta{color:var(--muted);letter-spacing:0}main{min-height:0;overflow:auto}.slide{display:none;padding:25px 42px 20px;min-height:100%}.slide.active{display:flex;flex-direction:column;gap:16px}
.eyebrow{font-size:12px;font-weight:800;letter-spacing:.11em;color:var(--teal)}h1,h2,h3,p{margin:0}h1{font-size:clamp(35px,4.3vw,62px);line-height:1.17;letter-spacing:-.05em}h2{font-size:clamp(26px,3vw,40px);line-height:1.25;letter-spacing:-.045em}h3{font-size:20px;line-height:1.4}p{line-height:1.65}.lead{font-size:19px;color:var(--muted)}.small{font-size:12px;line-height:1.6;color:var(--muted)}.source{font-size:11px;line-height:1.5;color:var(--muted);margin-top:auto}a{color:var(--teal);text-underline-offset:3px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:22px}.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.panel{background:var(--white);border:1px solid var(--line);border-radius:15px;padding:21px}.tint{background:var(--pale);border-color:#c7e4dc}.dark{background:var(--ink);color:white;border:0}.dark .small{color:#bdcecf}.accent{color:var(--teal)}.tag{display:inline-block;border-radius:6px;background:var(--pale);color:var(--teal);padding:5px 10px;font-size:12px;font-weight:700}.tag.warn{color:var(--red);background:#fae9e5}.number{font-size:49px;font-weight:800;letter-spacing:-.04em}.arrow{color:var(--teal);font-size:28px;font-weight:700}.hero{display:grid;grid-template-columns:1.15fr .85fr;gap:35px;align-items:center;flex:1}.hero h1{margin:15px 0 23px}.paper-title{font-size:18px;line-height:1.5;max-width:650px}.question{font-size:29px;line-height:1.55;letter-spacing:-.04em}.hero-cards{display:grid;gap:14px}.hero-cards .panel{padding:23px}.mini-label{font-size:12px;font-weight:800;letter-spacing:.07em;margin-bottom:9px;color:var(--muted)}
.overview{background:white;border-radius:12px;border:1px solid var(--line);padding:10px;text-align:center}.overview img{width:100%;max-height:230px;object-fit:contain}.flow{display:flex;align-items:center;gap:10px}.flow .panel{flex:1;text-align:center;padding:15px 10px;font-size:16px}.flow b{display:block;margin-bottom:5px}.flow .small{font-size:12px}.fsm-layout{display:grid;grid-template-columns:300px 1fr;gap:25px}.fsm-image{background:white;border-radius:12px;padding:10px;text-align:center}.fsm-image img{height:325px;max-width:100%;object-fit:contain}.stack{display:grid;gap:13px}.example{display:grid;grid-template-columns:1fr 40px 1fr;align-items:center;gap:10px}.example .panel{padding:15px}.example p{font-size:17px}.review-line{font-size:15px;line-height:1.65;padding:14px 18px;border-left:4px solid var(--teal);background:var(--pale)}
.film{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}.film figure{margin:0}.film img{display:block;width:100%;border-radius:8px;border:1px solid var(--line)}figcaption{font-size:11px;color:var(--muted);margin-top:5px;text-align:center}.compare{width:100%;border-collapse:collapse;font-size:15px}.compare th,.compare td{padding:11px 13px;text-align:left;border-bottom:1px solid var(--line);line-height:1.4}.compare thead{background:#e8edeb}.compare th{font-weight:700}.pill-row{display:flex;gap:8px;flex-wrap:wrap}.pill{border:1px solid var(--line);border-radius:20px;padding:7px 13px;font-size:13px;background:white}.change{display:grid;grid-template-columns:1fr 38px 1fr;gap:14px;align-items:center}.change .panel{min-height:150px}.change p{font-size:23px;font-weight:700;line-height:1.5;margin-top:13px}.change .small{font-size:13px;font-weight:400;margin-top:9px}.feedback{font-size:16px;border-left:4px solid var(--gold);padding:12px 18px;background:#fff9ec}.code{font-family:Consolas,monospace;font-size:12px;line-height:1.6;background:#eaf0ed;padding:10px 13px;border-radius:8px;overflow-wrap:anywhere}.scene-card{margin:0;background:white;border:1px solid var(--line);border-radius:12px;overflow:hidden}.scene-card img{display:block;width:100%;height:145px;object-fit:contain;background:#e6e6e6}.scene-card figcaption{padding:9px;font-size:13px;color:var(--ink);margin:0;font-weight:700}.good{color:var(--teal)}.bad{color:var(--red)}.compare b{float:right}.result-head{display:flex;align-items:center;justify-content:space-between;gap:20px}.score{font-size:27px;white-space:nowrap;font-weight:800;letter-spacing:-.05em}.score span{color:var(--muted);font-size:16px;font-weight:400}.failure{display:grid;grid-template-columns:.9fr 1.1fr;gap:22px}.failure figure{margin:0;background:white;border:1px solid var(--line);border-radius:14px;padding:12px}.failure img{width:100%;height:260px;object-fit:contain}.quote{font-size:23px;font-weight:700;line-height:1.5}.failure .panel{padding:18px}.limits{font-size:14px;line-height:1.8}.links{display:flex;gap:20px;flex-wrap:wrap;font-size:12px}
.notes{margin:0 42px;border-top:1px solid #c6d5ce;background:#e9eeea;padding:12px 18px 14px;border-radius:9px 9px 0 0;max-height:175px;overflow:auto}.notes-label{font-size:11px;letter-spacing:.08em;font-weight:800;color:var(--teal);margin-bottom:6px}.notes-text{font-size:14px;line-height:1.8}.notes-text strong{color:var(--teal)}.notes[hidden]{display:none}.notes-source{display:none}footer{display:flex;align-items:center;gap:15px;padding:0 42px;position:relative}footer .progress{height:3px;position:absolute;left:0;bottom:0;background:var(--teal);transition:width .2s}.controls{display:flex;gap:7px;margin-left:auto}button{border:1px solid var(--line);background:white;color:var(--ink);border-radius:7px;padding:6px 12px;font-size:12px}button:hover{background:var(--pale)}button:disabled{opacity:.4;cursor:default}.count{font-size:13px;font-weight:800;letter-spacing:.08em}.time{font-size:12px;color:var(--muted)}
.cycle-banner{border:1px solid #a5ccc3;border-radius:13px;background:var(--pale);padding:15px 20px;line-height:1.7;font-size:19px;text-align:center}.cycle-steps{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.cycle-steps .panel{padding:22px}.cycle-steps h3{margin:7px 0 12px}.night{background:#1d3043;color:white}.night .mini-label,.night .small{color:#c5d8df}.cycle-tag{color:var(--teal);font-size:12px;font-weight:bold}.cycle-code{font-family:Consolas,monospace;font-size:17px;line-height:1.7;padding:16px;background:#e9f2ed;border-radius:10px}
.fsm-state{border:2px solid var(--teal);border-radius:13px;background:white;padding:15px 19px}.fsm-state h3{color:var(--teal);margin-bottom:9px}.fsm-event{text-align:center;font-size:16px;line-height:1.5;color:var(--muted)}.fsm-event b{color:var(--teal)}.fsm-definition{font-size:16px;line-height:1.6}.fsm-state .pill-row{margin-top:8px}
.app.notes-hidden{grid-template-rows:54px minmax(0,1fr) 54px}
.memory-demo{display:grid;grid-template-columns:1.05fr .95fr;gap:20px}.memory-demo .panel{padding:15px 19px}.memory-demo .scene-card img{height:175px}.demo-controls{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:12px}.demo-controls button[aria-pressed="true"]{background:var(--teal);color:white}.rule-line{font-size:19px;line-height:1.55}.memory-json{max-height:200px;overflow:auto;white-space:pre-wrap;font-size:11px}.memory-detail summary{cursor:pointer;font-size:12px;color:var(--teal)}.transition{font-size:15px;line-height:1.8;padding:11px 16px;background:#e8edeb;border-radius:9px}.demo-expect{font-size:23px;font-weight:800;margin:10px 0;color:var(--teal)}
@media(max-height:850px) and (min-width:801px){.slide{zoom:.82}.notes{max-height:145px}.notes-text{font-size:13px}}
@media(min-height:900px){.slide{padding-top:37px;gap:23px}.overview img{max-height:280px}.scene-card img{height:180px}.fsm-image img{height:390px}.failure img{height:320px}.notes{max-height:190px}.notes-text{font-size:16px}}
@media(max-width:800px){header,footer{padding-left:18px;padding-right:18px}.slide{padding:20px 18px}.notes{margin:0 18px;max-height:190px}.hero,.grid2,.failure{grid-template-columns:1fr}.hero{gap:18px}.hero-cards{grid-template-columns:1fr 1fr}.fsm-layout{grid-template-columns:180px 1fr;gap:13px}.fsm-image img{height:260px}.flow .panel{font-size:13px;padding:10px 6px}.scene-card img{height:110px}.compare{font-size:12px}.compare th,.compare td{padding:8px}.change p{font-size:18px}.top-meta{display:none}.result-head{align-items:start}.score{font-size:22px}.film{gap:3px}.question{font-size:24px}}
@media print{body{background:white}.app{display:block;height:auto}header,footer,.notes{display:none}.slide,.slide.active{display:flex;min-height:0;height:185mm;padding:10mm;page-break-after:always;gap:12px}.notes-source{display:block;font-size:11px;line-height:1.6;border-top:1px solid #ccc;padding-top:8px;margin-top:auto}.overview img{max-height:200px}.fsm-image img{height:260px}.scene-card img{height:115px}.failure img{height:210px}a{color:inherit}h1{font-size:40px}h2{font-size:28px}@page{size:A4 landscape;margin:5mm}}
</style></head><body><div class="app notes-hidden">
<header><strong>PAM / PAPER → EXPERIMENT</strong><span class="top-meta">논문 리뷰와 3D 아침 습관 실험 · 2026.10.24</span></header>
<main>
<section class="slide active" data-part="논문 소개 · 읽을 대본">
 <div class="eyebrow">01 / PAPER REVIEW</div>
 <div class="hero"><div><span class="tag">KAIST AI · CoRL 2026 논문</span><h1>로봇은 언제<br><span class="accent">먼저 도와야 할까?</span></h1><p class="paper-title">An Agentic Framework for Proactive Robots<br>with Procedural Assistance Memory</p><p class="small" style="margin-top:14px">Dohyun Lee, Minho Park 외 · arXiv:2610.21211v1</p></div>
 <div class="hero-cards"><div class="panel"><div class="mini-label">문제 · 같은 빈 접시, 다른 도움</div><p class="question">아직 먹기 전일까?<br>이미 다 먹은 뒤일까?</p><div class="pill-row" style="margin-top:15px"><span class="pill">식사 전 → 음식 제공</span><span class="pill">식사 후 → 접시 정리</span></div></div><div class="panel tint"><div class="mini-label">핵심 아이디어</div><h3>활동 단계와 개인의 습관을 기억해,<br>언제 어떤 도움을 줄지 판단한다.</h3></div></div></div>
 <p class="source">출처: 논문 p.1, Abstract 및 p.4, §3.2의 빈 그릇 예시를 접시로 풀어 설명 · <a href="../papers/2610.21211v1.pdf" target="_blank">논문 원문</a> · <a href="https://github.com/DAVIAN-Robotics/PAM" target="_blank">저자 공개 저장소</a></p>
 <div class="notes-source">제가 가져온 논문은 KAIST의 ‘절차적 도움 기억을 이용한 선제적 로봇 프레임워크’입니다. 이 논문이 해결하려는 문제를 예로 들면, 식탁에 빈 접시가 놓여 있다고 해보겠습니다. 아직 밥을 먹기 전이라면 음식을 가져다주는 것이 맞지만, 이미 다 먹은 뒤라면 접시를 치우는 것이 맞습니다. 겉으로 같은 장면이어도 필요한 도움은 반대인 것입니다. 지금 보이는 모습만으로는 이 사람이 무엇을 하려는지 판단하기 어렵고, 사람마다 습관도 다릅니다. 그래서 이 논문은 활동 단계와 개인의 반복 행동을 PAM이라는 기억에 저장하고, 현재 관찰과 함께 읽어 언제 어떤 도움을 줄지 판단합니다.</div>
</section>
<section class="slide" data-part="논문 구조 · 읽을 대본">
 <div class="eyebrow">02 / HOW IT WORKS</div><h2>지금은 행동을 판단하고, 하루가 끝나면 기억을 고친다.</h2>
 <div class="overview"><img src="@@OVERVIEW@@" alt="논문 Figure 2. 행동 예측기, 로봇 실행기, 하루 종료 후 기억 수정 모듈의 구조"></div>
 <div class="flow"><div class="panel"><b>최근 사진 + PAM</b><span class="small">개인의 도움 절차 기억</span></div><span class="arrow">→</span><div class="panel tint"><b>VLM 행동 판단</b><span class="small">사진과 글을 이해하는 모델</span></div><span class="arrow">→</span><div class="panel"><b>행동 또는 대기</b><span class="small">논문에서는 로봇이 실행</span></div></div>
 <div class="grid2"><p class="review-line"><b>현재 판단:</b> 최근 8초의 5개 시점<br><span class="small">각 시점의 두 카메라 사진을 좌우로 결합 · Thinking OFF</span></p><p class="review-line"><b>하루 종료 후 자기반성:</b> 200개 시점으로 기억 수정<br><span class="small">기존 기억과 하루 기록 참고 · Thinking ON · 다음 날 적용</span></p></div>
 <p class="source">출처: 논문 Figure 2, §3.1–3.3 및 부록 구현 설정. 그림의 1 Hz는 논문의 설정이며, 우리 실험의 실시간 처리 성능을 뜻하지 않음.</p>
 <div class="notes-source">구조는 두 흐름으로 나뉩니다. 먼저 사진과 글을 함께 이해하는 모델인 VLM이 최근 사진과 기존 기억을 보고, 지금 할 행동이나 대기를 고릅니다. 입력은 최근 8초에서 뽑은 다섯 개 시점이며, 각 시점의 두 카메라 사진을 붙여 사용합니다. 논문에서는 선택한 행동을 별도의 로봇 실행기가 수행합니다. 하루가 끝나면 같은 계열의 모델이 하루 기록을 돌아보고 기억을 수정합니다. 이것이 자기반성이며, 수정된 기억은 다음 날 판단에 사용됩니다.</div>
</section>
<section class="slide" data-part="FSM과 PAM의 관계 · 읽을 대본">
 <div class="eyebrow">03 / FSM → PAM</div><h2>PAM은 FSM 구조로 도움의 맥락을 기억한다.</h2>
 <p class="fsm-definition"><b>FSM(Finite-State Machine, 유한 상태 기계)</b>: 활동을 몇 개의 <b>상태</b>로 나누고, 관찰된 사건에 따라 다음 상태로 <b>전이</b>하도록 표현한 구조.</p>
 <div class="fsm-layout"><div class="fsm-image"><img src="@@FSM@@" alt="논문 Figure 3 원본: 식사 준비, 식사, 정리, 떠남의 상태와 전이"><p class="small">논문 Figure 3 원본</p></div><div class="stack">
 <div class="fsm-state"><h3>상태: 식사 준비</h3><p><b>도움 조건</b> · 사람이 앉음<br><b>선택할 행동</b> · 시리얼 가져오기</p><div class="pill-row"><span class="pill">이 규칙은 식사 준비라는 맥락 안에 있다.</span></div></div>
 <div class="fsm-event">↓ <b>전이 조건: 사람이 숟가락을 집음</b><br><span class="small">관찰된 사건이 다음 활동 단계를 알려준다.</span></div>
 <div class="fsm-state"><h3>다음 상태: 식사 중</h3><p>현재 활동 단계에 맞는 도움 규칙을 참고한다.</p></div>
 <p class="review-line"><b>왜 단계가 필요할까?</b><br>같은 빈 그릇도 <b>식사 전에는 음식 제공</b>, <b>식사 후에는 정리</b>의 단서가 될 수 있다.</p></div></div>
 <p class="review-line"><b>FSM은 기억을 정리하는 구조, VLM은 행동을 판단하는 모델.</b><br>프로그램이 현재 상태 하나를 고정해 규칙만 실행하는 방식이 아니다. VLM이 상태·도움 규칙·전이 전체와 최근 사진을 함께 읽는다.</p>
 <p class="source">출처: 논문 p.4, §3.2 및 Figure 3. 오른쪽은 원본의 ‘앉음 → 시리얼’, ‘숟가락 집기 → 식사 단계’를 풀어 그린 예시. 논문의 장점은 모델 재학습 없이 기억을 수정해 적응한다는 점.</p>
 <div class="notes-source">여기서 중요한 것이 FSM, 즉 유한 상태 기계입니다. 활동을 몇 개의 상태로 나누고, 관찰된 사건에 따라 다음 상태로 넘어가도록 표현하는 구조입니다. PAM은 이 구조 안에 도움 조건과 행동도 저장합니다. 논문의 예시를 보면, 식사 준비라는 상태에서 사람이 앉으면 시리얼을 가져옵니다. 이것은 도움 규칙입니다. 반면 사람이 숟가락을 집으면 식사 중 상태로 넘어갑니다. 이것은 단계 전이입니다. 이 상태 구분이 앞서 말한 빈 접시의 모호함을 줄여줍니다. 다만 FSM이 혼자 행동을 결정하는 것은 아닙니다. 사진과 글을 이해하는 VLM이 이 기억 전체와 최근 사진을 함께 읽고 실제 행동을 고릅니다. 따라서 FSM은 기억의 구조이고, VLM은 판단하는 모델이라고 이해하면 됩니다.</div>
</section>
<section class="slide" data-part="낮의 처리: 사진과 기억에서 행동으로 · 읽을 대본">
 <div class="eyebrow">04 / DURING THE DAY</div><h2>사진만 보내는 것이 아니라, FSM 형태의 기억도 함께 보낸다.</h2>
 <div class="film"><figure><img src="@@FRAME0@@" alt="0초의 두 카메라 사진"><figcaption>0초</figcaption></figure><figure><img src="@@FRAME1@@" alt="2초의 두 카메라 사진"><figcaption>2초</figcaption></figure><figure><img src="@@FRAME2@@" alt="4초의 두 카메라 사진"><figcaption>4초</figcaption></figure><figure><img src="@@FRAME3@@" alt="6초의 두 카메라 사진"><figcaption>6초</figcaption></figure><figure><img src="@@FRAME4@@" alt="8초의 두 카메라 사진"><figcaption>8초</figcaption></figure></div>
 <div class="cycle-steps"><div class="panel"><div class="mini-label">입력 1 · 최근 관찰</div><h3>8초 동안의 5개 시점</h3><p>사람의 위치와 행동,<br>물건의 위치·사용 여부</p></div><div class="panel tint"><div class="mini-label">입력 2 · PAM</div><h3>FSM 형태의 기억 전체</h3><p>활동 단계 + 도움 조건·행동<br>+ 단계가 바뀌는 사건</p></div><div class="panel"><div class="mini-label">두 입력을 함께 해석</div><h3>VLM이 행동 선택</h3><p>현재 장면에서 도움이 필요한가?<br>지금 실행 가능한 행동인가?</p></div></div>
 <div class="cycle-banner"><b>최근 사진 + PAM + 고정 지시문 → VLM → 행동 문장 또는 대기</b><br><span class="small">우리 장면의 예: 식탁 착석 + 우유 없음 → “우유를 사용자 곁에 가져다놓기”</span></div>
 <div class="grid2"><p class="review-line"><b>논문:</b> 행동 문장 → 로봇 실행기가 실제 동작</p><p class="review-line"><b>우리 실험:</b> 행동 문장 → 화면에 표시하고 정답과 비교</p></div>
 <p class="source">처리 구조: 논문 §3.1–3.2와 부록. 위 사진은 설명을 위해 사용한 우리 3D 실험의 실제 입력이며, 논문 원본 사진이 아니다. 이 슬라이드는 모델을 새로 호출하지 않는다.</p>
 <div class="notes-source">이제 실제 판단이 어떻게 나오는지 보겠습니다. 먼저 최근 8초에서 다섯 개 시점의 사진을 가져옵니다. 이 사진들과 함께, 앞서 설명한 FSM 형태의 PAM을 글로 모델에 넣습니다. 즉, 현재 보이는 상황과 그 사람이 평소 어떤 단계에서 어떤 도움을 필요로 했는지를 동시에 제공하는 것입니다. 사진과 글을 이해하는 VLM은 둘을 함께 읽고 지금 도움이 필요한지, 어떤 행동을 할 수 있는지 판단합니다. 우리 장면으로 보면 사람이 식탁에 앉았고 우유가 없을 때 ‘우유를 가져오기’라는 결과가 나오는 식입니다. 필요하지 않으면 대기를 선택합니다. 논문은 이 결과를 로봇 실행기에 전달하지만, 우리는 행동 문장을 출력하는 데서 멈추고 맞는 판단인지 확인합니다.</div>
</section>
<section class="slide" data-part="하루 종료 후: 자기반성과 기억 수정 · 읽을 대본">
 <div class="eyebrow">05 / END-OF-DAY REFLECTION</div><h2>밤에는 하루 기록을 돌아보고, 놓친 도움을 기억에 반영한다.</h2>
 <div class="cycle-steps"><div class="panel"><div class="mini-label">자기반성에 넣는 자료</div><h3>하루의 관찰과 기록</h3><p>하루 영상에서 고른 사진<br>기존 PAM<br>사람·로봇의 행동 요약<br>사용자 피드백이 있으면 함께</p><p class="small" style="margin-top:10px">논문 설정: 200개 시점</p></div><div class="panel night"><div class="mini-label">VLM 자기반성 · 추론 사용</div><h3>놓친 도움과 반복 패턴 검토</h3><p>사람이 직접 한 행동 중<br>미리 도울 수 있었던 것은?<br>기존 조건이 습관과 맞는가?</p></div><div class="panel tint"><div class="mini-label">출력 · 수정된 PAM</div><h3>기억 내용을 추가·수정</h3><p>활동 상태<br>도움 조건과 행동<br>상태 사이의 전이</p><p class="small" style="margin-top:10px">모델 가중치를 다시 학습하는 과정이 아님</p></div></div>
 <div class="panel"><div class="mini-label">논문 §3.3의 예시</div><h3>사람이 빈 그릇을 꺼낸 뒤 직접 시리얼을 붓는 장면을 관찰</h3><p style="margin-top:9px">→ “빈 그릇을 꺼내면 시리얼을 미리 가져다주면 되겠다”는 도움 규칙을 기억에 추가할 수 있다.</p></div>
 <div class="cycle-banner"><b>낮: 같은 PAM으로 판단</b> → <b>하루 종료: PAM 수정</b> → <b>다음 날: 수정된 PAM 사용</b></div>
 <p class="source">출처: 논문 p.5, §3.3. ‘밤’은 하루 활동 종료 후의 별도 처리 단계를 쉽게 표현한 말이며, 특정 시각에 자동 실행된다는 뜻이 아니다. 위 예시는 논문이 제시한 작동 원리로, 우리 실험의 새 성능 결과가 아니다.</p>
 <div class="notes-source">낮 동안에는 같은 기억을 사용하고, 하루가 끝나면 자기반성 단계로 넘어갑니다. 쉽게 말해 밤에 하루를 돌아보는 과정입니다. 모델은 하루 영상에서 고른 사진, 기존 PAM, 사람과 로봇의 행동 기록을 받고, 사용자 피드백이 있으면 그것도 참고합니다. 여기서 사람이 직접 수행한 행동을 보고 로봇이 미리 도울 수 있었던 순간을 찾습니다. 논문에서는 사람이 빈 그릇을 꺼낸 뒤 시리얼을 붓는 장면을 예로 듭니다. 이 기록을 보고 빈 그릇을 꺼낼 때 시리얼을 가져다주자는 규칙을 만들 수 있습니다. 필요하면 기존 조건뿐 아니라 활동 단계나 단계 사이의 연결도 수정합니다. 바뀌는 것은 모델 자체가 아니라 모델이 읽는 PAM의 내용입니다. 이 수정된 기억은 다음 날부터 사용합니다.</div>
</section>
<section class="slide" data-part="다음 날: 갱신된 기억을 사용하는 실제 예시 · 읽을 대본">
 <div class="eyebrow">06 / THE NEXT DAY</div><h2>다음 날에도 같은 판단 과정을 쓰지만, 참고하는 기억이 달라진다.</h2>
 <div class="change"><div class="panel"><span class="tag">저자 공개 예시 · 1일차 기억</span><p>그릇을 책상에 놓음<br>→ 시리얼 가져오기</p><p class="small">식사 준비 단계의 도움 규칙</p></div><span class="arrow">→</span><div class="panel tint"><span class="tag">저자 공개 예시 · 2일차 기억</span><p>그릇을 책상에 놓음<br><b>또는 책상에 앉음</b><br>→ 시리얼 가져오기</p><p class="small">같은 도움을 시작할 수 있는 조건이 추가됨</p></div></div>
 <div class="panel"><div class="mini-label">같은 2일차 공개 기억에 추가된 다른 규칙</div><h3>시리얼을 그릇에 부음 → 우유 가져오기</h3><p class="small" style="margin-top:8px">기억 수정에는 기존 조건의 보완뿐 아니라 새로운 도움 규칙의 추가도 포함된다.</p></div>
 <div class="cycle-banner"><b>다음 날의 새 사진 + 갱신된 FSM 형태의 PAM → VLM → 그 상황에 맞는 행동</b></div>
 <p class="review-line">한 장면을 보고 끝나는 시스템이 아니라, <b>관찰 → 판단 → 기록 → 기억 수정 → 다음 판단</b>이 이어지는 구조다.</p>
 <p class="source">출처: 저자 공개 저장소 docs/static/data/pam-fsm.json의 day1·day2. 공개 시각화용 기억을 한국어로 요약했으며, 우리 실험의 결과가 아니다. 이 화면의 변화가 모든 장면의 성능 향상을 보장하는 것은 아니다.</p>
 <div class="notes-source">수정된 기억을 다음 날 다시 사진과 함께 넣으면, 판단에 참고하는 조건이 달라집니다. 저자가 공개한 기억 변화 예시를 보면, 1일차에는 사람이 그릇을 책상에 놓을 때 시리얼을 가져오도록 되어 있습니다. 2일차에는 사람이 책상에 앉는 경우도 같은 도움의 조건으로 추가됩니다. 또 시리얼을 그릇에 부으면 우유를 가져오라는 규칙도 새로 생깁니다. 즉, 같은 모델을 사용하더라도 읽는 기억이 달라지면서 도움을 판단할 수 있는 상황이 늘어나는 것입니다. 전체 흐름은 사진을 보고 판단하고, 하루 기록을 돌아보며 기억을 고친 뒤, 다음 날 그 기억을 다시 사용하는 순환입니다. 이제 이 구조를 우리 아침 식사 상황에 어떻게 적용했는지 보겠습니다.</div>
</section>
<section class="slide" data-part="PAM의 구체적인 적용 예시 · 말할 키워드">
 <div class="eyebrow">07 / PAM EXAMPLE</div><h2>우리 PAM에는 어떤 기억이 들어 있을까?</h2>
 <p class="small">식탁에 앉은 장면부터 판단한다. 저장된 우유 규칙을 한국어로 풀어쓴 예시. 오른쪽 버튼으로 조건을 비교할 수 있다.</p>
 <div class="memory-demo"><div class="stack"><div class="panel dark"><div class="mini-label" style="color:#bdcecf">상황 · 식탁에 앉아 식사를 준비하는 단계</div><p class="rule-line">“다른 음식이 바뀌어도<br>아침에는 우유를 마시는 사람이다.”</p></div><div class="panel tint"><div class="mini-label">도움 조건 → 행동</div><p class="rule-line"><b>식탁에 앉음</b> + <b>곁에 우유 없음</b><br>+ 우유를 잡거나 만지지 않음<br><span class="accent"><b>→ 우유를 사용자 곁으로 가져오기</b></span></p></div><div class="transition"><b>FSM의 전이 조건 · 다음 단계로 넘어가는 사건</b><br>사람이 식탁에서 먹거나 마시기 시작함<br>→ <b>아침 식사 중</b> 단계</div></div><div class="panel"><div class="demo-controls"><button type="button" data-demo="0" aria-pressed="true">착석 · 우유 없음</button><button type="button" data-demo="1" aria-pressed="false">착석 · 우유 있음</button></div><figure class="scene-card"><img id="demoImage" src="@@NO_MILK@@" alt="식탁에 앉았고 곁에 우유가 없는 장면"><figcaption id="demoCaption">식탁에 앉음 · 우유는 주방에 있음</figcaption></figure><div class="demo-expect" id="demoExpected">규칙에 따른 기대 행동: 우유 가져오기</div><p class="small" id="demoReason">사진을 올바르게 읽으면 도움 조건이 충족된다.</p><p class="small" style="margin-top:9px"><b>이 화면은 규칙 설명용 예시입니다.</b><br>실제 모델은 ‘우유 있음’ 장면에서도 오답을 냈으며, 뒤의 결과표에 표시합니다.</p></div></div>
 <details class="memory-detail"><summary>실제로 저장된 PAM 일부 보기 — 도움 규칙·전이</summary><pre class="code memory-json">@@MEMORY_EXAMPLE@@</pre></details>
 <p class="source">출처: 저장된 실험 기억에서 우유의 도움 규칙(rules)과 다음 단계로 넘어가는 조건(next)을 그대로 발췌. 버튼은 저장된 사진과 기대 행동만 바꾸며, 모델을 새로 호출하지 않음.</p>
 <div class="notes-source"><strong>말할 키워드</strong> · 앞 화면의 FSM을 아침 식사에 적용 · 실제 저장된 PAM을 한국어로 해석 · 시작 장면: 식탁에 앉아 식사 준비 · 기억: 메뉴가 바뀌어도 우유를 마시는 습관 · 조건: 식탁 착석 + 우유 없음 + 잡고 있지 않음 · 행동: 우유 가져오기 · 전이: 먹거나 마시기 시작하면 식사 중 · 버튼으로 우유가 없는 경우와 있는 경우 비교 · ‘우유 있음 → 대기’는 기대 행동이며 실제 성공 결과가 아님</div>
</section>
<section class="slide" data-part="우리 실험 설계 · 말할 키워드">
 <div class="eyebrow">08 / OUR EXPERIMENT</div><h2>책상 보조를 아침 식사로, 로봇 동작을 글로 바꿨다.</h2>
 <div class="film"><figure><img src="@@FRAME0@@" alt="실제 판단 입력: 0초 두 카메라 결합 사진"><figcaption>0초</figcaption></figure><figure><img src="@@FRAME1@@" alt="실제 판단 입력: 2초"><figcaption>2초</figcaption></figure><figure><img src="@@FRAME2@@" alt="실제 판단 입력: 4초"><figcaption>4초</figcaption></figure><figure><img src="@@FRAME3@@" alt="실제 판단 입력: 6초"><figcaption>6초</figcaption></figure><figure><img src="@@FRAME4@@" alt="실제 판단 입력: 8초"><figcaption>8초</figcaption></figure></div>
 <p class="small">실제 API에 보낸 5장의 결합 사진. 각 사진 안에 좌·우 카메라가 함께 있다.</p>
 <table class="compare"><thead><tr><th>항목</th><th>논문</th><th>우리 실험</th></tr></thead><tbody><tr><th>환경 / 출력</th><td>실제 책상 / 로봇 실행</td><td>3D 아침 식사 / 행동 문장</td></tr><tr><th>판단과 기억</th><td>VLM + PAM + 자기반성</td><td>PAM을 참고한 행동 판단 결과를 제시</td></tr><tr><th>모델</th><td>Qwen3.5-27B</td><td>OpenRouter로 Qwen3.5-27B 호출</td></tr><tr><th>습관 / 시작 장면</th><td>여러 날의 경험을 기억에 반영</td><td>우유를 마시는 습관을 가정 / 식탁 착석</td></tr></tbody></table>
 <div class="pill-row"><span class="pill">우유 가져오기</span><span class="pill">컵을 싱크대로</span><span class="pill">접시를 싱크대로</span><span class="pill">또는 대기</span></div>
 <p class="source">발표에서는 저장된 실행 중 식탁 착석 두 조건을 제시. 컵·접시 정리는 행동 목록에 있으나 이번 결과에는 포함하지 않음. 원저자의 전체 로봇 코드를 그대로 실행한 실험은 아님.</p>
 <div class="notes-source"><strong>말할 키워드</strong> · 메뉴가 달라도 우유를 마시는 습관 가정 · 합성 3D 사진 · 두 카메라 × 다섯 시점 · OpenRouter 원격 호출 · 결과는 ‘우유 가져오기’ 같은 글 · 5일 학습 완료가 아니라 기존 기억을 직접 작성 · 식탁에 앉은 상태에서 우유 유무를 비교</div>
</section>
<section class="slide" data-part="식탁 착석 두 장면의 결과 · 말할 키워드">
 <div class="eyebrow">09 / TEST RESULTS</div><h2>식탁에 앉았을 때,<br>우유가 필요한 경우와 이미 있는 경우를 구분할까?</h2>
 <div class="grid2"><figure class="scene-card"><img id="resultNoMilk" src="@@NO_MILK@@" alt="식탁 의자에 앉았고 우유는 주방에 있는 평가 장면"><figcaption>우유 없음 → 기대 행동: 우유 가져오기</figcaption></figure><figure class="scene-card"><img id="resultMilk" src="@@MILK@@" alt="식탁 의자에 앉았고 우유가 식탁 위에 있는 평가 장면"><figcaption>우유 있음 → 기대 행동: 대기</figcaption></figure></div>
 <table class="compare"><thead><tr><th>장면</th><th>기대 행동</th><th>실제 모델 출력</th><th>판정</th></tr></thead><tbody>@@ROWS@@</tbody></table>
 <p class="review-line"><b>성공:</b> 식탁에 앉았고 우유가 없을 때 우유 가져오기를 선택했다.<br><span class="bad"><b>실패:</b> 우유가 이미 식탁 위에 있어도 다시 가져오기를 선택했다.</span></p>
 <p class="source">저장된 실제 API 응답 중 식탁 착석 두 조건을 제시. 새 실험을 실행한 결과가 아니며, 각 조건 1회 실행이다. 기억 수정의 전후 성능 비교나 자기반성 효과를 주장하지 않는다.</p>
 <div class="notes-source"><strong>말할 키워드</strong> · 시작은 식탁에 앉은 상태 · 우유가 없을 때: 가져오기 선택, 성공 · 이미 우유가 있을 때: 대기를 기대했지만 가져오기 선택, 실패 · 두 조건 각각 1회 실행 · 저장된 실제 응답을 사용 · 다음 화면에서 실패 장면의 모델 설명 확인</div>
</section>
<section class="slide" data-part="해석과 한계 · 말할 키워드">
 <div class="eyebrow">10 / WHAT WE LEARNED</div><h2>기억이 맞아도, 사진을 잘못 읽으면 행동은 틀린다.</h2>
 <div class="failure"><figure><img src="@@MILK@@" alt="실패 장면 확대. 흰색과 파란색 우유병이 사람 앞 식탁에 놓여 있다"><figcaption>실제 입력: 우유병은 사람 앞 식탁 위에 있다.</figcaption></figure><div class="stack"><div class="panel"><div class="mini-label">모델의 장면 설명 · 한국어 요약</div><p class="quote">“우유병은 주방 보관대에<br>남아 있다.”</p><p class="small" style="margin-top:12px">저장된 observation 응답이 우유 위치를 잘못 서술함.</p></div><div class="panel tint"><h3>도움 조건을 기억에 담아도,<br>정확한 장면 이해가 필요하다.</h3><p class="small" style="margin-top:8px">다음: 우유 위치·가림 정도를 달리한 장면 추가 → 반복 평가</p></div></div></div>
 <p class="limits"><b>해석 범위</b> · 단일 3D 환경의 식탁 착석 2조건 · 각 1회 실행 · 기존 습관을 가정한 기억 사용 · 실제 로봇과 정리 행동은 이번 비교에서 미검증</p>
 <div class="links"><a href="../artifacts/stage3_morning_reflection_reduced/결과모음.html" target="_blank">기존 실행 전체 기록 ↗</a><a href="../artifacts/stage3_morning_reflection_reduced/report.json" target="_blank">실행 결과 기록 ↗</a><a href="../records/실험일지.md" target="_blank">실험 일지 ↗</a><a href="../papers/2610.21211v1.pdf" target="_blank">논문 원문 ↗</a></div>
 <p class="source">사진만으로 오류의 내부 원인을 확정할 수는 없음. 우유 위치를 잘못 서술한 응답과 잘못된 행동 선택이 함께 관찰되었다는 결론.</p>
 <div class="notes-source"><strong>말할 키워드</strong> · 사진에는 우유가 식탁 위 · 모델 설명은 ‘주방에 있음’ · 기억에 적힌 조건과 장면 이해는 별개의 문제 · 논문의 기억 구조를 아침 식사 판단에 적용한 소규모 검증 · 다음에는 위치·가림·반복 실행을 늘려 확인</div>
</section>
</main>
<aside class="notes" aria-label="발표할 내용" hidden><div class="notes-label" id="noteLabel"></div><div class="notes-text" id="noteText"></div></aside>
<footer><span class="count" id="count">01 / 10</span><span class="time" id="time"></span><div class="controls"><button id="notesButton" aria-pressed="false" title="N 키">발표 메모 보기</button><button id="fullscreenButton" title="F 키">전체 화면</button><button id="prev" aria-label="이전 슬라이드">← 이전</button><button id="next" aria-label="다음 슬라이드">다음 →</button></div><div class="progress" id="progress"></div></footer>
</div>
<script>
const slides=[...document.querySelectorAll('.slide')]; let current=0;
const notes=document.querySelector('.notes'),notesButton=document.querySelector('#notesButton');
function show(index){current=Math.max(0,Math.min(slides.length-1,index));slides.forEach((s,i)=>s.classList.toggle('active',i===current)); const s=slides[current];document.querySelector('#noteLabel').textContent=s.dataset.part;document.querySelector('#noteText').innerHTML=s.querySelector('.notes-source').innerHTML;document.querySelector('#count').textContent=String(current+1).padStart(2,'0')+' / '+String(slides.length).padStart(2,'0');document.querySelector('#time').textContent=s.dataset.part.split(' · ')[0];document.querySelector('#prev').disabled=current===0;document.querySelector('#next').disabled=current===slides.length-1;document.querySelector('#progress').style.width=((current+1)/slides.length*100)+'%';document.querySelector('main').scrollTop=0;history.replaceState(null,'','#'+(current+1));}
const demoCases=[{src:document.querySelector('#resultNoMilk').src,caption:'식탁에 앉음 · 우유는 주방에 있음',action:'우유 가져오기',reason:'사진을 올바르게 읽으면 도움 조건이 충족된다.'},{src:document.querySelector('#resultMilk').src,caption:'식탁에 앉음 · 우유가 이미 식탁 위에 있음',action:'대기',reason:'‘곁에 우유가 없음’ 조건이 충족되지 않는다. 실제 모델은 이 장면을 오판했다.'}];
document.querySelectorAll('[data-demo]').forEach(button=>button.addEventListener('click',()=>{const index=Number(button.dataset.demo),example=demoCases[index];document.querySelectorAll('[data-demo]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));document.querySelector('#demoImage').src=example.src;document.querySelector('#demoImage').alt=example.caption;document.querySelector('#demoCaption').textContent=example.caption;document.querySelector('#demoExpected').textContent='규칙에 따른 기대 행동: '+example.action;document.querySelector('#demoReason').textContent=example.reason;}));
function toggleNotes(){notes.hidden=!notes.hidden;document.querySelector('.app').classList.toggle('notes-hidden',notes.hidden);notesButton.textContent=notes.hidden?'발표 메모 보기':'발표 메모 숨기기';notesButton.setAttribute('aria-pressed',String(!notes.hidden));}
async function fullscreen(){try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch(e){document.querySelector('#fullscreenButton').textContent='브라우저 F11 사용';}}
document.querySelector('#prev').onclick=()=>show(current-1);document.querySelector('#next').onclick=()=>show(current+1);notesButton.onclick=toggleNotes;document.querySelector('#fullscreenButton').onclick=fullscreen;
document.addEventListener('keydown',e=>{if(e.altKey||e.ctrlKey||e.metaKey||/INPUT|TEXTAREA/.test(e.target.tagName)||(e.key===' '&&e.target.tagName==='BUTTON'))return;if(['ArrowRight','PageDown',' '].includes(e.key)){e.preventDefault();show(current+1);}if(['ArrowLeft','PageUp'].includes(e.key)){e.preventDefault();show(current-1);}if(e.key.toLowerCase()==='n')toggleNotes();if(e.key.toLowerCase()==='f')fullscreen();if(e.key==='Home')show(0);if(e.key==='End')show(slides.length-1);});show((parseInt(location.hash.slice(1),10)||1)-1);
</script></body></html>'''

for key, value in tokens.items():
    document = document.replace("@@" + key + "@@", value)
assert "@@" not in document
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(document, encoding="utf-8")

class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []
    def handle_data(self, data):
        self.parts.append(data)
    def handle_starttag(self, tag, attrs):
        if tag == "br": self.parts.append("\n")

def plain(markup):
    parser = PlainText(); parser.feed(markup)
    return "".join(parser.parts).strip()

script_parts = ["PAM 논문 리뷰와 아침 습관 실험 — 발표 대본 및 키워드",
                "총 10개 화면 · 시간 제한 없음\n논문 부분은 읽을 대본, 우리 실험 부분은 말할 키워드입니다.\nHTML 화면 이동: ← → / 발표 메모: N / 전체 화면: F\n"]
sections = re.findall(r'<section\b[^>]*data-part="([^"]+)"[^>]*>(.*?)</section>', document, re.S)
assert len(sections) == 10
for index, (part, body) in enumerate(sections, 1):
    title = plain(re.search(r'<h[12][^>]*>(.*?)</h[12]>', body, re.S)[1])
    note = plain(re.search(r'<div class="notes-source">(.*?)</div>', body, re.S)[1])
    if "말할 키워드" in part:
        note = "\n".join("- " + phrase.strip() for phrase in note.replace("말할 키워드", "", 1).strip(" ·").split(" · "))
    script_parts.append(f"{'=' * 54}\n{index}번째 화면 | {title}\n{part}\n{'-' * 54}\n{note}\n")
SCRIPT = OUT.with_name("PAM_논문리뷰_실험발표_대본.txt")
SCRIPT.write_text("\n".join(script_parts), encoding="utf-8-sig")
# Keep earlier shared file links pointing to the latest presentation.
OUT.with_name("PAM_5분_발표.html").write_text(document, encoding="utf-8")
SCRIPT.with_name("PAM_5분_발표_대본.txt").write_text("\n".join(script_parts), encoding="utf-8-sig")
print(json.dumps({"file": str(OUT), "script": str(SCRIPT), "slides": len(sections), "time_limit": None,
                  "embedded_images": document.count("data:image/png;base64,"),
                  "bytes": OUT.stat().st_size}, ensure_ascii=False))
