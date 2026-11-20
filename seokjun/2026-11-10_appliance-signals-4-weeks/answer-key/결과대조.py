"""날짜별 실제 학습 결과와 로봇 판단을 예상 정답에 대조한다."""
import argparse
from collections import defaultdict
from datetime import date, time
import json
from pathlib import Path


DATA = Path(__file__).resolve().parent / "채점자료"
LABELS = {"실행", "대기", "취소", "미개입"}
GUIDE = """
예시
  python 결과대조.py --밤 실제밤.jsonl --낮 실제낮.jsonl --출력 대조결과.json
  python 결과대조.py --낮 실제명령.jsonl --명령만 --날짜 2026-10-23

실제 파일은 UTF-8 JSONL입니다. 아래 줄들은 입력 형식의 예시입니다.
밤에는 해당 날짜 밤의 전체 활성 규칙을 한 줄로 기록합니다. 변동이 없어도 그날의 줄을 넣습니다.
  {"날짜":"2026-10-12","규칙들":[]}
  {"날짜":"2026-10-16","규칙들":[{"규칙ID":"am_laptop","경로":"사건","조건":{}}]}
시각 규칙은 "경로":"시각"과 "시각":"HH:MM:SS"를 넣습니다. 조건의 키 순서는 무관합니다.
처음부터 설정된 고정안전 규칙은 밤의 학습 결과에서 제외합니다. 낮의 판단에서는 채점합니다.
낮 날짜는 판단이 일어난 실제 날짜입니다. 전날 밤까지 배운 규칙을 적용합니다.
  {"날짜":"2026-10-13","시각":"08:00:00","행동":"정답에 적힌 행동명","판정":"대기"}
낮 판정은 실행, 대기, 취소, 미개입 중 하나입니다. 키는 날짜·시각·행동입니다.
예상 시각은 한국 현지의 4초 눈금입니다. 허용 오차는 0초이며 늦은 실행도 정답과 구분합니다.
전체 판단 모드에는 로봇이 내린 판단을 기록하세요. 센서 관찰만 들어온 줄은 판단 기록이 아닙니다.
다른 내부 규칙 이름, 명령 코드, 행동 별칭을 쓰는 시스템은 내보낼 때 정답 파일에 나온
규칙ID와 행동명으로 대응시키세요. 한 명령을 여러 표현으로 중복 제출하면 중복으로 셉니다.
--명령만 모드는 실행 명령끼리 비교합니다. 대기·취소·미개입을 출력하지 않아도 됩니다.
실행을 마쳤지만 명령 한 건도 낼 일이 없었던 날에는 다음 줄로 재생 완료 사실을 표시하세요.
  {"날짜":"2026-10-13","실행기록완료":true}
결과가 비어 있고 완료 표시도 없으면 그날은 미제출입니다.
"""


def iso_day(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError(f"연-월-일 형식이 아닙니다. {value!r}")
    return value


def stamp(value):
    if not isinstance(value, str) or time.fromisoformat(value).isoformat(timespec="seconds") != value or len(value) != 8:
        raise ValueError(f"시:분:초 형식이 아닙니다. {value!r}")
    return value


def rows(path):
    with path.open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("한 줄에 JSON 개체 하나가 필요합니다.")
                iso_day(row["날짜"])
                yield row
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError(f"{path.name} {number}번째 줄 오류. {exc}") from exc


def selected(source, picked):
    return [row for row in source if not picked or row["날짜"] == picked]


def rule_key(rule):
    if not isinstance(rule, dict) or not isinstance(rule.get("규칙ID"), str) or not rule["규칙ID"].strip():
        raise ValueError(f"규칙 식별번호를 확인하세요. {rule!r}")
    route = rule["경로"]
    if route not in ("사건", "시각") or not isinstance(rule["조건"], dict):
        raise ValueError(f"규칙의 경로 또는 조건 형식이 잘못됐습니다. {rule!r}")
    if route == "사건" and rule.get("시각") is not None:
        raise ValueError(f"사건 규칙의 시각 항목은 빼 주세요. {rule!r}")
    return rule["규칙ID"], route, json.dumps(rule["조건"], ensure_ascii=False, sort_keys=True), stamp(rule["시각"]) if route == "시각" else ""


def unpack(key):
    identifier, route, conditions, when = key
    rule = {"규칙ID": identifier, "경로": route, "조건": json.loads(conditions)}
    if when:
        rule["시각"] = when
    return rule


def compare_nights(expected, actual):
    days = {r["날짜"] for r in expected}
    fixed = {r["규칙ID"] for r in expected if r["종류"] == "고정안전"}
    gold, observed, errors = defaultdict(set), {}, []
    for row in expected:
        if row["규칙ID"] not in fixed:
            gold[row["날짜"]].update(rule_key({"규칙ID": row["규칙ID"], **r}) for r in row["활성"])
    for row in actual:
        day = row["날짜"]
        if not isinstance(row.get("규칙들"), list):
            raise ValueError(f"{day} 밤에는 규칙들 배열이 필요합니다. 비어 있으면 []를 사용하세요.")
        if day in observed:
            errors.append({"차이": "중복", "날짜": day, "내용": "같은 밤의 전체 규칙 목록을 두 번 제출함"})
            continue
        items = set()
        for rule in row["규칙들"]:
            key = rule_key(rule)
            if key[0] in fixed:
                continue
            if key in items:
                errors.append({"차이": "중복", "날짜": day, "실제": unpack(key)})
            items.add(key)
        observed[day] = items
    matches = 0
    for day in sorted(days | set(observed)):
        if day not in observed or day not in days:
            errors.append({"차이": "추가" if day not in days else "누락", "날짜": day, "내용": "날짜별 규칙 목록",
                           "예상": [unpack(k) for k in sorted(gold[day])],
                           "실제": [unpack(k) for k in sorted(observed.get(day, set()))] if day in observed else None})
            continue
        want, got = gold[day], observed[day]
        matches += len(want & got)
        for identifier in sorted({k[0] for k in want ^ got}):
            missing = [unpack(k) for k in sorted(want - got) if k[0] == identifier]
            added = [unpack(k) for k in sorted(got - want) if k[0] == identifier]
            if missing and added:
                errors.append({"차이": "오판", "날짜": day, "규칙ID": identifier, "예상": missing, "실제": added})
            else:
                for rule in missing or added:
                    errors.append({"차이": "누락" if missing else "추가", "날짜": day, "예상" if missing else "실제": rule})
    return {"대상날짜수": len(days), "예상활성규칙수": sum(len(gold[day]) for day in days),
            "일치활성규칙수": matches, "차이": errors}


def decision_key(row):
    if not isinstance(row.get("행동"), str) or not row["행동"].strip():
        raise ValueError(f"비어 있는 행동명입니다. {row!r}")
    return row["날짜"], stamp(row["시각"]), row["행동"]


def compare_days(expected, actual, commands):
    days = {row["날짜"] for row in expected}
    all_gold = {decision_key(row): row["예상판정"] for row in expected}
    gold = {key: val for key, val in all_gold.items() if not commands or val == "실행"}
    observed, submitted, markers, errors = {}, set(), set(), []
    for row in actual:
        day = row["날짜"]
        if "실행기록완료" in row:
            if not commands or row["실행기록완료"] is not True or any(k in row for k in ("판정", "행동", "시각")):
                raise ValueError(f"{day} 완료 표시는 명령만 모드에서 별도 한 줄로 제출해야 합니다.")
            if day in markers:
                errors.append({"차이": "중복", "날짜": day, "내용": "같은 날 재생 완료 표시 중복"})
            markers.add(day)
            submitted.add(day)
            continue
        key = decision_key(row)
        label = row["판정"]
        if label not in LABELS:
            raise ValueError(f"{day} 알 수 없는 판정 {label!r}")
        submitted.add(day)
        if commands and label != "실행":
            continue
        if key in observed:
            errors.append({"차이": "중복", "날짜": day, "시각": key[1], "행동": key[2], "첫판정": observed[key], "중복판정": label})
        else:
            observed[key] = label
    for day in sorted(days - submitted):
        errors.append({"차이": "누락", "날짜": day, "내용": "이 날짜의 실제 재생 기록을 제출하지 않음"})
    for day in sorted(submitted - days):
        errors.append({"차이": "추가", "날짜": day, "내용": "정답 기간에 없는 날짜를 제출함"})
    matches = 0
    for key in sorted(set(gold) | set(observed)):
        g, a = gold.get(key), observed.get(key)
        if g == a:
            matches += 1
            continue
        errors.append({"차이": "추가" if g is None else ("누락" if a is None else "오판"),
                       "날짜": key[0], "시각": key[1], "행동": key[2], "예상": all_gold.get(key), "실제": a})
    return {"대상날짜수": len(days), "예상판정수": len(gold), "일치판정수": matches, "차이": errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog=GUIDE, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--밤", type=Path, help="실제 밤별 규칙 스냅샷 JSONL")
    parser.add_argument("--낮", type=Path, help="실제 낮 판단 JSONL")
    parser.add_argument("--날짜", type=iso_day, help="하루만 평가할 YYYY-MM-DD. 기본값은 전체 기간")
    parser.add_argument("--명령만", action="store_true", help="낮에 실행한 명령의 일치·누락·추가만 평가")
    parser.add_argument("--출력", type=Path, help="차이 전부를 기록할 UTF-8 JSON 경로")
    args = parser.parse_args()
    if not args.밤 and not args.낮:
        parser.error("--밤 또는 --낮으로 실제 결과 파일을 지정하세요.")
    if args.명령만 and not args.낮:
        parser.error("--명령만에는 --낮이 필요합니다.")
    night_file, day_file = DATA / "밤별규칙.jsonl", DATA / "시각별판단.jsonl"
    inputs = [p.resolve() for p in (night_file, day_file, args.밤, args.낮) if p]
    if args.출력 and args.출력.resolve() in inputs:
        parser.error("--출력에는 입력 파일과 다른 경로를 지정하세요.")
    report = {"범위": args.날짜 or "전체", "낮비교방식": "실행 명령만" if args.명령만 else "전체 판단"}
    try:
        for label, expected_path, actual_path in (("밤", night_file, args.밤), ("낮", day_file, args.낮)):
            if actual_path is None:
                continue
            gold = selected(rows(expected_path), args.날짜)
            if not gold:
                parser.error(f"{label} 정답에 요청한 기간의 기록이 없습니다.")
            actual = selected(rows(actual_path), args.날짜)
            report[label] = compare_nights(gold, actual) if label == "밤" else compare_days(gold, actual, args.명령만)
        differences = sum(len(report[k]["차이"]) for k in ("밤", "낮") if k in report)
        report["판정"] = "차이 있음" if differences else "일치"
        report["차이항목수"] = differences
        if args.출력:
            args.출력.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.error(f"파일을 확인하세요. {exc}")
    print(f"{report['판정']} | 범위 {report['범위']} | 차이 {differences}항목")
    for label in ("밤", "낮"):
        if label not in report:
            continue
        section = report[label]
        counts = {kind: sum(r["차이"] == kind for r in section["차이"]) for kind in ("누락", "추가", "오판", "중복")}
        item = "활성규칙수" if label == "밤" else "판정수"
        matched, wanted = section["일치" + item], section["예상" + item]
        print(f"{label} {section['대상날짜수']}일 | 예상 {wanted}건 중 일치 {matched}건 | "
              + " · ".join(f"{kind} {n}" for kind, n in counts.items()))
        for row in section["차이"][:3]:
            print(json.dumps(row, ensure_ascii=False))
    if args.출력:
        print(f"상세 대조 결과 {args.출력}")
    return int(differences != 0)


if __name__ == "__main__":
    raise SystemExit(main())
