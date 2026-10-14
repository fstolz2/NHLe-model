import json
import sqlite3
import git
from networkx import config
import requests
import pandas as pd

url = "https://api.nhle.com/stats/rest/en/skater/summary"
season = 20252026

# The API returns 100 rows at a time, so we page through until we have everyone
all_rows = []
start = 0
while True:
    params = {
        "start": start,
        "limit": 100,
        "sort": json.dumps([{"property": "playerId", "direction": "ASC"}]),
        "cayenneExp": f"seasonId={season} and gameTypeId=2",
    }
    data = requests.get(url, params=params).json()
    all_rows.extend(data["data"])
    start += 100
    if start >= data["total"]:
        break

df = pd.DataFrame(all_rows)
print("Pulled", len(df), "skaters")

# Save to SQLite (creates hockey.db in your project folder if it doesn't exist)
conn = sqlite3.connect("hockey.db")
df.to_sql("nhl_skaters", conn, if_exists="replace", index=False)


query = """
SELECT skaterFullName, teamAbbrevs, gamesPlayed, goals, points
FROM nhl_skaters
WHERE gamesPlayed >= 10
ORDER BY points DESC
LIMIT 50
"""
print(pd.read_sql(query, conn))

conn.close()

