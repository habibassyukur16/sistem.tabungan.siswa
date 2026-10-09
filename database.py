import os
import sqlite3
from werkzeug.security import generate_password_hash

# Di Vercel, hanya folder /tmp yang boleh ditulis
if os.environ.get("VERCEL"):
    DATABASE = "/tmp/tabungan.db"
else:
    DATABASE = "tabungan.db"

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # supaya data bisa dibaca per nama kolom
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin', 'siswa'))
        );

        CREATE TABLE IF NOT EXISTS siswa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            nama TEXT NOT NULL,
            nis TEXT NOT NULL UNIQUE,
            kelas TEXT NOT NULL,
            saldo INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS transaksi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            siswa_id INTEGER NOT NULL,
            jenis TEXT NOT NULL CHECK (jenis IN ('setor', 'tarik')),
            jumlah INTEGER NOT NULL CHECK (jumlah > 0),
            waktu TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (siswa_id) REFERENCES siswa(id) ON DELETE CASCADE
        );
    """)

    # Akun default dari guru: dibuat hanya kalau belum ada
    admin = conn.execute(
        "SELECT id FROM users WHERE username = ?", ("admin",)
    ).fetchone()
    if admin is None:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("admin", generate_password_hash("admin123"), "admin"),
        )

    siswa01 = conn.execute(
        "SELECT id FROM users WHERE username = ?", ("siswa01",)
    ).fetchone()
    if siswa01 is None:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("siswa01", generate_password_hash("siswa123"), "siswa"),
        )
        conn.execute(
            "INSERT INTO siswa (user_id, nama, nis, kelas) VALUES (?, ?, ?, ?)",
            (cur.lastrowid, "Siswa Contoh", "0001", "X-1"),
        )

    conn.commit()
    conn.close()