from dotenv import load_dotenv

# Load file .env 
load_dotenv()

def create_app():
    from backend import create_app as backend_create_app
    return backend_create_app()

app = create_app()

if __name__ == '__main__':
    app.run( debug=True)