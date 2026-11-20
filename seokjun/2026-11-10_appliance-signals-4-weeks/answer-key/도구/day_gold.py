"""낮 시간의 실제 가전·관찰 파일에서 평가자용 기회와 시간순 판단 근거를 뽑는다."""

RULES = {
    "wash_unload": ("세탁 완료 뒤 빨래 꺼내기", "세탁기 운전 완료", "세탁기에서 방금 세탁한 빨래 꺼내기", "기기필수", []),
    "wet_to_dryer": ("꺼낸 빨래를 건조기로 옮기기", "같은 회차 빨래를 바구니로 꺼낸 후 세탁기 문 닫힘", "바구니의 젖은 세탁물을 건조기 안에 넣기", "습관", ["날씨"]),
    "wet_to_rack": ("꺼낸 빨래를 건조대에 널기", "같은 회차 빨래를 바구니로 꺼낸 후 세탁기 문 닫힘", "바구니의 젖은 세탁물을 건조대로 옮겨 널기", "습관", ["날씨"]),
    "dry_start": ("세탁물을 넣은 건조기 시작", "건조기 안에 빨래를 넣은 뒤 건조기 문 닫힘", "건조기 운전 시작", "습관", []),
    "dry_unload": ("건조 종료 뒤 30분 내 빨래 꺼내기", "건조기 운전 완료", "건조기 안의 마른 빨래를 바구니로 꺼내기", "습관", []),
    "workout_water": ("운동 타이머 종료 뒤 물 준비", "운동하는 모습이 관찰된 스피커 타이머 종료", "마실 물이 없으면 생수병을 냉장고에서 거실 소파 곁으로 가져오기", "습관", []),
    "fridge_warning": ("문 열림 경고 때 냉장고 문 닫기", "냉장고 문 열림 경고", "문이 열려 있고 앞이 비면 냉장고 문 닫기", "고정안전", []),
    "pot_mat": ("분갈이 전에 방수 매트 준비", "빈 화분과 흙 포대를 함께 창가에 둠", "수납장의 방수 매트를 꺼내 창가 바닥에 깔기", "습관", []),
    "box_string": ("접어 둔 종이 상자에 끈 준비", "현관에서 빈 종이 상자를 납작하게 접어 겹쳐 놓음", "서랍의 끈을 접은 종이 상자 곁에 가져오기", "습관", []),
    "print_pickup": ("복사 후 출력물 가져오기", "프린터 복사 완료", "배출된 종이를 작업방 책상으로 가져오기", "습관", []),
    "lunch_prep": ("점심 요리 관찰", "점심에 냉장고에서 식재료가 든 통을 꺼냄", "식재료 준비와 가열 과정을 관찰", "관찰전용", []),
}

# 시각 자체가 규칙 후보가 될 때에도 같은 원본 동작을 찾는다.
# 기기 신호는 필수 조건일 뿐이고 물건·도착지는 관찰 문장에서 추가로 확인한다.
ACTIONS = {
    "wet_to_dryer": (r"세탁기 옆에 있는 건조기의 문을 연다", r"건조기 안에 빨래가 들어 있다", ("건조기", "문", "열림")),
    "wet_to_rack": (r"젖은 빨래가 든 바구니를 베란다에 놓는다", r"건조대에 빨래가 나란히 걸려 있다", None),
    "dry_start": (r"건조기 조작부를 누른다", r"건조기 통이 도는 동안", ("건조기", "운전", "시작")),
    "dry_unload": (r"사용자가 건조기 문을 연다", r"건조기 문을 닫고 빨래가 담긴 바구니를", ("건조기", "문", "열림")),
    "workout_water": (r"냉장고 문을 열고 문 선반에서 작은 생수병을 꺼낸다", r"생수병을 들고 소파 옆에 앉아", ("냉장고", "문", "열림")),
    "pot_mat": (r"수납장 맨 아래 칸에서 접혀 있는 방수 매트를 꺼낸다", r"바닥에 방수 매트를 펴고", None),
    "box_string": (r"서랍에서 끈 한 타래를 꺼내 상자를 묶는다", r"서랍에서 끈 한 타래를 꺼내 상자를 묶는다", None),
    "print_pickup": (r"출력된 종이를 들고 책상에 앉는다", r"출력된 종이를 들고 책상에 앉는다", ("프린터", "복사", "완료")),
}


def signals(d, dev, event, value, start=0, stop=86400):
    return [s["sec"] for s in d.signals
            if start <= s["sec"] <= stop and (s["기기"], s["항목"], s["값"]) == (dev, event, value)]


def observations(d, text, start, stop):
    return [t for t, _, sentence in d.changes if start <= t <= stop and text in sentence]


def first(d, text, start, stop):
    return next(iter(observations(d, text, start, stop)), None)


def washing(d):
    for end in signals(d, "세탁기", "운전", "완료"):
        deadline = end + 1800
        beginnings = signals(d, "세탁기", "운전", "시작", stop=end)
        began = beginnings[-1] if beginnings else None
        load = first(d, "세탁기 안으로 밀어 넣는다", began - 180, began) if began is not None else None
        undisturbed = began is not None and not signals(d, "세탁기", "문", "열림", began, end)
        current = d.frame(end)
        person_elsewhere = current and current[0] != "다용도실" and "사용자" in current[1]
        ready = load is not None and undisturbed and person_elsewhere
        checks = [(end, "가능" if ready else "확인필요",
                   "옷 투입과 운전 시작 뒤 문을 연 신호가 없고, 세탁이 끝났다. 사용자는 다른 방에 있다. 세탁물 꺼내기를 시작할 수 있다."
                   if ready else "빨래 투입·회차·현재 사용 여부를 먼저 확인한다.")]
        opened = signals(d, "세탁기", "문", "열림", end, deadline)
        started = first(d, "젖은 빨래를 바구니로 옮긴다", end, deadline)
        last = first(d, "마지막 옷을 꺼낸다", end, deadline)
        evidence = [t for t in (load, began, end, *opened[:1], started, last) if t is not None]
        if not ready and started is not None:
            checks.append((started, "선행", "사용자가 직접 젖은 빨래를 꺼내기 시작했다."))
        result = "함" if started is not None and last is not None else ("관찰 불가" if opened else "하지 않음")
        yield d.case("wash_unload", end, result, evidence=evidence, checks=checks,
                     reason="완료한 회차의 세탁물을 꺼내는지 사람의 문 열림과 바구니 관찰로 대조했다. 마감은 완료 후 30분이다.")
        if last is None:
            continue
        closed = signals(d, "세탁기", "문", "닫힘", last, deadline)
        if not closed:
            continue
        trigger = closed[0]
        guard = {"날씨": "비" if d.weather(trigger) == "비" else "비 없음"}
        dry = first(d, "건조기 안에 넣는다", trigger, trigger + 1800)
        full = first(d, "건조기 안에 빨래가 들어 있다", trigger, trigger + 1800)
        rack = first(d, "건조대에 걸친다", trigger, trigger + 1800)
        hanging = first(d, "건조대에 빨래가 나란히 걸려 있다", trigger, trigger + 1800)
        empty = first(d, "빈 바구니", trigger, trigger + 1800)
        for rid, hit, confirmed, alt, destination in (
            ("wet_to_dryer", dry, full, hanging, "건조기"), ("wet_to_rack", rack, hanging, full, "건조대")
        ):
            checks = [(trigger, "확인필요", f"젖은 빨래를 꺼냈다. {destination} 공간과 이번 옷의 건조 가능 여부는 아직 확인되지 않았다.")]
            evidence = [last, trigger]
            if hit is not None and confirmed is not None:
                checks.append((hit, "선행", f"사용자가 직접 빨래를 {destination}에 옮기고 있다."))
                evidence.extend([hit, confirmed])
                result, reason = "함", f"꺼낸 빨래가 실제로 {destination}에 들어가거나 걸린 것을 관찰했다."
            elif alt is not None and empty is not None:
                checks.append((max(alt, empty), "불필요", "이 회차 빨래는 다른 장소로 모두 옮겨져 바구니가 비었다."))
                evidence.extend([alt, empty])
                result, reason = "하지 않음", "다른 건조 방법으로 세탁물을 옮기고 바구니가 빈 것을 관찰했다."
            else:
                result, reason = "관찰 불가", "원래 바구니와 도착지의 세탁물이 모두 보이지 않아 행선지를 확정할 수 없다."
            yield d.case(rid, trigger, result, evidence=sorted(set(evidence)), checks=checks,
                         guards=guard, reason=reason)


def drying(d):
    for door in signals(d, "건조기", "문", "닫힘"):
        loaded = first(d, "건조기 안에 넣는다", door - 120, door)
        frame = d.frame(door)
        if loaded is None or not frame or "건조기 안에 빨래가 들어 있다" not in frame[1]:
            continue
        starts = signals(d, "건조기", "운전", "시작", door, door + 1800)
        checks = [(door, "확인필요", "빨래 투입과 문 닫힘은 확인했다. 선택 코스와 옷감의 건조 가능 여부를 확인할 자료가 없다.")]
        if starts:
            checks.append((starts[0], "선행", "사람이 건조기 조작부를 눌러 이미 운전이 시작됐다."))
        yield d.case("dry_start", door, "함" if starts else "하지 않음", evidence=[loaded, door, *starts[:1]],
                     checks=checks, reason="빨래가 든 건조기 문을 닫은 뒤의 운전 시작 신호를 별도로 확인했다.")

    for end in signals(d, "건조기", "운전", "완료"):
        near = signals(d, "건조기", "문", "열림", end, end + 1800)
        took = first(d, "건조기 안에서 빨래를 꺼내", end, end + 1800)
        checks = [(end, "확인필요", "건조가 끝났지만 곧바로 꺼내길 원하는지와 주변 상태가 확인되지 않았다.")]
        if took is not None:
            checks.append((took, "선행", "사용자가 이미 빨래를 꺼내고 있다."))
        result = "함" if took is not None else ("관찰 불가" if near else "하지 않음")
        yield d.case("dry_unload", end, result, evidence=[end, *near[:1], *([took] if took is not None else [])],
                     checks=checks, reason="30분 안에 발생한 필수 문 열림 신호를 검사했다. 나중에 사람이 열어도 그 시각은 이 마감 밖이다.")


def water(d):
    for t in signals(d, "스마트 스피커", "타이머", "종료"):
        exercise = first(d, "매트 위에서 무릎을 번갈아", t - 1800, t)
        if exercise is None:
            continue
        prepared = first(d, "물이 든 텀블러를 소파 옆 바닥에 놓는다", t - 1800, t)
        got = first(d, "문 선반에서 작은 생수병을 꺼낸다", t, t + 1800)
        served = first(d, "생수병을 들고 소파 옆에 앉아", t, t + 1800)
        if prepared is not None:
            checks = [(t, "불필요", "운동 전에 사용자가 물이 든 텀블러를 소파 곁에 놓았다. 추가 생수병을 제공하지 않는다.")]
            evidence = [prepared, exercise, t]
            result, why = "이미 함", "운동 전에 마실 물이 소파 곁에 이미 준비됐다. 이 기회는 냉장고에서 가져온 성공·실패 횟수에서 뺀다."
        elif got is not None and served is not None:
            checks = [(t, "확인필요", "운동과 타이머 종료는 확인했지만 냉장고 안 생수병 재고와 현재 제공 가능 여부는 보이지 않는다."),
                      (got, "선행", "사용자가 직접 냉장고를 열어 생수병을 꺼냈다.")]
            evidence = [exercise, t, got, served]
            result, why = "함", "냉장고 안에서 생수병을 꺼내 거실 소파 곁에 가져온 모습을 확인했다."
        else:
            checks = [(t, "확인필요", "운동 종료 시점에 물의 위치나 제공 가능 여부가 확인되지 않는다.")]
            evidence = [exercise, t]
            result, why = "관찰 불가", "냉장고에서 꺼낸 생수병과 거실 도착을 모두 입증하는 관찰이 없다."
        yield d.case("workout_water", t, result, evidence=evidence, checks=checks, reason=why)


def fridge(d):
    for t in signals(d, "냉장고", "문열림경고", "발생"):
        frame = d.frame(t)
        text = frame[1] if frame else ""
        if "그 앞에는 사람이 없다" in text and "문이 열려" in text:
            status, message = "가능", "경고가 울렸고 열린 문 앞이 빈 것이 이 시각에 직접 보인다. 닫기 시작 예상이다."
        elif "열린 냉장고 앞에 서서" in text:
            status, message = "위험", "열린 문 앞에서 사용자가 칸에 손을 넣고 있다. 손이 있는 동안 닫지 않는다."
        else:
            status, message = "확인필요", "경고음만으로는 문 앞에 사람이 있는지 알 수 없다. 시야 확보를 기다린다."
        checks = [(t, status, message)]
        closes = signals(d, "냉장고", "문", "닫힘", t, t + 1800)
        if closes and status != "가능":
            checks.append((closes[0], "선행", "사람이 냉장고 문을 닫아 닫기 작업이 끝났다."))
        yield d.case("fridge_warning", t, "함" if closes else "관찰 불가", evidence=[t, *closes[:1]],
                     checks=checks, reason="경고 시점과 이후 자연 기록에서 문이 닫힌 시각을 구분한다. 사람이 닫았다는 사실은 로봇 실행 성공이 아니다.")


def other_scenes(d):
    for rid, trigger_text, finished, state, status_reason in (
        ("pot_mat", "빈 화분 하나와 작은 흙 포대", "바닥에 방수 매트를 펴고", "확인필요", "화분과 흙은 보이지만 사용할 매트 위치가 아직 확인되지 않았다."),
        ("box_string", "납작하게 접은 상자를 겹쳐", "서랍에서 끈 한 타래를 꺼내", "확인필요", "접은 상자는 보이지만 묶을 끈의 위치와 재고가 확인되지 않았다."),
        ("print_pickup", None, "출력된 종이를 들고 책상에 앉는다", "가능", "복사가 끝났고 배출구로 나온 종이 한 장이 직전에 보였다. 사용자는 아직 들지 않았다."),
    ):
        triggers = (signals(d, "프린터", "복사", "완료") if trigger_text is None
                    else observations(d, trigger_text, 0, 86400))
        for t in triggers:
            done = first(d, finished, t, t + 1800)
            evidence = [t]
            if rid == "print_pickup":
                page = first(d, "배출구로 종이 한 장이 밀려 나온다", t - 60, t)
                if page is None:
                    raise ValueError(f"{d.date} 복사 완료 때 배출된 종이 확인 불가")
                evidence.insert(0, page)
            checks = [(t, state, status_reason)]
            if done is not None:
                evidence.append(done)
                if state != "가능":
                    checks.append((done, "선행", "사용자가 해당 물건을 직접 준비했다."))
            yield d.case(rid, t, "함" if done is not None else "관찰 불가", evidence=evidence, checks=checks,
                         reason="독립적인 앞 장면과 마감 안에 나온 물건·사람 행동을 대조했다. 한두 번의 사례는 습관 채택 기준에 부족하다.")

    for t, location, sentence in d.changes:
        if not (11 * 3600 <= t < 14 * 3600 and location == "주방"
                and "냉장고에서" in sentence and "하나를 꺼내 조리대에 놓는다" in sentence):
            continue
        cooked = next((p for p, _, s in d.changes if t < p <= t + 1800 and
                       any(word in s for word in ("냉장고", "인덕션", "전자레인지", "샌드위치")) and
                       any(word in s for word in ("인덕션을 끄고 국수를", "그릇을 꺼내 받침 위에", "샌드위치를 반으로 잘라"))), None)
        yield d.case("lunch_prep", t, "함" if cooked is not None else "관찰 불가",
                     evidence=[t, *([cooked] if cooked is not None else [])],
                     checks=[(t, "확인필요", "식재료가 나왔지만 메뉴 선택과 불·칼을 사용하는 조리는 평가 대상인 자율 도움에 포함하지 않는다.")],
                     reason="샌드위치 준비, 인덕션 조리, 전자레인지 데우기는 식재료 관찰 후에야 확인된다.")


def cases(d):
    return [*washing(d), *drying(d), *water(d), *fridge(d), *other_scenes(d)]
