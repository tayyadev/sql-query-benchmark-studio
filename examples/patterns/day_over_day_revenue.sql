WITH daily AS (
 SELECT created_day, SUM(total_cents) AS paid_cents
 FROM orders WHERE status = 'paid'
 GROUP BY created_day
)
SELECT created_day, paid_cents,
       LAG(paid_cents) OVER (ORDER BY created_day) AS prior_day_cents,
       paid_cents - LAG(paid_cents) OVER (ORDER BY created_day) AS change_cents
FROM daily ORDER BY created_day;
