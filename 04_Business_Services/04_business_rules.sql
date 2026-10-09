-- ================================================================
-- 04_business_rules.sql
-- Schema support for the business-services layer (api/business_services/).
--
-- Rationale (see 01-analysis/03_business_rules/GenApp_Business_Rules.md
-- Section 6, and 08_Legacy_to_Modern_Mapping/... Section 4):
--   - Legacy LGUPDB01 (Update Policy) enforces optimistic concurrency
--     by comparing a caller-supplied LASTCHANGED timestamp against the
--     row's current value before allowing an update.
--   - Legacy Customer updates (LGUCUS01/LGUCDB01) have NO equivalent
--     check - flagged in the Business Rules report as "an
--     inconsistency ... worth flagging for a modernized design."
--   - The Legacy-to-Modern Mapping report (Section 4) explicitly
--     recommends: "Apply the same ETag/version-column pattern
--     uniformly to Customer as well as Policy" - this migration does
--     exactly that, fixing the inconsistency rather than preserving it,
--     per that report's own guidance.
--
-- Also fixes a latent gap in the raw CRUD API (api/crud.py's generic
-- UPDATE never touches last_changed because PolicyUpdate never exposed
-- it): a BEFORE UPDATE trigger now sets last_changed = now() on every
-- update to either table, regardless of which code path performs the
-- UPDATE, so the value is always trustworthy for optimistic-lock
-- comparisons.
-- ================================================================
SET search_path TO genapp, public;

-- ---------------------------------------------------------------
-- customer.last_changed - new column, matching policy.last_changed
-- ---------------------------------------------------------------
ALTER TABLE genapp.customer
    ADD COLUMN IF NOT EXISTS last_changed TIMESTAMP NOT NULL DEFAULT now();

COMMENT ON COLUMN genapp.customer.last_changed IS
    'Optimistic-concurrency timestamp, auto-maintained by trigger on every UPDATE. Added during modernization to fix a documented inconsistency: legacy Customer updates (LGUCUS01/LGUCDB01) had no equivalent lock that Policy updates (LGUPDB01) already enforced - see docs/MIGRATION_BLUEPRINT.md and 01-analysis/03_business_rules Section 6.';

-- ---------------------------------------------------------------
-- Auto-maintain last_changed on every UPDATE, on both tables, no
-- matter which code path performs the write (raw CRUD API, a
-- business service, or a future direct SQL client).
-- ---------------------------------------------------------------
CREATE OR REPLACE FUNCTION genapp.set_last_changed()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_changed := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_customer_last_changed ON genapp.customer;
CREATE TRIGGER trg_customer_last_changed
    BEFORE UPDATE ON genapp.customer
    FOR EACH ROW EXECUTE FUNCTION genapp.set_last_changed();

DROP TRIGGER IF EXISTS trg_policy_last_changed ON genapp.policy;
CREATE TRIGGER trg_policy_last_changed
    BEFORE UPDATE ON genapp.policy
    FOR EACH ROW EXECUTE FUNCTION genapp.set_last_changed();
