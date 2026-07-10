import requests
import cloudinary
import cloudinary.uploader
import resend
from datetime import datetime
from functools import wraps
from flask import session, flash, redirect, url_for
from config import Config
from backend.model import db, User

# Konfigurasi Cloudinary
cloudinary.config(
    cloud_name=Config.CLOUDINARY_CLOUD_NAME,
    api_key=Config.CLOUDINARY_API_KEY,
    api_secret=Config.CLOUDINARY_API_SECRET,
    secure=True
)

# ==========================================
# HELPER FUNCTIONS - CLOUDINARY
# ==========================================
def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS

def upload_to_cloudinary(file, request_form_nama_motor=None):
    try:
        public_id = f"motor_{request_form_nama_motor}" if request_form_nama_motor else None
        
        upload_result = cloudinary.uploader.upload(
            file,
            folder="gorent/motors",
            public_id=public_id,
            transformation=[
                {'width': 800, 'height': 600, 'crop': 'limit'},
                {'quality': 'auto'},
                {'fetch_format': 'auto'}
            ],
            resource_type="image"
        )
        
        return {
            'url': upload_result['secure_url'],
            'public_id': upload_result['public_id']
        }
    except Exception as e:
        print(f"Error upload Cloudinary: {str(e)}")
        return None

def upload_ktp_to_cloudinary(file, user_id):
    try:
        # Generate public_id unik dengan user_id dan timestamp
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        public_id = f"ktp_user{user_id}_{timestamp}"
        
        upload_result = cloudinary.uploader.upload(
            file,
            folder="gorent/ktp",  
            public_id=public_id,
            transformation=[
                {'width': 1200, 'crop': 'limit'},  
                {'quality': 'auto'},
                {'fetch_format': 'auto'}
            ],
            resource_type="image"
        )
        
        print(f"KTP berhasil diupload: {upload_result['secure_url']}")
        
        return {
            'url': upload_result['secure_url'],
            'public_id': upload_result['public_id']
        }
    except Exception as e:
        print(f"Error upload KTP ke Cloudinary: {str(e)}")
        return None

def delete_from_cloudinary(public_id):
    try:
        cloudinary.uploader.destroy(public_id)
        return True
    except Exception as e:
        print(f"Error delete Cloudinary: {str(e)}")
        return False


def extract_public_id_from_url(url):
    try:
        if not url or 'cloudinary.com' not in url:
            return None
        
        parts = url.split('/')
        upload_idx = parts.index('upload')
        public_id_parts = parts[upload_idx + 1:]
        
        public_id_parts = [p for p in public_id_parts if not (p.startswith('v') and p[1:].isdigit())]
        
        if '.' in public_id_parts[-1]:
            public_id_parts[-1] = public_id_parts[-1].rsplit('.', 1)[0]
        
        return '/'.join(public_id_parts)
    except Exception as e:
        print(f"Warning: Gagal extract public_id: {e}")
        return None

# Kirim WA Otomatis
def send_invoice_whatsapp(transaksi, hp_cust):
    api_key = Config.FONNTE_API_KEY
    
    if not api_key:
        print('[ERROR] FONNTE_API_KEY belum diatur di .env')
        return False, 'API key not configured'
    
    if not hp_cust:
        print('[ERROR] Nomor HP customer kosong')
        return False, 'Customer phone is empty'
    
    try:
        # AMBIL DATA DENGAN SAFE ACCESS
        tgl_sewa = transaksi.tgl_sewa.strftime('%d %B %Y') if transaksi.tgl_sewa else '-'
        tgl_kembali = transaksi.tgl_kembali.strftime('%d %B %Y') if transaksi.tgl_kembali else '-'
        total_harga = f"Rp {transaksi.total_harga:,.0f}".replace(',', '.')
        nama_motor = transaksi.motor.nama_motor if transaksi.motor else 'Motor'
        nama_cust = transaksi.nama_cust or 'Customer'
        
        # AMBIL KODE VOUCHER DARI RELASI (SAFE)
        kode_voucher = None
        if transaksi.voucher:
            kode_voucher = transaksi.voucher.kode_voucher
        
        nominal_diskon = transaksi.nominal_diskon or 0
        
        # PENGKONDISIAN YANG AMAN
        if nominal_diskon > 0:
            harga_asli = transaksi.total_harga + nominal_diskon
            
            if kode_voucher:
                # Voucher masih ada di database
                payment_section = f"""💰 *Pembayaran:*
• Subtotal: Rp {harga_asli:,.0f}
• Voucher: {kode_voucher} (- Rp {nominal_diskon:,.0f})
• *Total: {total_harga}*"""
            else:
                # Voucher sudah dihapus admin, tapi diskon masih tercatat
                payment_section = f"""💰 *Pembayaran:*
• Subtotal: Rp {harga_asli:,.0f}
• Diskon Promo: - Rp {nominal_diskon:,.0f}
• *Total: {total_harga}*"""
        else:
            payment_section = f"""💰 *Pembayaran:*
• *Total: {total_harga}*"""

        message = f"""🏍️ *INVOICE - GORENT*

Halo *{nama_cust}* 👋
Terima kasih sudah sewa motor! ✅

📋 *Detail Pesanan:*
• Order ID: {transaksi.order_id}
• Motor: {nama_motor}
• Sewa: {tgl_sewa}
• Kembali: {tgl_kembali}
• Durasi: {transaksi.total_hari} hari

{payment_section}

📍 *Pengambilan:*
Tunjukkan Order ID & bawa KTP asli

Selamat berkendara! 🏍️"""
        
        url = "https://api.fonnte.com/send"
        
        # FORMAT NOMOR HP
        phone = ''.join(filter(str.isdigit, hp_cust))
        if phone.startswith('0'):
            phone = '62' + phone[1:]
        elif phone.startswith('8'):
            phone = '62' + phone
        elif not phone.startswith('62'):
            phone = '62' + phone
        
        payload = {
            'target': phone,
            'message': message,
            'countryCode': '62'
        }
        
        headers = {
            'Authorization': api_key
        }
        
        response = requests.post(url, data=payload, headers=headers, timeout=10)
        result = response.json()
        
        print(f"Fonnte Response: {result}")
        
        if result.get('status') == True or str(result.get('status')).lower() == 'true':
            print(f"✅ WhatsApp sent to: {phone}")
            return True, result.get('id') or result.get('reason')
        else:
            reason = result.get('reason', 'Unknown error')
            print(f"❌ Failed to send WhatsApp: {reason}")
            return False, reason
            
    except Exception as e:
        print(f"❌ WhatsApp error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False, str(e)
    
# Kirim Email Otomatis
def send_invoice_email(transaksi, cust_email):
    api_key = Config.RESEND_API_KEY
    
    if not api_key:
        print('[ERROR] RESEND_API_KEY belum diatur. Email tidak dikirim.')
        return False, 'API key not configured'
    
    if not cust_email:
        print('[ERROR] Email customer kosong')
        return False, 'Customer email is empty'
    
    try:
        resend.api_key = api_key
        
        # AMBIL DATA DENGAN SAFE ACCESS
        nama_cust = transaksi.nama_cust or 'Customer'
        nama_motor = transaksi.motor.nama_motor if transaksi.motor else 'Motor'
        tgl_sewa = transaksi.tgl_sewa.strftime('%d %B %Y') if transaksi.tgl_sewa else '-'
        tgl_kembali = transaksi.tgl_kembali.strftime('%d %B %Y') if transaksi.tgl_kembali else '-'
        total_hari = transaksi.total_hari or 0
        
        # AMBIL KODE VOUCHER DARI RELASI (SAFE)
        kode_voucher = None
        if transaksi.voucher:
            kode_voucher = transaksi.voucher.kode_voucher
        
        nominal_diskon = transaksi.nominal_diskon or 0
        harga_final = transaksi.total_harga
        harga_asli = harga_final + nominal_diskon
        
        # TAMPILAN VOUCHER YANG FLEKSIBEL
        if nominal_diskon > 0:
            if kode_voucher:
                # Voucher masih ada di database
                voucher_display = f'<span style="background: #fff3e0; color: #ef6c00; padding: 4px 10px; border-radius: 12px; font-weight: 700;">🎟️ {kode_voucher}</span>'
            else:
                # Voucher sudah dihapus admin
                voucher_display = '<span style="background: #ffebee; color: #c62828; padding: 4px 10px; border-radius: 12px; font-weight: 700; font-size: 12px;">🗑️ Voucher Dihapus</span>'
            
            diskon_display = f'<span style="color: #00e676; font-weight: 700;">- Rp {nominal_diskon:,.0f}</span>'
        else:
            voucher_display = '<span style="color: #757575;">-</span>'
            diskon_display = '<span style="color: #757575;">-</span>'
        
        subtotal = "text-decoration: line-through; color: #a0a0a0;" if nominal_diskon > 0 else "color: #1a1a1a;"
        
        subtotal_row = f"""
        <tr>
            <td style="padding: 8px 0; color: #757575; font-size: 14px;">Subtotal</td>
            <td style="padding: 8px 0; font-weight: 600; text-align: right; {subtotal}">Rp {harga_asli:,.0f}</td>
        </tr>"""
        
        # Send email via Resend
        params = {
            "from": "GoRent <onboarding@resend.dev>",
            "to": [cust_email],
            "subject": f"✅ Invoice Pembayaran - {transaksi.order_id}",
            "html": f"""
            <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9fafb;">
                <!-- Header -->
                <div style="background: linear-gradient(135deg, #ff5722 0%, #ff9800 100%); padding: 30px; border-radius: 12px 12px 0 0; text-align: center; color: white;">
                    <h1 style="margin: 0; font-size: 28px; font-weight: 800;">🏍️ GoRent</h1>
                    <p style="margin: 8px 0 0 0; opacity: 0.9;">Invoice Pembayaran</p>
                </div>
                
                <!-- Content -->
                <div style="background: white; padding: 30px; border: 1px solid #e5e7eb;">
                    <p style="font-size: 16px; color: #1a1a1a;">Halo <strong>{nama_cust}</strong>,</p>
                    <p style="color: #4a4a4a;">Terima kasih telah melakukan pembayaran. Berikut detail invoice Anda:</p>
                    
                    <!-- Order ID Badge -->
                    <div style="text-align: center; margin: 20px 0;">
                        <div style="display: inline-block; background: #fff3e0; border: 2px dashed #ff5722; padding: 12px 24px; border-radius: 8px;">
                            <div style="font-size: 11px; color: #757575; text-transform: uppercase; letter-spacing: 1px;">Order ID</div>
                            <div style="font-size: 18px; font-weight: 800; color: #ff5722; font-family: 'Courier New', monospace; margin-top: 4px;">{transaksi.order_id}</div>
                        </div>
                    </div>
                    
                    <!-- Detail Pemesanan -->
                    <div style="background-color: #f9f9f9; padding: 20px; margin: 20px 0; border-radius: 8px; border: 1px solid #e5e5e5;">
                        <h3 style="margin: 0 0 16px 0; color: #1a1a1a; font-size: 16px;">📋 Detail Pemesanan</h3>
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 8px 0; color: #757575; font-size: 14px;">Motor</td>
                                <td style="padding: 8px 0; color: #1a1a1a; font-weight: 600; text-align: right;">{nama_motor}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #757575; font-size: 14px;">Tanggal Sewa</td>
                                <td style="padding: 8px 0; color: #1a1a1a; font-weight: 600; text-align: right;">{tgl_sewa}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #757575; font-size: 14px;">Tanggal Kembali</td>
                                <td style="padding: 8px 0; color: #1a1a1a; font-weight: 600; text-align: right;">{tgl_kembali}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #757575; font-size: 14px;">Durasi</td>
                                <td style="padding: 8px 0; color: #1a1a1a; font-weight: 600; text-align: right;">{total_hari} hari</td>
                            </tr>
                        </table>
                    </div>
                    
                    <!-- Detail Pembayaran -->
                    <div style="background-color: #f9f9f9; padding: 20px; margin: 20px 0; border-radius: 8px; border: 1px solid #e5e5e5;">
                        <h3 style="margin: 0 0 16px 0; color: #1a1a1a; font-size: 16px;">💰 Detail Pembayaran</h3>
                        <table style="width: 100%; border-collapse: collapse;">
                            {subtotal_row}
                            <tr>
                                <td style="padding: 8px 0; color: #757575; font-size: 14px;">Voucher</td>
                                <td style="padding: 8px 0; text-align: right;">{voucher_display}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #757575; font-size: 14px;">Diskon</td>
                                <td style="padding: 8px 0; text-align: right;">{diskon_display}</td>
                            </tr>
                            <tr>
                                <td colspan="2" style="padding: 12px 0 0 0; border-top: 2px dashed #e5e5e5;"></td>
                            </tr>
                            <tr>
                                <td style="padding: 12px 0 0 0; color: #1a1a1a; font-size: 16px; font-weight: 700;">TOTAL BAYAR</td>
                                <td style="padding: 12px 0 0 0; color: #ff5722; font-size: 24px; font-weight: 800; text-align: right;">Rp {harga_final:,.0f}</td>
                            </tr>
                        </table>
                    </div>
                    
                    <!-- Info Pengambilan -->
                    <div style="background: #e3f2fd; padding: 16px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #1976d2;">
                        <h4 style="margin: 0 0 8px 0; color: #1565c0; font-size: 14px;">📍 Pengambilan Motor</h4>
                        <ul style="margin: 0; padding-left: 20px; color: #1565c0; font-size: 14px;">
                            <li>Tunjukkan <strong>Order ID</strong> di atas saat pengambilan motor</li>
                            <li>Bawa <strong>KTP asli</strong> yang digunakan saat pemesanan</li>
                        </ul>
                    </div>
                    
                    <!-- Footer -->
                    <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e5e5;">
                        <p style="color: #6b7280; font-size: 13px; margin: 0;">
                            <strong>GoRent</strong> - Sewa Motor Premium Terpercaya<br>
                            Hubungi: 0812-3456-7890
                        </p>
                    </div>
                </div>
                
                <!-- Bottom Bar -->
                <div style="background: #2c2c2e; padding: 16px; border-radius: 0 0 12px 12px; text-align: center;">
                    <p style="color: #a0a0a0; font-size: 12px; margin: 0;">
                        © 2026 GoRent. All rights reserved.
                    </p>
                </div>
            </div>
            """
        }
        
        # Kirim email
        email = resend.Emails.send(params)
        
        print(f"✅ Email sent via Resend: {email.get('id')}")
        return True, email.get('id')
        
    except resend.exceptions.ResendError as e:
        print(f"❌ Resend API Error: {str(e)}")
        return False, str(e)
    except Exception as e:
        print(f"❌ Failed to send email: {str(e)}")
        import traceback
        traceback.print_exc()
        return False, str(e)

# Kirim email reset password
def send_reset_password_email(user, reset_url):
    api_key = Config.RESEND_API_KEY
    
    if not api_key:
        print('[ERROR] RESEND_API_KEY belum diatur')
        return False, 'API key not configured'
    
    try:
        resend.api_key = api_key
        
        params = {
            "from": "GoRent <onboarding@resend.dev>",
            "to": [user.email],
            "subject": "🔐 Reset Password - GoRent",
            "html": f"""
            <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9fafb;">
                <!-- Header -->
                <div style="background: linear-gradient(135deg, #ff5722 0%, #ff9800 100%); padding: 30px; border-radius: 12px 12px 0 0; text-align: center; color: white;">
                    <h1 style="margin: 0; font-size: 28px; font-weight: 800;">🏍️ GoRent</h1>
                    <p style="margin: 8px 0 0 0; opacity: 0.9;">Reset Password</p>
                </div>
                
                <!-- Content -->
                <div style="background: white; padding: 30px; border: 1px solid #e5e7eb;">
                    <p style="font-size: 16px; color: #1a1a1a;">Halo <strong>{user.nama}</strong>,</p>
                    <p style="color: #4a4a4a;">Kami menerima permintaan untuk mereset password akun Anda. Klik tombol di bawah untuk membuat password baru:</p>
                    
                    <!-- Reset Button -->
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{reset_url}" style="display: inline-block; background: linear-gradient(135deg, #ff5722 0%, #ff9800 100%); color: white; padding: 14px 32px; border-radius: 10px; text-decoration: none; font-weight: 700; font-size: 16px; box-shadow: 0 4px 12px rgba(255, 87, 34, 0.3);">
                            🔑 Reset Password
                        </a>
                    </div>
                    
                    <!-- Alternative Link -->
                    <div style="background: #f5f5f5; padding: 16px; border-radius: 8px; margin: 20px 0;">
                        <p style="margin: 0 0 8px 0; font-size: 13px; color: #757575;">Jika tombol tidak berfungsi, copy link ini ke browser:</p>
                        <p style="margin: 0; font-size: 12px; color: #1976d2; word-break: break-all; font-family: 'Courier New', monospace;">
                            {reset_url}
                        </p>
                    </div>
                    
                    <!-- Warning -->
                    <div style="background: #fff3e0; padding: 16px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #ef6c00;">
                        <p style="margin: 0; color: #ef6c00; font-size: 13px; line-height: 1.6;">
                            ⏰ <strong>Perhatian:</strong> Link ini hanya berlaku selama <strong>1 jam</strong>. 
                            Jika Anda tidak meminta reset password, abaikan email ini.
                        </p>
                    </div>
                    
                    <!-- Footer -->
                    <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e5e5;">
                        <p style="color: #6b7280; font-size: 13px; margin: 0;">
                            Butuh bantuan? Hubungi kami di 0812-3456-7890
                        </p>
                    </div>
                </div>
                
                <!-- Bottom Bar -->
                <div style="background: #2c2c2e; padding: 16px; border-radius: 0 0 12px 12px; text-align: center;">
                    <p style="color: #a0a0a0; font-size: 12px; margin: 0;">
                        © 2026 GoRent. All rights reserved.
                    </p>
                </div>
            </div>
            """
        }
        
        email = resend.Emails.send(params)
        print(f"✅ Reset password email sent: {email.get('id')}")
        return True, email.get('id')
        
    except resend.exceptions.ResendError as e:
        print(f"❌ Resend API Error: {str(e)}")
        return False, str(e)
    except Exception as e:
        print(f"❌ Failed to send reset email: {str(e)}")
        return False, str(e)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Silakan login terlebih dahulu.', 'warning')
            return redirect(url_for('auth.login'))
        
        user = db.session.get(User, session['user_id'])
        
        # Untuk mmengatasi akun non aktif
        if user and not user.is_active:
            session.clear() # Hapus semua session (Otomatis Logout)
            flash('Sesi Anda telah berakhir karena akun dinonaktifkan oleh Admin.', 'danger')
            return redirect(url_for('auth.login'))
        
        # Untuk mengatasi jika password diubah, maka sesi lama akan berakhir
        if session.get('password_hash') != user.password_hash:
            session.clear() # Paksa logout
            flash('Sesi berakhir. Password akun ini telah diubah, silakan login kembali dengan password baru.', 'warning')
            return redirect(url_for('auth.login'))
        
        return f(*args, **kwargs)
    return decorated_function

def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_role' not in session or session['user_role'] not in allowed_roles:
                flash('Anda tidak memiliki izin untuk mengakses halaman ini.', 'danger')
                return redirect(url_for('customer.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Cek apakah sudah login
        if 'user_id' not in session:
            flash('Silakan login terlebih dahulu', 'danger')
            return redirect(url_for('auth.login'))
        
        # 2. Cek apakah role-nya admin
        if session.get('user_role') != 'admin':
            flash('Akses ditolak! Halaman ini khusus admin.', 'danger')
            return redirect(url_for('customer.index'))
        return f(*args, **kwargs)
    return decorated_function

