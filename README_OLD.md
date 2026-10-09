# IBM CICS GenApp Legacy Modernization

End-to-end modernization portfolio project demonstrating a structured migration of an
IBM CICS GenApp-style legacy application from COBOL/CICS/DB2/VSAM toward a modern
Python, PostgreSQL, and REST API architecture.

## Modernization Journey

```text
Legacy Source
  COBOL + CICS + DB2 + VSAM
            |
            v
01-analysis
  Inventory | Dependencies | Business Rules | Complexity
  Database Analysis | Transaction Matrix | CRUD | Legacy-to-Modern Mapping
            |
            v
02-migration_DB2_VSAM_to_PostgreSQL
  Copybook Parsing | EBCDIC Handling | VSAM Migration | DB2 Migration
  PostgreSQL Schema | Data Dictionary | Migration Validation
            |
            v
03_backend_REST_API
  FastAPI | Pydantic | PostgreSQL | CRUD and Domain APIs
            |
            v
04_Business_Services
  Customer | Policy | Claim Services | Legacy Return-Code Mapping
            |
            v
05_Automated_Tests
  Unit | Integration | API | Migration Tests
            |
            v
06_Legacy_vs_Modern_Validation
  Behavioral Parity | MATCH | DEVIATION | NEW_CAPABILITY | NOT_IMPLEMENTED
```

## Repository Structure

- `source/` - Original legacy reference material organized by component.
- `01-analysis/` - Legacy discovery and modernization analysis.
- `02-migration_DB2_VSAM_to_PostgreSQL/` - Data migration and PostgreSQL target work.
- `03_backend_REST_API/` - FastAPI modernization layer.
- `04_Business_Services/` - Modern Python business services.
- `05_Automated_Tests/` - Automated regression and integration tests.
- `06_Legacy_vs_Modern_Validation/` - Legacy-to-modern behavioral validation.

## Key Capabilities

- COBOL/CICS application discovery and dependency analysis.
- DB2 and VSAM data analysis and migration to PostgreSQL.
- COBOL copybook parsing, EBCDIC decoding, and binary field handling.
- PostgreSQL data dictionary and inquiry tools.
- FastAPI REST APIs with Pydantic request/response models.
- Python business services mapped to legacy functions.
- Automated migration, service, and API tests.
- Legacy-versus-modern validation with explicit parity status categories.

## Local Setup

### 1. Clone the repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd IBM-CICS-GenApp-Modernization
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it:

**Windows**
```bash
.venv\Scripts\activate
```

**macOS/Linux**
```bash
source .venv/bin/activate
```

### 3. Configure PostgreSQL

Copy `.env.example` to `.env` and provide your own local settings.

```bash
copy .env.example .env
```

On macOS/Linux:

```bash
cp .env.example .env
```

### 4. Install dependencies

Each implementation phase may contain its own requirements or setup instructions.
Start with the README in the phase you want to run.

## Security

Do not commit real passwords, API keys, or `.env` files. See `SECURITY.md`.

## Portfolio Value

This project focuses on modernization traceability:

```text
Legacy Business Rule
      ->
Legacy Program / Transaction
      ->
Data Dependency
      ->
Modern Python Service / API
      ->
Automated Test
      ->
Legacy Parity Validation
```

## Recommended GitHub Repository Name

`IBM-CICS-GenApp-Legacy-Modernization`
