WITH active_days AS (
 SELECT DISTINCT created_day FROM orders WHERE status = 'paid'
), grouped AS (
 SELECT created_day,
        created_day - ROW_NUMBER() OVER (ORDER BY created_day) AS island
 FROM active_days
)
SELECT MIN(created_day) AS first_day, MAX(created_day) AS last_day,
       COUNT(*) AS consecutive_days
FROM grouped GROUP BY island ORDER BY first_day;
