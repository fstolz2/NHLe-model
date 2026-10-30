import json
import time
import sqlite3
import requests
import pandas as pd

BASE = "https://lscluster.hockeytech.com/feed/index.php"
KEY = "f1aa699db3d81487"

def get_json(params):
    """Fetch and strip the ( ) wrapper HockeyTech puts around its JSON."""
    text = requests.get(BASE, params=params).text.strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    return json.loads(text)

# --- Get regular seasons from 2010-11 onward ---
seasons = get_json({"feed": "modulekit", "view": "seasons", "key": KEY,
                    "client_code": "ohl", "fmt": "json", "lang": "en"})
seasons = pd.DataFrame(seasons["SiteKit"]["Seasons"])
seasons["season_id"] = seasons["season_id"].astype(int)
regular = seasons[seasons["season_name"].str.contains("Regular Season")
                  & (seasons["season_id"] >= 42)]

# --- Pull skater stats for each season ---
all_rows = []
for _, s in regular.iterrows():
    params = {
        "feed": "statviewfeed", "view": "players", "season": s["season_id"],
        "team": "all", "position": "skaters", "rookies": 0,
        "statsType": "standard", "site_id": 2, "first": 0, "limit": 1000,
        "sort": "points", "league_id": 1, "lang": "en", "division": -1,
        "key": KEY, "client_code": "ohl",
    }
    players = get_json(params)[0]["sections"][0]["data"]

    for p in players:
        row = p["row"]
        # player_id is usually in row; fall back to the link in prop if not
        if "player_id" not in row:
            row["player_id"] = p.get("prop", {}).get("name", {}).get("playerLink")
        row["season_id"] = s["season_id"]
        row["season_name"] = s["season_name"]
        all_rows.append(row)

    print(s["season_name"], "-", len(players), "skaters")
    time.sleep(1)   # be polite to their server

df = pd.DataFrame(all_rows)

# Stats come back as text; convert the ones we need to numbers
for col in ["games_played", "goals", "assists", "points"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

print(df.columns.tolist())   # see every column we got
print(df[["name", "team_code", "season_name", "games_played", "goals", "points"]].head())

conn = sqlite3.connect("hockey.db")
df.to_sql("ohl_skaters", conn, if_exists="replace", index=False)


query = """
SELECT name, team_code, season_name, games_played, goals, assists, points,
    ROUND(CAST(points AS REAL) / games_played, 2) AS ppg
FROM ohl_skaters
WHERE games_played >= 10
    AND season_name = '2025-26 Regular Season'
ORDER BY points DESC
LIMIT 50
"""
print(pd.read_sql(query, conn))

conn.close()
print("Saved", len(df), "rows to ohl_skaters")