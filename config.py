import os

class Config:
    # Kunci rahasia untuk session dan flash messages
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'kunci_rahasia_rental_motor'
    
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') 
    
    if not SQLALCHEMY_DATABASE_URI:
        raise ValueError("❌ DATABASE_URL belum diatur! Pastikan sudah diisi di file .env atau Vercel Environment Variables.")
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    FROM_EMAIL = 'GoRent@gorent.com>'
    RESEND_API_KEY= os.environ.get('RESEND_API_KEY')
    
    SERVER_KEY = os.environ.get('SERVER_KEY')
    
    FONNTE_API_KEY = os.environ.get('FONNTE_API_KEY')
    
    CLOUDINARY_CLOUD_NAME=os.environ.get('CLOUDINARY_CLOUD_NAME')
    
    CLOUDINARY_API_KEY=os.environ.get('CLOUDINARY_API_KEY')
    
    CLOUDINARY_API_SECRET=os.environ.get('CLOUDINARY_API_SECRET')   