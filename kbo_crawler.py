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

MONTH_NAMES = ["JANUARY","FEBRUARY","MARCH","APRIL","MAY","JUNE",
               "JULY","AUGUST","SEPTEMBER","OCTOBER","NOVEMBER","DECEMBER"]

# ── API 호출 ──────────────────────────────────────────────────────────
def fetch_list(year: int, month: int) -> list:
    url = "https://www.koreabaseball.com/ws/Schedule.asmx/GetScheduleList"
    data = {
        "leId": "1",
        "srIdList": "0,9,6",
        "seasonId": str(year),
        "gameMonth": f"{month:02d}",
        "teamId": MY_TEAM_CODE,
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
        day_text = time_text = play_text = stadium_text = note_text = None

        for cell in cells:
            cls = cell.get("Class") or ""
            text = cell.get("Text", "").strip()
            if cls == "day":
                day_text = text
            elif cls == "time":
                time_text = BeautifulSoup(text, "html.parser").get_text(strip=True)
            elif cls == "play":
                play_text = text
            else:
                plain = BeautifulSoup(text, "html.parser").get_text(strip=True)
                if plain in {"잠실","사직","대구","수원","문학","광주","대전","창원","고척","울산","포항"}:
                    stadium_text = plain
                elif plain in {"우천취소","서스펜디드","취소"}:
                    note_text = plain

        if day_text:
            m = re.match(r"(\d{2})\.(\d{2})", day_text)
            if m:
                current_date = f"{year}-{m.group(1)}-{m.group(2)}"

        if not current_date or not play_text:
            continue

        soup = BeautifulSoup(play_text, "html.parser")
        spans = soup.find_all("span", recursive=False)
        if len(spans) < 2:
            continue

        team_a = spans[0].get_text(strip=True)
        team_b = spans[-1].get_text(strip=True)
        if MY_TEAM_NAME not in (team_a, team_b):
            continue

        DOOSAN_HOME = {"잠실"}
        is_home = stadium_text in DOOSAN_HOME if stadium_text else None
        opponent_name = team_a if team_b == MY_TEAM_NAME else team_b

        em = soup.find("em")
        score = None
        status = "scheduled"
        if em:
            score_spans = em.find_all("span")
            scores = [s.get_text(strip=True) for s in score_spans if s.get_text(strip=True).isdigit()]
            if len(scores) >= 2:
                a_score, b_score = int(scores[0]), int(scores[1])
                my_score = b_score if team_b == MY_TEAM_NAME else a_score
                opp_score = a_score if team_b == MY_TEAM_NAME else b_score
                win_span = em.find("span", class_="win")
                lose_span = em.find("span", class_="lose")
                same_span = em.find("span", class_="same")
                if win_span or lose_span:
                    result = "W" if my_score > opp_score else ("L" if my_score < opp_score else "D")
                    score = {"my": my_score, "opp": opp_score, "result": result}
                    status = "done"
                elif same_span:
                    score = {"my": my_score, "opp": opp_score, "result": "D"}
                    status = "done"

        opponent_code = TEAM_NAME_TO_CODE.get(opponent_name, "??")
        games.append({
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
        })

    return games


# ── HTML 생성 ─────────────────────────────────────────────────────────
def build_calendar_html(all_games: list, now: datetime) -> str:
    year  = now.year
    month = now.month  # 0-indexed 아님, 1-indexed

    # 이번 달 게임만
    prefix = f"{year}-{month:02d}-"
    game_map = {}
    for g in all_games:
        if g["date"].startswith(prefix):
            d = int(g["date"][8:])
            game_map[d] = g

    import calendar
    first_dow = calendar.monthrange(year, month)[0]  # 0=Mon
    first_dow = (first_dow + 1) % 7                  # WE 기준 0=Sun
    last_date = calendar.monthrange(year, month)[1]
    today = now.day

    # 날짜 셀 생성
    cells_html = ""
    # 빈 칸
    for _ in range(first_dow):
        cells_html += '<div class="day-cell empty"></div>\n'

    for d in range(1, last_date + 1):
        dow = (first_dow + d - 1) % 7
        g = game_map.get(d)

        classes = ["day-cell"]
        if dow == 0: classes.append("sun")
        if dow == 6: classes.append("sat")
        if d == today: classes.append("today")

        inner = f'<div class="day-num">{d}</div>'

        if g:
            if g["status"] == "cancelled":
                classes.append("has-game cancelled")
                inner += f'''
                <div class="emblem-wrap">
                  <img src="{g["emblem_url"]}" alt="{g["opponent"]}">
                </div>'''
            elif g["home"]:
                classes.append("home")
                result_badge = ""
                if g["score"]:
                    r = g["score"]["result"]
                    inner += f'<div class="result-badge result-{r}">{r}</div>'
                inner += f'''
                <div class="emblem-wrap">
                  <img src="{g["emblem_url"]}" alt="{g["opponent"]}">
                </div>
                <div class="game-time">{g["time"]}</div>
                <div class="home-dot"></div>'''
            else:
                classes.append("away")
                if g["score"]:
                    r = g["score"]["result"]
                    inner += f'<div class="result-badge result-{r}">{r}</div>'
                inner += f'''
                <div class="emblem-wrap">
                  <img src="{g["emblem_url"]}" alt="{g["opponent"]}">
                </div>
                <div class="game-time">{g["time"]}</div>
                <div class="home-dot"></div>'''

        cells_html += f'<div class="{" ".join(classes)}">{inner}</div>\n'

    updated_str = now.strftime("%Y.%m.%d")
    month_name = MONTH_NAMES[month - 1]

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: 460px;
    background: transparent;
    font-family: 'Pretendard', 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif;
  }}
  #calendar-wrap {{
    width: 100%;
    background: rgba(8, 8, 24, 0.72);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border-radius: 16px;
    border: 1px solid rgba(255,255,255,0.1);
    padding: 20px 20px 16px 20px;
    box-shadow: 0 8px 40px rgba(0,0,0,0.5);
  }}
  #cal-header {{ display:flex; align-items:baseline; gap:10px; margin-bottom:12px; }}
  #cal-month {{ font-size:28px; font-weight:700; color:#fff; letter-spacing:0.02em; text-shadow:0 2px 12px rgba(0,0,0,0.7); }}
  #cal-year {{ font-size:13px; color:rgba(255,255,255,0.55); letter-spacing:0.08em; }}
  .dow-row {{ display:grid; grid-template-columns:repeat(7,1fr); margin-bottom:4px; }}
  .dow-cell {{ text-align:center; font-size:10px; font-weight:600; letter-spacing:0.1em; color:rgba(255,255,255,0.55); padding:4px 0; }}
  .dow-cell.sun {{ color:rgba(255,90,90,0.6); }}
  .dow-cell.sat {{ color:rgba(100,160,255,0.6); }}
  #cal-grid {{ display:grid; grid-template-columns:repeat(7,1fr); gap:3px; }}
  .day-cell {{ aspect-ratio:1/1.15; border-radius:6px; position:relative; display:flex; flex-direction:column; align-items:center; justify-content:flex-start; padding-top:6px; background:transparent; }}
  .day-cell.empty {{ background:transparent; }}
  .day-cell.has-game {{ background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.09); }}
  .day-cell.home {{ background:rgba(255,255,255,0.88); border:1px solid rgba(255,255,255,0.95); }}
  .day-cell.away {{ background:rgba(19,18,48,0.65); border:1px solid rgba(255,255,255,0.12); }}
  .day-cell.today {{ outline:2px solid rgba(255,255,255,0.7); outline-offset:-2px; }}
  .day-cell.today .day-num {{ color:#fff; font-weight:800; }}
  .day-num {{ font-size:11px; font-weight:500; color:rgba(255,255,255,0.6); line-height:1; }}
  .day-cell.sun .day-num {{ color:rgba(255,100,100,0.7); }}
  .day-cell.sat .day-num {{ color:rgba(100,160,255,0.7); }}
  .day-cell.has-game .day-num, .day-cell.away .day-num {{ color:rgba(255,255,255,0.9); }}
  .day-cell.home .day-num {{ color:rgba(20,20,50,0.85); }}
  .emblem-wrap {{ flex:1; display:flex; align-items:center; justify-content:center; width:100%; }}
  .emblem-wrap img {{ width:72%; max-width:34px; object-fit:contain; filter:drop-shadow(0 1px 4px rgba(0,0,0,0.3)); opacity:0.95; }}
  .day-cell.away .emblem-wrap img {{ opacity:0.6; filter:drop-shadow(0 1px 4px rgba(0,0,0,0.5)) grayscale(0.2); }}
  .day-cell.cancelled .emblem-wrap img {{ opacity:0.2; filter:grayscale(1); }}
  .game-time {{ font-size:8.5px; color:rgba(255,255,255,0.45); margin-bottom:4px; letter-spacing:0.03em; }}
  .day-cell.home .game-time {{ color:rgba(20,20,50,0.6); }}
  .result-badge {{ position:absolute; top:4px; right:5px; font-size:8px; font-weight:700; border-radius:3px; padding:1px 3px; letter-spacing:0.05em; }}
  .result-W {{ background:rgba(50,200,100,0.25); color:#6de99a; }}
  .result-L {{ background:rgba(220,60,60,0.2); color:#f07070; }}
  .result-D {{ background:rgba(180,180,180,0.2); color:#c0c0c0; }}
  .home-dot {{ position:absolute; bottom:4px; left:50%; transform:translateX(-50%); width:4px; height:4px; border-radius:50%; background:rgba(255,255,255,0.5); }}
  .day-cell.home .home-dot {{ background:rgba(19,18,48,0.5); }}
  #legend {{ display:flex; gap:14px; margin-top:10px; }}
  .legend-item {{ display:flex; align-items:center; gap:5px; font-size:9.5px; color:rgba(255,255,255,0.35); letter-spacing:0.05em; }}
  .legend-dot {{ width:6px; height:6px; border-radius:50%; }}
  .legend-dot.home {{ background:rgba(255,255,255,0.88); border:1px solid rgba(255,255,255,0.5); }}
  .legend-dot.away {{ background:rgba(19,18,48,0.65); border:1px solid rgba(255,255,255,0.3); }}
  #updated-at {{ margin-top:8px; font-size:9px; color:rgba(255,255,255,0.2); letter-spacing:0.05em; }}
</style>
</head>
<body>
<div id="calendar-wrap">
  <div id="cal-header">
    <span id="cal-month">{month_name}</span>
    <span id="cal-year">{year}</span>
  </div>
  <div class="dow-row">
    <div class="dow-cell sun">SUN</div>
    <div class="dow-cell">MON</div>
    <div class="dow-cell">TUE</div>
    <div class="dow-cell">WED</div>
    <div class="dow-cell">THU</div>
    <div class="dow-cell">FRI</div>
    <div class="dow-cell sat">SAT</div>
  </div>
  <div id="cal-grid">
{cells_html}  </div>
  <div id="legend">
    <div class="legend-item"><div class="legend-dot home"></div>홈</div>
    <div class="legend-item"><div class="legend-dot away"></div>어웨이</div>
  </div>
  <div id="updated-at">UPDATED {updated_str}</div>
</div>
</body>
</html>"""


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

    all_games = sorted(all_games, key=lambda g: (g["date"], g["time"]))

    # schedule.json 저장
    output = {
        "updated": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "team": "두산 베어스",
        "games": all_games
    }
    with open("schedule.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("✅ schedule.json 저장 완료")

    # calendar.html 저장
    html = build_calendar_html(all_games, now)
    with open("calendar.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("✅ calendar.html 저장 완료")
    print(f"\n총 {len(all_games)}경기")


if __name__ == "__main__":
    main()
