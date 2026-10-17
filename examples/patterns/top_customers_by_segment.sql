WITH spend AS (
 SELECT c.segment, c.id AS customer_id, c.name,
        SUM(o.total_cents) AS paid_cents
 FROM customers c
 JOIN orders o ON o.customer_id = c.id AND o.status = 'paid'
 GROUP BY c.segment, c.id, c.name
), ranked AS (
 SELECT *, ROW_NUMBER() OVER (
    PARTITION BY segment ORDER BY paid_cents DESC, customer_id
 ) AS row_num
 FROM spend
)
SELECT segment, customer_id, name, paid_cents
FROM ranked WHERE row_num <= 3
ORDER BY segment, row_num;
