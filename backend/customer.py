from flask import Blueprint, render_template, request, session, flash, redirect, url_for
from backend.model import db, User, Motor, Kategori, Transaksi
from backend.helper import login_required

customer_bp = Blueprint('customer', __name__)

@customer_bp.route('/')
def index():
    return render_template('customers/index.html')

# Halaman daftar motor
@customer_bp.route('/motors')
def motors():
    # Ambil semua motor yang aktif dan tersedia, urutkan terbaru dulu
    list_motor = Motor.query.filter_by(is_active=True)\
                             .order_by(Motor.id_motor.desc())\
                             .all()
    kategori = Kategori.query.order_by(Kategori.nama_kategori).all()
    category = request.args.get('category') 
    return render_template('customers/motors.html',
                           motors=list_motor,
                           kategori=kategori,
                           current_category=category)
    
# Halaman Checkout
@customer_bp.route('/checkout')
@login_required
def checkout():
    return render_template('customers/checkout.html')

@customer_bp.route('/history')
@login_required
def history():
    transaksi = Transaksi.query.options(
        db.joinedload(Transaksi.voucher),
        db.joinedload(Transaksi.motor)
    ).filter_by(id_customer=session['user_id'])\
      .order_by(Transaksi.id_transaksi.desc())\
      .all()
    
    # Hitung total pengeluaran
    total_pengeluaran = 0
    for t in transaksi:
        if t.status_pembayaran == 'success':
            total_pengeluaran += t.total_harga
    
    # customer data
    for t in transaksi:
        t.customer = db.session.get(User, t.id_customer)
    
    return render_template('customers/riwayat-transaksi.html', 
                         transactions=transaksi,
                         total_spent=total_pengeluaran)
    
@customer_bp.route('/payment-success')
@login_required
def payment_success():
    order_id = request.args.get('order_id')
    
    if not order_id:
        flash('Order ID tidak ditemukan', 'danger')
        return redirect(url_for('index'))
    
    transaksi = Transaksi.query.filter_by(order_id=order_id).first()
    
    if not transaksi:
        flash('Transaksi tidak ditemukan', 'danger')
        return redirect(url_for('customer.index'))
    
    # hanya user yang bersangkutan yang bisa lihat
    if transaksi.id_customer != session['user_id']:
        flash('Akses ditolak', 'danger')
        return redirect(url_for('customer.index'))
    
    return render_template('customers/payment-success.html', transaksi=transaksi)