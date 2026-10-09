"""
crud.py
--------
A factory that builds a full CRUD APIRouter (list/get/create/update/
delete) for one PostgreSQL table, given its primary key column and
Pydantic Create/Update/Out schemas. All 8 core entity routers in
routers/ are ~10 lines of glue on top of this - see routers/customers.py
for the simplest example.

Kept deliberately as plain parametrized SQL (psycopg2, %s placeholders)
rather than an ORM, consistent with the rest of this project.
"""
from typing import Optional, Type

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2 import errors as pg_errors
from pydantic import BaseModel

from database import get_db, SCHEMA


def make_crud_router(
    *,
    table: str,
    pk_field: str,
    out_schema: Type[BaseModel],
    create_schema: Type[BaseModel],
    update_schema: Type[BaseModel],
    tags: list[str],
    prefix: str,
    pk_type=int,
    pk_generated: bool = True,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=tags)
    full_table = f'{SCHEMA}.{table}'

    @router.get("", response_model=list[out_schema], summary=f"List {table} rows")
    def list_rows(
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=500),
        db=Depends(get_db),
    ):
        with db.cursor() as cur:
            cur.execute(f'SELECT * FROM {full_table} ORDER BY {pk_field} LIMIT %s OFFSET %s', (limit, skip))
            return cur.fetchall()

    @router.get("/{pk}", response_model=out_schema, summary=f"Get one {table} row by {pk_field}")
    def get_row(pk: pk_type, db=Depends(get_db)):
        with db.cursor() as cur:
            cur.execute(f'SELECT * FROM {full_table} WHERE {pk_field} = %s', (pk,))
            row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"{table} {pk_field}={pk} not found")
        return row

    @router.post("", response_model=out_schema, status_code=201, summary=f"Create a {table} row")
    def create_row(payload: create_schema, db=Depends(get_db)):
        data = payload.model_dump(exclude_unset=True)
        # Drop an explicitly-None pk on a generated-identity table so the
        # database assigns the next value instead of erroring on NULL.
        if pk_generated and data.get(pk_field) is None:
            data.pop(pk_field, None)
        cols = list(data.keys())
        if not cols:
            raise HTTPException(status_code=400, detail="No fields provided")
        col_list = ", ".join(cols)
        placeholders = ", ".join(["%s"] * len(cols))
        overriding = " OVERRIDING SYSTEM VALUE " if (pk_generated and pk_field in cols) else " "
        sql = f'INSERT INTO {full_table} ({col_list}){overriding}VALUES ({placeholders}) RETURNING *'
        try:
            with db.cursor() as cur:
                cur.execute(sql, [data[c] for c in cols])
                row = cur.fetchone()
        except pg_errors.UniqueViolation as e:
            raise HTTPException(status_code=409, detail=str(e.diag.message_primary or e))
        except pg_errors.ForeignKeyViolation as e:
            raise HTTPException(status_code=422, detail=str(e.diag.message_primary or e))
        return row

    @router.put("/{pk}", response_model=out_schema, summary=f"Update a {table} row")
    def update_row(pk: pk_type, payload: update_schema, db=Depends(get_db)):
        data = payload.model_dump(exclude_unset=True)
        data.pop(pk_field, None)
        if not data:
            raise HTTPException(status_code=400, detail="No fields provided to update")
        set_clause = ", ".join(f"{c} = %s" for c in data.keys())
        sql = f'UPDATE {full_table} SET {set_clause} WHERE {pk_field} = %s RETURNING *'
        try:
            with db.cursor() as cur:
                cur.execute(sql, list(data.values()) + [pk])
                row = cur.fetchone()
        except pg_errors.ForeignKeyViolation as e:
            raise HTTPException(status_code=422, detail=str(e.diag.message_primary or e))
        if row is None:
            raise HTTPException(status_code=404, detail=f"{table} {pk_field}={pk} not found")
        return row

    @router.delete("/{pk}", status_code=204, summary=f"Delete a {table} row")
    def delete_row(pk: pk_type, db=Depends(get_db)):
        with db.cursor() as cur:
            cur.execute(f'DELETE FROM {full_table} WHERE {pk_field} = %s RETURNING {pk_field}', (pk,))
            row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"{table} {pk_field}={pk} not found")
        return None

    return router
