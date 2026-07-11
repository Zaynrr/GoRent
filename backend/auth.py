from flask import Blueprint, app, render_template, request, flash, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import secrets
from backend.model import db, User
from backend.helper import send_reset_password_email

auth_bp = Blueprint('auth', __name__)

# Route untuk register
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nama = request.form.get('nama').strip()
        email = request.form.get('email').strip()
        no_hp = request.form.get('no_hp').strip()
        password = request.form.get('password').strip()
        
        # Cek apakah Email sudah terdaftar
        email_exist = User.query.filter_by(email=email).first()
        if email_exist:
            flash('Email sudah terdaftar! Silakan gunakan email lain atau langsung login.', 'danger')
            return redirect(url_for('auth.register'))
            
        # Cek apakah Username sudah terdaftar
        username_exist = User.query.filter_by(nama=nama).first()
        if username_exist:
            flash('Username sudah digunakan! Silakan pilih username yang lain.', 'danger')
            return redirect(url_for('auth.register'))
        
        try:
            password_hash = generate_password_hash(password)
        
            # Buat user baru
            user_baru = User(
                nama=nama, 
                email=email, 
                no_hp=no_hp, 
                password_hash=password_hash
            )
            
            db.session.add(user_baru)
            db.session.commit()
            
            flash('Akun berhasil dibuat! Silakan login.', 'success')
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            db.session.rollback()
            flash('Terjadi kesalahan sistem saat membuat akun. Silakan coba lagi.', 'danger')
            return redirect(url_for('auth.register'))
        
    return render_template('register.html')

# Route untuk login
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Mengambil input username dari form
        username = request.form.get('username')
        password = request.form.get('password')

        # Cari user berdasarkan username (kolom 'nama')
        user = User.query.filter_by(nama=username).first()
        
        # Validasi input kosong
        if not username or not password:
            flash('Username dan password harus diisi.', 'danger')
            return redirect(url_for('auth.login'))

        # Cek apakah user ada dan password cocok
        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                flash('Akun Anda telah dinonaktifkan. Hubungi admin untuk informasi lebih lanjut.', 'danger')
                return redirect(url_for('auth.login'))

            session['user_id'] = user.id
            session['user_role'] = user.role
            session['user_name'] = user.nama
            session['password_hash'] = user.password_hash
            flash(f'Selamat datang, {user.nama}!', 'success')
            
            if user.role == 'admin':
                return redirect(url_for('admin.admin_dashboard'))
            else:
                return redirect(url_for('customer.index'))
        else:
            flash('Username atau password salah.', 'danger')
            return redirect(url_for('auth.login'))
            
    return render_template('login.html')

# Forgot Password
@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        
        if not email:
            flash('Email wajib diisi', 'danger')
            return redirect(url_for('auth.forgot_password'))
        
        # Cari user by email
        user = User.query.filter_by(email=email).first()
        
        success_message = 'Jika email terdaftar di sistem kami, link reset password telah dikirim. Silakan cek inbox Anda.'
        
        if user:
            token = secrets.token_urlsafe(32)
            expiry = datetime.now() + timedelta(hours=1)  
            
            user.reset_token = token
            user.reset_token_expiry = expiry
            db.session.commit()
            
            # Kirim email reset
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            
            email_success, email_result = send_reset_password_email(user, reset_url)
        
        flash(success_message, 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('forgot-password.html')

# Reset password
@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    # Validasi token
    user = User.query.filter_by(reset_token=token).first()
    
    if not user:
        flash('Link reset password tidak valid atau sudah digunakan', 'danger')
        return redirect(url_for('auth.login'))
    
    # Cek expired
    if user.reset_token_expiry < datetime.now():
        flash('Link reset password sudah kedaluwarsa. Silakan request ulang', 'warning')
        user.reset_token = None
        user.reset_token_expiry = None
        db.session.commit()
        return redirect(url_for('auth.forgot_password'))
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not password or not confirm_password:
            flash('Password wajib diisi', 'danger')
            return render_template('reset-password.html', token=token, user=user)
        
        if password != confirm_password:
            flash('Password dan konfirmasi password tidak cocok', 'danger')
            return render_template('reset-password.html', token=token, user=user)
        
        if len(password) < 6:
            flash('Password minimal 6 karakter', 'danger')
            return render_template('reset-password.html', token=token, user=user)
        
        if check_password_hash(user.password_hash, password):
            flash('Password baru tidak boleh sama dengan password saat ini!', 'danger')
            return render_template('reset-password.html', token=token, user=user)
        
        # Update password
        user.password_hash = generate_password_hash(password)
        user.reset_token = None  
        user.reset_token_expiry = None
        db.session.commit()
        
        flash('Password berhasil direset! Silakan login dengan password baru', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('reset-password.html', token=token, user=user)

# Logout
@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('Anda telah berhasil keluar.', 'info')
    return redirect(url_for('auth.login'))