import os
from dotenv import load_dotenv

# Load file .env terlebih dahulu
load_dotenv()

def create_app():
    # Memanggil factory function dari dalam folder backend
    from backend import create_app as backend_create_app
    return backend_create_app()

# Vercel mencari variabel bernama "app" di tingkat paling atas (top-level)
app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)