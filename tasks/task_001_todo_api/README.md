# Task 001 — TODO API

## Overview
A minimal Flask REST API for managing TODO items backed by SQLite via SQLAlchemy.

## The Bug
The `PUT /todos/<id>` endpoint modifies the ORM object in memory but **does not call `session.commit()`**, so updates are never written to the database. After the request completes the session is discarded and the change is lost.

## Expected Behaviour
After a successful `PUT /todos/<id>` request, the updated fields (e.g. `completed`, `title`) should be persisted and visible on subsequent `GET /todos` requests.

## Endpoints
| Method | Path              | Description              |
|--------|-------------------|--------------------------|
| GET    | `/todos`          | List all TODO items      |
| POST   | `/todos`          | Create a new TODO item   |
| PUT    | `/todos/<id>`     | Update an existing item  |
| DELETE | `/todos/<id>`     | Delete an item           |

## Running
```bash
pip install -r requirements.txt
python app.py
```

## Verification
```bash
bash verify.sh
```
