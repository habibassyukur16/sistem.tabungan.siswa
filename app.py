import os
import sqlite3
from functools import wraps

from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash)
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db, init_db

app = Flask(__name__)
# Kunci untuk mengamankan session. Nanti di Vercel kita isi lewat environment variable.
app.secret_key = os.environ.get("SECRET_KEY", "kunci-rahasia-untuk-belajar")
init_db()


@app.template_filter("rupiah")
def format_rupiah(nilai):
    """Mengubah 150000 menjadi 'Rp 150.000'."""
    return "Rp " + f"{nilai:,}".replace(",", ".")


def login_required(role=None):
    """Halaman hanya bisa dibuka kalau sudah login (dan sesuai peran, jika ditentukan)."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Silakan login terlebih dahulu.", "error")
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                return redirect(url_for("home"))
            return f(*args, **kwargs)
        return wrapper
    return decorator


@app.route("/")
def home():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session["role"] == "admin":
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("siswa_dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("home"))

        flash("Username atau password salah.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------- ADMIN ----------------

@app.route("/admin")
@login_required(role="admin")
def admin_dashboard():
    conn = get_db()
    daftar_siswa = conn.execute("""
        SELECT siswa.id, siswa.nama, siswa.nis, siswa.kelas,
               siswa.saldo, users.username
        FROM siswa
        JOIN users ON users.id = siswa.user_id
        ORDER BY siswa.nama
    """).fetchall()
    total = conn.execute(
        "SELECT COALESCE(SUM(saldo), 0) FROM siswa"
    ).fetchone()[0]
    conn.close()
    return render_template("admin_dashboard.html",
                           daftar_siswa=daftar_siswa, total=total)


@app.route("/admin/siswa/tambah", methods=["GET", "POST"])
@login_required(role="admin")
def tambah_siswa():
    if request.method == "POST":
        nama = request.form.get("nama", "").strip()
        nis = request.form.get("nis", "").strip()
        kelas = request.form.get("kelas", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not all([nama, nis, kelas, username, password]):
            flash("Semua kolom wajib diisi.", "error")
        elif len(password) < 6:
            flash("Password minimal 6 karakter.", "error")
        else:
            conn = get_db()
            try:
                cur = conn.execute(
                    "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                    (username, generate_password_hash(password), "siswa"),
                )
                conn.execute(
                    "INSERT INTO siswa (user_id, nama, nis, kelas) VALUES (?, ?, ?, ?)",
                    (cur.lastrowid, nama, nis, kelas),
                )
                conn.commit()
                flash(f"Siswa {nama} berhasil ditambahkan.", "success")
                return redirect(url_for("admin_dashboard"))
            except sqlite3.IntegrityError:
                conn.rollback()
                flash("Username atau NIS sudah dipakai siswa lain.", "error")
            finally:
                conn.close()

    return render_template("tambah_siswa.html", form=request.form)


@app.route("/admin/siswa/<int:siswa_id>/hapus", methods=["POST"])
@login_required(role="admin")
def hapus_siswa(siswa_id):
    conn = get_db()
    siswa = conn.execute(
        "SELECT user_id, nama FROM siswa WHERE id = ?", (siswa_id,)
    ).fetchone()

    if siswa is None:
        flash("Data siswa tidak ditemukan.", "error")
    else:
        # Menghapus akun user otomatis menghapus data siswa dan transaksinya (CASCADE)
        conn.execute("DELETE FROM users WHERE id = ?", (siswa["user_id"],))
        conn.commit()
        flash(f"Siswa {siswa['nama']} beserta riwayat transaksinya telah dihapus.",
              "success")

    conn.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/siswa/<int:siswa_id>/transaksi", methods=["GET", "POST"])
@login_required(role="admin")
def transaksi_siswa(siswa_id):
    conn = get_db()
    siswa = conn.execute(
        "SELECT * FROM siswa WHERE id = ?", (siswa_id,)
    ).fetchone()

    if siswa is None:
        conn.close()
        flash("Data siswa tidak ditemukan.", "error")
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        jenis = request.form.get("jenis")
        try:
            jumlah = int(request.form.get("jumlah", ""))
        except ValueError:
            jumlah = 0

        if jenis not in ("setor", "tarik"):
            flash("Jenis transaksi tidak valid.", "error")
        elif jumlah <= 0:
            flash("Jumlah harus berupa angka lebih dari 0.", "error")
        elif jenis == "tarik" and jumlah > siswa["saldo"]:
            flash("Saldo tidak cukup untuk penarikan ini.", "error")
        else:
            if jenis == "setor":
                conn.execute("UPDATE siswa SET saldo = saldo + ? WHERE id = ?",
                             (jumlah, siswa_id))
            else:
                conn.execute("UPDATE siswa SET saldo = saldo - ? WHERE id = ?",
                             (jumlah, siswa_id))
            conn.execute(
                "INSERT INTO transaksi (siswa_id, jenis, jumlah) VALUES (?, ?, ?)",
                (siswa_id, jenis, jumlah),
            )
            conn.commit()
            conn.close()
            flash(f"{jenis.capitalize()} {format_rupiah(jumlah)} berhasil dicatat.",
                  "success")
            return redirect(url_for("transaksi_siswa", siswa_id=siswa_id))

    riwayat = conn.execute(
        "SELECT * FROM transaksi WHERE siswa_id = ? ORDER BY id DESC",
        (siswa_id,),
    ).fetchall()
    conn.close()
    return render_template("transaksi_siswa.html", siswa=siswa, riwayat=riwayat)


@app.route("/admin/riwayat")
@login_required(role="admin")
def riwayat_admin():
    conn = get_db()
    daftar = conn.execute("""
        SELECT transaksi.jenis, transaksi.jumlah, transaksi.waktu,
               siswa.nama, siswa.nis
        FROM transaksi
        JOIN siswa ON siswa.id = transaksi.siswa_id
        ORDER BY transaksi.id DESC
    """).fetchall()
    conn.close()
    return render_template("riwayat_admin.html", daftar=daftar)


# ---------------- SISWA ----------------

@app.route("/siswa", methods=["GET", "POST"])
@login_required(role="siswa")
def siswa_dashboard():
    conn = get_db()
    # Data diambil berdasarkan akun yang sedang login, jadi siswa
    # tidak bisa melihat data siswa lain.
    siswa = conn.execute(
        "SELECT * FROM siswa WHERE user_id = ?", (session["user_id"],)
    ).fetchone()

    if siswa is None:
        conn.close()
        session.clear()
        flash("Data siswa tidak ditemukan. Hubungi admin.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        try:
            jumlah = int(request.form.get("jumlah", ""))
        except ValueError:
            jumlah = 0

        if jumlah <= 0:
            flash("Jumlah setoran harus berupa angka lebih dari 0.", "error")
        else:
            conn.execute("UPDATE siswa SET saldo = saldo + ? WHERE id = ?",
                         (jumlah, siswa["id"]))
            conn.execute(
                "INSERT INTO transaksi (siswa_id, jenis, jumlah) VALUES (?, ?, ?)",
                (siswa["id"], "setor", jumlah),
            )
            conn.commit()
            conn.close()
            flash(f"Setoran {format_rupiah(jumlah)} berhasil dicatat.", "success")
            return redirect(url_for("siswa_dashboard"))

    riwayat = conn.execute(
        "SELECT * FROM transaksi WHERE siswa_id = ? ORDER BY id DESC",
        (siswa["id"],),
    ).fetchall()
    conn.close()
    return render_template("siswa_dashboard.html", siswa=siswa, riwayat=riwayat)


if __name__ == "__main__":
    app.run(debug=True)