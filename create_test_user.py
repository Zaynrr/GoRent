from app import app, db, User
from werkzeug.security import generate_password_hash

with app.app_context():
    # Buat user test
    user = User(
        nama='Test User',
        email='test@test.com',
        no_hp='08123456789',
        password_hash=generate_password_hash('123456'),
        role='customer'
    )
    db.session.add(user)
    db.session.commit()
    print('✅ User test dibuat!')
    print('Email: test@test.com')
    print('Password: 123456')