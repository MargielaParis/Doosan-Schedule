import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime

# ── 상수 ──────────────────────────────────────────────────────────────
TEAM_CODE_MAP = {
    "OB": "두산", "LG": "LG", "HH": "한화", "SK": "SSG",
    "SS": "삼성", "NC": "NC", "KT": "KT", "LT": "롯데",
    "HT": "KIA", "WO": "키움"
}
TEAM_NAME_TO_CODE = {v: k for k, v in TEAM_CODE_MAP.items()}

TEAM_COLOR = {
    "LG":  "#C30452", "한화": "#FF6600", "SSG": "#CE0E2D",
    "삼성": "#1428A0", "NC":  "#315288", "KT":  "#000000",
    "롯데": "#041E42", "KIA": "#EA0029", "두산": "#131230",
    "키움": "#570514"
}

EMBLEM_URL = "https://6ptotvmi5753.edge.naverncp.com/KBO_IMAGE/emblem/regular/2026/initial_{code}.png"
MY_TEAM_CODE = "OB"
MY_TEAM_NAME = "두산"

HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.koreabaseball.com/Schedule/Schedule.aspx",
    "Origin": "https://www.koreabaseball.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/149.0.0.0 Safari/537.36"
}

# ── API 호출 ──────────────────────────────────────────────────────────
def fetch_list(year: int, month: int) -> list:
    url = "https://www.koreabaseball.com/ws/Schedule.asmx/GetScheduleList"
    data = {
        "leId": "1",
        "srIdList": "0,9,6",
        "seasonId": str(year),
        "gameMonth": f"{month:02d}",
        "teamId": MY_TEAM_CODE,   # 두산만 필터
    }
    resp = requests.post(url, headers=HEADERS, data=data, timeout=10)
    resp.raise_for_status()
    return resp.json().get("rows", [])


# ── 파싱 ──────────────────────────────────────────────────────────────
def parse_rows(rows: list, year: int, month: int) -> list[dict]:
    games = []
    current_date = None

    for row_obj in rows:
        cells = row_obj.get("row", [])
        
        # 셀을 순서대로 처리. Class="day" 셀이 날짜, "time"이 시간, "play"가 대진
        day_text = None
        time_text = None
        play_text = None
        stadium_text = None
        note_text = None  # 우천취소 등

        for cell in cells:
            cls = cell.get("Class") or ""
            text = cell.get("Text", "").strip()
            
            if cls == "day":
                day_text = text  # "06.02(화)"
            elif cls == "time":
                soup = BeautifulSoup(text, "html.parser")
                time_text = soup.get_text(strip=True)  # "18:30"
            elif cls == "play":
                play_text = text
            else:
                # 구장은 Class=None인 셀 중 하나 (index 고정 아님)
                # 우천취소도 마찬가지
                plain = BeautifulSoup(text, "html.parser").get_text(strip=True)
                if plain in {"잠실", "사직", "대구", "수원", "문학", "광주", "대전", "창원", "고척", "울산", "포항"}:
                    stadium_text = plain
                elif plain in {"우천취소", "서스펜디드", "취소"}:
                    note_text = plain

        # 날짜 업데이트 (RowSpan 있는 셀에만 있음)
        if day_text:
            m = re.match(r"(\d{2})\.(\d{2})", day_text)
            if m:
                current_date = f"{year}-{m.group(1)}-{m.group(2)}"

        if not current_date or not play_text:
            continue

        # play 파싱: <span>KIA</span><em><span class="win">X</span><span>vs</span><span class="lose">Y</span></em><span>두산</span>
        soup = BeautifulSoup(play_text, "html.parser")
        spans = soup.find_all("span", recursive=False)
        # spans[0]=팀A, spans[-1]=팀B, 중간 em 안에 스코어
        if len(spans) < 2:
            continue

        team_a = spans[0].get_text(strip=True)
        team_b = spans[-1].get_text(strip=True)

        # 두산 포함 여부 확인
        if MY_TEAM_NAME not in (team_a, team_b):
            continue

        # gameId에서 홈/어웨이 판단
        # play 안에 gameId 없으므로 relay 셀에서 찾아야 하나?
        # 구장으로 판단: 잠실=두산 홈
        DOOSAN_HOME = {"잠실"}
        is_home = stadium_text in DOOSAN_HOME if stadium_text else None

        opponent_name = team_a if team_b == MY_TEAM_NAME else team_b

        # 스코어 파싱
        em = soup.find("em")
        score = None
        status = "scheduled"
        if em:
            score_spans = em.find_all("span")
            scores = [s.get_text(strip=True) for s in score_spans if s.get_text(strip=True).isdigit()]
            if len(scores) >= 2:
                # team_a 스코어, team_b 스코어 순
                a_score, b_score = int(scores[0]), int(scores[1])
                my_score = b_score if team_b == MY_TEAM_NAME else a_score
                opp_score = a_score if team_b == MY_TEAM_NAME else b_score
                
                # win/lose/same 클래스로도 판단 가능
                win_span = em.find("span", class_="win")
                lose_span = em.find("span", class_="lose")
                same_span = em.find("span", class_="same")
                
                if win_span or lose_span:
                    # my_score 기준으로 결과 결정
                    result = "W" if my_score > opp_score else ("L" if my_score < opp_score else "D")
                    score = {"my": my_score, "opp": opp_score, "result": result}
                    status = "done"
                elif same_span:
                    score = {"my": my_score, "opp": opp_score, "result": "D"}
                    status = "done"
                # scores 있지만 win/lose/same 없으면 예정

        opponent_code = TEAM_NAME_TO_CODE.get(opponent_name, "??")

        game = {
            "date": current_date,
            "time": time_text or "18:30",
            "home": is_home,
            "opponent": opponent_name,
            "opponent_code": opponent_code,
            "opponent_color": TEAM_COLOR.get(opponent_name, "#888888"),
            "emblem_url": EMBLEM_URL.format(code=opponent_code),
            "stadium": stadium_text,
            "score": score,
            "status": status if note_text is None else "cancelled",
            "note": note_text,
        }
        games.append(game)

    return games


# ── 메인 ──────────────────────────────────────────────────────────────
def main():
    now = datetime.now()
    months = [(now.year, now.month)]
    if now.month == 12:
        months.append((now.year + 1, 1))
    else:
        months.append((now.year, now.month + 1))

    all_games = []
    for year, month in months:
        print(f"Fetching {year}-{month:02d} ...")
        rows = fetch_list(year, month)
        games = parse_rows(rows, year, month)
        all_games.extend(games)
        print(f"  두산 경기 {len(games)}개")

    output = {
        "updated": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "team": "두산 베어스",
        "games": sorted(all_games, key=lambda g: (g["date"], g["time"]))
    }

    with open("schedule.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ schedule.json 저장 완료 ({len(all_games)}경기)")
    
    # 샘플 출력
    for g in all_games[:5]:
        mark = "🏠" if g["home"] else "✈️"
        score_str = f"{g['score']['my']}-{g['score']['opp']} ({g['score']['result']})" if g["score"] else "예정"
        print(f"  {g['date']} {g['time']} {mark} vs {g['opponent']} [{g['stadium']}] {score_str}")


if __name__ == "__main__":
    main()
