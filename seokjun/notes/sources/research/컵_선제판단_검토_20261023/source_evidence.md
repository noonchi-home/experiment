# 검토용 출처 사실 메모

아래는 2026-10-23 원문 열람 및 공식 코드 읽기로 확인한 자료 위치와 내용이다. 모델의 실험을 재현한 것은 아니다. source URL만 제공되어 있으므로 검토자는 원문을 독립 열람했다고 주장하지 않는다.

## PAM

https://arxiv.org/html/2610.21211v1
https://davian-robotics.github.io/PAM/

- arXiv 제출일 2026-10-15. arXiv comment와 저자 프로젝트에 CoRL2026 표기. 별도 학회 공식 프로그램/proceedings 항목은 이번 조사에서 확보하지 못함.
- §3.2는 빈 그릇이 식사 전에는 시리얼을 가져올 단서, 식사 후에는 그릇을 치울 단서라는 사례를 직접 설명.
- §3.1 최신 프레임+PAM+상시 도움 역할. §3.3 하루 영상+기존 기억+행동요약+있을 때 사용자 피드백으로 외부 기억 변경.
- 부록A.2: Qwen3.5-27B. W=5, t,t-2,t-4,t-6,t-8초 프레임. observation/brief reasoning/task_index JSON, thinking모드는 꺼짐. 1초 간격 판단.
- 부록E.3: 기억은 단계별 규칙과 전이를 담은 hybrid FSM 텍스트. 한 상태에 확정할 필요가 없고, 단어와 상태 배정이 정확히 일치하지 않아도 상황에 의미상 적합하면 선택할 수 있다고 지시. task_index=-1이면 NO_ACT.
- 부록A.1: 한 사람 같은 책상 루틴, 5일×3.5~4.5분, 1146프레임, 6개 작업+NO_ACT를 저자 라벨링.
- 부록B 표5: FSM Memory의 Bowl→Storage(T5) Day5 F1 0.60±0.09. 표1은 별도 물리실행 결과로 8/10.
- 부록A.3: 물리 실행용 VLA들은 π0.5에서 미세조정. 따라서 판단모델 무재학습과 전체시스템 무학습은 다름.

## Proactive Physical AI

https://arxiv.org/html/2610.16967v1

- arXiv 공개일 2026-10-12. 논문 시스템명 ProAgent. 별도 학회 게재·수상 미확인.
- §3: Timing Model(StreamingJev)과 Response Model, causal world stream. Timing이 silence/response를 선택. 침묵 중에도 관측은 입력됨.
- §4.1: role조건은 목표 사건을 밝히지 않는 standing responsibility를 사용. 같은 영상을 explicit조건과 대응시킴.
- 표1 Base+Worker vs StreamingJev+Worker: Worker Qwen3.8-27B, 입력·스케줄 예산 동일. role F1 28.72→33.45%, FP/min0.62→0.18. F1은 episode-averaged이며 단순 정확도가 아님.
- 부록G.2: Qwen3.5-4B 기반, 언어모델과 native output head를 3epoch 업데이트, vision encoder와 merger 고정. 20,258개 sourcevideo에서 224,268개 sequence, 2,058,267개 supervised decisionturn. 전체영상으로 offline 라벨을 만들되 학습입력은 현재시점까지 제한. unknown구간 제외.
- 부록G.3: 응답 backbone은 별도학습하지 않고 contextual prompting. 선언된 device capabilities를 함수호출로 선택.
- 개입시점과 함수호출을 연구하나 컵 내용물 확인 등 목적있는 추가관찰의 선택정책을 검증한 것으로 확인하지 못함.

## Spatio-Temporal Object Modeling

https://proceedings.mlr.press/v205/patel23a.html
https://arxiv.org/html/2211.15501

- 공식 PMLR205:881–891, 2023. The6thConferenceonRobotLearning(CoRL2022).
- §3–4: 물체고유ID와 위치 그래프 G_t, 시각t→미래배치분포 p(G_t+δ); 지도학습 generativeGNN. 현재배치와 예측배치 차이로 물체이동.
- §5/부록A: HOMER5가상가구,50일학습10일시험. 실제 사람의 활동일정·행동script를 바탕으로 합성.
- §7.4: 준비·식후 물체 복귀·그릇싱크대 이동 Fetch시연.
- §8: 물체상태(깨끗함/더러움)와 현재humanactivity 모델링 부재. 평소보다 식사가 길면 너무 이른 정리 가능.

## ContextAgent와 공식 코드

https://arxiv.org/html/2505.14668
https://github.com/openaiotlab/ContextAgent/tree/f4674bf2a1385ce829c6a7f2ea9c53871dd1a8ce

- §4.1: video→VLM visualcontext(ICL), speechrecognition→audiocontext, notification과 persona 통합.
- §4.2: 주 reasoner는 teacher reasoningtraces를 포함한 SFT. 출력은 reasoning/proactivescore/toolchain. score≥threshold시 proactive서비스.
- §5.1: LoRA rank8,5epochs. ICLbaselines는 random10examples, data60/40train/test.
- 고정커밋 src/icl/inference_api.py 96–112: random.sample로 fewshot선택, prompt에 JSON예시삽입.
- 같은 파일187–225: sensorycontext+personacontext를 usercontent로 넣고 model호출, parse후 tools_str != 'None'이면 도구실행. 해당 API비교군 경로에 별도의 점수 threshold비교는 보이지 않음. 논문의 threshold서술과 구분해야 함.
- prompt/baselines/icl_fs.txt: proactive역할, tools, Examples, proactiveindex/score/actions/toolcalling출력형식. 비개입예시score0(논문의1–5정의와 차이). 이 코드파일을 논문전체의 학습구현이라고 해석하지 않음.
