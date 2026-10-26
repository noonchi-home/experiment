# GitHub에 올릴 자료와 재현 방법

검증한 공개 범위는 연구용 구현과 제한된 실제 결과입니다. 원저자의 공식 프로그램, 완전한 논문 성능 재현, 5일 학습 완료로 소개하지 않습니다.

## 포함

- `pam/`: 사진 준비, 프롬프트, API, 형식 검사, 날짜별 기억 저장
- `prompts/`, `config/`: 원문 전사와 출처, 공개 연결 설정(키 없음)
- `scenarios/breakfast/`: 현재 식탁 시작 기억; `scenarios/morning/`: 보존용 과거 설정
- `tests/`, `tools/`: 검사·실행·합성 생성 도구
- `examples/breakfast_2026-10-25/`: 원본 사진 20장, 상대 경로 목록, 실행 당시 기억, 실제 응답 두 건과 증거
- README, 출처 문서, 논문 충실도 검증 보고서

## 기본 제외

`.venv/`, `tmp/`, `artifacts/`, `records/`, `data/`, `reference/`, `papers/`, `presentation/`, `.env*`, 키 파일, 캐시입니다. 원문 그림이 들어 있는 HTML을 일반 실험 코드와 함께 자동 업로드하지 않습니다. 전체 과거 자료는 로컬에 보존합니다. 원문 프롬프트의 출처는 THIRD_PARTY.md를 확인하십시오.

공개용 사본만 새 폴더에 만들 수 있습니다. 기존 폴더를 덮어쓰지 않습니다.

```powershell
python tools/prepare_github_snapshot.py --output publish/PAM_breakfast_reviewed
```

이 명령은 **Git 저장소 생성, 커밋, GitHub 업로드를 하지 않습니다.** `snapshot_manifest.json`은 파일과 SHA-256 목록입니다. 새 원격 저장소 이름·공개 범위·코드 라이선스는 업로드 단계에서 정합니다.

## 다른 폴더에서도 실행되는지 확인

1. 사본 루트에서 Python 3.11 이상 환경을 만들고 `pip install -e '.[dev]'`를 실행합니다.
2. `python tools/verify_saved_evidence.py`는 포함된 원본 사진에서 모델 요청을 재구성하고 원본 응답과 결과를 대조합니다. API 호출·과금은 없습니다.
3. `python tools/run_breakfast_checks.py --dataset examples/breakfast_2026-10-25 --output artifacts/prepared`는 현재 초기 기억으로 새 입력을 준비합니다. 역시 API 호출이 없습니다.
4. 실제 재실행은 환경변수 키를 설정하고 새 출력 경로 및 `--execute`를 사용합니다. 결과는 이전과 달라질 수 있습니다.
5. 원문 대조·전체 자동 검사는 검토한 PDF를 별도로 `papers/2610.21211v1.pdf`에 준비한 뒤 `python tools/extract_paper_prompts.py --check`, `python -m unittest discover -s tests -v`로 실행합니다.

Git 줄바꿈 변환은 기록된 응답·사진·프롬프트 해시를 바꾸지 않도록 `.gitattributes`로 관리합니다. 실제 응답 파일을 다시 포맷하거나 수정한 뒤 원본이라고 부르면 안 됩니다. 공개 예시의 성공·실패 판정도 모델 입력과 분리되어 있습니다.

전체 3D 기록은 Blender 4.2와 `tools/render_morning_3d.py`로 별도 생성합니다. 포함된 두 장면만으로 200개 시점 자기반성을 실행할 수 없습니다. 과거 반성 보고서·발표를 다시 생성하는 도구는 로컬 전체 자료가 필요하므로 최소 공개 사본만으로 실행된다고 주장하지 않습니다.
