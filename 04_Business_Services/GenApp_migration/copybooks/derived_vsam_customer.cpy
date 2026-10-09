      *================================================================*
      * DERIVED COPYBOOK:  VSAM-CUSTOMER-RECORD
      * SOURCE:  KSDSCUST (VSAM KSDS, key = CUSTOMER-NUM, 225 bytes)
      * DERIVATION: reference/cobol/lgacvs01.cbl performs:
      *     EXEC CICS WRITE FILE('KSDSCUST')
      *          FROM(CA-Customer-Num)
      *          LENGTH(CUSTOMER-RECORD-SIZE)   *> = 225
      *          RIDFLD(CA-Customer-Num) KEYLENGTH(10)
      *     END-EXEC.
      * CA-Customer-Num is immediately followed in DFHCOMMAREA by
      * CA-REQUEST-SPECIFIC, which is redefined by CA-CUSTOMER-REQUEST
      * (see copybooks/lgcmarea.cpy). Because WRITE FROM/LENGTH reads
      * contiguous storage starting at CA-Customer-Num, the physical
      * VSAM record is CA-CUSTOMER-NUM immediately followed by the
      * first 215 bytes of CA-CUSTOMER-REQUEST (up through
      * CA-EMAIL-ADDRESS; CA-POLICY-DATA is NOT part of this record -
      * it is scratch commarea space beyond the 225-byte write length).
      * 10 + 10+20+10+20+4+8+3+20+20+100 = 225 bytes. Confirmed against
      * reference/data/ksdscust.txt (each line is exactly 225 chars).
      *================================================================*
       01  CUSTOMER-RECORD.
           05  CUST-NUM                        PIC 9(10).
           05  CUST-FIRST-NAME                 PIC X(10).
           05  CUST-LAST-NAME                  PIC X(20).
           05  CUST-DOB                        PIC X(10).
           05  CUST-HOUSE-NAME                 PIC X(20).
           05  CUST-HOUSE-NUM                  PIC X(04).
           05  CUST-POSTCODE                   PIC X(08).
           05  CUST-NUM-POLICIES               PIC 9(03).
           05  CUST-PHONE-MOBILE                PIC X(20).
           05  CUST-PHONE-HOME                   PIC X(20).
           05  CUST-EMAIL-ADDRESS                PIC X(100).
