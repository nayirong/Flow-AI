-- Migration 002: Auto-increment customers.total_bookings on bookings INSERT
--
-- A Postgres trigger fires after each INSERT into the bookings table and
-- increments total_bookings on the matching customers row (matched by
-- phone_number). This approach is race-condition-safe: the UPDATE is atomic
-- at the DB level and requires no application-side read-modify-write.
--
-- Run this migration in the HeyAircon per-client Supabase project.

CREATE OR REPLACE FUNCTION increment_customer_total_bookings()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE customers
    SET total_bookings = total_bookings + 1
    WHERE phone_number = NEW.phone_number;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_increment_total_bookings ON bookings;

CREATE TRIGGER trg_increment_total_bookings
    AFTER INSERT ON bookings
    FOR EACH ROW
    EXECUTE FUNCTION increment_customer_total_bookings();
