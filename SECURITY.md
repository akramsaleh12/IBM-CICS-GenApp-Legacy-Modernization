# Security Notes

This repository does not contain real database credentials or other production secrets.

## Local configuration

1. Copy `.env.example` to `.env`.
2. Set your own local PostgreSQL password.
3. Never commit `.env`.

The application should obtain credentials from environment variables rather than
hard-coded values.

## Before publishing

If this repository was previously pushed with a real credential, rotate that
credential before making the repository public.
