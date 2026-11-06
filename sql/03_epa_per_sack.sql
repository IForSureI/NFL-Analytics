-- Expected points taken away per sack, by down and distance (study 03).
SELECT down,
       CASE WHEN ydstogo <= 2 THEN '1-2' WHEN ydstogo <= 6 THEN '3-6' WHEN ydstogo <= 10 THEN '7-10' ELSE '11+' END AS to_go,
       COUNT(*) AS sacks,
       ROUND(-AVG(epa), 2) AS epa_taken
FROM read_parquet('data/raw/pbp_20*.parquet', union_by_name = true)
WHERE sack = 1 AND qb_dropback = 1 AND season BETWEEN 2016 AND 2025 AND season_type = 'REG' AND down BETWEEN 1 AND 3
GROUP BY 1, 2
HAVING COUNT(*) >= 40
ORDER BY epa_taken DESC;
