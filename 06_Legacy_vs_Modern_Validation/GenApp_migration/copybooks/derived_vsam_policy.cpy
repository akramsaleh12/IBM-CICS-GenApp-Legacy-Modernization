      *================================================================*
      * DERIVED COPYBOOK:  VSAM-POLICY-RECORD
      * SOURCE:  KSDSPOLY (VSAM KSDS, key = REQUEST-ID+CUST-NUM+POLICY-NUM,
      *          64 bytes)
      * DERIVATION: copied verbatim (field layout) from the WF-Policy-Info
      * working-storage record in reference/cobol/lgapvs01.cbl, which IS
      * the physical record written via
      *     EXEC CICS WRITE FILE('KSDSPOLY') FROM(WF-Policy-Info) ...
      * WF-Request-ID carries the policy-type discriminator character
      * ('C'=Commercial, 'E'=Endowment, 'H'=House, 'M'=Motor) that
      * selects which REDEFINES interpretation of the 43-byte data
      * area is valid for a given row. This is a CLASSIC VSAM
      * REDEFINES-by-discriminator pattern: unlike the customer record,
      * a single physical layout here services four distinct business
      * entities, distinguished only by the leading type byte.
      * NOTE: this is a SUMMARY/index record only - it carries a subset
      * of each policy type's full attribute set (the complete attribute
      * sets live in the DB2 tables policy/endowment/house/motor/
      * commercial - see ddl/db2_source_schema.sql). When migrating a
      * shop that ran GenApp in VSAM-only mode (no DB2 side), the
      * target columns not present here (issueDate, expiryDate,
      * brokerId, brokersReference, payment, commission, and most
      * type-specific detail fields) will be NULL after migration and
      * must be backfilled from another source of record if available.
      * Field-count check: 1 + 10 + 10 + 43 = 64 bytes. Confirmed
      * against reference/data/ksdspoly.txt (each line = 64 chars).
      *================================================================*
       01  POLICY-RECORD.
           05  POLICY-REQUEST-ID               PIC X(01).
      *        'C' = Commercial, 'E' = Endowment, 'H' = House, 'M' = Motor
           05  POLICY-CUSTOMER-NUM              PIC X(10).
           05  POLICY-NUM                       PIC X(10).
           05  POLICY-DATA                      PIC X(43).
      *    ---- 'C' (COMMERCIAL) INTERPRETATION OF POLICY-DATA ----
           05  POLICY-C-DATA REDEFINES POLICY-DATA.
               10  POLICY-C-POSTCODE            PIC X(08).
               10  POLICY-C-STATUS               PIC 9(04).
               10  POLICY-C-CUSTOMER              PIC X(31).
      *    ---- 'E' (ENDOWMENT) INTERPRETATION OF POLICY-DATA ----
           05  POLICY-E-DATA REDEFINES POLICY-DATA.
               10  POLICY-E-WITH-PROFITS         PIC X(01).
               10  POLICY-E-EQUITIES              PIC X(01).
               10  POLICY-E-MANAGED-FUND           PIC X(01).
               10  POLICY-E-FUND-NAME               PIC X(10).
               10  POLICY-E-LIFE-ASSURED             PIC X(30).
      *    ---- 'H' (HOUSE) INTERPRETATION OF POLICY-DATA ----
           05  POLICY-H-DATA REDEFINES POLICY-DATA.
               10  POLICY-H-PROPERTY-TYPE        PIC X(15).
               10  POLICY-H-BEDROOMS              PIC 9(03).
               10  POLICY-H-VALUE                  PIC 9(08).
               10  POLICY-H-POSTCODE                PIC X(08).
               10  POLICY-H-HOUSE-NAME               PIC X(09).
      *    ---- 'M' (MOTOR) INTERPRETATION OF POLICY-DATA ----
           05  POLICY-M-DATA REDEFINES POLICY-DATA.
               10  POLICY-M-MAKE                 PIC X(15).
               10  POLICY-M-MODEL                 PIC X(15).
               10  POLICY-M-VALUE                  PIC 9(06).
               10  POLICY-M-REGNUMBER               PIC X(07).
