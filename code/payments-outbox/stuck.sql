-- Chapter 05: the query that goes on a dashboard.
SELECT state,
       count(*)                          AS payments,
       max(now() - updated_at)           AS oldest,
       sum(amount_minor) / 100.0         AS rupees_in_limbo
FROM payments
WHERE state IN ('pending', 'unknown')
GROUP BY state;
