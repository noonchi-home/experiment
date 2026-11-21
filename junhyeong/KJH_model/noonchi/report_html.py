"""run_coffee.py 결과 -> report.html. 고른 task와 그 근거(트리거 확률, 믿음, 문턱, 허브 응답, FSM 수정)를 한 장에 보인다.

외부 파일·라이브러리 없이 HTML 하나로 만든다(브라우저로 바로 연다). 화면 문구는 한국어다.
"""
from __future__ import annotations

from html import escape

from .lora import LORA, ask_cost, group_gain_cost, trigger_gain_cost
from .trigger_pomdp import clock


def _thr(gain_cost: tuple[float, float]) -> float:
    g, c = gain_cost
    return c / (g + c)


# 문턱은 config/lora.json에서 계산한다(화면 문구가 설정과 어긋나지 않게)
TRIG_THR, TASK_THR, MON_THR = _thr(trigger_gain_cost()), _thr(group_gain_cost("task")), _thr(group_gain_cost("monitoring"))
TRIG_GAIN, TRIG_COST = trigger_gain_cost()
ASK_COST = ask_cost()

# 판단 용어(threshold, fired, belief 등)는 영어 그대로 쓴다(번역어보다 코드·논문 용어와 바로 이어진다)
OP_KO = {"add": "add", "remove": "remove"}
GROUP_KO = {"task": "task (A_T)", "monitoring": "monitoring (A_M)", "communication": "communication (A_C)"}

CSS = """
:root { --bg:#f7f7f5; --card:#fff; --fg:#1d1d1f; --muted:#6b6b70; --line:#e3e3e0; --accent:#2f6fde;
        --ok:#1f8a4c; --warn:#b26a00; --bad:#c0392b; --bar:#cfdcf5; --barfill:#2f6fde; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#151517; --card:#1f1f22; --fg:#ececee; --muted:#9a9aa2; --line:#33333a; --accent:#6d9cf0;
          --ok:#4cc27e; --warn:#e3a33a; --bad:#ef6b5b; --bar:#2b3550; --barfill:#6d9cf0; }
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.55 -apple-system, "Segoe UI", "Malgun Gothic", sans-serif; }
main { max-width:980px; margin:0 auto; padding:24px 16px 48px; }
h1 { font-size:24px; margin:0 0 4px; } h2 { font-size:19px; margin:32px 0 10px; } h3 { font-size:16px; margin:20px 0 8px; }
.muted { color:var(--muted); } .small { font-size:13px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; margin:10px 0; }
.badge { display:inline-block; padding:1px 8px; border-radius:999px; font-size:12px; border:1px solid var(--line); color:var(--muted); }
.badge.ok { color:var(--ok); border-color:var(--ok); } .badge.bad { color:var(--bad); border-color:var(--bad); }
.badge.warn { color:var(--warn); border-color:var(--warn); }
.task-title { font-weight:600; } .en { color:var(--muted); font-size:13px; }
.why { margin-top:6px; font-size:14px; } .why b { color:var(--accent); }
table { width:100%; border-collapse:collapse; font-size:14px; }
th, td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--line); vertical-align:top; }
th { color:var(--muted); font-weight:500; }
.num { font-variant-numeric:tabular-nums; white-space:nowrap; }
.bar { position:relative; height:10px; width:120px; background:var(--bar); border-radius:5px; display:inline-block; vertical-align:middle; }
.bar i { position:absolute; left:0; top:0; bottom:0; background:var(--barfill); border-radius:5px; }
.bar s { position:absolute; top:-3px; bottom:-3px; width:2px; background:var(--fg); opacity:.55; }
details { margin:12px 0; } summary { cursor:pointer; font-weight:600; font-size:16px; }
.scroll { overflow-x:auto; }
ul { margin:6px 0; padding-left:20px; }
.days { display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:10px; }
.days .card { margin:0; } .days h3 { margin:0 0 6px; }
.chip { display:inline-block; padding:1px 7px; margin:2px 3px 2px 0; border-radius:6px; font-size:13px; border:1px solid var(--line); }
.chip.ok { color:var(--ok); border-color:var(--ok); } .chip.bad { color:var(--bad); border-color:var(--bad); }
.chip.miss { color:var(--warn); border-color:var(--warn); border-style:dashed; }
.tabs { display:flex; gap:6px; margin:8px 0; flex-wrap:wrap; }
.tabs button { font:inherit; padding:5px 14px; border-radius:8px; border:1px solid var(--line); background:var(--card); color:var(--fg); cursor:pointer; }
.tabs button[aria-selected="true"] { border-color:var(--accent); color:var(--accent); font-weight:600; }
.js .daypanel { display:none; } .js .daypanel.on { display:block; }
.mark { font-size:12px; margin-left:4px; }
.belief .bar { width:64px; } .belief td.name { min-width:170px; } .belief td { padding:6px 5px; }
"""


def _f(x: float) -> str:
    return f"{x:.2f}"


def _p(x: float) -> str:
    """문턱과 견주는 확률은 세 자리로 적는다(0.20 > 0.20처럼 보이지 않게)."""
    return f"{x:.3f}"


def _short(label: str) -> str:
    return label.split(":")[0]


def _bar(p: float, threshold: float | None) -> str:
    line = f'<s style="left:{threshold * 100:.0f}%"></s>' if threshold is not None else ""
    return f'<span class="bar"><i style="width:{max(0, min(1, p)) * 100:.0f}%"></i>{line}</span>'


def _threshold(spec: dict) -> float:
    return spec["cost"] / (spec["gain"] + spec["cost"])


def _result(res: dict | None) -> str:
    """허브·로봇 응답 -> 한 줄."""
    if not res:
        return ""
    if res["via"] == "hub":
        state = ", ".join(f"{k}={v}" for k, v in res["state"].items())
        out = f"hub → {escape(res['device'])} {escape(res['command'])} · state: {escape(state)}"
    else:
        out = "robot → done" + (f" · photo {escape(res['photo'])}" if res.get("photo") else "")
    th = res.get("then")
    if th:
        out += f"<br>hub response <b>{escape(th['because'])}</b> → {escape(th['text'])}"
        r = th.get("result")
        if r and r["via"] == "hub" and "remaining_min" in r["state"]:
            out += f" → remaining {r['state']['remaining_min']} min"
        elif r and r.get("photo"):
            out += f" → photo {escape(r['photo'])}"
    return out


def _chosen_card(c: dict, tasks: list[str], labels: list[str], specs: list[dict]) -> str:
    i = c["task"]
    spec = specs[i]
    thr = _threshold(spec)
    why = (f"{clock(c['time'])}에 P(trigger) <b>{_p(c['p_trigger'])}</b> × belief <b>{_p(c['belief'])}</b> = P <b>{_p(c['p'])}</b>"
           f" &gt; threshold {_f(thr)} → EV {c['ev']:+.2f}")
    return (f'<div class="card"><div><span class="task-title">task {i}. {escape(labels[i])}</span> '
            f'<span class="badge">{GROUP_KO[spec["group"]]}</span></div>'
            f'<div class="en">{escape(tasks[i])}</div>'
            f'<div class="why">근거: {why}</div>'
            f'<div class="why small muted">실행: {_result(c.get("result"))}</div></div>')


def _trigger_table(day: dict) -> str:
    rows = []
    for w in day["windows"]:
        t = w["triggers"][0] if w["triggers"] else None
        if t is None:
            rows.append(f"<tr><td class='num'>{clock(w['time'])}</td><td colspan='4'>no trigger</td></tr>")
            continue
        fired = '<span class="badge ok">fired</span>' if t["fired"] else '<span class="muted">-</span>'
        base = "fired" if t["baseline"] else "-"
        picked = ", ".join(str(c["task"]) for c in w["chosen"]) or ""
        rows.append(f"<tr><td class='num'>{clock(w['time'])}</td><td>{escape(w.get('activity', ''))}</td>"
                    f"<td class='num'>{_bar(t['p'], t['threshold'])} {_f(t['p'])}</td><td>{fired}</td>"
                    f"<td class='muted'>{base}</td><td class='num'>{picked}</td></tr>")
    return ("<div class='scroll'><table><tr><th>시각</th><th>VLM activity</th><th>P(trigger) · 세로선 = threshold</th>"
            "<th>trigger</th><th>one-frame baseline</th><th>chosen task</th></tr>" + "".join(rows) + "</table></div>")


def _candidate_table(day: dict, labels: list[str], specs: list[dict], unrelated: float) -> str:
    """처음 믿음이 관계없는 task보다 높거나 고른 task만 보인다(나머지는 믿음이 낮아 고를 수 없음)."""
    cons = day["considered"]
    chosen = {c["task"]: c for w in day["windows"] for c in w["chosen"]}
    rows = []
    for i in sorted(cons, key=lambda k: (-cons[k]["p"], k)):
        r = cons[i]
        if i not in chosen and r["belief"] <= unrelated + 1e-9:
            continue
        thr = _threshold(specs[i])
        if i in chosen:
            verdict = f'<span class="badge ok">chosen {clock(chosen[i]["time"])}</span>'
        elif r["blocked"]:
            verdict = f'<span class="badge warn">blocked (hub)</span> <span class="small muted">{escape(r["blocked"])}</span>'
        else:
            verdict = f'<span class="badge">below threshold</span>'
        best = chosen[i] if i in chosen else r
        rows.append(f"<tr><td class='num'>{i}</td><td>{escape(_short(labels[i]))}</td><td>{specs[i]['group']}</td>"
                    f"<td class='num'>{_f(r['belief'])}</td><td class='num'>{_bar(best['p'], thr)} {_p(best['p'])}</td>"
                    f"<td class='num'>{_f(thr)}</td><td>{verdict}</td></tr>")
    skipped = len(specs) - len(rows)
    return ("<div class='scroll'><table><tr><th>#</th><th>task</th><th>group</th><th>belief</th>"
            "<th>P = P(trigger) × belief (chosen 시점, 아니면 하루 최고)</th><th>threshold</th><th>result</th></tr>" + "".join(rows) + "</table></div>"
            f"<p class='small muted'>나머지 {skipped}개는 FSM과 관계없는 task(belief {unrelated:.2f})라 어느 창에서도 threshold를 넘지 못했다.</p>")


def _night(day: dict, answer: set[int], labels: list[str]) -> str:
    chosen = set(day["chosen"])
    right, extra, missed = sorted(chosen & answer), sorted(chosen - answer), sorted(answer - chosen)
    li = [f"<li>answer 비교: right {right or '[]'} · extra {extra or '[]'} · missed {missed or '[]'}</li>"]
    for i, e in sorted(day["events"].items()):
        if e.get("acted"):
            what = "accepted (answer에 있음)" if e["accepted"] else "rejected (answer에 없음)"
        else:
            what = "self-done (안 골랐지만 answer에 있음)"
        li.append(f"<li>task {i} {escape(_short(labels[i]))}: {what} → belief <b>{_f(e['p'])}</b></li>")
    for d in day["decisions"]:
        if "asked" in d:
            li.append(f"<li><span class='badge'>ask (A_C)</span> task {d['asked']} {OP_KO[d['op']]} 제안: VOI {_f(d['voi'])} &gt; ask cost {_f(ASK_COST)} → "
                      f"answer <b>{'yes' if d['answer'] else 'no'}</b> → belief {_f(d['p'])}</li>")
        elif "applied" in d:
            li.append(f"<li><span class='badge ok'>applied</span> task {d['task']} {OP_KO[d['applied']]} "
                      f"(belief {_f(d['p'])}, EV {d['ev']:+.2f} &gt; 0)</li>")
        else:
            li.append(f"<li><span class='badge warn'>held</span> task {d['task']} {OP_KO[d['held']]} "
                      f"(belief {_f(d['p'])}, EV {d['ev']:+.2f} ≤ 0, 증거가 더 쌓이면 다시 봄)</li>")
    changed = day["rules_after"] != day["rules"]
    li.append(f"<li>FSM rules: {day['rules']} → <b>{day['rules_after']}</b>"
              + (" · trigger re-check" + (": no issues" if not day["recheck_issues"] else f": {len(day['recheck_issues'])} issue(s)")
                 if changed else " · kept") + "</li>")
    return "<ul>" + "".join(li) + "</ul>"


def _chips(day: dict, answer: set[int]) -> str:
    chosen = set(day["chosen"])
    out = [f'<span class="chip {"ok" if i in answer else "bad"}">{i} {"right" if i in answer else "extra"}</span>'
           for i in sorted(chosen)]
    out += [f'<span class="chip miss">{i} missed</span>' for i in sorted(answer - chosen)]
    return "".join(out) or "<span class='muted'>없음</span>"


def _night_summary(day: dict) -> str:
    """밤의 FSM edit을 한 줄씩 짧게."""
    li = []
    for d in day["decisions"]:
        if "asked" in d:
            li.append(f"ask: task {d['asked']} {d['op']}? → {'yes' if d['answer'] else 'no'}")
        elif "applied" in d:
            li.append(f"applied: {d['applied']} task {d['task']} (belief {_f(d['p'])})")
        else:
            li.append(f"held: {d['held']} task {d['task']} (belief {_f(d['p'])})")
    return "<ul class='small'>" + "".join(f"<li>{escape(x)}</li>" for x in li) + "</ul>" if li else "<p class='small muted'>FSM edit 없음</p>"


def _learning(days: list[dict], answer: set[int]) -> str:
    """날짜별 카드: 시작 FSM rules → chosen(right/extra/missed) → 밤의 FSM edit → FSM rules after."""
    cards = []
    for d in days:
        n_extra, n_miss = len(set(d["chosen"]) - answer), len(answer - set(d["chosen"]))
        state = ('<span class="badge ok">= answer</span>' if not n_extra and not n_miss
                 else f'<span class="badge">extra {n_extra} · missed {n_miss}</span>')
        cards.append(f"<div class='card'><h3>day {d['day']} {state}</h3>"
                     f"<div class='small muted'>FSM rules (시작) {d['rules']}</div>"
                     f"<div style='margin:6px 0'>{_chips(d, answer)}</div>"
                     f"<div class='small'><b>밤: FSM edit</b></div>{_night_summary(d)}"
                     f"<div class='small'>FSM rules after <b>{d['rules_after']}</b></div></div>")
    return f"<div class='days'>{''.join(cards)}</div>"


def _belief_table(days: list[dict], prior: dict[int, float], answer: set[int], labels: list[str], specs: list[dict]) -> str:
    """task마다 날짜별 시작 belief(그날 판단에 쓴 값)와 마지막 밤 뒤 belief. 세로선 = 그날 고를 수 있는 최소 belief
    (threshold / 그날 가장 큰 P(trigger)). 막대가 선을 넘어야 그날 고를 수 있다."""
    starts = [dict(prior)] + [d["belief"] for d in days[:-1]]
    rel = sorted(set(answer) | set(days[0]["rules"]) | {i for d in days for i in d["chosen"]})
    head = "".join(f"<th>day {d['day']} 시작</th>" for d in days) + f"<th>day {days[-1]['day']} 밤 뒤</th>"
    rows = []
    for i in rel:
        thr = _threshold(specs[i])
        cells = []
        for d, b in zip(days, starts):
            p_max = max((t["p"] for w in d["windows"] for t in w["triggers"]), default=0.0)
            need = min(1.0, thr / p_max) if p_max else 1.0
            mark = ("<span class='mark' style='color:var(--ok)'>✓</span>" if i in d["chosen"]
                    else "<span class='mark muted'>·</span>")
            cells.append(f"<td class='num' title='belief {b[i]:.3f}, 고를 수 있는 최소 belief {need:.2f}'>"
                         f"{_bar(b[i], need)} {_f(b[i])}{mark}</td>")
        last = days[-1]["belief"][i]
        cells.append(f"<td class='num'>{_bar(last, None)} {_f(last)}</td>")
        tag = "<span class='chip ok'>answer</span>" if i in answer else "<span class='chip'>not answer</span>"
        rows.append(f"<tr><td class='num'>{i}</td><td class='name'>{escape(_short(labels[i]))} {tag}</td><td>{specs[i]['group']}</td>{''.join(cells)}</tr>")
    return ("<div class='scroll'><table class='belief'><tr><th>#</th><th>task</th><th>group</th>" + head + "</tr>" + "".join(rows) + "</table></div>"
            "<p class='small muted'>✓ = 그날 chosen. 막대 = belief(거주자가 이 task를 원할 확률). 세로선 = 그날 고를 수 있는 최소 belief "
            "= threshold / 그날 가장 큰 P(trigger). answer에 있는 task는 accepted가 쌓여 오르고, 없는 task는 rejected·ask(no)로 내려간다.</p>")


def write_report(path, meta: dict, days: list[dict], tasks: list[str], labels: list[str], specs: list[dict],
                 answer: set[int], unrelated: float, prior: dict[int, float]) -> None:
    last = days[-1]
    final = {c["task"]: {**c, "time": w["time"]} for w in last["windows"] for c in w["chosen"]}
    same = set(last["chosen"]) == answer
    verdict = ('<span class="badge ok">= answer</span>' if same else
               f'<span class="badge bad">≠ answer</span>')
    cards = "".join(_chosen_card(final[i], tasks, labels, specs) for i in sorted(final)) or "<p>chosen task가 없다.</p>"
    trg = days[0]["triggers"][0] if days[0]["triggers"] else None
    rule = escape(trg["rule"]) if trg else "no trigger"
    r = LORA["reward"]

    day_html = []
    for d in days:
        day_html.append(
            f"<section class='daypanel{' on' if d is days[0] else ''}' id='day{d['day']}'>"
            f"<h3 class='muted'>day {d['day']} · chosen {d['chosen']} · FSM rules after {d['rules_after']}</h3>"
            f"<h3>① trigger: 지금 도움이 필요한 상황(H)인가</h3>"
            f"<p class='small muted'>trigger 문장: {rule}<br>P(trigger) = 1[06:00~08:00] × P(kitchen) × P(drinking coffee). "
            f"EV = P·{TRIG_GAIN:g} − (1−P)·{TRIG_COST:g} &gt; 0 이면 fired (threshold {_f(TRIG_THR)}). "
            f"belief가 창마다 이어지므로 one-frame baseline(한 창의 VLM 보고만 믿음)보다 덜 흔들린다.</p>"
            f"{_trigger_table(d)}"
            f"<h3>② task 선택: 20개 중 무엇을 요청할까</h3>"
            f"<p class='small muted'>FSM rules {d['rules']}. belief는 FSM에서 시작하고(FSM rule 0.8, 다음 state를 돕는 task 0.5 × reach, 그 밖 {unrelated:.2f}) "
            f"밤마다 갱신된다. threshold는 group별: task {_f(TASK_THR)}, monitoring {_f(MON_THR)}. task마다 하루 한 번.</p>"
            f"{_candidate_table(d, labels, specs, unrelated)}"
            f"<h3>③ 하루 끝: answer와 비교해 FSM edit</h3>{_night(d, answer, labels)}</section>")
    tabs = "".join(f"<button role='tab' data-day='day{d['day']}' aria-selected='{'true' if d is days[0] else 'false'}'>day {d['day']}</button>"
                   for d in days)

    html = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Coffee_man 판단 리포트</title><style>{CSS}</style></head>
<body><main>
<h1>Coffee_man 판단 리포트</h1>
<div class="muted small">case {escape(meta['case'])} · hub start {escape(meta['hub'])} · {len(days)} days · 생성 {escape(meta['created'])}</div>

<h2>결과: day {last['day']} chosen tasks {verdict}</h2>
<p class="small muted">answer tasks {sorted(answer)} (data/Coffee_man/answer.json, 모델 입력이 아니며 하루가 끝난 뒤 비교에만 쓴다).
날마다 chosen: {' → '.join(str(d['chosen']) for d in days)}</p>

<h2>학습 과정: day 1 → day {last['day']}</h2>
<p class="small muted">같은 아침 영상을 날마다 다시 본다. 낮에 고른 task를 밤에 answer와 비교해 belief를 고치고, belief로 FSM rule을 add·remove 한다.
다음 날은 고친 belief와 FSM으로 시작한다.</p>
{_learning(days, answer)}
<h3>task별 belief 변화</h3>
{_belief_table(days, prior, answer, labels, specs)}

<h2>day {last['day']} output: chosen task와 근거</h2>
{cards}

<h2>날짜별 사고 과정</h2>
<div class="tabs" role="tablist">{tabs}</div>
{''.join(day_html)}

<h2>판단 기준</h2>
<div class="card small">
<p>Kostavelis 외, <i>A POMDP Design Framework for Decision Making in Assistive Robots</i>(HCI International 2017)의 틀:
state를 LoRA(Level of Robot Alert) H(도움 필요) / M(로봇 관여) / L(지켜보기)로 묶고, action을 task(A_T, 환경을 바꿈) / communication(A_C, 묻기) /
monitoring(A_M, 상태만 알아냄) group으로 나누고, LoRA를 낮추면 양수·높이면 음수인 reward를 준다(config/lora.json).</p>
<table><tr><th>결정</th><th>상황이 맞을 때 (gain)</th><th>틀렸을 때 (cost)</th><th>threshold P = cost / (gain + cost)</th></tr>
<tr><td>trigger fire</td><td>H→M {r['H']['M']:+.2f}</td><td>L→M {r['L']['M']:+.2f}</td><td>{_f(TRIG_THR)}</td></tr>
<tr><td>task (A_T)</td><td>H→L {r['H']['L']:+.2f}</td><td>L→H {r['L']['H']:+.2f}</td><td>{_f(TASK_THR)}</td></tr>
<tr><td>monitoring (A_M)</td><td>H→L {r['H']['L']:+.2f}</td><td>L→M {r['L']['M']:+.2f}</td><td>{_f(MON_THR)}</td></tr>
<tr><td>ask (A_C)</td><td>-</td><td>L→M {r['L']['M']:+.2f}</td><td>VOI &gt; ask cost {_f(ASK_COST)}이면 ask</td></tr></table>
<p class="muted">모든 판단은 한 단계 앞의 EV(expected value) = P·gain − (1−P)·cost &gt; 0 으로 정한다. 같은 입력이면 같은 결과가 나온다(VLM 관찰 이후).</p>
</div>
</main>
<script>
// 날짜 탭: JS가 없으면 모든 날이 차례로 보인다
document.body.classList.add("js");
document.querySelectorAll(".tabs button").forEach(b => b.addEventListener("click", () => {{
  document.querySelectorAll(".tabs button").forEach(x => x.setAttribute("aria-selected", x === b));
  document.querySelectorAll(".daypanel").forEach(p => p.classList.toggle("on", p.id === b.dataset.day));
}}));
</script>
</body></html>
"""
    path.write_text(html, encoding="utf-8")
