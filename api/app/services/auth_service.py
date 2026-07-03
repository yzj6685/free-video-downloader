from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import threading
from pathlib import Path

from fastapi import HTTPException

from app.config import get_settings
from app.models import AuthResponse, UserResponse
from app.services.billing_service import utc_now


_lock = threading.Lock()


class AuthStore:
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or get_settings().billing_database_path

    def _connect(self) -> sqlite3.Connection:
        path = Path(self.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with _lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )

    def get_user_by_email(self, email: str) -> sqlite3.Row | None:
        self.initialize()
        with self._connect() as connection:
            return connection.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    def create_user(self, email: str, password_hash: str) -> sqlite3.Row:
        self.initialize()
        now = utc_now()
        try:
            with _lock, self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO users (email, password_hash, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (email, password_hash, now, now),
                )
                user_id = cursor.lastrowid
                row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
                if row is None:
                    raise RuntimeError("created user missing")
                return row
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="该邮箱已注册，请直接登录。") from exc

    def create_session(self, user_id: int) -> str:
        self.initialize()
        token = secrets.token_urlsafe(32)
        now = utc_now()
        with _lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO auth_sessions (token, user_id, created_at, last_seen_at) VALUES (?, ?, ?, ?)",
                (token, user_id, now, now),
            )
        return token

    def get_user_by_token(self, token: str) -> sqlite3.Row | None:
        self.initialize()
        now = utc_now()
        with _lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT users.* FROM auth_sessions
                JOIN users ON users.id = auth_sessions.user_id
                WHERE auth_sessions.token = ?
                """,
                (token,),
            ).fetchone()
            if row:
                connection.execute("UPDATE auth_sessions SET last_seen_at = ? WHERE token = ?", (now, token))
            return row

    def delete_session(self, token: str) -> None:
        self.initialize()
        with _lock, self._connect() as connection:
            connection.execute("DELETE FROM auth_sessions WHERE token = ?", (token,))


class AuthService:
    def __init__(self, store: AuthStore | None = None) -> None:
        self.store = store or AuthStore()

    def register(self, email: str, password: str) -> AuthResponse:
        user = self.store.create_user(email, self._hash_password(password))
        token = self.store.create_session(int(user["id"]))
        return AuthResponse(token=token, user=self._user_response(user))

    def login(self, email: str, password: str) -> AuthResponse:
        user = self.store.get_user_by_email(email)
        if user is None or not self._verify_password(password, str(user["password_hash"])):
            raise HTTPException(status_code=401, detail="邮箱或密码不正确。")
        token = self.store.create_session(int(user["id"]))
        return AuthResponse(token=token, user=self._user_response(user))

    def me(self, token: str | None) -> UserResponse:
        user = self._require_user(token)
        return self._user_response(user)

    def logout(self, token: str | None) -> None:
        if token:
            self.store.delete_session(token)

    def _require_user(self, token: str | None) -> sqlite3.Row:
        if not token:
            raise HTTPException(status_code=401, detail="请先登录。")
        user = self.store.get_user_by_token(token)
        if user is None:
            raise HTTPException(status_code=401, detail="登录状态已失效，请重新登录。")
        return user

    def _hash_password(self, password: str) -> str:
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 120_000)
        return f"pbkdf2_sha256$120000${salt}${digest.hex()}"

    def _verify_password(self, password: str, stored: str) -> bool:
        try:
            algorithm, rounds_text, salt, expected = stored.split("$", 3)
            if algorithm != "pbkdf2_sha256":
                return False
            rounds = int(rounds_text)
            digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), rounds)
            return hmac.compare_digest(digest.hex(), expected)
        except Exception:
            return False

    def _user_response(self, row: sqlite3.Row) -> UserResponse:
        return UserResponse(id=int(row["id"]), email=str(row["email"]), created_at=str(row["created_at"]))


auth_service = AuthService()
