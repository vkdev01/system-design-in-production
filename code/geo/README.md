# Chapter 08 - geospatial matching with H3

```bash
pip install -r requirements.txt
python index.py                       # cell ids, areas, ring expansion costs
python loadtest.py --one-cell         # the airport hotspot drill
python race.py --concurrent 2         # two riders, one driver: exactly one wins
psql "$DATABASE_URL" -f schema.sql    # requires the h3 and postgis extensions
```

Resolution choices: 9 for the driver index (~0.105 km2), 7 for zones and surge
(~5.16 km2). Expand rings 1 -> 2 -> 3 -> 5 and rank by real distance, never by
ring number.
