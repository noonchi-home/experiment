원자 행동 9개와 기종·펌웨어별 가전 명령·신호를 TypeScript 인터페이스로 정의했다. noonchi의 src/contract/atomic-actions.ts와 src/contract/appliance-driver.ts 두 파일이 로컬 작업 폴더에 있다. 팀 개발 브랜치 feat/noonchi의 afb20e8에서 만든 feat/atomic-action-interfaces 브랜치이며 커밋·푸시 전이다.

go에는 도착 확인과 마지막 위치 반환을 명시했고 장애물 감지·정지·우회는 후속 이동 구현이 담당한다. 가전은 설치 ID·모델·펌웨어를 제공한다. 각 속성의 조회·자동 알림·이력과 기기 제어가 독립 선택 기능이다. wait는 기존 관찰 조건과 경과 시간 외에 기종별 새 알림도 받을 수 있다.

프로젝트 TypeScript 검사와 컴파일 전용 사용 예 검사가 모두 통과했다. 결과는 .ai-collab/checks/1794288456855676900-88c2bf4a/record.json과 .ai-collab/checks/1794288435816522800-3ab819cf/record.json에 있다. .ai-collab/notes/check_atomic_actions_2026-11-10.ts에서 메서드 9개, 누락 구현·거짓 도착 거부, 가상 기종별 서로 다른 신호 지원 및 호출 형식을 확인했다. 실제 주행·기기별 연결·FSM 연결은 후속 범위다.

기존 FSM 연구와 3초 관찰 데이터 형식은 이전 인계와 .ai-collab/notes/codex_appliance_plan_validation_2026-11-09.md를 참고한다.

2026-11-10 후속 변경. 새 공통 인터페이스를 기존 트윈 전용 Command/CommandType 11종에서 분리했다. AtomicActions.set은 모델이 이름과 인수를 정한 요청을 받는다. ApplianceDriver는 임의의 가전 종류와 신호 이름을 등록할 수 있고 control.commands에는 해당 모델이 지원하는 명령 이름과 Zod 요청 규격을 둔다. 실제 실행 연결 시 미등록 이름은 unsupported, 허용 범위 밖의 입력은 failed로 처리하도록 규정했다. 기존 트윈 서버 명령과 실제 가전 연결 코드는 독립적이다.

noonchi/tests/appliance-commands.test.ts에서 테스트용 세탁기 모델별 코스 허용값과 읽기 전용 가전을 확인했다. 2건 통과 기록은 .ai-collab/checks/1794291211964625600-9cacc73f/record.json, 전체 타입 검사는 .ai-collab/checks/1794291229830452900-1993f881/record.json, 9개 메서드와 기종별 명령의 컴파일 예는 .ai-collab/checks/1794291206576675100-cf900401/record.json에 있다. 코드와 테스트는 로컬 브랜치에 커밋 전이며 하드웨어는 실행하지 않았다.

병행 작업인 4주 합성 데이터와 평가 정답지는 별도 인계 .ai-collab/handoffs/7fff8d275be543d19557647a4793b07c.json과 실험정답/가전신호_4주_예상정답을 참고한다.
