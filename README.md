# Sistema de Gestión de Biblioteca (Flask + MongoDB Atlas)
**Demo:** https://sistema-de-gestion-de-biblioteca.onrender.com
**Stack:** Flask · MongoDB Atlas · Gunicorn · Render · Bootstrap 5
**Correr local**
conda activate ml_venv
pip install -r requirements.txt
export MONGODB_URI="mongodb+srv://<USER>:<PASS>@<CLUSTER>/?retryWrites=true&w=majority"; export FLASK_APP=app.py; flask run -p 5001
**Env vars**  MONGODB_URI=... · FLASK_SECRET_KEY=... · MONGODB_DB=biblioteca
**Deploy (Render)** Build: `pip install -r requirements.txt` · Start: `gunicorn app:app`
