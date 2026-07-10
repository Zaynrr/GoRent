from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

# ===== KATEGORI =====
class Kategori(db.Model):
    __tablename__ = 'kategori'

    id_kategori  = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nama_kategori = db.Column(db.String(50), nullable=False)

    # Relasi ke Motor
    motors = db.relationship('Motor', backref='kategori', lazy=True)

    def __repr__(self):
        return f'<Kategori {self.nama_kategori}>'


# ===== MOTOR =====
class Motor(db.Model):
    __tablename__ = 'motor'

    id_motor = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_kategori = db.Column(db.Integer, db.ForeignKey('kategori.id_kategori'), nullable=True)
    nama_motor = db.Column(db.String(100), nullable=False)
    transmisi = db.Column(db.Enum('Matic', 'Manual'), nullable=False)
    cc_motor = db.Column(db.Integer, nullable=False)
    harga_sewa = db.Column(db.Integer, nullable=False)
    status_motor = db.Column(db.Enum('Tersedia', 'Disewa', 'Maintenance', 'Dikembalikan'), nullable=True, default='Tersedia')
    foto_motor = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=True, default=True)
    version = db.Column(db.Integer, default=0, nullable=False)

    # Relasi ke Transaksi
    transaksi = db.relationship('Transaksi', backref='motor', lazy=True)

    def __repr__(self):
        return f'<Motor {self.nama_motor}>'

# ===== USERS =====
class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nama = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    no_hp = db.Column(db.String(20), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=True, default='customer')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, nullable=True, default=datetime.utcnow)
    reset_token = db.Column(db.String(255), nullable=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)

    # Relasi ke Transaksi
    transaksis = db.relationship('Transaksi', backref='customer', lazy=True)

    def __repr__(self):
        return f'<User {self.nama}>'

# ===== TRANSAKSI =====
class Transaksi(db.Model):
    __tablename__ = 'transaksi'

    id_transaksi = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_customer = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    id_motor = db.Column(db.Integer, db.ForeignKey('motor.id_motor'), nullable=False)
    order_id = db.Column(db.String(50), unique=True, nullable=False)
    id_voucher = db.Column(db.Integer, db.ForeignKey('voucher.id'), nullable=False)
    nama_cust = db.Column(db.String(100), nullable=True)
    hp_cust = db.Column(db.String(20), nullable=True)
    email_cust = db.Column(db.String(100), nullable=True)
    tgl_sewa = db.Column(db.Date, nullable=False)
    tgl_kembali = db.Column(db.Date, nullable=False)
    total_hari = db.Column(db.Integer, nullable=False)
    total_harga = db.Column(db.Integer, nullable=False)
    status_pembayaran = db.Column(db.String(50), nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    status_rental = db.Column(db.Enum('Disewa', 'Dikembalikan'), nullable=True, default='Tersedia')
    kondisi_motor = db.Column(db.Enum('Tidak Ada Kerusakan','Ada Kerusakan','Body Lecet/Pecah','Spion Rusak/Hilang','Lampu Pecah/Mati','Ban/Velg Bermasalah','Mesin Bermasalah'), nullable=True, default='Tidak Ada Kerusakan')
    denda_kerusakan = db.Column(db.Numeric(10, 2), nullable=True, default=0.00)
    status_verifikasi_ktp = db.Column(db.Enum('Belum Diverifikasi', 'Verified'), nullable=True, default='Belum Diverifikasi')
    KTP = db.Column(db.String(255), nullable=False)
    nominal_diskon = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, nullable=True, default=datetime.now())
    snap_token = db.Column(db.String(255), nullable=True)
    waktu_expired = db.Column(db.DateTime, nullable=True)
    voucher = db.relationship('Voucher', backref='transaksis', lazy=True)
    status_pembayaran_denda = db.Column(db.String(20), default='Tidak Ada Denda')

    def __repr__(self):
        return f'<Transaksi {self.order_id}>'
    
class Voucher(db.Model):
    __tablename__ = 'voucher'
    
    id = db.Column(db.Integer, primary_key=True)
    kode_voucher = db.Column(db.String(50), unique=True, nullable=False) # Misal: GORENT50
    tipe_diskon = db.Column(db.String(10), nullable=False) # 'percent' atau 'fixed'
    nilai_diskon = db.Column(db.Integer, nullable=False) # Misal: 50 (untuk 50% atau Rp 50.000)
    min_belanja = db.Column(db.Integer, default=0) # Minimal belanja
    max_diskon = db.Column(db.Integer, nullable=True) # Maksimal diskon (khusus percent)
    tgl_mulai = db.Column(db.DateTime, nullable=False)
    tgl_selesai = db.Column(db.DateTime, nullable=False)
    kuota = db.Column(db.Integer, default=100) # Kuota penggunaan
    total_pakai = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    
    def __repr__(self):
        return f'<Voucher {self.kode_voucher}>'