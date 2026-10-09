-- ================================================================
-- 03_comments.sql
-- Adds native PostgreSQL COMMENT ON TABLE / COMMENT ON COLUMN
-- metadata to every table in the genapp schema. This is the standard
-- PostgreSQL mechanism for a self-describing data dictionary - the
-- comments are stored in pg_catalog.pg_description and readable via
-- \d+ in psql, information_schema-based tooling, or the
-- streamlit_app/data_dictionary_app.py viewer in this package.
--
-- Descriptions are derived from the source COBOL copybooks
-- (copybooks/derived_vsam_customer.cpy, derived_vsam_policy.cpy) and
-- the real DB2 DDL (ddl/db2_source_schema.sql / reference/jcl/db2cre.jcl),
-- not guessed - see docs/MIGRATION_BLUEPRINT.md for the full field-
-- level derivation.
-- ================================================================
SET search_path TO genapp, public;

-- ---------------------------------------------------------------
-- customer
-- ---------------------------------------------------------------
COMMENT ON TABLE genapp.customer IS
    'Policyholder master record. Source of record for a customer''s identity and contact details; every policy references exactly one customer. Migrated from both DB2 CUSTOMER and VSAM KSDSCUST (see load_vsam_customer.py).';
COMMENT ON COLUMN genapp.customer.customer_number IS 'Primary key. Auto-generated identity in DB2-mode; carried over verbatim from the VSAM KSDSCUST key (CUST-NUM, PIC 9(10)) when migrating from VSAM.';
COMMENT ON COLUMN genapp.customer.first_name IS 'Customer given name. Source: DB2 firstName CHAR(10) / VSAM CUST-FIRST-NAME PIC X(10).';
COMMENT ON COLUMN genapp.customer.last_name IS 'Customer family name. Source: DB2 lastName CHAR(20) / VSAM CUST-LAST-NAME PIC X(20).';
COMMENT ON COLUMN genapp.customer.date_of_birth IS 'Date of birth. Source: DB2 dateOfBirth DATE / VSAM CUST-DOB PIC X(10), formatted YYYY-MM-DD.';
COMMENT ON COLUMN genapp.customer.house_name IS 'Named-property component of the customer''s home address (used instead of/alongside a house number for named UK properties). Source: DB2 houseName CHAR(20) / VSAM CUST-HOUSE-NAME PIC X(20).';
COMMENT ON COLUMN genapp.customer.house_number IS 'Numbered-property component of the customer''s home address. Source: DB2 houseNumber CHAR(4) / VSAM CUST-HOUSE-NUM PIC X(04).';
COMMENT ON COLUMN genapp.customer.postcode IS 'UK postal code of the customer''s home address. Source: DB2 postcode CHAR(8) / VSAM CUST-POSTCODE PIC X(08).';
COMMENT ON COLUMN genapp.customer.phone_home IS 'Landline/home contact number. Source: DB2 phonehome CHAR(20) / VSAM CUST-PHONE-HOME PIC X(20).';
COMMENT ON COLUMN genapp.customer.phone_mobile IS 'Mobile contact number. Source: DB2 phonemobile CHAR(20) / VSAM CUST-PHONE-MOBILE PIC X(20).';
COMMENT ON COLUMN genapp.customer.email_address IS 'Contact email address. Source: DB2 emailaddress CHAR(100) / VSAM CUST-EMAIL-ADDRESS PIC X(100).';

-- ---------------------------------------------------------------
-- customer_secure
-- ---------------------------------------------------------------
COMMENT ON TABLE genapp.customer_secure IS
    'Authentication credentials for a customer''s self-service web/portal login, 1:1 with customer. DB2-only - no VSAM equivalent exists (VSAM KSDSCUST carries no auth data).';
COMMENT ON COLUMN genapp.customer_secure.customer_number IS 'Primary key and foreign key to customer.customer_number (ON DELETE CASCADE).';
COMMENT ON COLUMN genapp.customer_secure.customer_pass IS 'Hashed customer password/credential (DB2 CHAR(32), sized for an MD5-length hex digest). Never store as plaintext; treat as sensitive.';
COMMENT ON COLUMN genapp.customer_secure.state_indicator IS 'Single-character account state flag (source system does not document the code list beyond "A" = active in sample data - confirm the full value set with the business before relying on it).';
COMMENT ON COLUMN genapp.customer_secure.pass_changes IS 'Running count of how many times this customer has changed their password.';

-- ---------------------------------------------------------------
-- policy
-- ---------------------------------------------------------------
COMMENT ON TABLE genapp.policy IS
    'Policy header record shared by all policy types. The policy_type column is the discriminator selecting which one of endowment/house/motor/commercial holds this policy''s type-specific detail row. Migrated from both DB2 POLICY and VSAM KSDSPOLY (see load_vsam_policy.py) - VSAM-sourced rows only populate policy_number/customer_number/policy_type; the remaining columns are DB2-only (VSAM''s summary record does not carry them).';
COMMENT ON COLUMN genapp.policy.policy_number IS 'Primary key. Auto-generated identity in DB2-mode; carried over from VSAM KSDSPOLY''s POLICY-NUM (PIC X(10)) when migrating from VSAM.';
COMMENT ON COLUMN genapp.policy.customer_number IS 'Foreign key to customer.customer_number - the policyholder.';
COMMENT ON COLUMN genapp.policy.issue_date IS 'Date the policy was issued/incepted. DB2-only field (not present in the VSAM KSDSPOLY summary record).';
COMMENT ON COLUMN genapp.policy.expiry_date IS 'Date the policy expires/is due for renewal. DB2-only field.';
COMMENT ON COLUMN genapp.policy.policy_type IS 'Single-character policy-type discriminator: C = Commercial, E = Endowment, H = House, M = Motor. Selects which detail table (commercial/endowment/house/motor) holds this policy''s type-specific attributes. Source: VSAM POLICY-REQUEST-ID (the leading byte of the KSDSPOLY record) / DB2 policyType CHAR(1).';
COMMENT ON COLUMN genapp.policy.last_changed IS 'Timestamp of the last update to this policy row. Defaults to the load time for migrated rows.';
COMMENT ON COLUMN genapp.policy.broker_id IS 'Identifier of the broker who placed this policy, if sold through a broker channel. DB2-only field.';
COMMENT ON COLUMN genapp.policy.brokers_reference IS 'The broker''s own reference/case number for this policy. DB2-only field.';
COMMENT ON COLUMN genapp.policy.payment IS 'Payment amount associated with the policy (units per the source system''s convention, typically minor currency units / pence). DB2-only field.';
COMMENT ON COLUMN genapp.policy.commission IS 'Commission amount paid on this policy. DB2-only field.';

-- ---------------------------------------------------------------
-- endowment
-- ---------------------------------------------------------------
COMMENT ON TABLE genapp.endowment IS
    'Type-specific detail for policy_type = ''E'' (Endowment / life-assurance-linked savings policies). 1:1 with policy via policy_number. VSAM-sourced rows only populate with_profits/equities/managed_fund/fund_name/life_assured (from KSDSPOLY''s POLICY-E-DATA REDEFINES); term/sum_assured/padding_data are DB2-only.';
COMMENT ON COLUMN genapp.endowment.policy_number IS 'Primary key and foreign key to policy.policy_number (ON DELETE CASCADE).';
COMMENT ON COLUMN genapp.endowment.equities IS 'Flag (Y/N-style single char) indicating the fund invests in equities. Source: VSAM POLICY-E-EQUITIES PIC X(01) / DB2 equities CHAR(1).';
COMMENT ON COLUMN genapp.endowment.with_profits IS 'Flag indicating this is a with-profits endowment fund. Source: VSAM POLICY-E-WITH-PROFITS PIC X(01) / DB2 withProfits CHAR(1).';
COMMENT ON COLUMN genapp.endowment.managed_fund IS 'Flag indicating the policy is linked to a professionally managed fund. Source: VSAM POLICY-E-MANAGED-FUND PIC X(01) / DB2 managedFund CHAR(1).';
COMMENT ON COLUMN genapp.endowment.fund_name IS 'Name of the underlying investment fund. Source: VSAM POLICY-E-FUND-NAME PIC X(10) / DB2 fundName CHAR(10).';
COMMENT ON COLUMN genapp.endowment.term IS 'Policy term length in years. DB2-only field.';
COMMENT ON COLUMN genapp.endowment.sum_assured IS 'Guaranteed sum payable on maturity or death, in the source system''s currency unit convention. DB2-only field.';
COMMENT ON COLUMN genapp.endowment.life_assured IS 'Name of the person whose life is assured under this policy (may differ from the policyholder). Source: VSAM POLICY-E-LIFE-ASSURED PIC X(30) / DB2 lifeAssured CHAR(31).';
COMMENT ON COLUMN genapp.endowment.padding_data IS 'Large free-text scratch field from the original DB2 schema (declared VARCHAR(32606) in DB2); purpose not documented by the source system. Migrated as-is for completeness.';

-- ---------------------------------------------------------------
-- house
-- ---------------------------------------------------------------
COMMENT ON TABLE genapp.house IS
    'Type-specific detail for policy_type = ''H'' (House / home & contents insurance policies). 1:1 with policy via policy_number. Fully populated from VSAM KSDSPOLY''s POLICY-H-DATA REDEFINES - this is the one detail table where the VSAM summary record and DB2 row carry the same fields.';
COMMENT ON COLUMN genapp.house.policy_number IS 'Primary key and foreign key to policy.policy_number (ON DELETE CASCADE).';
COMMENT ON COLUMN genapp.house.property_type IS 'Type of insured property, e.g. "HOUSE", "FARM". Source: VSAM POLICY-H-PROPERTY-TYPE PIC X(15) / DB2 propertyType CHAR(15).';
COMMENT ON COLUMN genapp.house.bedrooms IS 'Number of bedrooms. Source: VSAM POLICY-H-BEDROOMS PIC 9(03) / DB2 bedrooms SMALLINT. NOTE: sample source data has at least one malformed value (a stray space instead of zero-padding) - validate this column after any real-data load; see README "Known data-quality findings".';
COMMENT ON COLUMN genapp.house.value IS 'Insured value of the property, in the source system''s currency unit convention. Source: VSAM POLICY-H-VALUE PIC 9(08) / DB2 value INTEGER.';
COMMENT ON COLUMN genapp.house.house_name IS 'Named-property identifier of the insured address (distinct from customer.house_name, which is the policyholder''s own home). Source: VSAM POLICY-H-HOUSE-NAME PIC X(09) / DB2 houseName CHAR(20) (note the VSAM field is narrower than the DB2 column - VSAM-sourced values may be truncated relative to a full DB2-mode record).';
COMMENT ON COLUMN genapp.house.house_number IS 'Numbered-property identifier of the insured address. DB2-only field (not present in the VSAM KSDSPOLY summary record for house policies).';
COMMENT ON COLUMN genapp.house.postcode IS 'Postal code of the insured property. Source: VSAM POLICY-H-POSTCODE PIC X(08) / DB2 postcode CHAR(8).';

-- ---------------------------------------------------------------
-- motor
-- ---------------------------------------------------------------
COMMENT ON TABLE genapp.motor IS
    'Type-specific detail for policy_type = ''M'' (Motor / vehicle insurance policies). 1:1 with policy via policy_number. VSAM-sourced rows only populate make/model/value/reg_number (from KSDSPOLY''s POLICY-M-DATA REDEFINES); colour/cc/year_of_manufacture/premium/accidents are DB2-only.';
COMMENT ON COLUMN genapp.motor.policy_number IS 'Primary key and foreign key to policy.policy_number (ON DELETE CASCADE).';
COMMENT ON COLUMN genapp.motor.make IS 'Vehicle manufacturer, e.g. "FORD". Source: VSAM POLICY-M-MAKE PIC X(15) / DB2 make CHAR(15).';
COMMENT ON COLUMN genapp.motor.model IS 'Vehicle model. Source: VSAM POLICY-M-MODEL PIC X(15) / DB2 model CHAR(15).';
COMMENT ON COLUMN genapp.motor.value IS 'Insured value of the vehicle, in the source system''s currency unit convention. Source: VSAM POLICY-M-VALUE PIC 9(06) / DB2 value INTEGER.';
COMMENT ON COLUMN genapp.motor.reg_number IS 'Vehicle registration/license plate number. Source: VSAM POLICY-M-REGNUMBER PIC X(07) / DB2 regNumber CHAR(7).';
COMMENT ON COLUMN genapp.motor.colour IS 'Vehicle colour. DB2-only field.';
COMMENT ON COLUMN genapp.motor.cc IS 'Engine displacement in cubic centimetres. DB2-only field.';
COMMENT ON COLUMN genapp.motor.year_of_manufacture IS 'Vehicle manufacture year, stored as a DATE (day/month are placeholder values from the source system). DB2-only field.';
COMMENT ON COLUMN genapp.motor.premium IS 'Insurance premium charged for this vehicle policy. DB2-only field.';
COMMENT ON COLUMN genapp.motor.accidents IS 'Count of recorded accidents/claims history against this vehicle policy. DB2-only field.';

-- ---------------------------------------------------------------
-- commercial
-- ---------------------------------------------------------------
COMMENT ON TABLE genapp.commercial IS
    'Type-specific detail for policy_type = ''C'' (Commercial property insurance policies), covering multi-peril cover (fire/crime/flood/weather) for a business property. 1:1 with policy via policy_number. VSAM-sourced rows only populate zipcode/status/customer (from KSDSPOLY''s POLICY-C-DATA REDEFINES); all peril/premium and address-detail columns are DB2-only.';
COMMENT ON COLUMN genapp.commercial.policy_number IS 'Primary key and foreign key to policy.policy_number (ON DELETE CASCADE).';
COMMENT ON COLUMN genapp.commercial.request_date IS 'Timestamp the commercial cover quote/request was made. DB2-only field.';
COMMENT ON COLUMN genapp.commercial.start_date IS 'Cover start date. DB2-only field.';
COMMENT ON COLUMN genapp.commercial.renewal_date IS 'Cover renewal due date. DB2-only field.';
COMMENT ON COLUMN genapp.commercial.address IS 'Full postal address of the insured commercial property. DB2-only field.';
COMMENT ON COLUMN genapp.commercial.zipcode IS 'Postal code of the insured property. Source: VSAM POLICY-C-POSTCODE PIC X(08) / DB2 Zipcode CHAR(8).';
COMMENT ON COLUMN genapp.commercial.latitude_n IS 'Latitude of the insured property (north), stored as text per the source system''s convention. DB2-only field.';
COMMENT ON COLUMN genapp.commercial.longitude_w IS 'Longitude of the insured property (west), stored as text per the source system''s convention. DB2-only field.';
COMMENT ON COLUMN genapp.commercial.customer IS 'Free-text business/customer name associated with the commercial policy (distinct from the customer table - this is the DB2 source''s own denormalized copy). Source: VSAM POLICY-C-CUSTOMER PIC X(31) / DB2 Customer CHAR(255).';
COMMENT ON COLUMN genapp.commercial.property_type IS 'Free-text description of the commercial property type/use. DB2-only field.';
COMMENT ON COLUMN genapp.commercial.fire_peril IS 'Flag/code indicating whether fire peril cover is included. DB2-only field.';
COMMENT ON COLUMN genapp.commercial.fire_premium IS 'Premium charged for fire peril cover. DB2-only field.';
COMMENT ON COLUMN genapp.commercial.crime_peril IS 'Flag/code indicating whether crime peril cover is included. DB2-only field.';
COMMENT ON COLUMN genapp.commercial.crime_premium IS 'Premium charged for crime peril cover. DB2-only field.';
COMMENT ON COLUMN genapp.commercial.flood_peril IS 'Flag/code indicating whether flood peril cover is included. DB2-only field.';
COMMENT ON COLUMN genapp.commercial.flood_premium IS 'Premium charged for flood peril cover. DB2-only field.';
COMMENT ON COLUMN genapp.commercial.weather_peril IS 'Flag/code indicating whether weather peril cover is included. DB2-only field.';
COMMENT ON COLUMN genapp.commercial.weather_premium IS 'Premium charged for weather peril cover. DB2-only field.';
COMMENT ON COLUMN genapp.commercial.status IS 'Numeric status code for the commercial policy/quote (underwriting decision state). Source: VSAM POLICY-C-STATUS PIC 9(04) / DB2 Status SMALLINT. Code list not documented by the source system - confirm with the business.';
COMMENT ON COLUMN genapp.commercial.rejection_reason IS 'Free-text reason the commercial quote/policy was rejected, if applicable. DB2-only field.';

-- ---------------------------------------------------------------
-- claim
-- ---------------------------------------------------------------
COMMENT ON TABLE genapp.claim IS
    'Insurance claims filed against a policy. Many-to-one with policy. DB2-only - no VSAM equivalent exists (KSDSPOLY carries no claims data).';
COMMENT ON COLUMN genapp.claim.claim_number IS 'Primary key. Auto-generated identity.';
COMMENT ON COLUMN genapp.claim.policy_number IS 'Foreign key to policy.policy_number - the policy this claim was filed against.';
COMMENT ON COLUMN genapp.claim.claim_date IS 'Date the claim was filed.';
COMMENT ON COLUMN genapp.claim.paid IS 'Amount actually paid out on this claim, in the source system''s currency unit convention.';
COMMENT ON COLUMN genapp.claim.value IS 'Claimed/assessed value of the loss, which may differ from the amount ultimately paid.';
COMMENT ON COLUMN genapp.claim.cause IS 'Free-text description of what caused the claim, e.g. "Storm damage to roof".';
COMMENT ON COLUMN genapp.claim.observations IS 'Free-text adjuster/handler notes and observations about the claim.';
