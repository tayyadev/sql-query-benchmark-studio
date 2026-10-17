WITH RECURSIVE calendar(day) AS (
 SELECT 0 UNION ALL SELECT day + 1 FROM calendar WHERE day < 30
)
SELECT calendar.day, COUNT(o.id) AS orders
FROM calendar LEFT JOIN orders o ON o.created_day = calendar.day
GROUP BY calendar.day ORDER BY calendar.day;
