SELECT c.id, c.name, c.segment
FROM customers c
WHERE NOT EXISTS (
 SELECT 1 FROM orders o WHERE o.customer_id = c.id AND o.status = 'paid'
)
ORDER BY c.id LIMIT 50;
