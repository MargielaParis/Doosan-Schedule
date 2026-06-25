# 두산 베어스 KBO 일정 API

GitHub Pages로 서빙되는 두산 베어스 경기 일정 JSON API.

## 엔드포인트

```
https://{username}.github.io/{repo}/schedule.json
```

## 갱신 주기

매주 월요일 00:00 KST 자동 실행 (GitHub Actions)

## schedule.json 구조

```json
{
  "updated": "2026-06-26T12:00:00",
  "team": "두산 베어스",
  "games": [
    {
      "date": "2026-06-26",
      "time": "18:30",
      "home": true,
      "opponent": "KIA",
      "opponent_code": "HT",
      "opponent_color": "#EA0029",
      "emblem_url": "https://...initial_HT.png",
      "stadium": "잠실",
      "score": { "my": 5, "opp": 3, "result": "W" },
      "status": "done"
    }
  ]
}
```

## status 값

| 값 | 의미 |
|---|---|
| `done` | 경기 완료 |
| `scheduled` | 예정 |
| `cancelled` | 우천취소 등 |

## 레포 구조

```
├── kbo_crawler.py
├── schedule.json          # 자동 생성
└── .github/workflows/
    └── update_schedule.yml
```

## GitHub Pages 설정

Settings → Pages → Source: `Deploy from a branch` → Branch: `main` / `/(root)`
