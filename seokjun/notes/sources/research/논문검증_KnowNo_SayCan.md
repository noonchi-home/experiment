# KnowNo·SayCan 원문 검증 메모

검증일: 2026-10-23. 최종 사용자용 해설의 출처 확인용. 원문 사실과 프로젝트 적용 아이디어를 분리했다. 합성 데이터·API 실험은 아직 실행하지 않았다.

## KnowNo

- 정식 제목: Robots That Ask For Help: Uncertainty Alignment for Large Language Model Planners. CoRL 2023; [공식 서지](https://proceedings.mlr.press/v229/ren23a.html), [원문 PDF](https://proceedings.mlr.press/v229/ren23a/ren23a.pdf), [저자 프로젝트](https://robot-help.github.io/).
- **방법**: 관찰·지시의 텍스트 → LLM 행동후보 네 개 + '목록 밖 다른 답' → 선택지 문자별 next-token likelihood → 별도 정답 있는 calibration 데이터로 정한 threshold → prediction set. 학습된 LLM 자체를 fine-tuning할 필요는 없다. 단순히 '자신감 몇 점?'을 묻는 방식이 아니다. [저자 설명 Approach](https://robot-help.github.io/), [§2, PDF p3](https://proceedings.mlr.press/v229/ren23a/ren23a.pdf#page=3).
- **집합 처리**: 실행 가능한 후보가 하나면 선택. non-singleton이면 도움 요청; 인간은 집합에 정답이 있으면 선택하고 없으면 중단한다. 따라서 빈 집합도 단일후보가 아니며 실행 근거가 없다. '목록 밖 답'일 때는 인간이 구체적 행동을 제공한다(각주2). [§3.2, PDF p4–5](https://proceedings.mlr.press/v229/ren23a/ren23a.pdf#page=4).
- **보장 조건**: calibration/test 시나리오가 같은 분포에서 추출되고 인간이 정확히 도와야 한다. perception의 정확한 텍스트 표현과 저수준 실행 성공도 가정한다. 집합에 정답이 들어가는 분포상 확률 보장이지 매번 정답임을 보증하지 않는다. 평균 집합 크기의 최적성에는 점수가 진짜 조건부 확률을 모델링한다는 추가 조건이 있다. [§3.1–3.3, p4–5](https://proceedings.mlr.press/v229/ren23a/ren23a.pdf#page=4), [§6, p8](https://proceedings.mlr.press/v229/ren23a/ren23a.pdf#page=8).
- **다단계**: 시간순 데이터 전체 단위로 calibration; 테스트는 현재·과거만 사용한다. 단계를 독립표본처럼 취급해 단일단계 보장을 그대로 반복하지 않는다. [§3.3, PDF p5](https://proceedings.mlr.press/v229/ren23a/ren23a.pdf#page=5).
- **수치**: 실제 UR5 음식모형 분류 50회. KnowNo/Simple Set의 계획성공률 모두76%; 실제 작업성공률74%/72%; 단계별 도움58%/72%, 에피소드별 도움92%/100%. 따라서 단계별 차이는 **14%p**다. 사람의 도움을 포함한 결과다. [§4.2·Table1, PDF p7](https://proceedings.mlr.press/v229/ren23a/ren23a.pdf#page=7).

### 우리 실험에 관한 해석·제안 (논문 결과 아님)

- 우선 모호한 상태에서 ASK 또는 OBSERVE를 선택하는지를 평가할 수 있다. 이것은 KnowNo에서 받은 설계 아이디어이며 CP 구현·통계보장 재현이라고 부르면 안 된다.
- 사용하려는 API가 필요한 선택지 점수를 노출하는지, 고정된 후보·점수 추출 절차를 만들 수 있는지 별도 검증해야 한다. 자기보고 confidence=0.9는 자동으로 보정된 성공확률이 아니다.
- synthetic 데이터도 calibration용과 test용 시나리오를 나눠야 한다. 같은 시나리오의 다른 프레임을 두 집합에 섞으면 누출 위험이 있다.
- 어떤 컵이든 정리 가능하다는 설정이라면 정답이 하나일 필요 없다. 반대로 사용자의 숨은 취향이 다른 경우에는 관찰에서 알 수 없는 것을 정답 유일성으로 강요하지 않는다.
- 빈 집합, '목록 밖 답'만 남는 경우, 오류 응답의 구체적 처리(재질문/보류)는 프로젝트 정책으로 명시해야 한다. 논문에서 singleton E의 구현 세부 분기를 충분히 설명하지 않으므로 '하나면 어떤 종류든 무조건 물리 실행'이라고 쓰지 않는다.

## SayCan

- 정식 제목: Do As I Can, Not As I Say: Grounding Language in Robotic Affordances. CoRL 2022, PMLR 출판2023. [공식 서지](https://proceedings.mlr.press/v205/ichter23a.html), [원문 HTML v2](https://arxiv.org/html/2204.01691v2), [저자 프로젝트](https://say-can.github.io/). PMLR PDF는 web 크기 제한으로 열리지 않아 같은 논문의 arXiv v2 방법·실험·한계를 확인했다.
- **방법**: 사용자 목표와 준비된 로봇 skill 목록이 입력이다. 각 skill의 목표 적합성(LLM 언어 점수)과 현재 상태에서의 실행 성공가능성(affordance/value function)을 곱해 최대 후보를 실행한다. 이전 선택을 기록하고 현재 상태로 반복하며 done에서 끝난다. [§3·Algorithm1](https://arxiv.org/html/2204.01691v2), [저자 Approach](https://say-can.github.io/).
- **학습 범위**: 고수준 언어모델만 다운로드하면 완성되는 구조가 아니다. 실험의 저수준 skill은 BC/RL, affordance는 TD 학습 value function을 사용했다. 실행 능력·점수 모델이 이미 준비됐다는 조건이 있다. [§4](https://arxiv.org/html/2204.01691v2).
- **실험**: PaLM540B와 이동형 로봇, 7범주101개 지시. mock kitchen 계획84%·실제수행74%; 실제 office kitchen 계획81%·수행60%. 각각 전체 지시 기준이며 74%는 성공한 계획84% 중의 비율이 아니다. 각 지표는 평가자3명 중2명 이상 동의로 성공 판정한다. [§5–5.1·Table1–2](https://arxiv.org/html/2204.01691v2).
- **비교**: affordance를 없앤 No VF의 계획성공률67%; 생성문을 skill에 매핑한 Generative는74%. 이것을 실제수행률과 섞으면 안 된다. [Table2](https://arxiv.org/html/2204.01691v2).
- **한계**: skill 종류·성능이 병목이며 LLM 오류도 상속한다. 피드백은 현재 value function을 통해 들어오므로 실행 실패를 충분히 반영하지 못할 수 있다. §5.2가 Inner Monologue를 후속 확장으로 직접 연결한다. [§5.2·§8](https://arxiv.org/html/2204.01691v2).

### 우리 실험에 관한 해석·제안 (논문 결과 아님)

- '컵을 정리하는 것이 적절한가'와 '지금 이 컵을 식기세척기로 옮길 수 있는가'를 따로 판단한다는 아이디어를 가져올 수 있다.
- 예시 숫자로 적합성×가능성을 보여줄 때 반드시 설명용 가상 점수라고 표시한다. API에 두 점수를 쓰게 하는 것만으로 학습된 affordance를 재현한 것은 아니다.
- 지금은 synthetic JSON의 장치 상태·컵의 위치·접근 가능 여부로 실행 전제조건을 검사하는 단순 규칙을 두고 모델의 목표 선택과 조합할 수 있다. 이는 응용 설계다.
- 현재 모델이 판단한 EXECUTE는 Task3에 넘기는 실행 후보다. 컵을 다시 집는 등 상태 변경이 생기면 Task3 최신상태 검증에서 무효화해야 한다.
- SayCan은 받은 목표를 실행하는 연구다. 먼저 나서서 목표를 만들어야 하는지, 사용자에게 물을지까지 모두 해결했다고 설명하지 않는다.

## 집필 주의

- 사용자 제시 '인지→평가→결정→실행·피드백'은 설명을 위한 대응 틀이다. 이 두 논문이 인간 심리를 그대로 구현했다는 주장은 없다.
- 근거 요약과 컵 예시는 분리한다. 원문 세부 내용의 장문 번역 대신 핵심을 짧게 인용·요약하고, 프로젝트 예시·한계의 함의를 독자적 설명으로 전개한다.
- 본문 수치는 해당 연도·환경·모델의 결과다. 현재 모든 모델의 성공률이나 우리 실험 예상 성공률로 일반화하지 않는다.
