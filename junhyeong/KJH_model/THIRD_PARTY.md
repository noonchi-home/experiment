# 출처와 자료 구분

이 폴더는 김준형이 정한 목표·기능·현실구현안을 바탕으로 만든 판단 모델입니다. 아래 연구들의 공식 구현이 아니며, 논문과 공개 자료를 참고해 단순화한 별도의 Python 구현입니다.

- 개발 도구: **Claude Code** (모델 Claude Opus 5.5, Anthropic). 코드(`noonchi/`, 실행·수집 스크립트), 시나리오 데이터, README를 작성했습니다. 결과는 직접 실행해 확인했습니다.
- 코드가 호출하는 VLM: **Qwen3.5-27B** 하나만 씁니다(Alibaba Qwen, OpenRouter `qwen/qwen3.5-27b`, Alibaba 제공자 고정). 팀 저장소 `Noonchi/ai`(PAM)와 같은 모델·같은 설정이며, 설정값은 `ai/config/openrouter.json`, `ai/pam/openrouter.py`를 따랐습니다. Chat Completions + Structured Outputs(strict)로 영상 창 → 관찰 기록만 맡고(`noonchi/vision.py`), 판단은 결정론적 코드가 합니다. `record_video_vlm.py`를 실행할 때만 호출합니다. `run_coffee.py`는 호출하지 않습니다.
  - 모델·제공자 정보(입력 종류, 지원 매개변수, 가격): https://openrouter.ai/qwen/qwen3.5-27b (2026-10-30 확인. Alibaba 제공자는 response_format·structured_outputs 지원)
- 영상 프레임 추출: **FFmpeg**(https://ffmpeg.org, LGPL/GPL). 이 폴더에 포함하지 않았고, `record_video_vlm.py`가 설치된 실행 파일을 부릅니다. 개발 PC에서는 PyPI `imageio-ffmpeg` 0.8.1 wheel에 든 ffmpeg 실행 파일을 썼습니다.
- 설계에서 참고한 연구(코드·문구를 옮기지 않고 생각만 가져왔습니다):
  - **PAM**: Dohyun Lee, Minho Park 외, *An Agentic Framework for Proactive Robots with Procedural Assistance Memory*, CoRL 2026, arXiv:2610.21211. https://arxiv.org/abs/2610.21211 → FSM 기억(상태·규칙·전이)과 tasks.json의 행동 문장 형식, 반성 단계의 기억 수정. PAM은 VLM이 FSM 기억을 읽고 판단하지만, 여기서는 VLM은 관찰만 하고 트리거·task·FSM 수정을 코드가 정합니다.
  - **KnowNo**: Ren 외, *Robots That Ask For Help*, CoRL 2023, arXiv:2307.01928. https://arxiv.org/abs/2307.01928 → 애매할 때만 거주자에게 묻기(`noonchi/fsm_edit.py` 질문).
  - **POMDP 설계 틀**: Ioannis Kostavelis, Dimitrios Giakoumis, Sotiris Malassiotis, Dimitrios Tzovaras, *A POMDP Design Framework for Decision Making in Assistive Robots*, HCI International 2017, LNCS 10271, pp. 467–479. https://link.springer.com/chapter/10.1007/978-3-319-58071-5_35 (공개 본문, 2026-11-04 확인) → 튜플 {S, A, Ω, R, O, T, b0}로 적기, 상태를 로봇 경계 수준(High/Medium/Low)으로 묶기, 행동을 task / communication / monitoring으로 묶기, 경계 수준을 낮추면 양수·높이면 음수인 보상, 상태도(FSM)로 전이 확률 정하기, POMDP는 무엇을 할지만 정하고 실행은 아래에 맡기기(`config/lora.json`, `noonchi/lora.py`, `trigger_pomdp.py`, `task_pomdp.py`, `fsm_edit.py`). 보상의 크기, task 20개의 묶음 나누기, 한 단계 기대 이득 풀이는 논문에 없고 이 폴더에서 정했다. 같은 설계를 쓴 후속 논문: Kostavelis 외, *Robotic Assistance in Medication Intake: A Complete Pipeline*, Applied Sciences 12(3):1379, 2022. https://doi.org/10.3390/app12031379
  - **POMDP**: Kaelbling, Littman, Cassandra, *Planning and Acting in Partially Observable Stochastic Domains*, Artificial Intelligence 101(1–2), 1998 → 믿음 갱신과 기대 이득 행동 선택(`noonchi/trigger_pomdp.py`, `noonchi/task_pomdp.py`, `noonchi/fsm_edit.py`). 여러 단계 계획은 하지 않고 한 단계로 줄였습니다.
  - **정보 가치**: Howard, *Information Value Theory*, IEEE Trans. Systems Science and Cybernetics 2(1), 1966 → FSM 수정안을 반영하기 전에 질문할지 정하는 VOI(`noonchi/fsm_edit.py`).
  - **FSM 수정 믿음**(`noonchi/fsm_edit.py`): 위 POMDP의 믿음 갱신·기대 이득과 Howard의 정보 가치, KnowNo의 "애매할 때만 묻기"를 PAM 반성 단계의 규칙 수정에 적용했습니다. 모델 수치를 숨은 상태로 두는 생각은 Ross, Chaib-draa, Pineau, *Bayes-Adaptive POMDPs*, NeurIPS 2007을 참고했으며, 그 방법을 구현한 것은 아닙니다(규칙마다 원함/원하지 않음 하나만 둠).
- 팀 문서: 구현명세서 SSOT의 "AI 모델은 보고 말하기만 한다" 원칙과 Sprint-01 회의 결정("지금 정보로 판단할 수 있는가, 추가 정보를 얻어야 하는가")을 따랐습니다.

- 영상: `data/Coffee_man/Coffee_man.mp4`는 사용자가 넣은 파일입니다. 출처와 이용 조건은 이 폴더에 기록되어 있지 않습니다. 공개·배포 전에 확인해야 합니다.
- 실제 VLM 기록: `data/Coffee_man/live_qwen_rep1`은 2026-11-04에 `record_video_vlm.py`로 Qwen3.5-27B에서 받은 관찰을 그대로 저장한 것입니다. 프레임 PNG는 저장하지 않았습니다.
- 정답 task(`data/Coffee_man/answer.json`), 초기 FSM, task 20개, 허브 등록 가전은 사용자가 정한 가정입니다. 관찰 모델 수치는 사람이 정한 값이며, 위 Qwen 관찰을 받기 전에 정했습니다. 이득·비용은 2026-11-04에 Kostavelis 외(2017)의 경계 수준 보상표(`config/lora.json`)로 바꿨습니다. 이때는 Qwen 관찰이 이미 있었지만, 표의 값을 정답에 맞추려고 고치지 않았습니다.
- 스마트홈 허브와 로봇은 가상입니다(`noonchi/smarthome.py`). 실제 기기·서비스의 API를 쓰지 않았습니다.

`.env`(API 키)와 `runs/`(실행 결과)는 Git에 넣지 않습니다.

이 폴더 자체의 라이선스는 아직 정하지 않았습니다. 이 파일은 재배포 권한을 주는 문서가 아닙니다.
