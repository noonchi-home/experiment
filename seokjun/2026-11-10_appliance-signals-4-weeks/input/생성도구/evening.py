"""한 집의 저녁. 모든 시각은 자정부터 지난 초이며 4초 눈금이다."""


def clock(hour, minute=0):
    return hour * 3600 + minute * 60


def frames(day, base, place, changes):
    for delta, text in changes:
        day.see(base + delta, place, text)


def return_home(day, start, from_work):
    day.see(start - 60, "현관", "닫힌 현관문과 신발장이 보인다. 문 앞에는 사람이 보이지 않는다.")
    day.signal(start, "사람", "현관문", "문", "열림")
    day.see(start, "현관", "문이 안쪽으로 열리고 사용자가 신발장 옆으로 들어온다.")
    day.see(start + 8, "현관", "사용자가 문을 등지고 신발을 벗는다.")
    day.signal(start + 12, "사람", "현관문", "문", "닫힘")
    if from_work:
        if day.rain and start < clock(20):
            frames(day, start, "현관", [
                (20, "사용자가 가방을 벤치 위에 올린다. 닫힌 장우산 끝에서 바닥으로 물방울이 떨어진다."),
                (36, "사용자가 신발장 옆에 세워 둔 얕은 플라스틱 쟁반을 바닥에 놓는다."),
                (48, "사용자가 우산의 고정 끈을 풀고, 펼친 우산을 쟁반 위에 기울여 둔다."),
                (68, "쟁반 바닥에 물방울이 고여 있다. 사용자가 벤치에서 가방을 집는다."),
            ])
            day.note(start + 48, "퇴근 뒤 물방울이 떨어지는 장우산을 현관 쟁반 위에 펴 둠.")
            desk = start + 96
        else:
            day.see(start + 20, "현관", "사용자가 어깨에서 가방을 내려 한 손에 들고 실내화로 갈아 신는다.")
            desk = start + 52
        day.see(desk - 12, "거실", "사용자가 가방을 들고 책상 쪽으로 지나간다.")
        day.see(desk, "작업방", "사용자가 책상 옆에 가방을 놓는다.")
        day.see(desk + 12, "작업방", "가방 안에서 꺼낸 노트북이 책상 위에 놓인다.")
        if day.n % 6 != 1:
            day.see(desk + 28, "작업방", "사용자가 가방 앞주머니에서 감긴 충전기를 꺼내 책상 위에 둔다.")
            day.see(desk + 44, "작업방", "사용자가 책상 아래 멀티탭에 충전기 플러그를 꽂는다.")
        day.see(desk + 68, "거실", "사용자가 소파에 기대어 휴대전화 화면을 본다.")
    else:
        day.see(start + 20, "현관", "사용자가 벗은 운동화를 신발장 아래에 밀어 넣는다.")
        day.see(start + 44, "거실", "사용자가 거실 의자에 겉옷을 걸친다.")
        day.see(start + 72, "거실", "사용자가 소파에 기대 있고 무릎 위 휴대전화 화면이 켜져 있다.")


def visit(day, t, arriving):
    day.signal(t, "사람", "현관문", "문", "열림")
    day.see(t, "현관", "사용자가 문을 열자 종이봉투를 든 방문객이 서 있다." if arriving
            else "방문객이 현관에서 신발을 신고 사용자가 문고리를 잡고 있다.")
    day.signal(t + 16, "사람", "현관문", "문", "닫힘")
    day.see(t + 16, "현관", "닫힌 문 안쪽에서 두 사람이 슬리퍼를 나란히 정리한다." if arriving
            else "현관문이 닫히고 현관 안쪽에는 사용자만 보인다.")
    day.see(t + 48, "주방" if arriving else "거실",
            "두 사람이 주방 식탁 옆에서 종이봉투를 내려놓는다." if arriving
            else "사용자가 거실 의자에 앉아 펼쳐진 잡지를 보고 있다.")
    if arriving:
        day.see(t + 72, "주방", "방문객이 주방 식탁에 앉아 있다. 앞에는 종이봉투와 귤 몇 개가 놓여 있다.")


def unload_clean_dishes(day, start):
    """직전 세척 뒤 식기가 남은 날에는 저녁 준비 전에 바구니를 비운다."""
    day.signal(start, "사람", "식기세척기", "문", "열림")
    day.see(start, "주방", "사용자가 식기세척기 문을 내린다. 바구니에 그릇 여러 개가 놓여 있다.")
    day.see(start + 12, "주방", "사용자가 윗바구니에서 마른 컵을 꺼내 싱크대 옆 찬장에 넣는다.")
    day.see(start + 36, "주방", "사용자가 아랫바구니에서 접시를 겹쳐 꺼낸다.")
    day.see(start + 56, "주방", "사용자가 마른 접시를 낮은 찬장 안에 놓는다.")
    day.signal(start + 80, "사람", "식기세척기", "문", "닫힘")
    day.see(start + 80, "주방", "비어 있는 바구니가 안으로 들어가고 사용자가 식기세척기 문을 올려 닫는다.")
    day.see(start + 96, "주방", "닫힌 식기세척기 위 조리대에 컵 하나가 보이고 사용자는 싱크대 앞에 서 있다.")
    day.note(start, "이전에 운전을 완료한 식기세척기에서 마른 그릇을 꺼내 찬장에 정리.")


def dinner(day, start, late_sport):
    """저녁 준비, 식사, 그릇 적재, 식탁 정리 장면을 기록한다."""
    rng = day.rng
    kitchen_table = day.guest or day.n in (6, 24)
    dishes = [
        ("카레가 담긴 밀폐용기", "카레밥 그릇", "숟가락"),
        ("두부조림이 담긴 반찬통", "밥공기와 두부조림 접시", "젓가락"),
        ("볶음밥이 든 유리 용기", "볶음밥 접시", "숟가락"),
        ("국이 든 용기", "국그릇과 밥공기", "숟가락"),
        ("멸치볶음과 김치가 든 통", "밥공기와 작은 반찬 접시", "젓가락"),
    ]
    container, plate, utensil = rng.choice(dishes)
    channel, drama = rng.choice((("채널 07", "가족 드라마"), ("채널 22", "사극 재방송"),
                                 ("채널 11", "일일 드라마"), ("채널 07", "연속극 재방송")))
    if day.clean_dishes:
        unload_clean_dishes(day, start - 196)
    day.see(start - 36, "주방", "사용자가 조리대 한쪽을 닦고 작은 그릇을 꺼낸다.")
    day.signal(start, "사람", "냉장고", "문", "열림")
    day.see(start, "주방", "사용자가 냉장고 문을 열고 안쪽 선반에 손을 넣는다.")
    day.see(start + 8, "주방", f"사용자가 냉장고 선반에서 {container} 하나를 꺼낸다.")
    day.signal(start + 20, "사람", "냉장고", "문", "닫힘")
    frames(day, start, "주방", [
        (20, "사용자가 냉장고를 닫고 조리대 위에 용기를 내려놓는다."),
        (44, "사용자가 그릇에 밥을 담아 조리대 앞에 놓는다."),
        (80, "전자레인지 안쪽에 뚜껑을 비스듬히 덮은 그릇이 보인다."),
        (92, "사용자가 전자레인지의 시작 버튼에서 손을 뗀다."),
        (112, "사용자가 수저통에서 수저를 꺼내 빈 쟁반 위에 둔다."),
        (148, "조리대 위에 밥그릇과 반찬 뚜껑이 보인다. 사용자는 싱크대 앞에 서 있다."),
    ])
    day.signal(start + 92, "사람", "전자레인지", "운전", "시작")
    ready = start + 92 + rng.choice((80, 96, 112))
    day.signal(ready, "기계", "전자레인지", "운전", "완료")
    day.see(ready + 8, "주방", "사용자가 전자레인지에서 김이 나는 그릇을 꺼낸다.")
    serve = ready + rng.choice((48, 60, 76))
    if kitchen_table:
        if day.guest:
            day.see(serve, "주방", "방문객이 주방 식탁에서 귤을 한쪽으로 치우고 사용자가 수저를 두 벌 놓는다.")
            day.see(serve + 24, "주방", "두 사람이 주방 식탁 양쪽 의자를 당긴다. 그릇 두 개가 식탁에 놓여 있다.")
        else:
            day.see(serve, "주방", f"주방 식탁 위에 {plate}, 수저와 물컵이 보인다.")
            day.see(serve + 24, "주방", "사용자가 주방 식탁에 의자를 당겨 앉는다.")
    else:
        day.see(serve, "주방", f"쟁반 위에 {plate}, 물컵과 수저가 놓여 있다.")
        day.see(serve + 16, "거실", "사용자가 벽과 소파 사이에서 다리가 접힌 작은 식탁을 꺼낸다.")
        day.see(serve + 28, "거실", "사용자가 TV 앞 바닥에 식탁 다리를 펴고 모서리를 눌러 본다.")
        day.see(serve + 52, "주방", "사용자가 조리대에서 쟁반을 양손으로 든다.")
        day.see(serve + 68, "거실", "사용자가 TV 앞 낮은 식탁에 쟁반을 내려놓는다.")
        day.signal(serve + 88, "사람", "TV", "전원", "켜짐")
        day.see(serve + 88, "거실", "사용자가 리모컨을 들고 있다. TV 화면이 밝아진다.")
        day.signal(serve + 104, "사람", "TV", "채널", channel)
        day.see(serve + 104, "거실", f"TV 편성 안내에 ‘{drama}’가 뜨고 사용자가 리모컨을 내려놓는다.")
    place = "주방" if kitchen_table else "거실"
    eat = serve + (48 if kitchen_table else 124)
    day.see(eat, place, f"사용자가 식탁 앞에서 {utensil}을 들고 식사한다.")
    day.see(eat + 192, place, "사용자가 수저를 잠깐 내려놓고 물을 마신다.")
    day.see(eat + 216, place, "식탁 위에 반쯤 남은 밥그릇이 있고 사용자는 앉아서 식사를 이어 간다.")
    if day.n % 4 == 2 and not kitchen_table:
        pause = eat + 360
        day.see(pause, "거실", "사용자가 먹던 그릇을 그대로 두고 식탁에서 일어난다.")
        day.signal(pause + 20, "사람", "냉장고", "문", "열림")
        day.see(pause + 20, "주방", "사용자가 냉장고에서 김치통을 꺼낸다.")
        day.signal(pause + 32, "사람", "냉장고", "문", "닫힘")
        day.see(pause + 32, "주방", "냉장고 문이 닫히고 사용자가 작은 접시에 김치를 던다.")
        day.see(pause + 60, "거실", "사용자가 김치 접시를 들고 TV 앞 식탁으로 돌아온다.")
        day.see(pause + 76, "거실", "사용자가 다시 앉아 식사한다.")
    finish = (clock(22, 7) if late_sport else eat + rng.randrange(17, 31) * 60)
    day.see(finish, place, "빈 그릇 안에 수저가 놓여 있다. 사용자가 그릇을 포개기 시작한다.")
    day.see(finish + 24, "주방", "사용자가 빈 그릇을 들고 싱크대 옆에 선다.")
    load = finish + 68
    day.signal(load, "사람", "식기세척기", "문", "열림")
    day.see(load, "주방", "사용자가 싱크대 아래 식기세척기 문을 내려 연다.")
    day.see(load + 16, "주방", "사용자가 빈 그릇을 식기세척기 하단 바구니 칸에 끼운다.")
    day.see(load + 44, "주방", "사용자가 수저를 담고 바구니를 안으로 민다.")
    day.signal(load + 56, "사람", "식기세척기", "문", "닫힘")
    day.see(load + 56, "주방", "사용자가 손잡이를 놓자 식기세척기 문이 닫혀 있다.")
    if day.n % 6 != 2:
        day.signal(load + 68, "사람", "식기세척기", "운전", "시작")
        day.see(load + 68, "주방", "사용자가 식기세척기 시작 버튼을 누른다. 표시등이 켜진다.")
        cycle = rng.choice((52, 58, 64, 72)) * 60
        day.signal(load + 68 + cycle, "기계", "식기세척기", "운전", "완료")
    else:
        day.note(load, "식후 그릇 적재만 관찰. 저녁 운전 시작 신호는 없음.")
    after = load + 108
    if kitchen_table:
        day.see(after, "주방", "식탁에 빈 컵과 물병이 남아 있고 사용자가 식탁 위를 닦는다.")
        day.see(after + 64, "거실", "소파에 앉은 두 사람 사이에 방문객의 종이봉투가 놓여 있다."
                if day.guest else "사용자가 거실 의자에 앉아 잡지를 보고 있다.")
        return
    day.see(after, "거실", "사용자가 비워진 접이식 식탁의 다리를 안으로 접는다.")
    day.see(after + 20, "거실", "사용자가 접힌 식탁을 벽과 소파 사이에 세운다.")
    day.see(after + 60, "거실", "사용자가 소파에 기대어 TV 화면을 본다.")
    if not late_sport:
        off = after + rng.randrange(4, 15) * 60
        day.signal(off, "사람", "TV", "전원", "꺼짐")
        day.see(off, "거실", "사용자가 리모컨을 내려놓는다. TV 화면이 어두워진다.")
        day.see(off + 28, "거실", "소파 등받이 너머로 사용자의 어깨와 휴대전화가 보인다.")
    day.note(serve, "저녁 쟁반 준비 뒤 접이식 식탁을 TV 앞으로 옮겨 식사. 선택한 드라마는 날짜별로 다름.")


def beer(day, at, late_sport):
    day.see(at - 20, "거실", "사용자가 주방 쪽으로 걸어간다.")
    day.signal(at, "사람", "냉장고", "문", "열림")
    day.see(at, "주방", "사용자가 냉장고 문을 연다.")
    day.see(at + 8, "주방", "사용자가 냉장고 문 안쪽 선반에서 ‘맥주’가 쓰인 캔 한 개를 꺼낸다.")
    day.signal(at + 16, "사람", "냉장고", "문", "닫힘")
    day.see(at + 16, "주방", "사용자가 한 손에 캔을 쥔 채 냉장고 문을 닫는다.")
    day.see(at + 36, "거실", "사용자가 소파 옆 탁자에 맥주 캔을 내려놓는다.")
    if late_sport:
        day.see(at + 72, "거실", "사용자가 맥주 캔을 쟁반 옆에 두고 낮은 식탁에서 식사를 이어 간다.")
    else:
        day.see(at + 60, "거실", "사용자가 소파에 앉아 있다. 옆 탁자 위에는 맥주 캔이 놓여 있다.")


def sports(day, late_sport):
    # 편성은 밤 10시, 사용자가 채널을 선택한 시각은 날짜별로 조금씩 다르다.
    offset = {1: 8, 5: -32, 8: 64, 12: -12, 15: 28, 19: 0, 22: -48, 26: 40}
    broadcast = clock(22) + offset[day.n]
    early = day.n in (5, 15)
    if early:
        beer(day, broadcast - day.rng.choice((224, 328, 384)), late_sport)
    if not late_sport:
        on = broadcast - day.rng.choice((20, 36, 48, 92))
        day.signal(on, "사람", "TV", "전원", "켜짐")
        day.see(on, "거실", "사용자가 소파에서 리모컨을 누르자 TV 화면이 켜진다.")
        day.see(on + 12, "거실", "소파에서 TV를 보는 사용자의 손에 리모컨이 있다.")
    day.signal(broadcast, "사람", "TV", "채널", "채널 37")
    day.see(broadcast, "거실", "TV 화면에 경기장과 점수판이 뜬다. 사용자가 리모컨을 내려놓는다.")
    day.see(broadcast + 12, "거실", "TV 화면에 경기 시간이 표시되고 사용자는 화면 쪽을 보고 있다.")
    at = broadcast + day.rng.choice((40, 96, 188, 252))
    if not early:
        beer(day, at, late_sport)
    toast = broadcast + 100 if early else at + 92
    day.see(toast, "거실", "사용자가 맥주 캔의 고리를 당긴 뒤 캔을 입에 댄다.")
    day.see(toast + 16, "거실", "화면에 경기 점수판이 보이고 사용자의 손 옆에 열린 맥주 캔이 놓여 있다.")
    off = broadcast + day.rng.randrange(65, 87) * 60
    day.signal(off, "사람", "TV", "전원", "꺼짐")
    day.see(off, "거실", "사용자가 리모컨 버튼을 누른다. 점수판이 사라지고 TV 화면이 꺼진다.")
    day.see(off + 24, "거실", "사용자가 소파 옆에서 빈 맥주 캔을 집어 든다.")
    day.see(off + 52, "주방", "사용자가 캔을 싱크대 옆 분리수거 바구니에 내려놓는다.")
    day.see(off + 88, "복도", "복도 모퉁이 아래로 거실 불빛이 비친다. 시야에 사람은 없다.")
    day.note(broadcast, "경기 채널 선택 전에 맥주가 이미 놓임." if early
             else "경기 채널 선택 후 냉장고에서 맥주를 가져와 마심.")


def quiet_evening(day):
    start = clock(22) + day.rng.randrange(-50, 51) * 4
    if day.n % 3 == 0:
        day.see(start - 36, "거실", "소파 팔걸이에 잡지와 접힌 담요가 놓여 있다.")
        day.signal(start, "사람", "TV", "전원", "켜짐")
        day.see(start, "거실", "사용자가 소파에 앉아 리모컨을 누른다. TV 화면이 켜진다.")
        day.signal(start + 20, "사람", "TV", "채널", "채널 18")
        day.see(start + 20, "거실", "TV 편성 안내에 ‘여행 다큐멘터리’가 뜬다.")
        day.see(start + 80, "거실", "사용자가 다리 위에 담요를 덮고 TV 화면을 본다.")
        stop = start + day.rng.randrange(19, 36) * 60
        day.signal(stop, "사람", "TV", "전원", "꺼짐")
        day.see(stop, "거실", "사용자가 리모컨을 누르자 TV가 꺼진다.")
        day.see(stop + 40, "거실", "소파 위에는 접힌 담요와 잡지만 보인다.")
    else:
        day.see(start - 52, "침실", "사용자가 협탁에서 종이책을 들어 베개에 기대어 앉는다.")
        day.signal(start, "사람", "독서등", "전원", "켜짐")
        day.see(start, "침실", "사용자가 협탁의 스위치를 누른다. 책 표지가 환해진다.")
        day.see(start + 20, "침실", "사용자가 독서등 아래 펼친 종이책을 보고 있다.")
        stop = start + day.rng.randrange(13, 36) * 60
        day.see(stop - 24, "침실", "사용자가 책갈피를 끼우고 책을 덮는다.")
        day.signal(stop, "사람", "독서등", "전원", "꺼짐")
        day.see(stop, "침실", "독서등이 꺼진다. 협탁 위에 닫힌 책의 윤곽이 보인다.")
        day.see(stop + 60, "복도", "로봇 앞에는 어두운 침실 문턱과 복도 바닥이 보인다.")


def build(day):
    rng = day.rng
    late_sport = day.n == 19 and not day.meal_out and not day.guest
    if day.meal_out:
        if day.work != "출근":
            leave = clock(17, 56) + rng.randrange(0, 121) * 4
            day.see(leave - 40, "현관", "사용자가 외투를 걸치고 신발을 신는다.")
            day.signal(leave, "사람", "현관문", "문", "열림")
            day.see(leave, "현관", "사용자가 문을 열고 신발장 앞을 지나 밖으로 나간다.")
            day.signal(leave + 12, "사람", "현관문", "문", "닫힘")
            day.see(leave + 12, "현관", "닫힌 문 안쪽으로 빈 현관이 보인다.")
        return_home(day, clock(20, 44) + rng.randrange(0, 360) * 4, day.work == "출근")
    else:
        if day.work == "출근":
            arrive = clock(18, 8) + rng.randrange(0, 810) * 4
            return_home(day, arrive, True)
        else:
            arrive = clock(17, 44) + rng.randrange(0, 270) * 4
            day.see(arrive, "거실", "소파 옆에서 사용자가 읽던 책을 의자 위에 올려둔다.")
            day.see(arrive + 44, "거실", "블라인드 사이로 빛이 들어오고 사용자가 소파에 앉아 있다.")
        start = clock(21, 28) if late_sport else arrive + rng.randrange(12, 33) * 60
        if day.guest:
            visit(day, start - 6 * 60, True)
        dinner(day, start, late_sport)
        if day.guest:
            visit(day, clock(20, 58) + rng.randrange(0, 100) * 4, False)
    if day.date.weekday() in (0, 4):
        sports(day, late_sport)
    else:
        quiet_evening(day)
