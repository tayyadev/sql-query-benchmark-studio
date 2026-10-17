SELECT c.segment, COUNT(o.id) AS paid_orders,
       ROUND(SUM(o.total_cents) / 100.0, 2) AS revenue
FROM customers c
JOIN orders o ON o.customer_id = c.id AND o.status = 'paid'
GROUP BY c.segment
ORDER BY revenue DESC;
