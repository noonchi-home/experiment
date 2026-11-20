"""4초 관찰과 기기 신호에서 아침 행동의 독립 선행 사건과 실제 결과를 짝짓는다."""
import re


RULES = {
    "am_water": ("약통을 식탁에 놓은 뒤 물컵 준비", "사용자가 아침에 약통을 식탁에 내려놓음",
                 "정수기 물을 컵에 받아 식탁으로 가져오기", "습관", []),
    "am_laptop": ("아침 외출 가방에 노트북 넣기", "아침에 사용자가 작업방 책상 앞에 서고 옆 의자에 가방이 보임",
                  "책상의 노트북을 가방의 안쪽 칸에 넣기", "습관", []),
    "am_charger": ("노트북을 넣은 다음 충전기 챙기기", "사용자가 노트북을 가방 안쪽 칸에 넣음",
                   "작업방의 노트북 충전기를 가방 앞주머니에 넣기", "습관", []),
    "am_alarm": ("생활 알림 이후 약통 열림 관찰", "아침 스마트 스피커의 생활 알림이 울림",
                 "30분 안에 사용자가 약통을 여는지 관찰. 약 건네기·복용 확인은 채점 대상 밖", "관찰전용", []),
    "am_bedding": ("일어나서 이불 개는 과정을 관찰", "사람이 아침 침실 조명을 켬",
                   "사람이 침실을 떠나기 전 이불을 접어 두는 모습 관찰. 이불 접기 기구 미확정", "관찰전용", []),
    "am_drip": ("아침 식사와 함께 드립커피 만들기 관찰", "아침 주방 냉장고 문을 사람이 처음 엶",
                "전기포트로 끓인 물을 필터에 부어 커피를 준비하는 과정 관찰. 뜨거운 물 조작 기능 미확정", "관찰전용", []),
    "am_hair": ("욕실에서 나온 뒤 머리 말리기 관찰", "욕실에서 복도로 나온 사용자가 보임",
                "드라이어를 사용해 머리를 말리는지 관찰. 사용자 몸에 기기를 대는 도움은 채점 대상 밖", "관찰전용", []),
    "am_desk": ("가방 옆에 앉아 노트북으로 일하는 장면", "아침 작업방 책상에 앉고 가방은 의자 옆에 걸려 있음",
                "사용자가 가방을 챙기는지 또는 책상에서 노트북을 여는지 관찰", "관찰전용", []),
}

ACTIONS = {
    "am_water": ("컵걸이에서 작은 유리컵을 빼고 정수기", "물이 담긴 컵을 들어 식탁 쪽으로 가져온다", None),
    "am_laptop": ("노트북 덮개를 닫고 양손으로 들어", "노트북을 가방의 납작한 안쪽 칸에 밀어 넣", None),
    "am_charger": ("멀티탭에서 노트북 충전기를 뺀다", "가방 앞주머니에 충전기를 넣고", None),
}


def first(rows, words, start=0, end=10 * 3600):
    """양 끝 포함. 각 관찰의 첫 변화 시각을 찾는다."""
    pattern = re.compile(words)
    return next((t for t, _, s in rows if start <= t <= end and pattern.search(s)), None)


def signal(d, device, event, value, start=0, end=10 * 3600):
    return next((row["sec"] for row in d.signals
                 if start <= row["sec"] <= end and
                 (row["기기"], row["항목"], row["값"]) == (device, event, value)), None)


def movement_case(d, rule, trigger, existing_pattern, wait_reason):
    """결과는 사후 궤적, 판단은 그때 보인 재고·사용자 선행만 쓴다."""
    until = trigger + 1800
    begin, finish, _ = ACTIONS[rule]
    attempted = first(d.changes, begin, trigger, until)
    done = first(d.changes, finish, attempted if attempted is not None else trigger, until)
    already = first(d.changes, existing_pattern, trigger, until) if existing_pattern else None
    checks = [(trigger, "확인필요", wait_reason)]
    evidence = [trigger]
    if already is not None and (attempted is None or already < attempted):
        # '이미 있던 물컵', '앞주머니를 벌리자 보인 충전기'는 처리가 이미 끝난 근거.
        # 이를 확인한 시각까지 로봇의 취소를 앞당기지 않는다.
        evidence.append(already)
        checks.append((already, "불필요", "사용할 물컵이 식탁에 이미 있다." if rule == "am_water"
                       else "앞주머니가 열리자 안에 충전기와 감긴 선이 보인다. 하나 더 넣으면 중복이다."))
        result, reason = "이미 함", "사람이 새로 준비하지 않고 이미 놓인 물건을 사용하거나 확인했다."
    elif attempted is not None and done is not None:
        evidence.extend((attempted, done))
        checks.append((attempted, "선행", "사용자가 직접 대상에 손을 대고 옮기는 동작을 시작했다."))
        result, reason = "함", "시작 동작과 올바른 목적지로 물건을 옮기는 장면이 차례로 보였다."
    else:
        if attempted is not None:
            evidence.append(attempted)
            checks.append((attempted, "선행", "사람이 직접 준비하는 것은 보였지만 목적지까지 옮겼는지 확인되지 않았다."))
        result, reason = "관찰 불가", "30분 안에 출발과 목적지를 연결할 관찰이 부족하다. 관찰 공백을 실패로 세지 않는다."
    return d.case(rule, trigger, result, evidence=evidence, checks=checks, guards={}, reason=reason)


def cases(d):
    out = []
    alarm = signal(d, "스마트 스피커", "생활 알림", "울림")
    if alarm is not None:
        opened = first(d.changes, "약통 윗면의 작은 뚜껑 하나를 젖힌다", alarm, alarm + 1800)
        evidence = [alarm] if opened is None else [alarm, opened]
        out.append(d.case(
            "am_alarm", alarm, "관찰 불가" if opened is None else "함", evidence=evidence,
            checks=[(alarm, "확인필요", "소리만으로 약통을 열었는지, 복용했는지, 물이 필요한지 알 수 없다.")],
            guards={}, reason=("30분 안에 사용자가 약통을 열었다. 삼켰는지는 관찰로 판단하지 않는다."
                               if opened is not None else "마감까지 약통 개방을 확인할 수 없고 시야에 공백이 있다.")))

    pill = first(d.changes, "약통을 식탁에 내려놓는다")
    if pill is not None:
        out.append(movement_case(d, "am_water", pill, "식탁 위에 이미 있던 물컵을 잡는다",
                                 "약통은 보이지만 사용할 물컵의 현재 재고·자리와 사용자의 선행 여부를 아직 확인해야 한다."))

    desk = first(d.changes, "책상 앞에 서 있다. 가방이 의자에 걸려 있다")
    if desk is not None:
        out.append(movement_case(d, "am_laptop", desk, None,
                                 "사용자가 서 있고 가방이 보인다. 노트북 위치, 빈 안쪽 칸이 아직 함께 확인되지 않았다."))

    packed = first(d.changes, ACTIONS["am_laptop"][1])
    if packed is not None:
        out.append(movement_case(d, "am_charger", packed, "가방 앞주머니를 벌린다. 검은 충전기",
                                 "노트북은 들어갔다. 앞주머니 안과 충전기 위치는 확인 전이다."))

    seated = first(d.changes, "책상 앞에 앉는다. 가방은 의자 옆")
    if seated is not None:
        working = first(d.changes, "노트북 덮개를 들어 올리고 책상 위 충전 케이블을 연결", seated, seated + 1800)
        evidence = [seated] if working is None else [seated, working]
        checks = [(seated, "확인필요", "책상 앞에 앉았고 가방은 걸려 있다. 외출 준비가 시작됐다는 근거가 없다.")]
        if working is not None:
            checks.append((working, "불필요", "사용자가 책상에서 노트북을 열고 전원을 연결한다. 현재 사용할 노트북을 가방에 넣지 않는다."))
        out.append(d.case("am_desk", seated, "함" if working is not None else "관찰 불가",
                          evidence=evidence, checks=checks, guards={},
                          reason="책상에서 노트북을 여는 일과 외출 가방에 노트북을 넣는 일을 구별한다."))

    light = signal(d, "침실 조명", "전원", "켜짐")
    if light is not None:
        exit_room = signal(d, "침실 조명", "전원", "꺼짐", light, light + 1800)
        until = exit_room if exit_room is not None else light + 1800
        folded = first(d.changes, "접힌 이불이 놓여|개어 둔 이불과 베개", light, until)
        untidy = first(d.changes, "베개 밑에 이불 모서리가 끼어", light, until)
        status, evidence, reason = "관찰 불가", [light], "침실을 나가기 전 최종 이불 상태가 보이지 않는다."
        if folded is not None:
            status, evidence, reason = "함", [light, folded], "기상 직후 침실에서 접혀 있는 이불이 보인다."
        elif untidy is not None and exit_room is not None:
            status, evidence, reason = "하지 않음", [light, untidy, exit_room], "이불이 베개 밑에 끼인 채 옷을 집은 뒤 복도로 갔다. 이 기상 장면은 여기서 끝난다."
        out.append(d.case("am_bedding", light, status, evidence=evidence,
                          checks=[(light, "확인필요", "사람이 침실에 있다. 이불 접기 동작의 로봇 지원이 확인되지 않았다.")],
                          guards={}, reason=reason))

    fridge = signal(d, "냉장고", "문", "열림")
    if fridge is not None:
        boil = signal(d, "전기포트", "운전", "시작", fridge, fridge + 1800)
        cup = first(d.changes, "커피가 든 잔을 식탁에 놓는다", fridge, fridge + 1800)
        status, reason = "관찰 불가", "전기포트 운전은 보이나 커피잔을 식탁에 둔 결과를 확인할 수 없다."
        if boil is None:
            status, reason = "하지 않음", "30분 동안 이 집의 드립커피 준비에 필요한 전기포트 시작 신호가 없다."
        elif cup is not None:
            status, reason = "함", "전기포트 시작 뒤 식탁에 커피가 든 잔을 놓았다."
        out.append(d.case("am_drip", fridge, status, evidence=[t for t in (fridge, boil, cup) if t is not None],
                          checks=[(fridge, "확인필요", "아침 냉장고를 열었다. 커피를 원한다는 근거와 로봇의 뜨거운 물 취급 능력을 확인할 수 없다.")],
                          guards={}, reason=reason))

    bath_exit = first(d.changes, "욕실 문이 열리고 사용자가 (머리에 수건을|수건으로 손을)")
    if bath_exit is not None:
        motor = signal(d, "헤어드라이어", "전원", "켜짐", bath_exit, bath_exit + 1800)
        hair = first(d.changes, "드라이어를 한 손에 들고 옆머리를 말린다", bath_exit, bath_exit + 1800)
        status = "하지 않음" if motor is None else ("함" if hair is not None else "관찰 불가")
        reason = {
            "하지 않음": "30분 안에 헤어드라이어 전원 켜짐 신호가 없다.",
            "함": "화장대 쪽에서 사람이 드라이어를 직접 사용해 머리를 말렸다.",
            "관찰 불가": "전원은 켜졌으나 머리 말리는 동작을 확인할 수 없다.",
        }[status]
        out.append(d.case("am_hair", bath_exit, status, evidence=sorted(set(t for t in (bath_exit, motor, hair) if t is not None)),
                          checks=[(bath_exit, "확인필요", "욕실 밖에서 보이는 모습만 기록한다. 드라이어로 사람의 머리를 말리는 로봇 기능은 확인되지 않았다.")],
                          guards={}, reason=reason))
    return out
