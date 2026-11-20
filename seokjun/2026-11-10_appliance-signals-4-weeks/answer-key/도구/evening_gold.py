"""28일 관찰의 저녁 사건 부호화. 미래 행은 자연행동 확인에만 쓴다."""
from datetime import date


BEER = "냉장고의 맥주 한 캔을 사용자 곁 소파 탁자로 가져오기"
DINNER_TABLE = "접힌 거실 식탁을 TV 앞으로 가져가기"
LOAD_DISHES = "저녁 빈 그릇을 식기세척기 하단 바구니에 넣기"
RULES = {
    "pm_beer_channel": ("채널 선택 뒤 맥주", "사용자가 TV 채널을 선택함", BEER, "습관", ["채널", "요일"]),
    "pm_beer_power": ("TV 전원 켜짐 뒤 맥주", "사용자가 TV 전원을 켬", BEER, "습관", ["요일"]),
    "pm_table": ("저녁 쟁반과 TV 앞 식탁", "그릇·물컵·수저를 한 쟁반에 차림", DINNER_TABLE, "습관", []),
    "pm_tray": ("TV 앞 식탁을 편 뒤 쟁반 가져오기", "저녁 쟁반을 차린 후 TV 앞의 접이식 식탁을 폄", "저녁 쟁반을 주방 조리대에서 TV 앞 식탁으로 옮기기", "습관", []),
    "pm_dinner_tv": ("저녁 쟁반을 TV 앞에 놓은 뒤 전원", "저녁 쟁반이 TV 앞 낮은 식탁에 놓임", "거실 TV 전원 켜기", "습관", []),
    "pm_stow": ("거실 저녁을 마친 뒤 식탁 정리", "TV 앞 식사 뒤 사용한 수저와 빈 그릇이 식기세척기 바구니로 들어감", "식사를 마친 거실 접이식 식탁을 접어 소파 옆에 세우기", "습관", []),
    "pm_load": ("저녁 식사 뒤 빈 그릇", "저녁 식탁의 그릇이 비고 수저가 그 안에 놓임", LOAD_DISHES, "습관", []),
    "pm_wash": ("저녁 식기 적재 후 세척 시작", "사용한 그릇을 넣은 뒤 식기세척기 문이 닫힘", "적재된 식기세척기 운전 시작", "습관", []),
    "pm_clean": ("세척 종료 직후 마른 그릇 정리", "식기세척기가 세척 완료를 알림", "세척된 그릇을 식기세척기에서 찬장으로 옮기기", "습관", []),
    "pm_wet": ("젖은 우산 아래 물받이", "현관에서 닫힌 우산 끝에 물방울이 떨어짐", "현관 쟁반을 우산 밑에 놓기", "습관", []),
    "pm_read_on": ("종이책을 들고 앉을 때 독서등", "협탁에서 종이책을 들어 침대에 기대어 앉음", "침실 독서등 켜기", "습관", []),
    "pm_read_off": ("책을 덮을 때 독서등", "책갈피를 끼우고 종이책을 덮음", "침실 독서등 끄기", "습관", []),
    "pm_pause": ("식사 중 잠깐 자리 비움", "먹던 그릇을 식탁에 그대로 두고 사용자가 일어남", LOAD_DISHES, "고정안전", []),
    "pm_kitchen": ("이미 주방 식탁에 차린 저녁", "수저와 음식을 주방 식탁에 놓아 저녁 자리가 마련됨", DINNER_TABLE, "고정안전", []),
    "pm_guest": ("방문객 식사 차림", "종이봉투를 든 방문객이 도착", "주방 식탁에 수저 두 벌 놓기", "습관", []),
    "pm_return": ("저녁 귀가 관찰", "사용자가 현관문 안으로 들어옴", "귀가만으로 저녁 식사를 단정하지 않기", "관찰전용", []),
}

BEER_START = "냉장고 문 안쪽 선반에서 ‘맥주’가 쓰인 캔 한 개를 꺼낸다"
BEER_END = "소파 옆 탁자에 맥주 캔을 내려놓는다"
TABLE_START = "벽과 소파 사이에서 다리가 접힌 작은 식탁을 꺼낸다"
TABLE_END = "TV 앞 바닥에 식탁 다리를 펴고"
LOAD_START = "싱크대 아래 식기세척기 문을 내려 연다"
LOAD_END = "빈 그릇을 식기세척기 하단 바구니 칸에 끼운다"
WASH = "식기세척기 시작 버튼을 누른다"
UMBRELLA_TRAY = "얕은 플라스틱 쟁반을 바닥에 놓는다"
GUEST_CUTLERY = "사용자가 수저를 두 벌 놓는다"

# 시간이 같은 한 줄에서 시작과 결과가 모두 확인되는 단일 조작도 있다.
# 손에 닿지 않은 물건이나 처음 움직인 의도는 앞선 시각으로 소급하지 않는다.
ACTIONS = {
    "pm_beer_channel": (BEER_START, BEER_END, ("냉장고", "문", "열림")),
    "pm_beer_power": (BEER_START, BEER_END, ("냉장고", "문", "열림")),
    "pm_table": (TABLE_START, TABLE_END, None),
    "pm_tray": ("조리대에서 쟁반을 양손으로 든다", "TV 앞 낮은 식탁에 쟁반을 내려놓는다", None),
    "pm_dinner_tv": ("리모컨을 들고 있다. TV 화면이 밝아진다", "리모컨을 들고 있다. TV 화면이 밝아진다", ("TV", "전원", "켜짐")),
    "pm_stow": ("비워진 접이식 식탁의 다리를 안으로 접는다", "접힌 식탁을 벽과 소파 사이에 세운다", None),
    "pm_load": (LOAD_START, LOAD_END, ("식기세척기", "문", "열림")),
    "pm_wash": (WASH, WASH, ("식기세척기", "운전", "시작")),
    "pm_clean": ("윗바구니에서 마른 컵을 꺼내", "마른 접시를 낮은 찬장 안에 놓는다", ("식기세척기", "문", "열림")),
    "pm_wet": (UMBRELLA_TRAY, UMBRELLA_TRAY, None),
    "pm_read_on": ("협탁의 스위치를 누른다. 책 표지가 환해진다", "협탁의 스위치를 누른다. 책 표지가 환해진다", ("독서등", "전원", "켜짐")),
    "pm_read_off": ("독서등이 꺼진다", "독서등이 꺼진다", ("독서등", "전원", "꺼짐")),
    "pm_guest": (GUEST_CUTLERY, GUEST_CUTLERY, None),
}


def scene(d, phrase, lo, hi):
    return [t for t, _, text in d.changes if lo <= t <= hi and phrase in text]


def signals(d, device, event, value, lo, hi):
    return [s["sec"] for s in d.signals if lo <= s["sec"] <= hi and
            (s["기기"], s["항목"], s["값"]) == (device, event, value)]


def power_case(d, t, device, target):
    latest = d.last_signal(device, "전원", t)
    changes = signals(d, device, "전원", target, t + 4, t + 1800)
    if latest is None:
        checks = [(t, "확인필요", f"{device}의 현재 전원 상태를 확인한 이전 신호가 없다. 전원 상태를 먼저 조회한다.")]
    else:
        source = latest["신호ID"]
        value = latest["값"]
        if value == target:
            checks = [(t, "불필요", f"{source}에서 {device} {value} 확인. 이미 목표 상태다.")]
        else:
            checks = [(t, "가능", f"현재까지 마지막 전원 신호 {source}에서 {device} {value} 확인. 지금 {target} 명령이 가능하다.")]
    if changes and latest is None:
        checks.append((changes[0], "선행", f"사용자가 {device} 전원을 조작해 {target} 상태가 됐다."))
    proof = changes[:1]
    if latest and latest["신호ID"].startswith(d.date + "-"):
        proof = [latest["sec"], *proof]
    result = "이미 함" if latest and latest["값"] == target else ("함" if changes else "하지 않음")
    return result, proof, checks


def beer_case(d, s):
    t = s["sec"]
    key = "pm_beer_channel" if s["항목"] == "채널" else "pm_beer_power"
    guards = {"요일": "월화수목금토일"[date.fromisoformat(d.date).weekday()]}
    if key == "pm_beer_channel":
        guards["채널"] = s["값"]
    pre = scene(d, BEER_END, t - 1800, t)
    disposed = scene(d, "분리수거 바구니에 내려놓는다", t - 1800, t)
    if pre and (not disposed or pre[-1] > disposed[-1]):
        return d.case(key, t, "이미 함", evidence=[pre[-1], t],
                      checks=[(t, "선행", "이번 시청에 앞서 사용자가 캔을 탁자에 둔 모습이 기록됐다. 두 번째 캔을 준비하지 않는다.")],
                      guards=guards, reason="채널·전원 전부터 사용자 곁에 있던 캔은 새 맥주 수령 실적에서 제외한다.")
    end = t + 1800
    takes = scene(d, BEER_START, t, end)
    checks = [(t, "확인필요", "현재 냉장고 안에 가져올 맥주가 있는지 이 시각까지의 관찰로 확인되지 않았다.")]
    if takes:
        placed = scene(d, BEER_END, takes[0], takes[0] + 120)
        checks.append((takes[0], "선행", "사용자가 직접 냉장고 선반에서 맥주를 집었다. 같은 캔을 또 가져오지 않는다."))
        proof = [t, takes[0], *placed[:1]]
        return d.case(key, t, "함" if placed else "관찰 불가", evidence=proof, checks=checks, guards=guards,
                      reason="마감 안에 냉장고에서 맥주를 꺼냈고 소파 탁자에 놓은 장면을 대조했다." if placed else "꺼낸 물건의 도착을 확인할 수 없다.")
    opened = signals(d, "냉장고", "문", "열림", t, end)
    proof = [t]
    neg = True
    for op in opened:
        close = signals(d, "냉장고", "문", "닫힘", op + 4, op + 600)
        item = scene(d, "냉장고에서 김치통을 꺼낸다", op, close[0] if close else op)
        if not (close and item and all(d.frame(k) is not None for k in range(op, close[0] + 1, 4))):
            neg = False
        proof.extend([op, *item[:1], *close[:1]])
    return d.case(key, t, "하지 않음" if neg else "관찰 불가", evidence=sorted(set(proof)), checks=checks, guards=guards,
                  reason=("30분 동안 냉장고 문을 열지 않았다. 냉장고에서 가져오는 행동에 필요한 신호가 없다." if not opened
                          else "문을 연 동안 연속 관찰된 꺼낸 물건은 김치통이다." if neg else "냉장고를 열었으나 꺼낸 대상과 도착을 모두 확인할 수 없다."))


def cases(d):
    out = []
    for s in d.signals:
        t = s["sec"]
        if s["기기"] == "TV" and (s["항목"] == "채널" or (s["항목"], s["값"]) == ("전원", "켜짐")):
            out.append(beer_case(d, s))
        if (s["기기"], s["항목"], s["값"]) == ("식기세척기", "운전", "완료"):
            opens = signals(d, "식기세척기", "문", "열림", t, t + 1800)
            taken = scene(d, "마른 접시를 낮은 찬장 안에 놓는다", t, t + 1800)
            result = "함" if taken else "관찰 불가" if opens else "하지 않음"
            out.append(d.case("pm_clean", t, result, evidence=[t, *opens, *taken[:1]],
                              checks=[(t, "확인필요", "세척 완료 신호는 받았지만 마른 그릇을 지금 찬장으로 옮길지 확인되지 않았다.")],
                              guards={}, reason="세척 직후 30분의 문 열림 로그와 마른 그릇 회수 장면을 확인했다. 다음날 비운 것을 전날 실적으로 소급하지 않는다."))
    for t, place, text in d.changes:
        if t < 17 * 3600:
            continue
        def add(key, result, proof, checks, reason):
            out.append(d.case(key, t, result, evidence=sorted(set([t, *proof])), checks=checks, guards={}, reason=reason))
        if text.startswith("쟁반 위에") and "물컵과 수저" in text:
            starts = scene(d, TABLE_START, t, t + 1800)
            finishes = scene(d, TABLE_END, t, t + 1800)
            checks = [(t, "확인필요", "주방에 차린 쟁반은 보이지만 현재 TV 앞 공간과 접힌 식탁의 상태는 보이지 않는다.")]
            if starts:
                checks.append((starts[0], "선행", "사용자가 작은 식탁을 직접 꺼내기 시작했다."))
            add("pm_table", "함" if starts and finishes else "관찰 불가", starts[:1] + finishes[:1], checks,
                "준비된 식사 쟁반을 보고 생긴 기회다. 이후 식탁을 꺼내 TV 앞에 펴는 모습을 확인한다.")
        elif TABLE_END in text:
            tray = [v for v, _, line in d.changes if t - 1800 <= v < t and line.startswith("쟁반 위에") and "물컵과 수저" in line]
            if not tray:
                continue
            start = scene(d, "조리대에서 쟁반을 양손으로 든다", t, t + 1800)
            finish = scene(d, "TV 앞 낮은 식탁에 쟁반을 내려놓는다", t, t + 1800)
            checks = [(t, "확인필요", "거실 식탁은 펴졌지만 주방을 떠난 뒤 쟁반의 현재 상태와 사람이 들었는지 확인해야 한다.")]
            if start:
                checks.append((start[0], "선행", "사용자가 주방 쟁반을 양손으로 들었다."))
            add("pm_tray", "함" if start and finish else "관찰 불가", tray[-1:] + start[:1] + finish[:1], checks,
                "주방의 준비와 거실의 빈 식탁이 먼저 확인됐고 같은 쟁반을 TV 앞 식탁으로 옮긴 시작과 도착을 찾았다.")
        elif "TV 앞 낮은 식탁에 쟁반을 내려놓는다" in text:
            result, proof, checks = power_case(d, t, "TV", "켜짐")
            add("pm_dinner_tv", result, proof, checks, "저녁상이 차려진 뒤의 전원 신호를 확인한다. 특정 드라마나 채널의 선택은 요구하지 않는다.")
        elif (text.startswith("주방 식탁 위에") and "수저와 물컵" in text) or GUEST_CUTLERY in text:
            add("pm_kitchen", "이미 함", [], [(t, "불필요", "주방 식탁 위에 수저와 음식을 차리고 있다. TV 앞에 또 상을 마련할 근거가 없다.")],
                "오늘의 저녁 자리가 주방에 마련됐다. 접이식 식탁을 여는 쟁반 조건은 발생하지 않았다.")
        elif "먹던 그릇을 그대로 두고" in text:
            resumed = scene(d, "다시 앉아 식사한다", t, t + 1800)
            add("pm_pause", "하지 않음" if resumed else "관찰 불가", resumed[:1],
                [(t, "위험", "음식이 남은 상태에서 일어났다. 빈 그릇이나 식사 종료를 확인할 때까지 치우지 않는다.")],
                "사용자가 잠시 일어선 동안 식기를 치우지 않았고 다시 앉아 식사하는 모습을 대조했다.")
        elif "빈 그릇 안에 수저가 놓여" in text:
            loading = scene(d, LOAD_START, t, t + 1800)
            loaded = scene(d, LOAD_END, t, t + 1800)
            checks = [(t, "확인필요", "식사는 끝났지만 사용자가 그릇을 포개고 있어 아직 인계 가능한 그릇과 바구니 공간이 확인되지 않았다.")]
            if loading:
                checks.append((loading[0], "선행", "사용자가 그릇을 들고 식기세척기 문을 직접 열기 시작했다. 적재를 중복하지 않는다."))
            add("pm_load", "함" if loaded else "관찰 불가", loading[:1] + loaded[:1], checks,
                "저녁 식사가 끝난 시각 이후 실제 하단 바구니에 그릇을 넣은 장면을 사용한다.")
        elif "손잡이를 놓자 식기세척기 문이 닫혀" in text:
            loaded = scene(d, LOAD_END, t - 1800, t)
            closed = signals(d, "식기세척기", "문", "닫힘", t, t)
            if not loaded or not closed:
                continue
            starts = signals(d, "식기세척기", "운전", "시작", t, t + 1800)
            add("pm_wash", "함" if starts else "하지 않음", [loaded[-1], *starts[:1]],
                [(t, "가능", "그릇 적재와 문 닫힘이 확인됐고 이번 적재 뒤 아직 운전 시작 신호가 없다. 학습한 경우에만 시작 명령을 낼 수 있다.")],
                "적재만 한 날은 마감까지 운전 시작 신호가 없다. 같은 날 사람의 자연 선택과 학습한 규칙의 예상 명령은 각각 보존한다.")
        elif "수저를 담고 바구니를 안으로 민다" in text:
            table = scene(d, "TV 앞 낮은 식탁에 쟁반을 내려놓는다", t - 7200, t)
            if not table:
                continue
            fold = scene(d, "비워진 접이식 식탁의 다리를 안으로 접는다", t, t + 1800)
            stow = scene(d, "접힌 식탁을 벽과 소파 사이에 세운다", t, t + 1800)
            checks = [(t, "확인필요", "주방에서는 식기 적재가 보이지만 거실 식탁에 다른 물건이나 음식이 남았는지 확인할 수 없다.")]
            if fold:
                checks.append((fold[0], "선행", "비워진 식탁과 사람이 다리를 접는 모습이 함께 확인됐다."))
            add("pm_stow", "함" if fold and stow else "관찰 불가", table[-1:] + fold[:1] + stow[:1], checks,
                "이번 식사는 TV 앞에서 했고, 적재 후 빈 식탁을 접어 벽과 소파 사이에 세우는 것을 확인했다.")
        elif "닫힌 장우산 끝에서" in text:
            placed = scene(d, UMBRELLA_TRAY, t, t + 1800)
            checks = [(t, "확인필요", "젖은 우산은 보이지만 물받이로 쓸 빈 쟁반은 확인되지 않았다.")]
            if placed:
                checks.append((placed[0], "선행", "사람이 이미 쟁반을 바닥에 내려놓았다."))
            add("pm_wet", "함" if placed else "관찰 불가", placed[:1], checks, "실제로 물방울이 관찰된 귀가만 비교한다.")
        elif "협탁에서 종이책을 들어 베개에 기대어" in text:
            result, proof, checks = power_case(d, t, "독서등", "켜짐")
            add("pm_read_on", result, proof, checks, "책을 들고 기대어 앉은 뒤 사람이 독서등을 켰는지 전원 신호를 확인했다.")
        elif "책갈피를 끼우고 책을 덮는다" in text:
            result, proof, checks = power_case(d, t, "독서등", "꺼짐")
            add("pm_read_off", result, proof, checks, "책을 덮은 뒤 사람의 소등 신호를 확인한다.")
        elif "종이봉투를 든 방문객이 서 있다" in text:
            serving = scene(d, GUEST_CUTLERY, t, t + 1800)
            checks = [(t, "확인필요", "방문은 확인됐으나 함께 식사할지, 수저가 더 필요한지 알 수 없다.")]
            if serving:
                checks.append((serving[0], "선행", "사용자가 주방 식탁에 수저를 두 벌 놓고 있다."))
            add("pm_guest", "함" if serving else "관찰 불가", serving[:1], checks, "수저 두 벌을 놓은 것은 이번 방문 한 건의 관찰이다.")
        elif "사용자가 신발장 옆으로 들어온다" in text:
            add("pm_return", "관찰 불가", [], [(t, "확인필요", "현관에서 귀가만 보인다. 집에서 먹을지 밖에서 이미 먹었는지 알 수 없다.")],
                "집 밖의 식사는 관찰할 수 없다. 귀가 자체는 식탁을 펴야 한다는 정답으로 사용하지 않는다.")
    return out  # 시간순 정렬과 60분 기회 묶기는 공통 생성기에서 수행한다.
