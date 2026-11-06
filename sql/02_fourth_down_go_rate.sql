-- League 4th-down go rate by distance and field zone, by season (raw rates; the bot in study 02 adds WP).
SELECT season,
       CASE WHEN ydstogo = 1 THEN '1' WHEN ydstogo <= 3 THEN '2-3' WHEN ydstogo <= 6 THEN '4-6' ELSE '7+' END AS to_go,
       CASE WHEN yardline_100 >= 60 THEN 'own side' WHEN yardline_100 >= 35 THEN 'midfield' ELSE 'opponent 34-in' END AS zone,
       COUNT(*) AS fourth_downs,
       ROUND(AVG(CASE WHEN play_type IN ('run','pass') THEN 1 ELSE 0 END), 3) AS go_rate
FROM read_parquet('data/raw/pbp_20*.parquet', union_by_name = true)
WHERE down = 4 AND season >= 2018 AND season_type = 'REG'
  AND play_type IN ('run','pass','punt','field_goal') AND qtr <= 4
  AND COALESCE(qb_kneel, 0) = 0 AND COALESCE(qb_spike, 0) = 0
GROUP BY 1, 2, 3
ORDER BY season, to_go, zone;
