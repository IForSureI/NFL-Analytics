-- EPA per play on neutral early downs, dropbacks vs designed runs, by season (study 06).
SELECT season,
       ROUND(AVG(CASE WHEN qb_dropback = 1 THEN epa END), 3) AS epa_dropback,
       ROUND(AVG(CASE WHEN qb_dropback = 0 THEN epa END), 3) AS epa_designed_run,
       ROUND(AVG(qb_dropback), 3) AS pass_rate
FROM read_parquet('data/raw/pbp_20*.parquet', union_by_name = true)
WHERE season_type = 'REG' AND down IN (1, 2) AND wp BETWEEN 0.2 AND 0.8 AND half_seconds_remaining > 120
  AND play_type IN ('run','pass') AND epa IS NOT NULL
  AND COALESCE(qb_kneel, 0) = 0 AND COALESCE(qb_spike, 0) = 0 AND COALESCE(two_point_attempt, 0) = 0
GROUP BY season
ORDER BY season;
