-- Business Queries for Streamlit Dashboard
-- Keep separate from the DB creation script so schema/data setup remains clean.
-- These are used by the pre-AI dashboard and can be reused, modified, or replaced by AI-generated SQL later.

SET search_path TO costco_analytics;

-- 1. Big Winners: Category Revenue Leaders
SELECT
    c.name AS category_name,
    c.deptcode AS department_code,
    ROUND(SUM(sti.subtotal)::numeric, 2) AS total_revenue,
    SUM(sti.quantity) AS total_units_sold,
    COUNT(DISTINCT st.transactionid) AS transaction_count
FROM costco_analytics.salestransactionitem sti
JOIN costco_analytics.product p ON sti.productid = p.productid
JOIN costco_analytics.category c ON p.categoryid = c.categoryid
JOIN costco_analytics.salestransaction st ON sti.transactionid = st.transactionid
JOIN costco_analytics.warehouse w ON st.warehouseid = w.warehouseid
WHERE (:region = 'All' OR w.region = :region)
  AND (:warehouse = 'All' OR w.name = :warehouse)
  AND (:category = 'All' OR c.name = :category)
  AND st.transactiondate::date BETWEEN :start_date AND :end_date
GROUP BY c.name, c.deptcode
ORDER BY total_revenue DESC;

-- 2. Location Battle: Warehouse Performance Ranking
SELECT
    w.warehouseid,
    w.name AS warehouse_name,
    w.location,
    w.region,
    ROUND(COALESCE(SUM(st.totalamount), 0)::numeric, 2) AS total_revenue,
    COUNT(st.transactionid) AS transaction_count,
    RANK() OVER (
        PARTITION BY w.region
        ORDER BY COALESCE(SUM(st.totalamount), 0) DESC
    ) AS regional_rank
FROM costco_analytics.warehouse w
LEFT JOIN costco_analytics.salestransaction st ON w.warehouseid = st.warehouseid
WHERE (:region = 'All' OR w.region = :region)
  AND (:warehouse = 'All' OR w.name = :warehouse)
  -- This subquery checks if the transaction contains the filtered category 
  -- without duplicating the transaction row!
  AND (:category = 'All' OR st.transactionid IN (
        SELECT sti.transactionid 
        FROM costco_analytics.salestransactionitem sti
        JOIN costco_analytics.product p ON sti.productid = p.productid
        JOIN costco_analytics.category c ON p.categoryid = c.categoryid
        WHERE c.name = :category
      ))
  AND (st.transactiondate IS NULL OR st.transactiondate::date BETWEEN :start_date AND :end_date)
GROUP BY w.warehouseid, w.name, w.location, w.region
ORDER BY total_revenue DESC;

-- 3. Empty Shelf: Low Inventory / Restocking Alert
SELECT
    w.name AS warehouse_name,
    p.name AS product_name,
    i.stockquantity,
    i.reorderlevel,
    ps.leadtimedays,
    s.name AS supplier_name,
    CASE
        WHEN i.stockquantity = 0 THEN 'Out of Stock'
        WHEN i.stockquantity < i.reorderlevel THEN 'Restock Now'
        WHEN i.stockquantity <= i.reorderlevel + 5 THEN 'Monitor Closely'
        ELSE 'Healthy'
    END AS inventory_status
FROM costco_analytics.inventory i
JOIN costco_analytics.warehouse w ON i.warehouseid = w.warehouseid
JOIN costco_analytics.product p ON i.productid = p.productid
JOIN costco_analytics.category c ON p.categoryid = c.categoryid
LEFT JOIN costco_analytics.productsupplier ps ON p.productid = ps.productid
LEFT JOIN costco_analytics.supplier s ON ps.supplierid = s.supplierid
WHERE i.stockquantity <= i.reorderlevel + 5
  AND (:region = 'All' OR w.region = :region)
  AND (:warehouse = 'All' OR w.name = :warehouse)
  AND (:category = 'All' OR c.name = :category)
ORDER BY
    CASE
        WHEN i.stockquantity = 0 THEN 1
        WHEN i.stockquantity < i.reorderlevel THEN 2
        ELSE 3
    END,
    ps.leadtimedays DESC NULLS LAST;

-- 4. Hidden Failure: Warehouse-Category Underperformance
SELECT
    w.name AS warehouse_name,
    w.location,
    w.region,
    c.name AS category_name,
    ROUND(SUM(sti.subtotal)::numeric, 2) AS category_revenue,
    SUM(sti.quantity) AS units_sold,
    COUNT(DISTINCT st.transactionid) AS transaction_count
FROM costco_analytics.warehouse w
JOIN costco_analytics.salestransaction st ON w.warehouseid = st.warehouseid
JOIN costco_analytics.salestransactionitem sti ON st.transactionid = sti.transactionid
JOIN costco_analytics.product p ON sti.productid = p.productid
JOIN costco_analytics.category c ON p.categoryid = c.categoryid
WHERE (:region = 'All' OR w.region = :region)
  AND (:warehouse = 'All' OR w.name = :warehouse)
  AND (:category = 'All' OR c.name = :category)
  AND st.transactiondate::date BETWEEN :start_date AND :end_date
GROUP BY w.name, w.location, w.region, c.name
ORDER BY category_revenue ASC;

-- 5. Move It or Lose It: Promotional Action Candidates
SELECT
    w.name AS warehouse_name,
    p.name AS product_name,
    i.stockquantity,
    i.reorderlevel,
    COALESCE(SUM(sti.quantity), 0) AS units_sold,
    CASE
        WHEN i.stockquantity > 50 AND COALESCE(SUM(sti.quantity), 0) < 5 
            THEN 'Overstock: Run Promotion'
        WHEN p.product_details::text ILIKE '%Winter%' AND i.stockquantity > i.reorderlevel 
            THEN 'Seasonal Clearance'
        ELSE 'Healthy Inventory'
    END AS promotion_recommendation
FROM costco_analytics.inventory i
JOIN costco_analytics.warehouse w ON i.warehouseid = w.warehouseid
JOIN costco_analytics.product p ON i.productid = p.productid
LEFT JOIN costco_analytics.salestransactionitem sti ON p.productid = sti.productid
LEFT JOIN costco_analytics.salestransaction st ON sti.transactionid = st.transactionid
    AND st.transactiondate::date BETWEEN :start_date AND :end_date
WHERE 
    (:region = 'All' OR w.region = :region) AND 
    (:warehouse = 'All' OR w.name = :warehouse) AND 
    (:category = 'All' OR p.categoryid IN (SELECT categoryid FROM costco_analytics.category WHERE name = :category))
GROUP BY w.name, p.name, i.stockquantity, i.reorderlevel, p.product_details
ORDER BY i.stockquantity DESC;

