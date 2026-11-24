"""TV 중계: 동료 집 LG NetCast TV(47LM6700)를 노트북에서 다룬다.

  netcast.py  와이파이(NetCast ROAP): 켜짐·꺼짐 확인, 끄기 (켜기는 와이파이로 안 됨)
  monitor.py  0.5초마다 응답을 보고 켜짐·꺼짐이 바뀐 시각을 남김
  ir.py       아두이노 적외선 브리지(USB 시리얼): 켜기·끄기, 리모컨 신호 배우기
  fake.py     TV·아두이노 없이 시험하는 가짜 TV·가짜 시리얼
  arduino/ir_bridge/ir_bridge.ino  아두이노에 올리는 코드
"""
