-- ================================================================
-- 01_schema.sql
-- Creates the target schema/namespace and shared extensions.
-- Both the database and the schema are named "genapp" (the source
-- application's real name). scripts/run_migration.py creates the
-- "genapp" database itself automatically if it doesn't already exist
-- (see db_connect.ensure_database_exists) before this file runs.
-- ================================================================
CREATE SCHEMA IF NOT EXISTS genapp;
SET search_path TO genapp, public;

-- pgcrypto is useful if any DB2 fields need one-way hashing during
-- migration (e.g. SSN masking) - optional, comment out if not needed.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
