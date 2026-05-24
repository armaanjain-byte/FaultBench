# Task 003 — User Auth

## Overview
A user authentication module with password hashing (SHA-256 + salt), JWT token creation, and token verification backed by SQLite.

## The Bug
`token_manager.py :: verify_token` passes `options={"verify_exp": False}` to `jwt.decode()`, which explicitly **disables** expiration checking. This means tokens whose `exp` claim is in the past are silently accepted as valid — a serious security vulnerability.

## Expected Behaviour
`verify_token` should raise `jwt.ExpiredSignatureError` when presented with an expired token. The `verify_exp` option should either be removed (defaults to `True`) or set to `True`.

## Running
```bash
pip install -r requirements.txt
python -c "from auth import register, login; register('alice','pw'); print(login('alice','pw'))"
```

## Verification
```bash
bash verify.sh
```
