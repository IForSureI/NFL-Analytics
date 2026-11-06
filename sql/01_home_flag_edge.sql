-- Accepted flags on the road team minus the home team, per game, by season and flag kind (study 01).
-- Uses the ten most common objective flag types; the Python study uses the full list in nflan/penalties.py, so numbers differ slightly.
WITH plays AS (
  SELECT * FROM read_parquet('data/raw/pbp_20*.parquet', union_by_name = true) WHERE season >= 2016
),
flags AS (
  SELECT season, game_id, penalty_type,
         CASE WHEN penalty_team = home_team THEN 'home' ELSE 'road' END AS side,
         CASE WHEN penalty_type IN ('False Start','Defensive Offside','Neutral Zone Infraction','Encroachment',
                                    'Delay of Game','Illegal Formation','Illegal Shift','Illegal Motion',
                                    'Illegal Substitution','Ineligible Downfield Pass') THEN 'objective'
              ELSE 'subjective_or_other' END AS kind
  FROM plays
  WHERE penalty = 1 AND penalty_team IS NOT NULL AND penalty_type IS NOT NULL
    AND "desc" NOT ILIKE '%declined%' AND "desc" NOT ILIKE '%offsetting%'
),
games AS (SELECT season, COUNT(DISTINCT game_id) AS n_games FROM plays GROUP BY season)
SELECT f.season, f.kind,
       ROUND((SUM(CASE WHEN side = 'road' THEN 1 ELSE 0 END) - SUM(CASE WHEN side = 'home' THEN 1 ELSE 0 END))
             / ANY_VALUE(g.n_games), 3) AS extra_road_flags_per_game
FROM flags f JOIN games g USING (season)
GROUP BY f.season, f.kind
ORDER BY f.season, f.kind;
