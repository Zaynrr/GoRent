from flask import Blueprint, app, app, request, jsonify, session
from backend.model import db, Motor, Transaksi, Voucher
from backend.helper import login_required, allowed_file, upload_ktp_to_cloudinary, delete_from_cloudinary, extract_public_id_from_url, send_invoice_email, send_invoice_whatsapp
import requests, base64, hashlib, random
from datetime import datetime
from config import Config

api_bp = Blueprint('api', __name__)

# Api Upload KTP BARU
@api_bp.route('/api/upload-ktp', methods=['POST'])
@login_required
def upload_ktp():
    try:
        # Cek apakah ada file yang diupload
        if 'ktp' not in request.files:
            return jsonify({
                'success': False,
                'error': 'Tidak ada file KTP yang diupload'
            }), 400
        
        file = request.files['ktp']
        
        # Cek file kosong
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'File KTP kosong'
            }), 400
        
        # Validasi format file
        if not allowed_file(file.filename):
            return jsonify({
                'success': False,
                'error': 'Format file tidak didukung. Gunakan JPG atau PNG'
            }), 400
        
        # Validasi ukuran (max 5MB)
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > 5 * 1024 * 1024:
            return jsonify({
                'success': False,
                'error': 'Ukuran file terlalu besar. Maksimal 5MB'
            }), 400
        
        if file_size < 10 * 1024:  # Min 10KB (pasti bukan file kosong/corrupt)
            return jsonify({
                'success': False,
                'error': 'File terlalu kecil, kemungkinan corrupt'
            }), 400
        
        # Upload ke Cloudinary
        upload_result = upload_ktp_to_cloudinary(file, session['user_id'])
        
        if not upload_result:
            return jsonify({
                'success': False,
                'error': 'Gagal upload KTP ke server'
            }), 500
        
        print(f"KTP user {session['user_id']} berhasil diupload")
        
        return jsonify({
            'success': True,
            'ktp_url': upload_result['url'],
            'public_id': upload_result['public_id']
        }), 200
        
    except Exception as e:
        print(f"Error upload KTP: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Terjadi kesalahan: {str(e)}'
        }), 500

# Api Payment Midtrans
@api_bp.route('/api/payment', methods=['POST'])
@login_required
def payment():
    try:
        data = request.json
        
        if not data:
            return jsonify({'error': 'Data tidak diterima'}), 400
        
        ktp_url = data.get('ktpUrl', '')
        if not ktp_url:
            return jsonify({'error': 'Foto KTP wajib diupload'}), 400
        
        motor = Motor.query.filter_by(nama_motor=data['motorName']).first()
        
        if not motor:
            return jsonify({'error': 'Motor tidak ditemukan'}), 404
        
        expected_version = motor.version
        
        if motor.status_motor != 'Tersedia':
            return jsonify({
                'error': 'Maaf, motor ini sudah dipesan customer lain.',
                'motor_status': motor.status_motor
            }), 409
        
        start_date = datetime.strptime(data['startDate'], '%Y-%m-%d')
        end_date = datetime.strptime(data['endDate'], '%Y-%m-%d')
        total_days = max((end_date - start_date).days, 1)
        base_price = total_days * data.get('motorPrice', 0)
        
        nama_cust = data.get('fullName', '')
        email_cust = data.get('email', '')
        hp_cust = data.get('phone', '')
        
        # VALIDASI VOUCHER (input dari user tetap pakai kode)
        kode_voucher_input = data.get('voucher_code', '').upper().strip() if data.get('voucher_code') else None
        nominal_diskon = 0
        final_price = base_price
        id_voucher = None  
        
        if kode_voucher_input:
            voucher = Voucher.query.filter_by(kode_voucher=kode_voucher_input, is_active=True).first()
            
            if voucher:
                now = datetime.now()
                if (voucher.tgl_mulai <= now <= voucher.tgl_selesai and 
                    voucher.total_pakai < voucher.kuota and 
                    base_price >= voucher.min_belanja):
                    
                    # Hitung diskon
                    if voucher.tipe_diskon == 'percent':
                        nominal_diskon = (voucher.nilai_diskon / 100) * base_price
                        if voucher.max_diskon and nominal_diskon > voucher.max_diskon:
                            nominal_diskon = voucher.max_diskon
                    else:
                        nominal_diskon = voucher.nilai_diskon
                        
                    if nominal_diskon > base_price:
                        nominal_diskon = base_price
                        
                    final_price = base_price - int(nominal_diskon)
                    
                    # Simpan ID voucher saja (TIDAK simpan kode)
                    id_voucher = voucher.id
                    
                    voucher.total_pakai += 1
                    print(f"✅ Voucher {voucher.kode_voucher} (ID: {voucher.id}) digunakan. Diskon: Rp {nominal_diskon:,}")
                else:
                    print(f"⚠️ Voucher {kode_voucher_input} tidak valid, bayar harga normal")
    
        order_id = f"ORDER-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(1000,9999)}"
        
        db.session.refresh(motor)
        
        if motor.version != expected_version:
            return jsonify({
                'error': 'Motor status berubah. Silakan refresh dan coba lagi.',
                'retry': True
            }), 409
        
        motor.version += 1
        motor.status_motor = 'Disewa'
        
        # Simpan transaksi dengan id_voucher & nominal_diskon 
        transaksi_baru = Transaksi(
            id_customer=session['user_id'],
            id_motor=motor.id_motor,
            id_voucher=id_voucher,  
            order_id=order_id,
            nama_cust=nama_cust,
            hp_cust=hp_cust,
            email_cust=email_cust,
            tgl_sewa=start_date.date(),
            tgl_kembali=end_date.date(),
            total_hari=total_days,
            total_harga=int(final_price),
            status_pembayaran='pending',
            payment_method='pending',
            status_rental='Disewa',
            kondisi_motor='Tidak Ada Kerusakan',
            denda_kerusakan=0.00,
            status_verifikasi_ktp='Belum Diverifikasi',
            KTP=ktp_url,
            nominal_diskon=int(nominal_diskon) 
        )
        
        db.session.add(transaksi_baru)
        db.session.commit()
        
        print(f"✅ Transaksi dibuat: {order_id}")
        print(f"💰 Base: Rp {base_price:,} | Diskon: Rp {nominal_diskon:,} | Final: Rp {final_price:,}")
        if id_voucher:
            print(f"🎟️ Voucher ID: {id_voucher}")
        
        # Call Midtrans API
        encoded_key = base64.b64encode(f"{Config.SERVER_KEY}:".encode()).decode()
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Basic {encoded_key}"
        }

        payload = {
            "transaction_details": {
                "order_id": order_id,
                "gross_amount": int(final_price)
            },
            "customer_details": {
                "first_name": nama_cust,
                "email": email_cust,
                "phone": hp_cust
            }
        }

        response = requests.post(
            "https://app.sandbox.midtrans.com/snap/v1/transactions",
            json=payload,
            headers=headers
        )

        if response.status_code != 201:
            motor.status_motor = 'Tersedia'
            motor.version -= 1
            if id_voucher:
                voucher.total_pakai -= 1
            db.session.delete(transaksi_baru)
            db.session.commit()
            
            return jsonify({
                'error': 'Gagal membuat transaksi Midtrans',
                'details': response.text
            }), 500

        midtrans_response = response.json()
        
        # Simpan snap_token ke database agar bisa dipanggil ulang
        transaksi_baru.snap_token = midtrans_response.get('token')
        db.session.commit()
        
        return jsonify({
            'success': True,
            'token': midtrans_response.get('token'),
            'redirect_url': midtrans_response.get('redirect_url'),
            'order_id': order_id,
            'total_price': int(final_price)
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Server Error: {str(e)}")
        return jsonify({'error': f'Terjadi kesalahan: {str(e)}'}), 500

# Midtrans Webhook
@api_bp.route('/midtrans/notification', methods=['POST'])
def midtrans_notification():
    try:
        data = request.get_json()
        
        id_order = data.get('order_id')
        status_transaksi = data.get('transaction_status')
        tipe_pembayaran = data.get('payment_type')
        fraud_status = data.get('fraud_status')
        status_code = data.get('status_code')
        gross_amount = data.get('gross_amount')
        signature_key = data.get('signature_key')
        
        cust_detail = data.get('customer_details', {})
        cust_email = cust_detail.get('email', '')
        
        expiry_time = data.get('expiry_time')
        
        # print("\n" + "="*80)
        # print("🔔 MIDTRANS NOTIFICATION RECEIVED!")
        # print(f"Order ID: {id_order}")
        # print(f"Status: {status_transaksi}")
        # print(f"Email: {cust_email}")
        # print("="*80 + "\n")
        
        # ===== VERIFIKASI SIGNATURE =====
        # expected_signature = hashlib.sha512(
        #     f"{id_order}{status_code}{gross_amount}{Config.SERVER_KEY}".encode()
        # ).hexdigest()
        
        # if expected_signature != signature_key:
        #     print("❌ INVALID SIGNATURE!")
        #     return jsonify({'status': 'error', 'message': 'Invalid signature'}), 403
        
        # print("✅ Signature valid!")
        
        transaksi = Transaksi.query.options(
            db.joinedload(Transaksi.voucher),  
            db.joinedload(Transaksi.motor),    
            db.joinedload(Transaksi.customer)  
        ).filter(
            (Transaksi.order_id == id_order)
        ).order_by(Transaksi.id_transaksi.desc()).first()
        
        if not transaksi:
            print(f"⚠️ Transaksi {id_order} TIDAK DITEMUKAN di database")
            return jsonify({
                'status': 'success',
                'message': 'Transaction not found in database, but acknowledged'
            }), 200

        # Skip jika sudah dibatalkan customer
        if transaksi.status_pembayaran == 'cancelled':
            print(f"⚠️ Transaksi {id_order} sudah dibatalkan customer, skip webhook")
            return jsonify({'status': 'success'}), 200
        
        # IDEMPOTENCY CHECK
        if status_transaksi in ['settlement', 'capture'] and transaksi.status_pembayaran == 'success':
            print(f"⚠️ Transaksi {id_order} sudah success, skip processing")
            return jsonify({'status': 'success'}), 200

        if expiry_time:
            try:
                # Potong zona waktu "+0700" atau "-0700" jika dikirim oleh Midtrans
                clean_expiry = expiry_time.split(' +')[0].split(' -')[0]
                transaksi.waktu_expired = datetime.strptime(clean_expiry, '%Y-%m-%d %H:%M:%S')
            except ValueError as ve:
                print(f"⚠️ Format string waktu expired tidak sesuai: {ve}")
        
        # Process berdasarkan status
        if status_transaksi == 'capture':
            if fraud_status == 'challenge':
                transaksi.status_pembayaran = 'pending'
            elif fraud_status == 'accept':
                transaksi.status_pembayaran = 'success'
                transaksi.status_rental = 'Disewa'
        elif status_transaksi == 'settlement':
            transaksi.status_pembayaran = 'success'
            transaksi.status_rental = 'Disewa'
        elif status_transaksi == 'pending':
            transaksi.status_pembayaran = 'pending'
        elif status_transaksi in ['deny', 'failure', 'expire', 'cancel']:
            transaksi.status_pembayaran = 'failed'
            transaksi.status_rental = 'Dikembalikan'
            
            # 1. Kembalikan status Motor ke 'Tersedia'
            motor = db.session.get(Motor, transaksi.id_motor)
            if motor:
                motor.status_motor = 'Tersedia'
                print(f"✅ Motor {motor.nama_motor} dikembalikan ke Tersedia")
                
            # 2. Reset / Kembalikan Kuota Voucher
            if transaksi.id_voucher:
                voucher = db.session.get(Voucher, transaksi.id_voucher)
                if voucher and voucher.total_pakai > 0:
                    voucher.total_pakai -= 1
                    print(f"🔄 Kuota voucher (ID: {voucher.id}) berhasil dikembalikan.")
            
            # 3. Hapus foto KTP dari Cloudinary & kosongkan dari Database
            if transaksi.KTP:
                print(f"🗑️ Menghapus KTP dari Cloudinary untuk Order ID: {id_order}")
                delete_from_cloudinary(transaksi.KTP)
                transaksi.KTP = '-' 
                transaksi.status_verifikasi_ktp = 'Belum Diverifikasi'
        elif status_transaksi == 'refund':
            transaksi.status_pembayaran = 'refunded'
            transaksi.status_rental = 'Dikembalikan'
            
            motor = db.session.get(Motor, transaksi.id_motor)
            if motor:
                motor.status_motor = 'Tersedia'
        
        transaksi.payment_method = tipe_pembayaran
        
        if transaksi.status_pembayaran == 'success':
            motor = db.session.get(Motor, transaksi.id_motor)
            if motor:
                motor.status_motor = 'Disewa'
        
        db.session.commit()
        
        # KIRIM INVOICE JIKA SUCCESS
        if transaksi.status_pembayaran == 'success':
            print(f"📧 Sending invoice for {id_order}")
            
            # Kirim Email
            if cust_email:
                email_success, email_result = send_invoice_email(transaksi, cust_email)
                print(f"📧 Email: {'✅' if email_success else '❌'} - {email_result}")
            else:
                print(f"⚠️ Email customer kosong, skip email invoice")
            
            # Ambil nomor HP
            cust_hp = transaksi.hp_cust
            if not cust_hp and transaksi.customer:
                cust_hp = transaksi.customer.no_hp
            
            # Kirim WhatsApp
            if cust_hp:
                wa_success, wa_result = send_invoice_whatsapp(transaksi, cust_hp)
                print(f"📱 WA: {'✅' if wa_success else '❌'} - {wa_result}")
            else:
                print(f"⚠️ HP customer kosong, skip WA invoice")
        
        print(f"✅ Transaksi {id_order} berhasil diupdate!")
        print(f"Status Pembayaran: {transaksi.status_pembayaran}")
        print(f"Payment Method: {transaksi.payment_method}")
        print("="*80 + "\n")
        
        return jsonify({'status': 'success'}), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'success',
            'message': 'Acknowledged but error occurred'
        }), 200

# Api Cancel Transaksi
@api_bp.route('/api/cancel-transaction/<order_id>', methods=['POST'])
@login_required
def cancel_transaction(order_id):
    try:
        transaksi = Transaksi.query.filter(
            (Transaksi.order_id == order_id)
        ).order_by(Transaksi.id_transaksi.desc()).first()
        
        if not transaksi:
            return jsonify({'success': False, 'error': 'Transaksi tidak ditemukan'}), 404
        
        if transaksi.id_customer != session['user_id']:
            return jsonify({'success': False, 'error': 'Akses ditolak'}), 403
        
        if transaksi.status_pembayaran != 'pending':
            return jsonify({
                'success': False, 
                'error': 'Transaksi tidak bisa dibatalkan'
            }), 400
        
        # KEMBALIKAN KUOTA VOUCHER (pakai id_voucher)
        voucher_info = None
        
        if transaksi.id_voucher:
            voucher = db.session.get(Voucher, transaksi.id_voucher)
            
            if voucher and voucher.total_pakai > 0:
                voucher.total_pakai -= 1
                
                voucher_info = {
                    'kode': voucher.kode_voucher,  
                    'id': voucher.id,
                    'sisa_kuota': voucher.kuota - voucher.total_pakai,
                    'total_pakai_baru': voucher.total_pakai
                }
                
                print(f"🎟️ Voucher dikembalikan: {voucher.kode_voucher} (ID: {voucher.id})")
        
        # HAPUS FOTO KTP
        if transaksi.KTP:
            try:
                public_id = extract_public_id_from_url(transaksi.KTP)
                if public_id:
                    delete_from_cloudinary(public_id)
                    print(f"✅ Foto KTP dihapus: {public_id}")
            except Exception as e:
                print(f"⚠️ Error hapus KTP: {str(e)}")
            
            transaksi.KTP = '-'
            transaksi.status_verifikasi_ktp = 'Belum Diverifikasi'
        
        # STATUS FINAL
        transaksi.status_pembayaran = 'cancelled'
        transaksi.status_rental = 'Dikembalikan'
        
        # KEMBALIKAN MOTOR
        motor = db.session.get(Motor, transaksi.id_motor)
        if motor:
            motor.status_motor = 'Tersedia'
        
        db.session.commit()
        
        # CANCEL DI MIDTRANS
        try:
            encoded_key = base64.b64encode(f"{Config.SERVER_KEY}:".encode()).decode()
            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "authorization": f"Basic {encoded_key}"
            }
            cancel_url = f"https://api.sandbox.midtrans.com/v2/{transaksi.order_id}/cancel"
            requests.post(cancel_url, headers=headers, timeout=10)
            print(f"✅ Cancelled di Midtrans: {transaksi.order_id}")
        except Exception as e:
            print(f"⚠️ Gagal cancel di Midtrans: {str(e)}")
        
        response_data = {
            'success': True,
            'message': 'Pesanan berhasil dibatalkan'
        }
        
        if voucher_info:
            response_data['voucher_returned'] = True
            response_data['voucher_message'] = f"Voucher {voucher_info['kode']} telah dikembalikan (sisa kuota: {voucher_info['sisa_kuota']})"
        
        return jsonify(response_data)
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error cancel: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Api cek ketersediaan motor
@api_bp.route('/api/check-motor-availability')
@login_required
def check_motor_availability():
    motor_name = request.args.get('motor', '')
    
    if not motor_name:
        return jsonify({
            'available': False,
            'reason': 'Nama motor tidak diberikan'
        })
    
    motor = Motor.query.filter_by(nama_motor=motor_name).first()
    
    if not motor:
        return jsonify({
            'available': False,
            'reason': 'Motor tidak ditemukan'
        })
    
    if motor.status_motor != 'Tersedia':
        return jsonify({
            'available': False,
            'reason': f'Motor ini sudah {motor.status_motor.lower()}. Silakan pilih motor lain.'
        })
    
    # CHECK APAKAH ADA TRANSAKSI PENDING UNTUK MOTOR INI
    transaksi_pending = Transaksi.query.filter_by(
        id_motor=motor.id_motor,
        status_pembayaran='pending',
        status_rental='Disewa'
    ).first()
    
    if transaksi_pending:
        return jsonify({
            'available': False,
            'reason': 'Motor sedang dalam proses pemesanan oleh customer lain. Silakan coba beberapa menit lagi.'
        })
    
    return jsonify({
        'available': True,
        'status': motor.status_motor
    })

@api_bp.route('/api/check-voucher', methods=['POST'])
@login_required
def check_voucher():
    try:
        data = request.json
        code = data.get('code', '').upper().strip()
        total_price = int(data.get('total_price', 0))
        
        if not code:
            return jsonify({'success': False, 'error': 'Kode voucher kosong'}), 400
        
        # Cari voucher by kode (input dari user)
        voucher = Voucher.query.filter_by(kode_voucher=code, is_active=True).first()
        
        if not voucher:
            return jsonify({'success': False, 'error': 'Kode voucher tidak valid'}), 404
            
        now = datetime.now()
        
        if now < voucher.tgl_mulai:
            return jsonify({'success': False, 'error': 'Voucher belum aktif'}), 400
        if now > voucher.tgl_selesai:
            return jsonify({'success': False, 'error': 'Voucher sudah kedaluwarsa'}), 400
        if voucher.total_pakai >= voucher.kuota:
            return jsonify({'success': False, 'error': 'Kuota voucher sudah habis'}), 400
        if total_price < voucher.min_belanja:
            return jsonify({
                'success': False, 
                'error': f'Minimal belanja Rp {voucher.min_belanja:,}'
            }), 400
            
        # Hitung diskon
        nominal_diskon = 0
        if voucher.tipe_diskon == 'percent':
            nominal_diskon = (voucher.nilai_diskon / 100) * total_price
            if voucher.max_diskon and nominal_diskon > voucher.max_diskon:
                nominal_diskon = voucher.max_diskon
        else:
            nominal_diskon = voucher.nilai_diskon
            
        if nominal_diskon > total_price:
            nominal_diskon = total_price
            
        final_price = total_price - int(nominal_diskon)
        
        return jsonify({
            'success': True,
            'discount_amount': int(nominal_diskon),
            'final_price': final_price,
            'message': f'Voucher {code} berhasil digunakan! Hemat Rp {int(nominal_diskon):,}'
        })
        
    except Exception as e:
        print(f"❌ Error check voucher: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500