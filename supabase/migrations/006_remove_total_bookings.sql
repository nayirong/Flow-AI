-- Migration 006: Remove total_bookings denormalized column from customers
--
-- Rationale: total_bookings is a derived aggregate (COUNT of bookings rows for
-- a customer). Storing it as a denormalized column on customers creates a
-- consistency risk (trigger can fail, go out of sync) and violates the
-- principle of keeping aggregations separate from source data.
--
-- Replacement: compute on-demand via:
--   SELECT COUNT(*) FROM bookings WHERE phone_number = $1;
-- or joined:
--   SELECT c.*, COUNT(b.id) AS total_bookings
--   FROM customers c
--   LEFT JOIN bookings b ON b.phone_number = c.phone_number
--   GROUP BY c.id;
--
-- Applied to: hey-aircon-crm, flow-ai-crm (when provisioned)

-- 1. Drop the trigger first (references the function below)
DROP TRIGGER IF EXISTS trg_increment_total_bookings ON bookings;

-- 2. Drop the trigger function
DROP FUNCTION IF EXISTS increment_customer_total_bookings();

-- 3. Drop the column
ALTER TABLE customers DROP COLUMN IF EXISTS total_bookings;
