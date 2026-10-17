WITH daily AS (
 SELECT created_day, SUM(total_cents) AS day_cents
 FROM orders WHERE status = 'paid'
 GROUP BY created_day
)
SELECT created_day, day_cents,
       SUM(day_cents) OVER (ORDER BY created_day
         ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_cents
FROM daily ORDER BY created_day;
