# 간섭 민감도 기반 사람별 선제적 로봇 지원: 설계 명세 v0.1

> 용도: 구현 에이전트(Codex) 전달용 설계 문서
> 기반 시스템: PAM (Procedural Assistance Memory, KAIST 2026)
> 표기: **[확정]** 논의로 결정된 사항 / **[미정]** 구현 전 정해야 하거나 실험으로 정할 사항 / **[초기값]** 바꿔도 되는 설정값

---

## 0. 한 줄 요약

로봇이 **"언제, 무엇을"** 도울지는 PAM의 FSM 메모리가 정하고, **"어떤 방식으로"** 도울지는 사람마다 학습한 **간섭 민감도 w**와 **도움 선호 h**로 **밤에 미리** 정해둔다. 낮에는 정해둔 방식대로 바로 실행하고, 그날의 반응으로 밤에 w와 h를 갱신한다.

---

## 1. 기반 시스템: PAM

### 1.1 구성 요소 (원 논문 기준)

| 구성 요소 | 역할 | 비고 |
|---|---|---|
| Memory | 사람의 루틴을 FSM(JSON)으로 저장 | 상태 = 활동 단계, 상태별 (trigger, action) 규칙, 이벤트 기반 전이 |
| Task Predictor (VLM) | 최근 프레임 + 메모리 → 태스크 번호 또는 NO_ACT | 1Hz, 최근 5프레임(stride 2), thinking off |
| Executor (VLA) | 선택된 태스크를 로봇 동작으로 실행 | 태스크별로 파인튜닝된 원자 스킬 |
| Reflector (VLM) | 하루가 끝나면 영상·요약·피드백으로 메모리 수정 | 하루 1회, thinking on, 메모리는 하루 동안 고정 |

### 1.2 PAM 메모리 스키마 (원본)

```json
{
  "initial_state": "<state_id>",
  "states": [
    {
      "id": "<snake_case>",
      "description": "<one-sentence>",
      "rules": [
        {"trigger": "<NL statement>", "action": "Pick up <object> and place it <location>."}
      ],
      "next": [{"to": "<state_id>", "on": "<NL event>"}]
    }
  ]
}
```

`<location>` ∈ {`next to the person`, `in the designated storage area`, `in the trash can`}

### 1.3 PAM 규칙 제약 (유지) [확정]

- 규칙의 action은 영상에서 사람이 실제로 한 동작만 미러링한다.
- 트리거가 사람이 물건을 다루는 중인 상황이면, 그 물건 ≠ action 대상 물건.
- 트리거는 로봇 도움 여부와 무관하게 관찰되는 단서여야 한다.
- 사람이 들고 있거나 만지는 물건은 내려놓기 전까지 조작 불가.

### 1.4 PAM의 한계와 이 확장이 다루는 지점

| PAM의 한계 | 이 확장의 대응 |
|---|---|
| 선택지가 실행 / NO_ACT 두 개뿐 | 행동 방식 메뉴 (5장) |
| 실행하면 사람을 방해하지 않는다고 가정 | 간섭 민감도 w로 방해 가능성 예측 (7장) |
| 애매하면 물어봐야 하지만 프레임워크 밖 | 방식에 `ask` 포함 |
| 규칙을 더 많이 추가하는 쪽으로 편향 (과잉 개입) | 방식 선택으로 수위 조절 |
| 한 사람만 다룸 | 사람별 FSM + 사람별 프로필 |

---

## 2. 용어

| 용어 | 기호 | 뜻 |
|---|---|---|
| 지각된 간섭성 | – | 로봇 행동이 사람에게 침범적·방해된다고 느껴지는 정도 |
| 간섭 민감도 | w | 4개 요인 각각에 대해 그 사람이 얼마나 예민한가. 사람별 벡터 |
| 행동의 성질 | x | 특정 (규칙, 방식)이 4개 요인을 얼마나 건드리는가 |
| 도움 선호 | h | 그 사람이 로봇의 도움 자체를 얼마나 반기는가. 사람별 스칼라 + 단계 유형별 보정 |
| 도움 값 | help(mode) | 방식별로 정해둔 도움의 크기 |
| 확신도 | c | 낮에 트리거가 정말 맞는 상황인지에 대한 확률 |
| 방식 | mode | 같은 action을 어떻게 실행할지 (언제/어디/시작) |

w와 h의 차이: **h는 "도와줄까 말까", w는 "도와준다면 어떤 방식이 거슬리나"**. 둘을 분리해야 "가까이 오는 건 싫지만 도움은 원하는 사람"을 표현할 수 있다.

---

## 3. 확정된 설계 결정 [확정]

1. **목표 환경**: 특정 시나리오가 아닌 보편적 가정 환경, 다인 가구.
2. **사람별 FSM**: 사람마다 루틴이 다르므로 FSM을 사람별로 둔다.
3. **판단은 밤, 실행은 낮**: 방식 선택은 밤에 reflector가 미리 하고, 낮에는 적힌 방식대로 실행. 낮에는 정해진 예외만 처리.
4. **간섭 민감도 요인 4개**: 근접성, 영역 침범, 통제 침해, 타이밍.
5. **도움 선호 h** 도입.
6. **행동 방식은 미리 정의된 메뉴**에서 고른다 (로봇이 새 방식을 즉석 생성하지 않음).
7. **선형 모델 + 온라인 로지스틱 갱신**으로 w 학습 (신경망·멀티헤드 어텐션 사용 안 함).
8. 제외: 빈도 요인, 과업 관련성 요인, "알리고 함" 방식, MBTI 기반 추정 (16장).

---

## 4. 데이터 모델

### 4.1 가구 메모리 최상위

```json
{
  "household_id": "home_01",
  "profiles": { "<person_id>": { ... 4.2 ... } },
  "fsms":     { "<person_id>": { ... 4.3 ... } },
  "config":   { ... 12장 하이퍼파라미터 ... }
}
```

### 4.2 사람별 프로필

```json
{
  "person_id": "son",
  "w":  {"proximity": 1.0, "territory": 2.5, "control": 0.8, "timing": 1.2},
  "w0": {"proximity": 1.0, "territory": 2.5, "control": 0.8, "timing": 1.2},
  "h": 1.0,
  "h0": 1.0,
  "h_phase_offset": {"prep": 0.0, "consume": 0.0, "work": 0.0, "cleanup": 0.0},
  "history_summary": "<reflector가 갱신하는 자연어 요약, 선택>"
}
```

- `w0`, `h0`: 고무줄 항의 기준점 (11장).
- 유효 도움 선호: `h_eff(person, phase_type) = h + h_phase_offset[phase_type]`

### 4.3 사람별 FSM (PAM 스키마 확장)

```json
{
  "person_id": "son",
  "initial_state": "meal_preparation",
  "states": [
    {
      "id": "meal_preparation",
      "description": "Person is gathering ingredients and preparing food.",
      "phase_type": "prep",
      "rules": [
        {
          "rule_id": "son_r01",
          "trigger": "Person sets the cereal box down after pouring.",
          "action": "Pick up the milk and place it next to the person.",
          "action_type": "provide",
          "owner": "shared",
          "removes_from_workspace": false,
          "mode": {"when": "wait", "where": "far", "start": "silent"},
          "p_annoy": 0.28,
          "score": 0.42,
          "reason": "근접성·타이밍 민감, 통제 침해는 둔감",
          "exploring": false
        }
      ],
      "next": [{"to": "eating", "on": "Person picks up a spoon"}]
    }
  ]
}
```

추가 필드:

| 필드 | 위치 | 값 | 작성 주체 |
|---|---|---|---|
| `phase_type` | state | `prep` / `consume` / `work` / `cleanup` | reflector가 FSM 생성 시 |
| `rule_id` | rule | 고유 ID | 시스템 |
| `action_type` | rule | `provide`(사람 옆에) / `store`(보관함) / `trash`(쓰레기통) | location에서 자동 도출 |
| `owner` | rule | `shared` 또는 person_id | reflector |
| `removes_from_workspace` | rule | bool | `store`·`trash`면 true |
| `mode` | rule | 5장 참고, 또는 `"skip"` | 밤 선택 알고리즘 (8장) |
| `p_annoy`, `score` | rule | float | 밤 선택 알고리즘 |
| `reason` | rule | 자연어 한 줄 | reflector |
| `exploring` | rule | bool | 탐색 스케줄러 (10.6) |

### 4.4 낮 실행 로그 (밤 학습의 입력)

```json
{
  "date": "2026-11-02",
  "executions": [
    {
      "t": "08:12:31",
      "person_id": "son",
      "rule_id": "son_r01",
      "phase_type": "prep",
      "planned_mode": {"when": "wait", "where": "far", "start": "silent"},
      "executed_mode": {"when": "wait", "where": "far", "start": "silent"},
      "confidence": 0.8,
      "downgrade_reason": null,
      "others_present": []
    }
  ]
}
```

### 4.5 반응 이벤트 (밤에 reflector가 영상에서 추출)

```json
{
  "t": "08:12:50",
  "person_id": "son",
  "rule_id": "son_r01",
  "event_type": "pushed_away_used",
  "evidence": "Person slid the milk 20cm away, then poured it."
}
```

`event_type` 목록과 학습 매핑은 10.1.

---

## 5. 행동 방식 메뉴 [확정, 값은 초기값]

### 5.1 손잡이

| 손잡이 | 선택지 | 줄이는 요인 | 근거 |
|---|---|---|---|
| `when` | `absent` / `now` / `wait` | 타이밍 (absent는 전부) | McFarlane 방해 조율 분류: 예정형 / 즉시형 / 중재형 |
| `where` | `near` / `far` | 근접성 | HRI 근접학 |
| `start` | `silent` / `ask` | 통제 침해, 영역 침범 | McFarlane 협상형 |
| (전체) | `skip` | 전부 (도움도 0) | – |

- `absent`: 사람이 없을 때 실행. `provide`는 **오기 전에 미리 세팅**, `store`·`trash`는 **자리를 뜬 뒤 정리**.
- `wait`: 트리거가 떠도 다음 FSM 전이(과업 경계)까지 미룸.
- `where`는 `provide`에만 적용 (`store`·`trash`는 목적지가 고정).
- `far`: 손 닿는 범위의 끝. **[미정]** 실제 거리 값.

### 5.2 유효 조합

무효 조합: `absent` + `ask` (물어볼 사람이 없음)

| action_type | 유효 조합 수 | 목록 |
|---|---|---|
| `provide` | 10 + skip | absent×{near,far}×silent (2), now×{near,far}×{silent,ask} (4), wait×{near,far}×{silent,ask} (4) |
| `store` | 5 + skip | absent×silent, now×{silent,ask}, wait×{silent,ask} |
| `trash` | 2 + skip | now×ask, wait×ask (안전 규칙 9.5) |

### 5.3 도움 값 help(mode) [초기값]

`provide`:
| when \ where | near | far |
|---|---|---|
| now | 1.00 | 0.85 |
| wait | 0.80 | 0.70 |
| absent | 0.90 | 0.80 |

`store` / `trash`:
| when | 값 |
|---|---|
| now | 1.00 |
| wait | 0.85 |
| absent | 0.70 |

- `start = ask`이면 위 값 × 0.8
- `skip` = 0

---

## 6. 행동의 성질 x 계산 [확정 구조, 값은 초기값]

x는 (규칙, 방식, 대상 사람)마다 계산한다. 각 성분은 0~1.

### 6.1 규칙에서 나오는 기본 속성

- `territory_other` = 규칙의 `owner`가 `shared`도 아니고 대상 사람도 아님 → 1, 아니면 0
- `removes` = `removes_from_workspace`
- `timing_base` = 단계 유형별 기본값 **[초기값]**

| phase_type | timing_base |
|---|---|
| consume | 1.0 |
| work | 0.8 |
| prep | 0.3 |
| cleanup | 0.3 |

**[미정]** 이후 "다음 전이까지 남은 시간" 기반으로 정교화.

### 6.2 방식별 x

```
x.proximity =
    0                       if when == absent
    1.0                     if action_type == provide and where == near
    0.3                     if action_type == provide and where == far
    0.7                     if action_type in {store, trash}       # 사람 근처 물건을 집으러 감

x.territory =
    0                       if not territory_other
    0.3                     if territory_other and start == ask
    1.0                     if territory_other and start == silent   # absent여도 1 (부재 중 침범)

x.control =
    (0.3 if start == ask else 1.0)   if removes
    0.1                              otherwise                      # 놓아주는 건 약함

x.timing =
    0                       if when == absent
    0.2 * timing_base       if when == wait
    timing_base             if when == now
```

---

## 7. 예측 모델 [확정]

```
P_annoy(person, rule, mode) = σ( w_person · x(rule, mode, person) + b )
σ(z) = 1 / (1 + exp(−z))
```

- `b` [초기값] = −3 (아무 요인도 안 건드릴 때 불만 확률 ≈ 5%)
- 의미: 사람이 예민한 요인을 그 방식이 많이 건드릴수록 불만 확률이 올라간다.

---

## 8. 밤 파이프라인 (Reflector 확장)

### 8.1 순서

1. **PAM 원래 작업**: 사람별로 그날 영상·요약·피드백으로 FSM 수정 (상태·규칙·전이 추가/수정). 새 상태에는 `phase_type`, 새 규칙에는 `owner`를 채운다.
2. **반응 이벤트 추출**: 영상 + 실행 로그(4.4)를 보고 4.5 형식 이벤트 목록 생성.
3. **w 갱신** (10.2)
4. **h 갱신** (10.3)
5. **방식 재선택**: 모든 사람의 모든 규칙에 대해 8.2 실행. `mode`, `p_annoy`, `score` 기록.
6. **탐색 표시** (10.6)
7. **reason 작성**: 규칙마다 선택 이유를 한 줄로.
8. **(선택) 새 요인 제안**: 기존 4요인으로 설명 안 되는 반응이 반복되면 자연어로 제안만 기록 (자동 반영 안 함).

### 8.2 방식 선택 알고리즘

```python
def select_mode(person, rule, state):
    candidates = valid_modes(rule.action_type)          # 5.2
    candidates = apply_safety_filters(candidates, rule) # 9.5
    h_eff = person.h + person.h_phase_offset[state.phase_type]

    best, best_score = "skip", 0.0                      # skip: help 0, annoy 0
    for m in candidates:
        x = compute_x(rule, m, person, state)           # 6장
        p = sigmoid(dot(person.w, x) + config.b)
        s = h_eff * help(rule.action_type, m) - p
        if s > best_score:
            best, best_score = m, s
    return best, best_score
```

- 점수 = `h_eff × help(mode) − P_annoy(mode)`
- 모든 방식의 점수가 0 이하이면 `skip`.
- 밤에는 확신도 c를 알 수 없으므로 점수식에 넣지 않는다 (낮 예외로 처리, 9.2).

---

## 9. 낮 실행 로직

### 9.1 흐름

```python
def on_tick(frames):
    for person in present_persons(frames):                 # [미정] 사람 식별
        task, c = predict_with_confidence(person.fsm, frames)
        if task is None:
            continue
        rule = lookup_rule(person, task)
        mode = rule.mode

        if rule.exploring:
            mode = rule.mode                                # 이미 ask로 설정돼 있음
        if c < config.c_min:
            mode = downgrade(person, rule, mode, "low_confidence")
        if today_rejected(person, rule):
            mode = downgrade(person, rule, mode, "rejected_today")
        others = present_persons(frames) - {person}
        if others:
            mode = resolve_multi_person(rule, mode, {person} | others)
        mode = apply_safety_rules(rule, mode, frames)

        execute(rule, mode)                                 # wait면 다음 전이까지 대기열
        log_execution(...)                                  # 4.4
```

### 9.2 확신도 c [초기값]

- 같은 입력으로 태스크 예측기를 k번 샘플링 (k = 5, temperature 0.3)
- c = 다수결 태스크가 나온 비율
- `c < c_min` (0.6)이면 한 단계 낮춤

### 9.3 한 단계 낮춤 (downgrade)

현재 방식보다 `P_annoy`가 **엄격히 낮은** 유효 방식들 중 점수가 가장 높은 것. 없으면 `skip`.

### 9.4 여러 명이 같이 있을 때

```
score_multi(m) = min_p( h_eff_p ) × help(m) − max_p( P_annoy_p(m) )
선택 = argmax_m score_multi(m)    # 0 이하면 skip
```

더 민감하고 도움을 덜 원하는 사람 기준으로 보수적으로 고른다. 저장된 w, h로 낮에 바로 계산 (가벼움).

### 9.5 고정 안전 규칙 (학습과 무관) [확정]

1. `trash`는 반드시 `ask` (`absent`, `silent` 불가).
2. 규칙이 다른 사람의 영역을 건드리고(`territory_other`) 그 주인이 없으면 `skip`, 주인이 나타날 때까지 보류.
3. 사람이 들고 있거나 만지는 물건은 조작 불가 (PAM 제약 유지).
4. **[미정]** 단계당 최대 개입 횟수 상한 (빈도 요인 대체용 고정 규칙, 필요 시).

### 9.6 당일 거부 처리

- 낮에 명시적 거부(음성 "안 해도 돼", 정지 버튼 등)를 감지하면 그 규칙을 **그날만** 한 단계 낮춤.
- **[미정]** 실시간 거부 감지 방법. 최소 구현은 음성 키워드 또는 버튼.

---

## 10. 학습

### 10.1 반응 이벤트 → 학습 매핑

| event_type | 조건 | w 갱신 (y, 가중치, 대상 요인) | h 갱신 (s) |
|---|---|---|---|
| `complaint` | 로봇 행동 직후 말·제스처로 불만 | y=1, 1.0, 전체 | – |
| `undo_remove` | 로봇이 치운 걸 사람이 다시 가져옴 | y=1, 1.0, control | – |
| `pushed_away_used` | 가져다준 걸 밀어두고 사용 | y=1, 0.7, proximity | +0.5 |
| `unused_returned` | 가져다준 걸 안 쓰고 치움 | – | −1 |
| `used` | 가져다준 걸 불만 없이 사용 | y=0, 0.3, 전체 | +0.5 |
| `ask_accepted` | 물었는데 수락 | y=0, 0.3, 전체 | +0.5 |
| `ask_declined` | 물었는데 거절 | – | −1 |
| `missed_opportunity` | 로봇이 안 했는데 사람이 그 규칙의 행동을 직접 함 | – | +1 |
| `no_reaction` | 로봇이 했고 눈에 띄는 반응 없음 | y=0, 0.3, 전체 | – |

원칙:
- **무반응은 승인이 아니다** → 약한 가중치(0.3).
- **방식이 싫은 것(w)과 도움 자체가 싫은 것(h)을 분리**한다. `ask_declined`가 h의 가장 깨끗한 신호 (묻기는 간섭이 가장 적은 방식이라 거절 = 도움 자체 거절).
- 대상 요인 마스크: 원인이 분명한 이벤트는 해당 요인만 갱신.

### 10.2 w 갱신 (온라인 로지스틱 회귀 + 사전분포)

이벤트마다:
```
p   = σ(w · x + b)
g   = weight × (y − p) × (x ⊙ mask)        # mask: 대상 요인만 1
w  ← w + η × [ g − λ × (w − w0) ]
```

밤 갱신이 끝나면:
```
w_i ← clip(w_i, w_min_i, w_max_i)
w_i ← clip(w_i, w_i_before_tonight − Δw_max, w_i_before_tonight + Δw_max)
```

- 이벤트가 없는 날에도 고무줄 항만 적용: `w ← w − η × λ × (w − w0)`
- 해석: w0를 평균으로 하는 가우시안 사전분포 하의 온라인 로지스틱 회귀 (MAP).

### 10.3 h 갱신

이벤트마다 (s는 10.1의 값, φ = 이벤트 시점 단계 유형):
```
h                    ← h + η_h × (1 − α) × s
h_phase_offset[φ]    ← h_phase_offset[φ] + η_h × α × s
```

밤마다:
```
h                 ← h − λ_h × (h − h0)
h_phase_offset[·] ← h_phase_offset[·] − λ_h × h_phase_offset[·]
clip(h, h_min, h_max), clip(|Δh| per night ≤ Δh_max)
```

- α: 사람 전체 vs 단계 보정에 나누는 비율. 처음엔 사람 전체 값으로 움직이고, 특정 단계 기록이 쌓이면 그 단계만 달라짐.

### 10.4 안정 장치 요약

| 장치 | 막는 것 |
|---|---|
| λ, λ_h (기본값 당김) | 한 번의 반응에 휘둘림, 끝없는 발산 |
| [w_min, w_max], [h_min, h_max] | 비현실적 값, 음수 |
| Δw_max, Δh_max (하룻밤 최대 변화) | 급격한 행동 변화 |
| 고정 안전 규칙 (9.5) | 위험 행동이 학습으로 풀림 |

### 10.5 갱신 폭 비율과 허용 불만 빈도

긍정·부정 신호의 크기 비율이 수렴하는 불만 빈도를 결정한다 (예: 긍정 +0.01, 부정 −0.1이면 약 9%에서 균형). **[미정]** 허용 불만 빈도를 먼저 정하고 가중치를 역산할 것.

### 10.6 탐색

- `skip`이 3일 이상 연속인 규칙은, 다음 날 확률 ε로 가장 점수 높은 `ask` 방식으로 설정하고 `exploring: true` 표시.
- 사람당 하루 최대 1개 규칙.
- 목적: 꺼진 규칙이 영원히 관찰되지 않는 문제 방지 (`ask`는 비용이 낮음).

---

## 11. 초기값 (Cold start)

| 항목 | 출처 | 상태 |
|---|---|---|
| w0, [w_min, w_max] | 영상 기반 예비 사용자 연구: 평균 = w0, 5~95% 백분위 = 범위 | [미정] 연구 전에는 아래 임시값 |
| h0, 단계 유형별 offset 기본값 | 예비 연구의 "도움이 됐다" 문항 | [미정] |
| 개인 초기값 (선택) | Big Five 10문항 + Hong 심리적 반발 척도 → w0 예측 | [미정] 선택 기능 |

임시값 [초기값]: w0 = 모든 요인 1.0, h0 = 1.0, offset = 0, w ∈ [0, 5], h ∈ [0.1, 3].

---

## 12. 하이퍼파라미터 [초기값]

| 이름 | 값 | 의미 |
|---|---|---|
| b | −3.0 | 예측 식 기준선 |
| η | 0.5 | w 학습률 |
| λ | 0.1 | w 기본값 당김 |
| Δw_max | 0.3 | 하룻밤 w 성분별 최대 변화 |
| η_h | 0.1 | h 학습률 |
| λ_h | 0.05 | h 기본값 당김 |
| Δh_max | 0.2 | 하룻밤 h 최대 변화 |
| α | 0.5 | h 갱신 중 단계 보정 몫 |
| k | 5 | 확신도 샘플링 횟수 |
| c_min | 0.6 | 낮 다운그레이드 확신도 기준 |
| ε | 0.3 | 탐색 확률 |
| ask 도움 배율 | 0.8 | 5.3 |

---

## 13. 첫 구현 마일스톤: 시뮬레이션

실제 로봇·사람 실험 전에 학습 구조가 작동하는지 검증한다.

### 13.1 가상 가구

- 사람 N명 (2~4), 각자 **진짜 값** w\*, h\*, h\*_phase_offset을 가짐.
- 사람별 루틴 = FSM 템플릿 (예: 시리얼 아침 루틴, PAM의 6개 태스크 구조 참고). 단계 유형 포함.
- 공용/개인 물건과 영역 정의.

### 13.2 하루 시뮬레이션

각 트리거 발생 시 로봇이 9장 로직으로 방식 선택 → 가상 사람 반응 생성:

```
로봇이 행동함 (사람 있음):
    P_complaint = σ(w* · x + b*)
    불만이면: 가장 큰 기여 요인 argmax_i(w*_i x_i)에 따라
        control → undo_remove, proximity → pushed_away_used, 그 외 → complaint
    불만 아니면: provide는 P(use) = clip(h*_eff / 2, 0, 1)로 used / unused_returned
                 그 외는 no_reaction
로봇이 ask:
    P(accept) = clip(h*_eff / 2, 0, 1) → ask_accepted / ask_declined
로봇이 skip 또는 미발동:
    루틴상 필요한 행동이면 사람이 직접 함 → missed_opportunity
```

- 이벤트 추출 노이즈: 확률 p_noise로 이벤트 누락 또는 잘못된 타입.
- 주의: `missed_opportunity`는 h\*와 무관하게 발생하도록 둔다. "직접 하는 걸 선호"와 "도움을 놓침"이 구분되지 않는 실제 문제를 그대로 재현해, 학습기가 이 편향을 `ask_declined`·`unused_returned`로 상쇄하는지 확인하기 위함.

### 13.3 지표

| 지표 | 정의 |
|---|---|
| 불만률 | 로봇 개입 중 불만 이벤트 비율 |
| 도움률 | 루틴상 도움 기회 중 로봇이 도운 비율 |
| 효용 | Σ (h\*_eff × help − annoy\*) |
| 파라미터 오차 | ‖w − w\*‖, \|h − h\*\| |
| 수렴 일수 | 오차가 기준 이하로 들어오는 날 |

### 13.4 비교 대상

| ID | 설명 |
|---|---|
| B0 | PAM 기본: 항상 `now / near / silent` |
| B1 | 고정 w0, h0 (학습 없음) |
| B2 | w만 학습 (h 없음, `missed_opportunity`는 w를 낮추는 방향으로 처리) |
| Ours | w + h 학습 |
| B3 (후속) | LLM reflector가 숫자 없이 로그만 보고 방식 결정 |

검증할 가설: Ours가 B2보다 진동이 적고 수렴이 빠르다 ("투덜대지만 도움은 원하는 사람" 유형에서 특히).

### 13.5 시뮬레이션 산출물

- 날짜별 w, h 궤적 그래프
- 사람 유형별(4사분면: h 높/낮 × w 높/낮) 지표 비교
- 하이퍼파라미터(λ, Δw_max, ε) 민감도 분석

---

## 14. 사람 실험 계획 (요약)

1. **요인 검증 예비 연구**: 여러 공간(책상, 거실, 침실, 공용)의 로봇 행동 클립에서 4요인을 섞어 변화. 평가 문항: 간섭성 4문항(개인 공간 침범, 불필요한 방해, 부적절한 순간, 자율성 존중) + "도움이 됐다". 짧은 인터뷰로 누락 요인 탐색. 혼합효과 회귀로 요인별 효과 → w0, 범위 산출.
2. **실제 로봇 다일 실험**: 책상 시나리오, 며칠 단위. 근접성·통제 침해·타이밍 개인화와 h 학습 효과 확인.
3. **비교 실험 후보**: PAM 원본 vs 방식 메뉴 추가 / w 기반 vs LLM만 / 평균 w0 vs 성격 기반 w0 / 1인 vs 다인.

---

## 15. 이론적 정식화 (논문용)

- 사람의 실제 상태(단계, 필요 여부)는 숨어 있고 로봇은 관찰로 추정 → **POMDP로 정식화**.
- 실제 풀이는 근사: FSM 기반 단계 추적(belief tracking, 계획 제외) + 한 스텝 기대값 판단(myopic) + w, h의 bandit식 온라인 갱신.
- 서술 예: "문제를 POMDP로 정식화하고, FSM 기반 belief tracking과 myopic 근사, 사람별 선형 간섭 모델의 온라인 베이지안 갱신으로 해결한다."

---

## 16. 결정 이력: 뺀 것과 이유

| 항목 | 이유 | 대체 |
|---|---|---|
| 빈도 요인 | 근거가 단일 연구(32명)에 의존, 다른 변수와 혼재. 대응 손잡이가 skip뿐. 밤에 미리 못 정함 | 타이밍 + 단계별 h로 대부분 대체, 필요 시 고정 상한 (9.5-4) |
| 과업 관련성 요인 | 광고 연구에서 옮겨온 축. 사실상 "필요성"의 우회 표현 | 제외 |
| 필요성 ("불필요한 방해") | 행동의 성질이 아니라 판단 오류 | 확신도 c, 점수식 |
| 관찰당하는 느낌 | 시스템 차원 문제 | 동의 절차, 카메라 설계 |
| 비가역성 | 개인 취향이 아니라 공통 위험 | 고정 안전 규칙 (trash = ask) |
| "알리고 함" 방식 | 제외 결정 | – |
| MBTI 기반 성격 추정 | 재검사 신뢰도 낮음. 행동→성격→민감도 경로는 오차 누적. 윤리 문제 | 반응에서 w, h 직접 학습. 성격은 선택적 초기값(Big Five)만 |
| 멀티헤드 어텐션 | 한 사람의 피드백 수십~수백 개로 수천 파라미터 학습 불가, 해석 불가 | 선형 w. 다수 사용자 사전학습이 가능해지면 비교 실험 |
| 낮 실시간 점수 계산 | 느리고 PAM 설계(메모리 하루 고정)와 불일치 | 밤 사전 결정 + 낮 예외 처리 |

---

## 17. 미정 사항 / 열린 문제

| 항목 | 내용 |
|---|---|
| 사람 식별 | 다인 가구에서 현재 사람 판별 방법 (얼굴, 체형, 자리 등) |
| 다인 시 예측기 호출 | 사람별 FSM로 예측기를 사람마다 호출할지, 통합할지 |
| 실시간 거부 감지 | 음성 키워드, 버튼 등 |
| `far` 실제 거리, `wait` 최대 대기 시간 | 하드웨어·과제에 맞춰 결정 |
| x, help 초기값 보정 | 예비 연구로 조정 |
| 허용 불만 빈도 | 몇 %까지 감수할지 → 이벤트 가중치 역산 |
| 놓친 기회 vs 직접 하는 걸 선호 | `missed_opportunity`의 모호성 해소 방법 |
| 간섭성 4문항의 요인 구조 | 원 연구는 평균 하나로만 보고 → 예비 연구에서 분리 여부 확인 |
| 영역 침범의 HRI 근거 | 로봇의 개인 공간·물건 침범 연구 보강 필요 |
| 타이밍 x 정교화 | 단계 유형 기본값 → 다음 전이까지 남은 시간 기반 |
| "hybrid FSM" 용어 | 학계에서는 이산+연속 의미. 논문에서 정의 명시 필요 |
| 방식 메뉴 확장 | 연속값(거리, 대기 시간), LLM 제안 → 검증 후 추가하는 절차 |

---

## 18. 요인 근거 요약 (질문 대응용)

> 로봇 개입의 지각된 간섭성을 측정한 HRI 연구(Hriscu 외, Bo 외 2026)의 측정 문항에서 근접성, 타이밍, 통제 침해를 가져왔고, 보편적 가정 환경을 위해 영역 침범을 추가했다. 각 요인에는 근접학, 방해 연구, 심리적 반발 이론, 사생활 조절 이론으로 독립 근거를 붙였고, 예비 사용자 연구로 검증한다. 행동 방식은 McFarlane의 방해 조율 분류와 근접학에 근거해 구성했다.

| 요인 | 직접 근거 | 독립 근거 |
|---|---|---|
| 근접성 | Hriscu 외 "개인 공간 침범" | Takayama & Pantofaru 2009, Syrdal 외 2007 |
| 타이밍 | Hriscu 외 "부적절한 순간", Bo 외 | Adamczyk & Bailey 2004, Iqbal & Bailey (과업 경계) |
| 통제 침해 | Hriscu 외 "자율성 존중" | Brehm 심리적 반발 이론, Peng 외 2019 |
| 영역 침범 | – | Altman 사생활 조절 이론 (HRI 근거 보강 필요) |

주의: Hriscu 외와 Bo 외는 같은 실험(32명)에서 나온 짝 논문이므로 독립 증거로는 하나로 취급.

---

## 19. 참고문헌

> 인용 전 원문으로 서지 정보 확인 필요.

- Lee, D., Park, M., et al. (2026). An Agentic Framework for Proactive Robots with Procedural Assistance Memory. arXiv:2610.21211. (PAM)
- Hriscu, L., Bo, V., Sanfeliu, A., & Garrell, A. (2026). When Should Robots Intervene? Balancing Engagement and Intrusiveness in Human-Robot Interaction. arXiv:2609.21734.
- Bo, V., Hriscu, L., Sanfeliu, A., & Garrell, A. (2026). Understanding Engagement and Intrusiveness in Assistive Human-Robot Interaction Using Individual Traits. arXiv:2609.21744.
- McFarlane, D. C. (2002). Comparison of Four Primary Methods for Coordinating the Interruption of People in Human-Computer Interaction. Human-Computer Interaction, 17.
- McFarlane, D. C., & Latorella, K. A. (2002). The Scope and Importance of Human Interruption in Human-Computer Interaction Design. Human-Computer Interaction, 17.
- Adamczyk, P. D., & Bailey, B. P. (2004). If Not Now, When? The Effects of Interruption at Different Moments Within Task Execution. CHI.
- Iqbal, S. T., & Bailey, B. P. (2006). Leveraging Characteristics of Task Structure to Predict the Cost of Interruption. CHI.
- Horvitz, E., Koch, P., & Apacible, J. (2004). BusyBody: Creating and Fielding Personalized Models of the Cost of Interruption. CSCW.
- Peng, Z., Kwon, Y., Lu, J., Wu, Z., & Ma, X. (2019). Design and Evaluation of Service Robot's Proactivity in Decision-Making Support Process. CHI.
- Kraus, M., et al. (2022). Including Social Expectations for Trustworthy Proactive Human-Robot Dialogue. UMAP. (None / Notification / Suggestion / Intervention)
- Takayama, L., & Pantofaru, C. (2009). Influences on Proxemic Behaviors in Human-Robot Interaction. IROS.
- Syrdal, D. S., Koay, K. L., Walters, M. L., & Dautenhahn, K. (2007). A Personalized Robot Companion? The Role of Individual Differences on Spatial Preferences in HRI Scenarios. RO-MAN.
- Brehm, J. W. (1966). A Theory of Psychological Reactance. Academic Press.
- Hong, S. M., & Faedda, S. (1996). Refinement of the Hong Psychological Reactance Scale. Educational and Psychological Measurement.
- Edwards, S. M., Li, H., & Lee, J.-H. (2002). Forced Exposure and Psychological Reactance: Antecedents and Consequences of the Perceived Intrusiveness of Pop-Up Ads. Journal of Advertising.
- Altman, I. (1975). The Environment and Social Behavior: Privacy, Personal Space, Territory, Crowding. Brooks/Cole.
- Peng, A., Li, B. Z., Sucholutsky, I., Kumar, N., Shah, J. A., Andreas, J., & Bobu, A. (2024). Adaptive Language-Guided Abstraction from Contrastive Explanations. CoRL. (ALGAE)
- Bobu, A., Wiggert, M., Tomlin, C., & Dragan, A. D. (2021). Feature Expansive Reward Learning: Rethinking Human Input. HRI. (FERL)
- Wu, J., et al. (2023). TidyBot: Personalized Robot Assistance with Large Language Models. IROS / Autonomous Robots.
- Sheridan, T. B., & Verplank, W. L. (1978). Human and Computer Control of Undersea Teleoperators. MIT.
