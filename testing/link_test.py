import json
import time
import sqlite3
import requests
import pandas as pd

session = requests.Session()

def get_json(url, params=None, tries=5):
    """Get JSON, waiting and retrying if the API pushes back."""
    for attempt in range(tries):
        try:
            r = session.get(url, params=params, timeout=20)
            if r.status_code == 200:
                return r.json()
            print(f"Status {r.status_code} - ", end="")
        except (requests.RequestException, ValueError) as e:
            print(f"Error ({type(e).__name__}) - ", end="")
        wait = 5 * (attempt + 1)
        print(f"waiting {wait}s and retrying")
        time.sleep(wait)
    raise RuntimeError(f"Gave up on {url}")

# --- Step 1: every NHL skater ID since 2011-12 ---
STATS_URL = "https://api.nhle.com/stats/rest/en/skater/summary"
player_ids = set()

for year in range(2000, 2026):
    season = int(f"{year}{year + 1}")          # e.g. 20112012
    start = 0
    while True:
        params = {
            "start": start, "limit": 100,
            "sort": json.dumps([{"property": "playerId", "direction": "ASC"}]),
            "cayenneExp": f"seasonId={season} and gameTypeId=2",
        }
        data = get_json(STATS_URL, params)
        player_ids.update(p["playerId"] for p in data["data"])
        start += 100
        time.sleep(0.5)
        if start >= data["total"]:
            break
    print(season, "done, unique players so far:", len(player_ids))

# --- Step 2: pull each player's career, keep OHL + NHL regular seasons ---
rows = []
for i, pid in enumerate(sorted(player_ids)):
    try:
        p = get_json(f"https://api-web.nhle.com/v1/player/{pid}/landing")
    except RuntimeError as e:
        print("Skipping", pid, "-", e)
        continue

    name = f'{p["firstName"]["default"]} {p["lastName"]["default"]}'
    for s in p.get("seasonTotals", []):
        if s["gameTypeId"] == 2:
            rows.append({
                "player_id": pid,
                "name": name,
                "position": p.get("position"),
                "birth_date": p.get("birthDate"),
                "season": s["season"],
                "league": s["leagueAbbrev"],
                "team": s["teamName"]["default"],
                "gp": s.get("gamesPlayed", 0),
                "goals": s.get("goals", 0),
                "assists": s.get("assists", 0),
                "points": s.get("points", 0),
            })

    if i % 200 == 0:
        print(f"{i}/{len(player_ids)} players pulled")
    time.sleep(0.25)

df = pd.DataFrame(rows)
conn = sqlite3.connect("hockey.db")
df.to_sql("career_seasons", conn, if_exists="replace", index=False)

query = """
WITH ohl AS (
    SELECT player_id, name, position, season, SUM(gp) AS gp, SUM(points) AS pts
    FROM career_seasons WHERE league = 'OHL'
    GROUP BY player_id, season
),
nhl AS (
    SELECT player_id, season, SUM(gp) AS gp, SUM(points) AS pts
    FROM career_seasons WHERE league = 'NHL'
    GROUP BY player_id, season
)
SELECT o.player_id, o.name, o.position, o.season AS ohl_season,
       o.gp AS ohl_gp, o.pts AS ohl_pts,
       n.gp AS nhl_gp, n.pts AS nhl_pts
FROM ohl o
JOIN nhl n
  ON o.player_id = n.player_id
 AND n.season = o.season + 10001
WHERE o.gp >= 20 AND n.gp >= 20
"""
pairs = pd.read_sql(query, conn)
pairs["ohl_ppg"] = pairs["ohl_pts"] / pairs["ohl_gp"]
pairs["nhl_ppg"] = pairs["nhl_pts"] / pairs["nhl_gp"]

def nhle(df):
    """Pooled factor: total NHL PPG divided by total OHL PPG."""
    return (df["nhl_pts"].sum() / df["nhl_gp"].sum()) / (df["ohl_pts"].sum() / df["ohl_gp"].sum())

print("Players in sample:", len(pairs))
print("OHL NHLe:", round(nhle(pairs), 3))

# Forwards vs defense
pairs["pos_group"] = pairs["position"].map(lambda p: "D" if p == "D" else "F")
print(pairs.groupby("pos_group").apply(nhle).round(3))

# Stability by season
print(pairs.groupby("ohl_season").apply(nhle).round(3))