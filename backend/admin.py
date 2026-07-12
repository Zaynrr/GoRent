import io, os, csv
import requests
from config import Config
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, send_file, make_response
from sqlalchemy import func, extract
from backend.model import db, User, Motor, Kategori, Transaksi, Voucher
from backend.helper import login_required, admin_required, allowed_file, upload_to_cloudinary, delete_from_cloudinary, extract_public_id_from_url, send_invoice_whatsapp
from werkzeug.security import generate_password_hash
from xhtml2pdf import pisa
import re

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Admin Dashboard 
@admin_bp.route('/dashboard')
@login_required
@admin_required
def admin_dashboard():
    today = datetime.now().date()
    
    total_motor = Motor.query.count()
    total_disewa = Motor.query.filter_by(status_motor='Disewa').count()
    jumlah_tersedia = Motor.query.filter_by(status_motor='Tersedia').count()
    
    total_transaksi = Transaksi.query.count()
    
    # Pendapatan harian
    pendapatan_harian = db.session.query(func.sum(Transaksi.total_harga)).filter(
        func.date(Transaksi.created_at) == today,
        Transaksi.status_pembayaran == 'success'
    ).scalar() or 0
    
    # Pendapatan Bulanan 
    pendapatan_bulanan = db.session.query(func.sum(Transaksi.total_harga)).filter(
        extract('month', Transaksi.created_at) == today.month,
        extract('year', Transaksi.created_at) == today.year,
        Transaksi.status_pembayaran == 'success'  
    ).scalar() or 0
    
    # Data untuk grafik 
    chart_labels = []
    chart_data = []

    for i in range(29, -1, -1):
        date = today - timedelta(days=i)
        chart_labels.append(date.strftime('%d %b'))
        
        daily_income = db.session.query(func.sum(Transaksi.total_harga)).filter(
            func.date(Transaksi.created_at) == date,
            Transaksi.status_pembayaran == 'success'  
        ).scalar() or 0
        
        chart_data.append(daily_income)
    
    return render_template(
        'admin/dashboardd.html',
        total_motors=total_motor,
        rented_count=total_disewa,
        available_count=jumlah_tersedia,
        total_transactions=total_transaksi,
        today_income=pendapatan_harian,
        month_income=pendapatan_bulanan,
        chart_labels=chart_labels,
        chart_data=chart_data
    )

# Dashboard chart data
@admin_bp.route('/dashboard/chart-data')
@login_required
@admin_required
def dashboard_chart_data():
    days = request.args.get('days', 30, type=int)
    today = datetime.now().date()
    
    labels = []
    values = []
    
    for i in range(days - 1, -1, -1):
        date = today - timedelta(days=i)
        labels.append(date.strftime('%d %b'))
        
        # Hitung transaksi yang success
        daily_income = db.session.query(func.sum(Transaksi.total_harga)).filter(
            func.date(Transaksi.created_at) == date,
            Transaksi.status_pembayaran == 'success'  
        ).scalar() or 0
        
        values.append(daily_income)
    
    return jsonify({
        'labels': labels,
        'values': values
    })
    
# Admin Motor
@admin_bp.route('/motors')
@login_required
@admin_required
def admin_motors():
    page = request.args.get('page', 1, type=int)
    per_page = 5  
    filter_type = request.args.get('filter', 'all')
    
    query = Motor.query.order_by(Motor.id_motor.desc())
    
    if filter_type == 'active':
        query = query.filter_by(is_active=True)
    elif filter_type == 'hidden':
        query = query.filter_by(is_active=False)
    elif filter_type == 'maintenance':
        query = query.filter_by(status_motor = 'maintenance')
    
    pagination = query.paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    
    motors = pagination.items
    kategori = Kategori.query.all()
    
    total_motor = Motor.query.count()
    jumlah_tersedia = Motor.query.filter_by(status_motor='Tersedia').count()
    jumlah_disewa = Motor.query.filter_by(status_motor='Disewa').count()
    jumlah_maintenance = Motor.query.filter_by(status_motor='Maintenance').count()
    
    jumlah_active = Motor.query.filter_by(is_active=True).count()
    jumlah_nonActive = Motor.query.filter_by(is_active=False).count()
    
    return render_template(
        'admin/motors.html', 
        motors=motors,
        kategori=kategori,
        pagination=pagination,
        filter_type=filter_type,
        total_motors=total_motor,
        available_count=jumlah_tersedia,
        rented_count=jumlah_disewa,
        maintenance_count=jumlah_maintenance,
        active_count=jumlah_active,
        hidden_count=jumlah_nonActive
    )

@admin_bp.route('/motor/add', methods=['POST'])
@login_required
@admin_required
def admin_motor_add():
    try:
        nama_motor_input = request.form.get('nama_motor')
       
        cek_motor = Motor.query.filter_by(nama_motor=nama_motor_input).first()
        
        if cek_motor:
            flash(f'Motor dengan nama "{nama_motor_input}" sudah ada!', 'warning')
            return redirect(url_for('admin.admin_motors'))
        
        foto_motor = None
        
        # Validasi dan upload gambar
        if 'gambar' in request.files:
            file = request.files.get('gambar')
            
            if file.filename != '':
                # Cek format file
                if not allowed_file(file.filename):
                    flash('Format file tidak didukung. Gunakan JPG, PNG, atau WebP', 'danger')
                    return redirect(url_for('admin.admin_motors'))
                
                # Cek ukuran foto
                file.seek(0, 2)
                file_size = file.tell()
                file.seek(0)
                
                if file_size > 5 * 1024 * 1024:
                    flash('Ukuran file terlalu besar. Maksimal 5MB', 'danger')
                    return redirect(url_for('admin.admin_motors'))
                
                # Upload ke Cloudinary
                upload_result = upload_to_cloudinary(file)
                
                if upload_result:
                    foto_motor = upload_result['url']
                else:
                    flash('Gagal upload gambar ke Cloudinary', 'danger')
                    return redirect(url_for('admin.admin_motors'))
        
        # Ambil id_kategori dari form
        id_kategori = request.form.get('id_kategori')
        if id_kategori == '':
            id_kategori = None
        else:
            id_kategori = int(id_kategori)
        
        motor_baru = Motor(
            nama_motor=request.form.get('nama_motor'),
            id_kategori=id_kategori,
            transmisi=request.form.get('transmisi'),
            cc_motor=int(request.form.get('cc_motor')),
            harga_sewa=int(request.form.get('harga_sewa')),
            status_motor=request.form.get('status_motor'),
            foto_motor=foto_motor,
            is_active=True
        )
        
        db.session.add(motor_baru)
        db.session.commit()
        
        flash(f'Motor "{motor_baru.nama_motor}" berhasil ditambahkan!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal menambahkan motor: {str(e)}', 'danger')
    
    return redirect(url_for('admin.admin_motors'))

@admin_bp.route('/motor/edit/<int:id>', methods=['POST'])
@login_required
@admin_required
def admin_motor_edit(id):
    motor = Motor.query.get_or_404(id)
    
    try:
        if motor.status_motor == 'Disewa':
            flash(f'Gagal: Motor "{motor.nama_motor}" sedang disewa, data tidak boleh diubah!', 'danger')
            return redirect(url_for('admin.admin_motors'))
        
        # Update data motor
        motor.nama_motor = request.form.get('nama_motor')
        
        id_kategori = request.form.get('id_kategori')
        motor.id_kategori = int(id_kategori) if id_kategori else None
        
        motor.transmisi = request.form.get('transmisi')
        motor.cc_motor = int(request.form.get('cc_motor'))
        motor.harga_sewa = int(request.form.get('harga_sewa'))
        motor.status_motor = request.form.get('status_motor')
        
        if 'gambar' in request.files:
            file = request.files['gambar']
            
            if file.filename != '':
                if not allowed_file(file.filename):
                    flash('Format file tidak didukung', 'danger')
                    return redirect(url_for('admin.admin_motors'))
                
                upload_result = upload_to_cloudinary(file)
                
                if upload_result:
                    if motor.foto_motor:
                        old_public_id = extract_public_id_from_url(motor.foto_motor)
                        if old_public_id:
                            delete_from_cloudinary(old_public_id)
                    
                    motor.foto_motor = upload_result['url']
        
        db.session.commit()
        flash(f'Motor "{motor.nama_motor}" berhasil diperbarui!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal memperbarui motor: {str(e)}', 'danger')
    
    return redirect(url_for('admin.admin_motors'))

@admin_bp.route('/motor/toggle-status', methods=['POST'])
@login_required
@admin_required
def admin_motor_toggle_status():
    id_motor = request.form.get('motor_id')
    action = request.form.get('action')
    
    motor = Motor.query.get_or_404(id_motor)
    
    try:
        if action == 'hide':
            motor.is_active = False
            flash(f'Motor "{motor.nama_motor}" disembunyikan dari katalog', 'success')
        elif action == 'show':
            motor.is_active = True
            flash(f'Motor "{motor.nama_motor}" ditampilkan di katalog', 'success')
        
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal mengubah status: {str(e)}', 'danger')
    
    return redirect(url_for('admin.admin_motors'))

@admin_bp.route('/motor/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def admin_motor_delete(id):
    motor = Motor.query.get_or_404(id)
    
    cek_motor = Transaksi.query.filter_by(id_motor=id).first()
    
    if cek_motor:
        flash(f'Motor "{motor.nama_motor}" tidak bisa dihapus karena memiliki riwayat transaksi/pernah disewa.', 'warning')
        return redirect(url_for('admin.admin_motors'))
    
    try:
        foto_url = motor.foto_motor
        nama_motor = motor.nama_motor
        
        # Hapus gambar
        if foto_url:
            try:
                public_id = extract_public_id_from_url(foto_url)
                # print(f"   Public ID: {public_id}")
                
                if public_id:
                    delete_result = delete_from_cloudinary(public_id)
                    # if delete_result:
                    #     print(f"✅ Foto berhasil dihapus dari Cloudinary")
                    # else:
                    #     print(f"⚠️ Gagal hapus foto dari Cloudinary")
                # else:
                #     print(f"⚠️ Tidak bisa extract public_id dari URL")
                    
            except Exception as cloudinary_error:
                print(f"⚠️ Error hapus dari Cloudinary: {str(cloudinary_error)}")
        
        # Hapus di database
        db.session.delete(motor)
        db.session.commit()
        
        flash(f'Motor "{nama_motor}" berhasil dihapus permanen', 'success')
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error delete motor: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f'Gagal menghapus motor: {str(e)}', 'danger')
    
    return redirect(url_for('admin.admin_motors'))

@admin_bp.route('/kategori/add', methods=['POST'])
@login_required
@admin_required
def admin_kategori_add():
    try:
        nama_kategori = request.form.get('nama_kategori', '').strip()
        
        cek_kategori = Kategori.query.filter(func.lower(Kategori.nama_kategori) == nama_kategori.lower()).first()
        
        # Validasi
        if not nama_kategori:
            flash('Nama kategori wajib diisi!', 'danger')
            return redirect(url_for('admin.admin_motors'))
        
        if cek_kategori:
            flash(f'Kategori "{nama_kategori}" sudah ada!', 'danger')
            return redirect(url_for('admin.admin_motors'))
        
        kategori_baru = Kategori(
            nama_kategori=nama_kategori
        )
        
        db.session.add(kategori_baru)
        db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Gagal menambah kategori: {str(e)}', 'danger')
        
    return redirect(url_for('admin.admin_motors'))

# Admin Transaksi
@admin_bp.route('/transaksi')
@login_required
@admin_required
def admin_transaksi():
    page = request.args.get('page', 1, type=int)
    per_page = 5
    filter_type = request.args.get('filter', 'all')
    voucher_filter = request.args.get('voucher', '').strip()
    
    # Query dengan joinedload untuk relasi voucher
    query = Transaksi.query.options(
        db.joinedload(Transaksi.voucher),
        db.joinedload(Transaksi.motor),
        db.joinedload(Transaksi.customer)
    ).order_by(Transaksi.id_transaksi.desc())
    
    if filter_type == 'success':
        query = query.filter(Transaksi.status_pembayaran == 'success')
    elif filter_type == 'pending':
        query = query.filter(Transaksi.status_pembayaran == 'pending')
    elif filter_type == 'cancelled':
        query = query.filter(Transaksi.status_pembayaran == 'cancelled')
    
    # Filter berdasarkan voucher
    if voucher_filter == 'with_voucher':
        query = query.filter(Transaksi.id_voucher != None)
    elif voucher_filter == 'without_voucher':
        query = query.filter(Transaksi.id_voucher == None)
    
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    transactions = pagination.items
    
    # Stats
    total_transactions = Transaksi.query.count()
    success_count = Transaksi.query.filter_by(status_pembayaran='success').count()
    pending_count = Transaksi.query.filter_by(status_pembayaran='pending').count()
    cancelled_count = Transaksi.query.filter_by(status_pembayaran='cancelled').count()
    rented_count = Motor.query.filter_by(status_motor='Disewa').count()
    
    # Stats voucher
    with_voucher_count = Transaksi.query.filter(Transaksi.id_voucher != None).count()
    without_voucher_count = total_transactions - with_voucher_count
    
    unverified_ktp_count = Transaksi.query.filter_by(status_verifikasi_ktp='Belum Diverifikasi').count()
    
    today_date = datetime.now().date()
    overdue_list = Transaksi.query.options(
        db.joinedload(Transaksi.motor)
    ).filter(
        Transaksi.status_rental == 'Disewa',
        Transaksi.tgl_kembali < today_date
    ).all()
    
    # Hitung total hari terlambat untuk setiap transaksi
    for overdue in overdue_list:
        tgl_k = overdue.tgl_kembali.date() if hasattr(overdue.tgl_kembali, 'date') else overdue.tgl_kembali
        overdue.days_overdue = (today_date - tgl_k).days
    
    overdue_count = len(overdue_list)
    
    return render_template(
        'admin/transaksi.html',
        transactions=transactions,
        pagination=pagination,
        filter_type=filter_type,
        voucher_filter=voucher_filter,
        total_transactions=total_transactions,
        success_count=success_count,
        pending_count=pending_count,
        cancelled_count=cancelled_count,
        rented_count=rented_count,
        with_voucher_count=with_voucher_count,
        without_voucher_count=without_voucher_count,
        unverified_ktp_count=unverified_ktp_count,
        overdue_count=overdue_count,
        overdue_list=overdue_list,
        today_date=today_date
    )

@admin_bp.route('/transaksi/update/<int:id>', methods=['POST'])
@login_required
@admin_required
def admin_transaction_update(id):
    try:
        data = request.get_json()
        field = data.get('field')
        value = data.get('value')
        
        transaksi = Transaksi.query.get_or_404(id)
        
        # Validasi field yang boleh diupdate
        allowed_status = ['kondisi_motor', 'denda_kerusakan', 'status_rental', 'status_verifikasi_ktp', 'status_pembayaran_denda']
        
        if field not in allowed_status:
            return jsonify({'success': False, 'error': 'Field tidak valid'}), 400
        
        if field == 'status_rental' and value == 'Dikembalikan':
            if transaksi.status_verifikasi_ktp != 'Verified':
                return jsonify({
                    'success': False, 
                    'error': 'KTP belum diverifikasi! Harap verifikasi KTP terlebih dahulu.'
                }), 400
        
        # Tidak bisa ubah kondisi & denda jika motor masih status disewa
        if field in ['kondisi_motor', 'denda_kerusakan', 'status_pembayaran_denda']:
            if transaksi.status_rental == 'Disewa':
                return jsonify({
                    'success': False, 
                    'error': 'Motor masih disewa! Ubah status rental menjadi "Dikembalikan" terlebih dahulu.'
                }), 400

        if field == 'denda_kerusakan':
            transaksi.denda_kerusakan = float(value) if value else 0
        else:
            setattr(transaksi, field, value)
        
        # Jika status rental berubah jadi Dikembalikan, update status motor
        if field == 'status_rental' and value == 'Dikembalikan':
            motor = Motor.query.get(transaksi.id_motor)
            if motor:
                motor.status_motor = 'Tersedia'
                
            # Hapus ktp dari Cloudinary
            if transaksi.KTP and transaksi.KTP != '-':
                try:
                    public_id = extract_public_id_from_url(transaksi.KTP)
                    if public_id:
                        delete_from_cloudinary(public_id)
                except Exception as e:
                    print(f"⚠️ Error hapus KTP saat dikembalikan: {str(e)}")
                
                transaksi.KTP = '-'
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Data berhasil diupdate'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error update transaction: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Export PDF
@admin_bp.route('/transaksi/export-pdf')
@login_required
@admin_required 
def export_transaksi_pdf():
    try:
        status_filter = request.args.get('status', 'all')
        days_filter = request.args.get('days', 'all')
        
        query = Transaksi.query.order_by(Transaksi.id_transaksi.desc())
        
        total_semua_transaksi = query.count()
        
        # Filter Rentang Waktu 
        if days_filter != 'all':
            try:
                days_int = int(days_filter)
                batas_waktu = datetime.now() - timedelta(days=days_int)
                query = query.filter(Transaksi.tgl_sewa >= batas_waktu)
            except ValueError:
                pass 
        
        # Filter Status / Kerusakan
        if status_filter == 'damage':
            # Hanya ambil yang kondisinya bukan 'Tidak Ada Kerusakan' dan bukan None
            query = query.filter(Transaksi.kondisi_motor != 'Tidak Ada Kerusakan', Transaksi.kondisi_motor.isnot(None))
        elif status_filter != 'all':
            query = query.filter_by(status_pembayaran=status_filter)
        
        
        # Convert ke list
        transactions_raw = query.all()
        today_date = datetime.now().date()
        
        # Hitung data 
        transactions = []
        for t in transactions_raw:
            nama_cust = t.nama_cust or (t.customer.nama if getattr(t, 'customer', None) else '-')
            email_cust = t.email_cust or (t.customer.email if getattr(t, 'customer', None) else '-')
            nama_motor = t.motor.nama_motor if getattr(t, 'motor', None) else '-'
            cc_motor = t.motor.cc_motor if getattr(t, 'motor', None) else '-'
            transmisi_motor = t.motor.transmisi if getattr(t, 'motor', None) else '-'
            
            is_overdue = False
            if t.status_rental == 'Disewa' and t.tgl_kembali:
                # Ambil tanggalnya saja jika memiliki atribut 'date'
                tgl_k = t.tgl_kembali.date() if hasattr(t.tgl_kembali, 'date') else t.tgl_kembali
                is_overdue = (tgl_k < today_date)
                
            order_id = t.order_id.replace('-', '- ') if t.order_id else '-'
            
            transactions.append({
                'order_id': order_id,
                'nama_cust': nama_cust,
                'email_cust': email_cust,
                'motor_name': nama_motor,
                'motor_cc': cc_motor,
                'motor_transmisi': transmisi_motor,
                'tgl_sewa': t.tgl_sewa.strftime('%d/%m/%Y') if t.tgl_sewa else '-',
                'tgl_kembali': t.tgl_kembali.strftime('%d/%m/%Y') if t.tgl_kembali else '-',
                'total_hari': t.total_hari or 0,
                'total_harga': t.total_harga or 0,
                'status_pembayaran': t.status_pembayaran,
                'status_rental': t.status_rental,
                'is_overdue': is_overdue,
                'kondisi_motor': getattr(t, 'kondisi_motor', 'Tidak Ada Kerusakan'),
                'detail_kerusakan': getattr(t, 'detail_kerusakan', '-'),
                'denda_kerusakan': getattr(t, 'denda_kerusakan', 0)
            })
        
        # Render HTML Content berdasarkan jenis filter
        if status_filter == 'damage':
            total_kerusakan = len(transactions)
            total_denda = sum(t['denda_kerusakan'] for t in transactions)
            
            html_content = render_template(
                'pdf/transaksi_report.html',
                report_type='damage', 
                transactions=transactions,
                total_transaksi=total_semua_transaksi,
                total_kerusakan=total_kerusakan,
                total_denda=total_denda,
                status_filter='Laporan Kerusakan Motor',
                days_filter=days_filter,
                current_time=datetime.now().strftime('%d %B %Y, %H:%M')
            )
        else:
            total_transaksi = len(transactions)
            total_pendapatan = sum(t['total_harga'] for t in transactions if t['status_pembayaran'] == 'success')
            total_pending = len([t for t in transactions if t['status_pembayaran'] == 'pending'])
            total_success = len([t for t in transactions if t['status_pembayaran'] == 'success'])
            
            html_content = render_template(
                'pdf/transaksi_report.html',
                report_type='normal', # Flag untuk template
                transactions=transactions,
                total_transaksi=total_transaksi,
                total_pendapatan=total_pendapatan,
                total_pending=total_pending,
                total_success=total_success,
                status_filter=status_filter,
                days_filter=days_filter, 
                current_time=datetime.now().strftime('%d %B %Y, %H:%M')
            )
        
        # Generate PDF
        prefix = "laporan_kerusakan_" if status_filter == 'damage' else "laporan_transaksi_"
        filename = f"{prefix}{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        # Buat buffer memori virtual untuk menyimpan PDF
        pdf_buffer = io.BytesIO()
        pisa_status = pisa.CreatePDF(html_content, dest=pdf_buffer, encoding='utf-8')
        
        # Convert HTML ke PDF dan simpan langsung ke dalam memori 
        # pisa_status = pisa.CreatePDF(
        #     html_content,
        #     dest=pdf_buffer,
        #     encoding='utf-8'
        # )
        
        if pisa_status.err:
            raise Exception(f"PDF generation error: {pisa_status.err}")
        
        # Kembalikan posisi "kursor baca" ke awal file (byte 0) agar bisa dibaca oleh Flask
        pdf_buffer.seek(0)
        
        # print(f"✅ PDF generated in memory: {filename}")
        
        # Kirim file langsung dari memori ke pengguna
        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        print(f"❌ Error export PDF: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f'Gagal export PDF: {str(e)}', 'danger')
        return redirect(url_for('admin.admin_transaksi'))
    
# Admin Kirim Reminder
@admin_bp.route('/transaksi/send-reminder/<int:id>', methods=['POST'])
@login_required
@admin_required
def send_reminder_whatsapp(id):
    try:
        transaksi = Transaksi.query.get_or_404(id)
        
        # Validasi status
        if transaksi.status_rental != 'Disewa':
            return jsonify({
                'success': False,
                'error': 'Motor sudah dikembalikan'
            }), 400
        
        # Ambil nomor HP
        hp_cust = transaksi.hp_cust
        if not hp_cust and transaksi.customer:
            hp_cust = transaksi.customer.no_hp
        
        if not hp_cust:
            return jsonify({
                'success': False,
                'error': 'Nomor HP tidak ditemukan'
            }), 400
        
        # Format nomor HP
        phone = ''.join(filter(str.isdigit, hp_cust))
        if phone.startswith('0'):
            phone = '62' + phone[1:]
        elif phone.startswith('8'):
            phone = '62' + phone
        
        # Format tanggal
        tgl_kembali = transaksi.tgl_kembali.date() if hasattr(transaksi.tgl_kembali, 'date') else transaksi.tgl_kembali
        today = datetime.now().date()
        
        # Cek apakah overdue
        is_overdue = tgl_kembali < today
        if is_overdue:
            days_overdue = (today - tgl_kembali).days
            deadline_text = f"*TERLAMBAT {days_overdue} HARI!*"
            urgency = "⚠️ *SEGERA KEMBALIKAN MOTOR ANDA!*"
        else:
            days_left = (tgl_kembali - today).days
            deadline_text = f"Sisa waktu: *{days_left} hari lagi*"
            urgency = "📌 *Pengingat Pengembalian Motor*"
        
        # Template pesan reminder
        message = f"""🏍️ *GORENT - PENGINGAT PENGEMBALIAN*

Halo *{transaksi.nama_cust}* 👋

{urgency}

━━━━━━━━━━━━━━━━━━━━
📋 *Detail Sewa Anda*
━━━━━━━━━━━━━━━━━━━━
📝 Order ID    : {transaksi.order_id}
🏍️ Motor       : {transaksi.motor.nama_motor}
📅 Batas Kembali: {tgl_kembali.strftime('%d/%m/%Y')}
{deadline_text}
━━━━━━━━━━━━━━━━━━━━

📍 *Mohon segera kembalikan motor sesuai jadwal.*

⚠️ Keterlambatan pengembalian akan dikenakan *denda tambahan*.

Jika ada kendala, silakan hubungi kami di 0812-3456-7890.

Terima kasih! 🙏"""
        
        # Kirim via Fonnte
        api_key = Config.FONNTE_API_KEY
        if not api_key:
            return jsonify({
                'success': False,
                'error': 'FONNTE_API_KEY belum diatur'
            }), 500
        
        url = "https://api.fonnte.com/send"
        payload = {
            'target': phone,
            'message': message
        }
        headers = {'Authorization': api_key}
        
        response = requests.post(url, data=payload, headers=headers)
        result = response.json()
        
        if result.get('status') == True or str(result.get('status')).lower() == 'true':
            return jsonify({
                'success': True,
                'message': f'Reminder berhasil dikirim ke {hp_cust}'
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('reason', 'Gagal kirim WA')
            }), 500
            
    except Exception as e:
        # print(f"Error send reminder: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
        
# Admin Kirim Reminder Tagihan Denda Kerusakan
@admin_bp.route('/transaksi/send-damage-reminder/<int:id>', methods=['POST'])
@login_required
@admin_required
def send_damage_reminder_whatsapp(id):
    try:
        transaksi = Transaksi.query.get_or_404(id)
        
        if not transaksi.denda_kerusakan or transaksi.denda_kerusakan <= 0:
            return jsonify({'success': False, 'error': 'Tidak ada tagihan denda kerusakan pada transaksi ini'}), 400
        
        hp_cust = transaksi.hp_cust
        if not hp_cust and transaksi.customer:
            hp_cust = transaksi.customer.no_hp
        
        if not hp_cust:
            return jsonify({'success': False, 'error': 'Nomor HP tidak ditemukan'}), 400
        
        phone = ''.join(filter(str.isdigit, hp_cust))
        if phone.startswith('0'): phone = '62' + phone[1:]
        elif phone.startswith('8'): phone = '62' + phone
            
        denda_format = f"Rp {transaksi.denda_kerusakan:,.0f}".replace(',', '.')
        kondisi = transaksi.kondisi_motor or 'Terdapat Kerusakan'
        
        message = f"""⚠️ *GORENT - TAGIHAN DENDA KERUSAKAN*

Halo *{transaksi.nama_cust}* 👋

Terkait penyewaan motor *{transaksi.motor.nama_motor}* (Order ID: {transaksi.order_id}) yang telah dikembalikan, kami mendapati adanya kerusakan dengan detail:

🔧 *Kondisi:* {kondisi}
💰 *Total Tagihan Denda:* {denda_format}

Mohon untuk segera melakukan pembayaran denda tersebut. 
📍 *KTP asli Anda masih kami simpan* dan dapat diambil kembali setelah seluruh tagihan diselesaikan.

Jika ada kendala atau ingin konfirmasi pembayaran, silakan balas pesan ini. Terima kasih. 🙏"""
        
        api_key = Config.FONNTE_API_KEY
        if not api_key:
            return jsonify({'success': False, 'error': 'FONNTE_API_KEY belum diatur'}), 500
        
        url = "https://api.fonnte.com/send"
        payload = {'target': phone, 'message': message}
        headers = {'Authorization': api_key}
        
        response = requests.post(url, data=payload, headers=headers)
        result = response.json()
        
        if result.get('status') == True or str(result.get('status')).lower() == 'true':
            return jsonify({'success': True, 'message': f'Tagihan denda berhasil dikirim ke {hp_cust}'})
        else:
            return jsonify({'success': False, 'error': result.get('reason', 'Gagal kirim WA')}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
        
# Admin Customers
@admin_bp.route('/customers')
@login_required
@admin_required
def admin_customers():
    page = request.args.get('page', 1, type=int)
    per_page = 5 
    tipe_filter = request.args.get('filter', 'all')
    
    user_customer = User.query.filter_by(role='customer')
    total_semua = user_customer.count()
    total_active = user_customer.filter_by(is_active=True).count()
    total_inactive = user_customer.filter_by(is_active=False).count()
    
    # Query untuk total_orders
    query = db.session.query(
        User,db.func.count(Transaksi.id_transaksi).label('total_orders')
    ).outerjoin(Transaksi, User.id == Transaksi.id_customer
    ).filter(User.role == 'customer'
    ).group_by(User.id)
    
    # filter
    if tipe_filter == 'active':
        query = query.filter(User.is_active == True)
    elif tipe_filter == 'inactive':
        query = query.filter(User.is_active == False)
    
    # Order dan paginate
    query = query.order_by(User.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Format data
    customer_list = []
    for user, total_orders in pagination.items:
        customer_data = {
            'id_user': user.id,
            'nama': user.nama,
            'email': user.email,
            'no_hp': user.no_hp,
            'is_active': user.is_active,
            'created_at': user.created_at if user.created_at else None,
            'total_orders': total_orders
        }
        customer_list.append(customer_data)
    
    # Ambil total order yang dilakukan oleh customer
    total_transaksi = db.session.query(Transaksi).join(
        User, Transaksi.id_customer == User.id
    ).filter(
        User.role == 'customer'
    ).count()
    
    return render_template(
        'admin/customers.html',
        customers=customer_list,
        pagination=pagination,
        filter_type=tipe_filter,
        total_transactions=total_transaksi,
        total_all=total_semua,
        total_active=total_active,
        total_inactive=total_inactive
    )

@admin_bp.route('/customers/toggle-status/<int:id>', methods=['POST'])
@login_required
@admin_required
def toggle_customer_status(id):
    try:
        data = request.get_json()
        is_active = data.get('is_active', True)
        
        customer = User.query.get_or_404(id)
        
        # Update status
        customer.is_active = is_active
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Account {"activated" if is_active else "deactivated"} successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error toggling customer status: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_bp.route('/customers/detail/<int:id>')
@login_required
@admin_required
def customer_detail(id):
    try:
        customer = User.query.get_or_404(id)
        
        # Hitung total orders
        total_orders = Transaksi.query.filter_by(id_customer=id).count()
        
        customer_data = {
            'id_user': customer.id,
            'nama': customer.nama,
            'email': customer.email,
            'no_hp': customer.no_hp,
            'is_active': customer.is_active,
            'created_at': customer.created_at if customer.created_at else None,
            'total_orders': total_orders
        }
        
        return jsonify({
            'success': True,
            'customer': customer_data
        })
        
    except Exception as e:
        # print(f"Error getting customer detail: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Admin Customer Export
@admin_bp.route('/customers/export')
@login_required
@admin_required
def export_customers():
    customers = User.query.filter_by(role='customer').order_by(User.id.desc()).all()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow(['ID', 'Name', 'Email', 'Phone', 'Status', 'Registered Date', 'Total Orders'])
    
    # Data
    for customer in customers:
        total_orders = Transaksi.query.filter_by(id_customer=customer.id).count()
        writer.writerow([
            customer.id,
            customer.nama,
            customer.email,
            customer.no_hp,
            'Active' if customer.is_active else 'Non-Active',
            customer.created_at if customer.created_at else '-',
            total_orders
        ])
    
    # response
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename=customers_{datetime.now().strftime("%Y%m%d")}.csv'
    response.headers['Content-type'] = 'text/csv'
    
    return response

# Admin voucher
@admin_bp.route('/vouchers')
@login_required
@admin_required
def admin_vouchers():
    page = request.args.get('page', 1, type=int)
    per_page = 5
    filter_type = request.args.get('filter', 'all')
    search_query = request.args.get('search', '').strip()
    
    waktu_skrng = datetime.now()

    total_vouchers = Voucher.query.count()
    
    # Aktif dalam periode, kuota belum habis
    total_aktif = Voucher.query.filter(
        Voucher.is_active == True,
        Voucher.tgl_mulai <= waktu_skrng,
        Voucher.tgl_selesai >= waktu_skrng,
        Voucher.total_pakai < Voucher.kuota
    ).count()
    
    # Non-Aktif
    total_nonaktif = Voucher.query.filter_by(is_active=False).count()
    
    # Expired
    total_expired = Voucher.query.filter(
        Voucher.is_active == True,
        Voucher.tgl_selesai < waktu_skrng
    ).count()
    
    # Belum Aktif
    total_belumAktif = Voucher.query.filter(
        Voucher.is_active == True,
        Voucher.tgl_mulai > waktu_skrng
    ).count()
    
    # Kuota Habis
    total_habis = Voucher.query.filter(
        Voucher.is_active == True,
        Voucher.total_pakai >= Voucher.kuota,
        Voucher.tgl_mulai <= waktu_skrng,
        Voucher.tgl_selesai >= waktu_skrng
    ).count()
    
    total_used = db.session.query(db.func.sum(Voucher.total_pakai)).scalar() or 0
    
    query = Voucher.query
    
    if filter_type == 'active':
        query = query.filter(
            Voucher.is_active == True,
            Voucher.tgl_mulai <= waktu_skrng,
            Voucher.tgl_selesai >= waktu_skrng,
            Voucher.total_pakai < Voucher.kuota
        )
    elif filter_type == 'inactive':
        query = query.filter_by(is_active=False)
    elif filter_type == 'expired':
        query = query.filter(
            Voucher.is_active == True,
            Voucher.tgl_selesai < waktu_skrng
        )
    elif filter_type == 'not_started':
        query = query.filter(
            Voucher.is_active == True,
            Voucher.tgl_mulai > waktu_skrng
        )
    elif filter_type == 'quota_full':
        query = query.filter(
            Voucher.is_active == True,
            Voucher.total_pakai >= Voucher.kuota,
            Voucher.tgl_mulai <= waktu_skrng,
            Voucher.tgl_selesai >= waktu_skrng
        )
    
    if search_query:
        query = query.filter(Voucher.kode_voucher.ilike(f'%{search_query}%'))

    query = query.order_by(Voucher.id.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template(
        'admin/vouchers.html',
        vouchers=pagination.items,
        pagination=pagination,
        filter_type=filter_type,
        search_query=search_query,
        total_vouchers=total_vouchers,
        total_aktif=total_aktif,
        total_nonaktif=total_nonaktif,
        total_expired=total_expired,
        total_belumAktif=total_belumAktif,
        total_habis=total_habis,
        total_used=total_used,
        waktu_skrng=waktu_skrng  
    )

@admin_bp.route('/voucher/add', methods=['POST'])
@login_required
@admin_required
def admin_voucher_add():
    try:
        tgl_mulai_str = request.form.get('tgl_mulai')
        tgl_selesai_str = request.form.get('tgl_selesai')
        
        kode = request.form.get('kode_voucher', '').upper().strip()
        tipe = request.form.get('tipe_diskon')
        nilai_diskon = int(request.form.get('nilai_diskon') or 0)
        min_belanja = int(request.form.get('min_belanja') or 0)
        max_diskon = int(request.form.get('max_diskon') or 0) or None
        tgl_mulai = datetime.strptime(tgl_mulai_str, '%Y-%m-%dT%H:%M')
        tgl_selesai = datetime.strptime(tgl_selesai_str, '%Y-%m-%dT%H:%M')
        kuota = int(request.form.get('kuota') or 100)
        
        cek_voucher = Voucher.query.filter(func.lower(Voucher.kode_voucher) == kode.lower()).first()
        
        # Validasi
        if not kode:
            flash('Kode voucher wajib diisi!', 'danger')
            return redirect(url_for('admin.admin_vouchers'))
        
        if cek_voucher:
            flash(f'Kode voucher "{kode}" sudah ada!', 'danger')
            return redirect(url_for('admin.admin_vouchers'))
        
        if tgl_selesai <= tgl_mulai:
            flash('Tanggal selesai harus setelah tanggal mulai!', 'danger')
            return redirect(url_for('admin.admin_vouchers'))
        
        voucher_baru = Voucher(
            kode_voucher=kode,
            tipe_diskon=tipe,
            nilai_diskon=nilai_diskon,
            min_belanja=min_belanja,
            max_diskon=max_diskon,
            tgl_mulai=tgl_mulai,
            tgl_selesai=tgl_selesai,
            kuota=kuota,
            total_pakai=0,
            is_active=True
        )
        
        db.session.add(voucher_baru)
        db.session.commit()
        
        flash(f'✅ Voucher "{kode}" berhasil ditambahkan!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Gagal menambah voucher: {str(e)}', 'danger')
    
    return redirect(url_for('admin.admin_vouchers'))

@admin_bp.route('/voucher/edit/<int:id>', methods=['POST'])
@login_required
@admin_required
def admin_voucher_edit(id):
    try:
        voucher = Voucher.query.get_or_404(id)
        
        tgl_mulai_str = request.form.get('tgl_mulai')
        tgl_selesai_str = request.form.get('tgl_selesai')
        
        kode = request.form.get('kode_voucher', '').upper().strip()
        tipe = request.form.get('tipe_diskon')
        nilai = int(request.form.get('nilai_diskon') or 0)
        min_belanja = int(request.form.get('min_belanja') or 0)
        max_diskon = int(request.form.get('max_diskon') or 0) or None
        tgl_mulai = datetime.strptime(tgl_mulai_str, '%Y-%m-%dT%H:%M')
        tgl_selesai = datetime.strptime(tgl_selesai_str, '%Y-%m-%dT%H:%M')
        kuota = int(request.form.get('kuota') or 100)
        
        # Cek duplikasi voucher 
        cek_voucher = Voucher.query.filter(
            func.lower(Voucher.kode_voucher) == kode.lower(),
            Voucher.id != id
        ).first()
        
        if cek_voucher:
            flash(f'Kode voucher "{kode}" sudah digunakan!', 'danger')
            return redirect(url_for('admin.admin_vouchers'))
        
        if tgl_selesai <= tgl_mulai:
            flash('Tanggal selesai harus setelah tanggal mulai!', 'danger')
            return redirect(url_for('admin.admin_vouchers'))
        
        voucher.kode_voucher = kode
        voucher.tipe_diskon = tipe
        voucher.nilai_diskon = nilai
        voucher.min_belanja = min_belanja
        voucher.max_diskon = max_diskon
        voucher.tgl_mulai = tgl_mulai
        voucher.tgl_selesai = tgl_selesai
        voucher.kuota = kuota
        
        db.session.commit()
        
        flash(f'✅ Voucher "{kode}" berhasil diupdate!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Gagal mengupdate voucher: {str(e)}', 'danger')
    
    return redirect(url_for('admin.admin_vouchers'))

@admin_bp.route('/voucher/toggle/<int:id>', methods=['POST'])
@login_required
@admin_required
def admin_voucher_toggle(id):
    try:
        voucher = Voucher.query.get_or_404(id)
        voucher.is_active = not voucher.is_active
        db.session.commit()
        
        status = 'diaktifkan' if voucher.is_active else 'dinonaktifkan'
        flash(f'✅ Voucher "{voucher.kode_voucher}" berhasil {status}!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Gagal: {str(e)}', 'danger')
    
    return redirect(url_for('admin.admin_vouchers'))

@admin_bp.route('/voucher/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def admin_voucher_delete(id):
    try:
        voucher = Voucher.query.get_or_404(id)
        
        # Cek apakah voucher pernah dipakai
        if voucher.total_pakai > 0:
            flash(f'❌ Voucher "{voucher.kode_voucher}" sudah digunakan {voucher.total_pakai} kali dan tidak bisa dihapus!', 'danger')
            return redirect(url_for('admin.admin_vouchers'))
        
        cekVoucher_transaksi = Transaksi.query.filter_by(id_voucher=voucher.id).first()
        
        if cekVoucher_transaksi:
            flash(f'❌ Voucher "{voucher.kode_voucher}" sudah tercatat di riwayat Transaksi pelanggan dan tidak boleh dihapus. Silakan gunakan fitur Non-Aktifkan.', 'danger')
            return redirect(url_for('admin.admin_vouchers'))
        
        kode = voucher.kode_voucher
        db.session.delete(voucher)
        db.session.commit()
        
        flash(f'✅ Voucher "{kode}" berhasil dihapus permanen!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Gagal menghapus voucher: {str(e)}', 'danger')
    
    return redirect(url_for('admin.admin_vouchers'))

@admin_bp.route('/voucher/detail/<int:id>')
@login_required
@admin_required
def admin_voucher_detail(id):
    try:
        voucher = Voucher.query.get_or_404(id)
        
        now = datetime.now()
        if now < voucher.tgl_mulai:
            status_text = '⏳ Belum Aktif'
            status_color = '#ff9800'
        elif now > voucher.tgl_selesai:
            status_text = '⏰ Expired'
            status_color = '#c62828'
        elif voucher.total_pakai >= voucher.kuota:
            status_text = '🚫 Kuota Habis'
            status_color = '#c62828'
        elif not voucher.is_active:
            status_text = '❌ Non-Aktif'
            status_color = '#757575'
        else:
            status_text = '✅ Aktif'
            status_color = '#00e676'
        
        return jsonify({
            'success': True,
            'voucher': {
                'kode': voucher.kode_voucher,
                'tipe': voucher.tipe_diskon,
                'nilai': voucher.nilai_diskon,
                'min_belanja': voucher.min_belanja,
                'max_diskon': voucher.max_diskon,
                'tgl_mulai': voucher.tgl_mulai.strftime('%d %b %Y %H:%M'),
                'tgl_selesai': voucher.tgl_selesai.strftime('%d %b %Y %H:%M'),
                'kuota': voucher.kuota,
                'total_pakai': voucher.total_pakai,
                'sisa_kuota': voucher.kuota - voucher.total_pakai,
                'is_active': voucher.is_active,
                'status_text': status_text,
                'status_color': status_color,
                'persentase_pakai': round((voucher.total_pakai / voucher.kuota) * 100, 1) if voucher.kuota > 0 else 0
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
@admin_bp.route('/voucher/reset/<int:id>', methods=['POST'])
@login_required
@admin_required
def admin_voucher_reset(id):
    voucher = Voucher.query.get_or_404(id)
    
    # Reset total penggunaan kembali menjadi 0
    voucher.total_pakai = 0
    db.session.commit()
    
    flash(f'Kuota penggunaan voucher {voucher.kode_voucher} berhasil direset menjadi 0.', 'success')

    # Redirect kembali ke halaman sebelumnya (mempertahankan filter/halaman)
    return redirect(request.referrer or url_for('admin.admin_vouchers'))