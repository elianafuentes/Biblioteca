from flask import Flask, render_template, request, redirect, url_for, flash
import pymongo
from pymongo import MongoClient
from bson.objectid import ObjectId
import datetime
import os
import certifi

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_secret_key")  # Necesario para usar flash messages

# Clase BibliotecaApp adaptada para Flask
class BibliotecaApp:
    def __init__(self):
        uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
        db_name = os.getenv("MONGODB_DB", "biblioteca")

        mongo_kwargs = {"serverSelectionTimeoutMS": 8000}
        if "mongodb.net" in uri or uri.startswith("mongodb+srv://"):
            mongo_kwargs.update({"tls": True, "tlsCAFile": certifi.where()})

        try:
            self.client = MongoClient(uri, **mongo_kwargs)
            self.client.admin.command("ping")
            self.db = self.client[db_name]
            print(f"Conexión a MongoDB ({'Atlas' if 'mongodb.net' in uri else 'Local'}) OK. BD: {db_name}")
            self.setup_database()
        except pymongo.errors.ServerSelectionTimeoutError as e:
            print("Error: No se pudo conectar a MongoDB (timeout). Revisa MONGODB_URI/IP/credenciales.")
            print(f"Detalle: {e}")
            raise
        except Exception as e:
            print(f"Error de conexión: {e}")
            raise
  
    def setup_database(self):
        """Configura la base de datos con las colecciones necesarias"""
        # Lista de colecciones a crear
        colecciones = ['autores', 'libros', 'ediciones', 'copias', 'usuarios', 'prestamos']
        
        # Crear colecciones si no existen
        colecciones_existentes = self.db.list_collection_names()
        for col in colecciones:
            if col not in colecciones_existentes:
                self.db.create_collection(col)
                print(f"Colección '{col}' creada.")
        
        # Crear índices para optimizar consultas
        self.db.autores.create_index([("nombre", pymongo.ASCENDING)])
        self.db.libros.create_index([("titulo", pymongo.ASCENDING)])
        self.db.ediciones.create_index([("ISBN", pymongo.ASCENDING)])
        self.db.usuarios.create_index([("RUT", pymongo.ASCENDING)])

# Inicializar la aplicación de biblioteca
biblioteca = BibliotecaApp()

# Rutas
@app.route('/')
def index():
    """Página principal"""
    return render_template('index.html')

# pagina autor

@app.route("/about")
def about():
    info = {
        "app": "Sistema de Gestión de Biblioteca",
        "autor": "Eliana Fuentes",
        "stack": ["Flask", "MongoDB Atlas", "Gunicorn", "Render"],
        "features": ["CRUD", "Préstamos/Devoluciones", "Agregaciones", "Validaciones"],
        "repo": "https://github.com/elianafuentes/Biblioteca",
        "demo": "https://sistema-de-gestion-de-biblioteca.onrender.com"
    }
    return render_template("about.html", info=info)


# =================== GESTIÓN DE AUTORES ===================
@app.route('/autores')
def listar_autores():
    """Listar todos los autores"""
    autores = list(biblioteca.db.autores.find())
    return render_template('autores/listar.html', autores=autores)

@app.route('/autores/agregar', methods=['GET', 'POST'])
def agregar_autor():
    """Agregar un nuevo autor"""
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        
        if nombre.strip():
            autor_id = biblioteca.db.autores.insert_one({"nombre": nombre}).inserted_id
            flash(f"Autor agregado correctamente con ID: {autor_id}", "success")
            return redirect(url_for('listar_autores'))
        else:
            flash("El nombre del autor no puede estar vacío.", "danger")
    
    return render_template('autores/agregar.html')

@app.route('/autores/editar/<autor_id>', methods=['GET', 'POST'])
def editar_autor(autor_id):
    """Editar un autor existente"""
    autor = biblioteca.db.autores.find_one({"_id": ObjectId(autor_id)})
    
    if not autor:
        flash("No se encontró el autor.", "danger")
        return redirect(url_for('listar_autores'))
    
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        
        if nombre.strip():
            biblioteca.db.autores.update_one(
                {"_id": ObjectId(autor_id)},
                {"$set": {"nombre": nombre}}
            )
            flash("Autor actualizado correctamente.", "success")
            return redirect(url_for('listar_autores'))
        else:
            flash("El nombre del autor no puede estar vacío.", "danger")
    
    return render_template('autores/editar.html', autor=autor)

@app.route('/autores/eliminar/<autor_id>', methods=['GET', 'POST'])
def eliminar_autor(autor_id):
    """Eliminar un autor"""
    autor = biblioteca.db.autores.find_one({"_id": ObjectId(autor_id)})
    
    if not autor:
        flash("No se encontró el autor.", "danger")
        return redirect(url_for('listar_autores'))
    
    if request.method == 'POST':
        # Verificar si el autor está asociado a algún libro
        libros_asociados = biblioteca.db.libros.count_documents({
            "autores.autor_id": ObjectId(autor_id)
        })
        
        if libros_asociados > 0:
            flash(f"No se puede eliminar. El autor está asociado a {libros_asociados} libros.", "danger")
        else:
            biblioteca.db.autores.delete_one({"_id": ObjectId(autor_id)})
            flash("Autor eliminado correctamente.", "success")
        
        return redirect(url_for('listar_autores'))
    
    return render_template('autores/eliminar.html', autor=autor)

# =================== GESTIÓN DE LIBROS ===================
@app.route('/libros')
def listar_libros():
    """Listar todos los libros"""
    libros = list(biblioteca.db.libros.find())
    return render_template('libros/listar.html', libros=libros, biblioteca=biblioteca)

@app.route('/libros/agregar', methods=['GET', 'POST'])
def agregar_libro():
    """Agregar un nuevo libro"""
    autores = list(biblioteca.db.autores.find())

    if not autores:
        flash("No hay autores registrados. Primero debe agregar autores.", "warning")
        return redirect(url_for('agregar_autor'))

    if request.method == 'POST':
        titulo = (request.form.get('titulo') or '').strip()
        autores_ids = request.form.getlist('autores')

        anio_publicacion_raw = (request.form.get('anio_publicacion') or '').strip()
        genero = (request.form.get('genero') or '').strip()

        # Validaciones básicas
        if not titulo:
            flash("El título del libro no puede estar vacío.", "danger")
            return render_template('libros/agregar.html', autores=autores)

        if not autores_ids:
            flash("Debe seleccionar al menos un autor.", "danger")
            return render_template('libros/agregar.html', autores=autores)

        # Validar año
        if not anio_publicacion_raw.isdigit():
            flash("El año de publicación debe ser un número.", "danger")
            return render_template('libros/agregar.html', autores=autores)

        anio_publicacion = int(anio_publicacion_raw)
        from datetime import datetime
        current_year = datetime.now().year
        if anio_publicacion < 1450 or anio_publicacion > current_year + 1:
            flash(f"El año de publicación debe estar entre 1450 y {current_year + 1}.", "danger")
            return render_template('libros/agregar.html', autores=autores)

        if not genero:
            flash("El género no puede estar vacío.", "danger")
            return render_template('libros/agregar.html', autores=autores)

        # Preparar autores
        autores_seleccionados = []
        for autor_id in autores_ids:
            autor = biblioteca.db.autores.find_one({"_id": ObjectId(autor_id)})
            if autor:
                autores_seleccionados.append({
                    "autor_id": autor['_id'],
                    "nombre": autor['nombre']
                })

        # Insertar libro
        libro_data = {
            "titulo": titulo,
            "autores": autores_seleccionados,
            "anio_publicacion": anio_publicacion,
            "genero": genero
        }

        libro_id = biblioteca.db.libros.insert_one(libro_data).inserted_id
        flash(f"Libro agregado correctamente con ID: {libro_id}", "success")
        return redirect(url_for('listar_libros'))

    return render_template('libros/agregar.html', autores=autores)

@app.route('/libros/editar/<libro_id>', methods=['GET', 'POST'])
def editar_libro(libro_id):
    """Editar un libro existente"""
    libro = biblioteca.db.libros.find_one({"_id": ObjectId(libro_id)})
    autores = list(biblioteca.db.autores.find())

    if not libro:
        flash("No se encontró el libro.", "danger")
        return redirect(url_for('listar_libros'))

    # Obtener IDs de autores actuales del libro
    autores_actuales = [str(autor['autor_id']) for autor in libro.get('autores', [])]

    if request.method == 'POST':
        titulo = (request.form.get('titulo') or '').strip()
        autores_ids = request.form.getlist('autores')

        anio_publicacion_raw = (request.form.get('anio_publicacion') or '').strip()
        genero = (request.form.get('genero') or '').strip()

        if not titulo:
            flash("El título del libro no puede estar vacío.", "danger")
            return render_template('libros/editar.html', libro=libro, autores=autores, autores_actuales=autores_actuales, biblioteca=biblioteca)

        updates = {"titulo": titulo}

        # Validar y actualizar año/género
        if anio_publicacion_raw:
            if not anio_publicacion_raw.isdigit():
                flash("El año de publicación debe ser un número.", "danger")
                return render_template('libros/editar.html', libro=libro, autores=autores, autores_actuales=autores_actuales, biblioteca=biblioteca)
            anio_publicacion = int(anio_publicacion_raw)
            from datetime import datetime
            current_year = datetime.now().year
            if anio_publicacion < 1450 or anio_publicacion > current_year + 1:
                flash(f"El año de publicación debe estar entre 1450 y {current_year + 1}.", "danger")
                return render_template('libros/editar.html', libro=libro, autores=autores, autores_actuales=autores_actuales, biblioteca=biblioteca)
            updates["anio_publicacion"] = anio_publicacion
        else:
            # Si viene vacío, permite quitarlo si quieres:
            updates["anio_publicacion"] = None

        if genero:
            updates["genero"] = genero
        else:
            updates["genero"] = None

        # Actualizar autores si se seleccionaron
        if autores_ids:
            autores_seleccionados = []
            for autor_id in autores_ids:
                autor = biblioteca.db.autores.find_one({"_id": ObjectId(autor_id)})
                if autor:
                    autores_seleccionados.append({
                        "autor_id": autor['_id'],
                        "nombre": autor['nombre']
                    })
            updates["autores"] = autores_seleccionados

        biblioteca.db.libros.update_one(
            {"_id": ObjectId(libro_id)},
            {"$set": updates}
        )

        flash("Libro actualizado correctamente.", "success")
        return redirect(url_for('listar_libros'))

    return render_template('libros/editar.html', libro=libro, autores=autores, autores_actuales=autores_actuales, biblioteca=biblioteca)

@app.route('/libros/eliminar/<libro_id>', methods=['GET', 'POST'])
def eliminar_libro(libro_id):
    """Eliminar un libro"""
    libro = biblioteca.db.libros.find_one({"_id": ObjectId(libro_id)})
    
    if not libro:
        flash("No se encontró el libro.", "danger")
        return redirect(url_for('listar_libros'))
    
    if request.method == 'POST':
        # Verificar si el libro tiene ediciones asociadas
        ediciones = biblioteca.db.ediciones.count_documents({"libro_id": ObjectId(libro_id)})
        
        if ediciones > 0:
            flash(f"No se puede eliminar. El libro tiene {ediciones} ediciones asociadas.", "danger")
        else:
            biblioteca.db.libros.delete_one({"_id": ObjectId(libro_id)})
            flash("Libro eliminado correctamente.", "success")
        
        return redirect(url_for('listar_libros'))
    
    return render_template('libros/eliminar.html', libro=libro, biblioteca=biblioteca)

# =================== GESTIÓN DE EDICIONES ===================
from bson.objectid import ObjectId
from flask import render_template, request, redirect, url_for, flash

@app.route('/ediciones')
def listar_ediciones():
    """Listar todas las ediciones"""
    pipeline = [
        {"$lookup": {
            "from": "libros",
            "localField": "libro_id",
            "foreignField": "_id",
            "as": "libro_info"
        }},
        {"$unwind": {"path": "$libro_info", "preserveNullAndEmptyArrays": True}}
    ]
    ediciones = list(biblioteca.db.ediciones.aggregate(pipeline))
    return render_template('ediciones/listar.html', ediciones=ediciones)


@app.route('/ediciones/agregar', methods=['GET', 'POST'])
def agregar_edicion():
    """Agregar una nueva edición"""
    libros = list(biblioteca.db.libros.find())

    if not libros:
        flash("No hay libros registrados. Primero debe agregar libros.", "warning")
        return redirect(url_for('agregar_libro'))

    if request.method == 'POST':
        isbn = (request.form.get('isbn') or '').strip()
        anio_raw = (request.form.get('anio') or '').strip()
        idioma = (request.form.get('idioma') or '').strip()
        libro_id = request.form.get('libro_id')

        editorial = (request.form.get('editorial') or '').strip()
        formato = (request.form.get('formato') or '').strip()   # tapa_dura | tapa_blanda | ebook | audiolibro
        paginas_raw = (request.form.get('paginas') or '').strip()

        # Validaciones de obligatorios
        if any(not v for v in [isbn, anio_raw, idioma, libro_id, editorial, formato, paginas_raw]):
            flash("Todos los campos son obligatorios.", "danger")
            return render_template('ediciones/agregar.html', libros=libros)

        # ISBN único
        if biblioteca.db.ediciones.find_one({"ISBN": isbn}):
            flash(f"Ya existe una edición con el ISBN {isbn}.", "danger")
            return render_template('ediciones/agregar.html', libros=libros)

        # Año
        try:
            anio = int(anio_raw)
        except ValueError:
            flash("El año debe ser un número.", "danger")
            return render_template('ediciones/agregar.html', libros=libros)

        from datetime import datetime
        current_year = datetime.now().year
        if anio < 1450 or anio > current_year + 1:
            flash(f"El año debe estar entre 1450 y {current_year + 1}.", "danger")
            return render_template('ediciones/agregar.html', libros=libros)

        # Páginas
        try:
            paginas = int(paginas_raw)
            if paginas <= 0:
                raise ValueError
        except ValueError:
            flash("Páginas debe ser un entero positivo.", "danger")
            return render_template('ediciones/agregar.html', libros=libros)

        # Formato
        formatos_validos = {"tapa_dura", "tapa_blanda", "ebook", "audiolibro"}
        if formato not in formatos_validos:
            flash("Formato inválido.", "danger")
            return render_template('ediciones/agregar.html', libros=libros)

        edicion_data = {
            "ISBN": isbn,
            "anio": anio,
            "idioma": idioma,
            "libro_id": ObjectId(libro_id),
            "editorial": editorial,
            "formato": formato,
            "paginas": paginas
        }

        edicion_id = biblioteca.db.ediciones.insert_one(edicion_data).inserted_id
        flash(f"Edición agregada correctamente con ID: {edicion_id}", "success")
        return redirect(url_for('listar_ediciones'))

    return render_template('ediciones/agregar.html', libros=libros)


@app.route('/ediciones/editar/<edicion_id>', methods=['GET', 'POST'])
def editar_edicion(edicion_id):
    """Editar una edición existente"""
    pipeline = [
        {"$match": {"_id": ObjectId(edicion_id)}},
        {"$lookup": {
            "from": "libros",
            "localField": "libro_id",
            "foreignField": "_id",
            "as": "libro_info"
        }},
        {"$unwind": {"path": "$libro_info", "preserveNullAndEmptyArrays": True}}
    ]
    resultado = list(biblioteca.db.ediciones.aggregate(pipeline))

    if not resultado:
        flash("No se encontró la edición.", "danger")
        return redirect(url_for('listar_ediciones'))

    edicion = resultado[0]
    libros = list(biblioteca.db.libros.find())

    if request.method == 'POST':
        isbn = (request.form.get('isbn') or '').strip()
        anio_raw = (request.form.get('anio') or '').strip()
        idioma = (request.form.get('idioma') or '').strip()
        libro_id = request.form.get('libro_id')

        editorial = (request.form.get('editorial') or '').strip()
        formato = (request.form.get('formato') or '').strip()
        paginas_raw = (request.form.get('paginas') or '').strip()

        if any(not v for v in [isbn, anio_raw, idioma, libro_id, editorial, formato, paginas_raw]):
            flash("Todos los campos son obligatorios.", "danger")
            return render_template('ediciones/editar.html', edicion=edicion, libros=libros)

        # Mantener ISBN único (excluyendo la edición actual)
        existing_isbn = biblioteca.db.ediciones.find_one({
            "ISBN": isbn,
            "_id": {"$ne": ObjectId(edicion_id)}
        })
        if existing_isbn:
            flash(f"Ya existe otra edición con el ISBN {isbn}.", "danger")
            return render_template('ediciones/editar.html', edicion=edicion, libros=libros)

        # Año
        try:
            anio = int(anio_raw)
        except ValueError:
            flash("El año debe ser un número.", "danger")
            return render_template('ediciones/editar.html', edicion=edicion, libros=libros)

        from datetime import datetime
        current_year = datetime.now().year
        if anio < 1450 or anio > current_year + 1:
            flash(f"El año debe estar entre 1450 y {current_year + 1}.", "danger")
            return render_template('ediciones/editar.html', edicion=edicion, libros=libros)

        # Páginas
        try:
            paginas = int(paginas_raw)
            if paginas <= 0:
                raise ValueError
        except ValueError:
            flash("Páginas debe ser un entero positivo.", "danger")
            return render_template('ediciones/editar.html', edicion=edicion, libros=libros)

        # Formato
        formatos_validos = {"tapa_dura", "tapa_blanda", "ebook", "audiolibro"}
        if formato not in formatos_validos:
            flash("Formato inválido.", "danger")
            return render_template('ediciones/editar.html', edicion=edicion, libros=libros)

        biblioteca.db.ediciones.update_one(
            {"_id": ObjectId(edicion_id)},
            {"$set": {
                "ISBN": isbn,
                "anio": anio,
                "idioma": idioma,
                "libro_id": ObjectId(libro_id),
                "editorial": editorial,
                "formato": formato,
                "paginas": paginas
            }}
        )

        flash("Edición actualizada correctamente.", "success")
        return redirect(url_for('listar_ediciones'))

    return render_template('ediciones/editar.html', edicion=edicion, libros=libros)


@app.route('/ediciones/eliminar/<edicion_id>', methods=['GET', 'POST'])
def eliminar_edicion(edicion_id):
    """Eliminar una edición"""
    pipeline = [
        {"$match": {"_id": ObjectId(edicion_id)}},
        {"$lookup": {
            "from": "libros",
            "localField": "libro_id",
            "foreignField": "_id",
            "as": "libro_info"
        }},
        {"$unwind": {"path": "$libro_info", "preserveNullAndEmptyArrays": True}}
    ]
    resultado = list(biblioteca.db.ediciones.aggregate(pipeline))
    if not resultado:
        flash("No se encontró la edición.", "danger")
        return redirect(url_for('listar_ediciones'))

    edicion = resultado[0]

    if request.method == 'POST':
        copias = biblioteca.db.copias.count_documents({"edicion_id": ObjectId(edicion_id)})
        if copias > 0:
            flash(f"No se puede eliminar. La edición tiene {copias} copias asociadas.", "danger")
            return redirect(url_for('listar_ediciones'))

        biblioteca.db.ediciones.delete_one({"_id": ObjectId(edicion_id)})
        flash("Edición eliminada correctamente.", "success")
        return redirect(url_for('listar_ediciones'))

    return render_template('ediciones/eliminar.html', edicion=edicion)


# =================== GESTIÓN DE COPIAS ===================
@app.route('/copias')
def listar_copias():
    """Listar todas las copias"""
    pipeline = [
        {
            "$lookup": {
                "from": "ediciones",
                "localField": "edicion_id",
                "foreignField": "_id",
                "as": "edicion_info"
            }
        },
        {
            "$unwind": {
                "path": "$edicion_info",
                "preserveNullAndEmptyArrays": True
            }
        },
        {
            "$lookup": {
                "from": "libros",
                "localField": "edicion_info.libro_id",
                "foreignField": "_id",
                "as": "libro_info"
            }
        },
        {
            "$unwind": {
                "path": "$libro_info",
                "preserveNullAndEmptyArrays": True
            }
        }
    ]
    
    copias = list(biblioteca.db.copias.aggregate(pipeline))
    return render_template('copias/listar.html', copias=copias)

@app.route('/copias/agregar', methods=['GET', 'POST'])
def agregar_copia():
    """Agregar una nueva copia"""
    # Obtener ediciones con información del libro
    pipeline = [
        {
            "$lookup": {
                "from": "libros",
                "localField": "libro_id",
                "foreignField": "_id",
                "as": "libro_info"
            }
        },
        {
            "$unwind": {
                "path": "$libro_info",
                "preserveNullAndEmptyArrays": True
            }
        }
    ]
    
    ediciones = list(biblioteca.db.ediciones.aggregate(pipeline))
    
    if not ediciones:
        flash("No hay ediciones registradas. Primero debe agregar ediciones.", "warning")
        return redirect(url_for('agregar_edicion'))
    
    if request.method == 'POST':
        edicion_id = request.form.get('edicion_id')
        
        if not edicion_id:
            flash("Debe seleccionar una edición.", "danger")
            return render_template('copias/agregar.html', ediciones=ediciones)
        
        # Obtener el último número de copia para esta edición
        ultima_copia = biblioteca.db.copias.find_one(
            {"edicion_id": ObjectId(edicion_id)},
            sort=[("numero", pymongo.DESCENDING)]
        )
        
        nuevo_numero = 1
        if ultima_copia:
            nuevo_numero = ultima_copia.get("numero", 0) + 1
        
        # Crear la nueva copia
        copia_data = {
            "numero": nuevo_numero,
            "edicion_id": ObjectId(edicion_id),
            "disponible": True  # Por defecto, una nueva copia está disponible
        }
        
        copia_id = biblioteca.db.copias.insert_one(copia_data).inserted_id
        flash(f"Copia agregada correctamente con ID: {copia_id}", "success")
        return redirect(url_for('listar_copias'))
    
    return render_template('copias/agregar.html', ediciones=ediciones)

@app.route('/copias/editar/<copia_id>', methods=['GET', 'POST'])
def editar_copia(copia_id):
    """Editar una copia existente"""
    # Obtener la copia con información de la edición y libro
    pipeline = [
        {
            "$match": {"_id": ObjectId(copia_id)}
        },
        {
            "$lookup": {
                "from": "ediciones",
                "localField": "edicion_id",
                "foreignField": "_id",
                "as": "edicion_info"
            }
        },
        {
            "$unwind": {
                "path": "$edicion_info",
                "preserveNullAndEmptyArrays": True
            }
        },
        {
            "$lookup": {
                "from": "libros",
                "localField": "edicion_info.libro_id",
                "foreignField": "_id",
                "as": "libro_info"
            }
        },
        {
            "$unwind": {
                "path": "$libro_info",
                "preserveNullAndEmptyArrays": True
            }
        }
    ]
    
    resultado = list(biblioteca.db.copias.aggregate(pipeline))
    if not resultado:
        flash("No se encontró la copia.", "danger")
        return redirect(url_for('listar_copias'))
    
    copia = resultado[0]
    
    # Obtener todas las ediciones para el formulario
    pipeline_ediciones = [
        {
            "$lookup": {
                "from": "libros",
                "localField": "libro_id",
                "foreignField": "_id",
                "as": "libro_info"
            }
        },
        {
            "$unwind": {
                "path": "$libro_info",
                "preserveNullAndEmptyArrays": True
            }
        }
    ]
    
    ediciones = list(biblioteca.db.ediciones.aggregate(pipeline_ediciones))
    
    if request.method == 'POST':
        numero = request.form.get('numero')
        disponible = 'disponible' in request.form
        edicion_id = request.form.get('edicion_id')
        
        # Validaciones y actualizaciones
        update_data = {}
        
        # Actualizar disponibilidad
        if disponible != copia.get('disponible', False):
            # Verificar si la copia está en préstamo antes de marcarla como disponible
            if disponible and biblioteca.db.prestamos.find_one({
                "copia_id": ObjectId(copia_id),
                "fecha_devolucion": None
            }):
                flash("No se puede marcar como disponible. La copia está en préstamo actualmente.", "danger")
            else:
                update_data["disponible"] = disponible
        
        # Actualizar número
        if numero and numero.isdigit() and int(numero) != copia.get('numero'):
            nuevo_numero = int(numero)
            # Verificar que el número no esté duplicado para la misma edición
            edicion_id_check = copia.get('edicion_info', {}).get('_id')
            duplicado = biblioteca.db.copias.find_one({
                "edicion_id": edicion_id_check,
                "numero": nuevo_numero,
                "_id": {"$ne": ObjectId(copia_id)}
            })
            
            if duplicado:
                flash(f"Ya existe una copia con el número {nuevo_numero} para esta edición.", "danger")
            else:
                update_data["numero"] = nuevo_numero
        
        # Actualizar edición
        if edicion_id and str(edicion_id) != str(copia.get('edicion_info', {}).get('_id')):
            update_data["edicion_id"] = ObjectId(edicion_id)
        
        if update_data:
            biblioteca.db.copias.update_one(
                {"_id": ObjectId(copia_id)},
                {"$set": update_data}
            )
            flash("Copia actualizada correctamente.", "success")
            return redirect(url_for('listar_copias'))
        else:
            flash("No se realizaron cambios.", "info")
    
    return render_template('copias/editar.html', copia=copia, ediciones=ediciones)

@app.route('/copias/eliminar/<copia_id>', methods=['GET', 'POST'])
def eliminar_copia(copia_id):
    """Eliminar una copia"""
    # Obtener la copia con información de la edición y libro
    pipeline = [
        {
            "$match": {"_id": ObjectId(copia_id)}
        },
        {
            "$lookup": {
                "from": "ediciones",
                "localField": "edicion_id",
                "foreignField": "_id",
                "as": "edicion_info"
            }
        },
        {
            "$unwind": {
                "path": "$edicion_info",
                "preserveNullAndEmptyArrays": True
            }
        },
        {
            "$lookup": {
                "from": "libros",
                "localField": "edicion_info.libro_id",
                "foreignField": "_id",
                "as": "libro_info"
            }
        },
        {
            "$unwind": {
                "path": "$libro_info",
                "preserveNullAndEmptyArrays": True
            }
        }
    ]
    
    resultado = list(biblioteca.db.copias.aggregate(pipeline))
    if not resultado:
        flash("No se encontró la copia.", "danger")
        return redirect(url_for('listar_copias'))
    
    copia = resultado[0]
    
    if request.method == 'POST':
        # Verificar si la copia está en préstamo
        prestamo_activo = biblioteca.db.prestamos.find_one({
            "copia_id": ObjectId(copia_id),
            "fecha_devolucion": None
        })
        
        if prestamo_activo:
            flash("No se puede eliminar. La copia está en préstamo actualmente.", "danger")
        else:
            # Verificar si la copia tiene historial de préstamos
            prestamos_historicos = biblioteca.db.prestamos.count_documents({
                "copia_id": ObjectId(copia_id)
            })
            
            if prestamos_historicos > 0:
                confirmacion = request.form.get('confirmar')
                if confirmacion != 'si':
                    flash(f"La copia tiene {prestamos_historicos} préstamos en su historial. Debe confirmar la eliminación.", "warning")
                    return render_template('copias/eliminar.html', copia=copia, prestamos_historicos=prestamos_historicos)
            
            biblioteca.db.copias.delete_one({"_id": ObjectId(copia_id)})
            flash("Copia eliminada correctamente.", "success")
        
        return redirect(url_for('listar_copias'))
    
    return render_template('copias/eliminar.html', copia=copia)

# =================== GESTIÓN DE USUARIOS ===================
@app.route('/usuarios')
def listar_usuarios():
    """Listar todos los usuarios"""
    usuarios = list(biblioteca.db.usuarios.find())
    return render_template('usuarios/listar.html', usuarios=usuarios)

@app.route('/usuarios/agregar', methods=['GET', 'POST'])
def agregar_usuario():
    """Agregar un nuevo usuario"""
    if request.method == 'POST':
        rut = request.form.get('rut', '').strip()
        nombre = request.form.get('nombre', '').strip()
        
        if not rut.strip() or not nombre.strip():
            flash("El RUT y el nombre no pueden estar vacíos.", "danger")
            return render_template('usuarios/agregar.html')
        
        # Verificar si ya existe un usuario con ese RUT
        if biblioteca.db.usuarios.find_one({"RUT": rut}):
            flash(f"Ya existe un usuario con el RUT {rut}.", "danger")
            return render_template('usuarios/agregar.html')
        
        usuario_data = {
            "RUT": rut,
            "nombre": nombre
        }
        
        usuario_id = biblioteca.db.usuarios.insert_one(usuario_data).inserted_id
        flash(f"Usuario agregado correctamente con ID: {usuario_id}", "success")
        return redirect(url_for('listar_usuarios'))
    
    return render_template('usuarios/agregar.html')

@app.route('/usuarios/editar/<usuario_id>', methods=['GET', 'POST'])
def editar_usuario(usuario_id):
    """Editar un usuario existente"""
    usuario = biblioteca.db.usuarios.find_one({"_id": ObjectId(usuario_id)})
   
    if not usuario:
        flash("No se encontró el usuario.", "danger")
        return redirect(url_for('listar_usuarios'))

    if request.method == 'POST':
        rut = request.form.get('rut')
        nombre = request.form.get('nombre')
       
        if not rut or not rut.strip() or not nombre or not nombre.strip():
            flash("El RUT y el nombre no pueden estar vacíos.", "danger")
            return render_template('usuarios/editar.html', usuario=usuario)
       
        # Verificar duplicado
        if rut != usuario.get('RUT') and biblioteca.db.usuarios.find_one({"RUT": rut}):
            flash(f"Ya existe otro usuario con el RUT {rut}.", "danger")
            return render_template('usuarios/editar.html', usuario=usuario)
       
        # Actualizar si todo está bien
        biblioteca.db.usuarios.update_one(
            {"_id": ObjectId(usuario_id)},
            {"$set": {"RUT": rut, "nombre": nombre}}
        )
        flash("Usuario actualizado correctamente.", "success")
        return redirect(url_for('listar_usuarios'))

    return render_template('usuarios/editar.html', usuario=usuario)


@app.route('/usuarios/eliminar/<usuario_id>', methods=['GET', 'POST'])
def eliminar_usuario(usuario_id):
    """Eliminar un usuario"""
    usuario = biblioteca.db.usuarios.find_one({"_id": ObjectId(usuario_id)})

    if not usuario:
        flash("No se encontró el usuario.", "danger")
        return redirect(url_for('listar_usuarios'))

    if request.method == 'POST':
        # Verificar si el usuario tiene préstamos activos (sin devolución)
        prestamos_activos = biblioteca.db.prestamos.count_documents({
            "usuario_id": ObjectId(usuario_id),
            "fecha_devolucion": None
        })

        if prestamos_activos > 0:
            flash(f"No se puede eliminar. El usuario tiene {prestamos_activos} préstamo(s) activo(s).", "danger")
            return redirect(url_for('listar_usuarios'))

        # Si no hay préstamos activos, se puede eliminar
        biblioteca.db.usuarios.delete_one({"_id": ObjectId(usuario_id)})
        flash("Usuario eliminado correctamente.", "success")
        return redirect(url_for('listar_usuarios'))

    return render_template('usuarios/eliminar.html', usuario=usuario)

@app.route('/usuarios/ver/<usuario_id>')
def ver_usuario(usuario_id):
    """Ver detalles de un usuario y su historial de préstamos"""
    usuario = biblioteca.db.usuarios.find_one({"_id": ObjectId(usuario_id)})
    
    if not usuario:
        flash("No se encontró el usuario.", "danger")
        return redirect(url_for('listar_usuarios'))
    
    # Buscar préstamos activos del usuario
    pipeline_activos = [
        {
            "$match": {
                "usuario_id": ObjectId(usuario_id),
                "fecha_devolucion": None
            }
        },
        {
            "$lookup": {
                "from": "copias",
                "localField": "copia_id",
                "foreignField": "_id",
                "as": "copia_info"
            }
        },
        {
            "$unwind": {
                "path": "$copia_info",
                "preserveNullAndEmptyArrays": True
            }
        },
        {
            "$lookup": {
                "from": "ediciones",
                "localField": "copia_info.edicion_id",
                "foreignField": "_id",
                "as": "edicion_info"
            }
        },
        {
            "$unwind": {
                "path": "$edicion_info",
                "preserveNullAndEmptyArrays": True
            }
        },
        {
            "$lookup": {
                "from": "libros",
                "localField": "edicion_info.libro_id",
                "foreignField": "_id",
                "as": "libro_info"
            }
        },
        {
            "$unwind": {
                "path": "$libro_info",
                "preserveNullAndEmptyArrays": True
            }
        }
    ]
    
    prestamos_activos = list(biblioteca.db.prestamos.aggregate(pipeline_activos))
    
    # Buscar historial de préstamos del usuario
    pipeline_historial = [
        {
            "$match": {
                "usuario_id": ObjectId(usuario_id),
                "fecha_devolucion": {"$ne": None}
            }
        },
        {
            "$lookup": {
                "from": "copias",
                "localField": "copia_id",
                "foreignField": "_id",
                "as": "copia_info"
            }
        },
        {
            "$unwind": {
                "path": "$copia_info",
                "preserveNullAndEmptyArrays": True
            }
        },
        {
            "$lookup": {
                "from": "ediciones",
                "localField": "copia_info.edicion_id",
                "foreignField": "_id",
                "as": "edicion_info"
            }
        },
        {
            "$unwind": {
                "path": "$edicion_info",
                "preserveNullAndEmptyArrays": True
            }
        },
        {
            "$lookup": {
                "from": "libros",
                "localField": "edicion_info.libro_id",
                "foreignField": "_id",
                "as": "libro_info"
            }
        },
        {
            "$unwind": {
                "path": "$libro_info",
                "preserveNullAndEmptyArrays": True
            }
        },
        {
            "$sort": {"fecha_prestamo": -1}
        }
    ]
    
    historial_prestamos = list(biblioteca.db.prestamos.aggregate(pipeline_historial))
    
    return render_template('usuarios/ver.html', 
                          usuario=usuario, 
                          prestamos_activos=prestamos_activos, 
                          historial_prestamos=historial_prestamos)


# =================== FILTROS JINJA ===================
@app.template_filter('timediff')
def timediff_filter(fecha):
    """Devuelve un timedelta entre ahora y 'fecha' (ahora - fecha)."""
    ahora = datetime.datetime.now()
    return ahora - fecha

@app.template_filter('dias_restantes')
def dias_restantes_filter(fecha_limite):
    """Días restantes (int) hasta 'fecha_limite'; 0 si ya venció o no hay fecha."""
    if not fecha_limite:
        return 0
    diff = fecha_limite - datetime.datetime.now()
    return diff.days if diff.days > 0 else 0

@app.template_filter('dias_retraso')
def dias_retraso_filter(fecha_limite):
    """Días de retraso (int) desde 'fecha_limite'; 0 si aún no venció o no hay fecha."""
    if not fecha_limite:
        return 0
    diff = datetime.datetime.now() - fecha_limite
    return diff.days if diff.days > 0 else 0

@app.template_filter('es_atrasado')
def es_atrasado_filter(fecha_limite):
    """True si hoy ya pasó la 'fecha_limite'."""
    if not fecha_limite:
        return False
    return datetime.datetime.now() > fecha_limite


# =================== GESTIÓN DE PRÉSTAMOS ===================

@app.route('/prestamos')
def listar_prestamos_activos():
    """Listar préstamos activos (sin fecha_devolucion)."""
    pipeline = [
        {"$match": {"fecha_devolucion": None}},
        {"$lookup": {
            "from": "usuarios",
            "localField": "usuario_id",
            "foreignField": "_id",
            "as": "usuario_info"
        }},
        {"$unwind": {"path": "$usuario_info", "preserveNullAndEmptyArrays": True}},
        {"$lookup": {
            "from": "copias",
            "localField": "copia_id",
            "foreignField": "_id",
            "as": "copia_info"
        }},
        {"$unwind": {"path": "$copia_info", "preserveNullAndEmptyArrays": True}},
        {"$lookup": {
            "from": "ediciones",
            "localField": "copia_info.edicion_id",
            "foreignField": "_id",
            "as": "edicion_info"
        }},
        {"$unwind": {"path": "$edicion_info", "preserveNullAndEmptyArrays": True}},
        {"$lookup": {
            "from": "libros",
            "localField": "edicion_info.libro_id",
            "foreignField": "_id",
            "as": "libro_info"
        }},
        {"$unwind": {"path": "$libro_info", "preserveNullAndEmptyArrays": True}},
        # ordenar por fecha_límite asc para ver primero lo urgente
        {"$sort": {"fecha_limite": 1, "fecha_prestamo": -1}}
    ]
    prestamos = list(biblioteca.db.prestamos.aggregate(pipeline))
    return render_template('prestamos/listar_activos.html', prestamos=prestamos)


@app.route('/prestamos/historial')
def listar_historial_prestamos():
    """Listar historial de préstamos (todos, devueltos o no)."""
    pipeline = [
        {"$lookup": {
            "from": "usuarios",
            "localField": "usuario_id",
            "foreignField": "_id",
            "as": "usuario_info"
        }},
        {"$unwind": {"path": "$usuario_info", "preserveNullAndEmptyArrays": True}},
        {"$lookup": {
            "from": "copias",
            "localField": "copia_id",
            "foreignField": "_id",
            "as": "copia_info"
        }},
        {"$unwind": {"path": "$copia_info", "preserveNullAndEmptyArrays": True}},
        {"$lookup": {
            "from": "ediciones",
            "localField": "copia_info.edicion_id",
            "foreignField": "_id",
            "as": "edicion_info"
        }},
        {"$unwind": {"path": "$edicion_info", "preserveNullAndEmptyArrays": True}},
        {"$lookup": {
            "from": "libros",
            "localField": "edicion_info.libro_id",
            "foreignField": "_id",
            "as": "libro_info"
        }},
        {"$unwind": {"path": "$libro_info", "preserveNullAndEmptyArrays": True}},
        {"$sort": {"fecha_prestamo": -1}}
    ]
    prestamos = list(biblioteca.db.prestamos.aggregate(pipeline))
    return render_template('prestamos/historial.html', prestamos=prestamos)


@app.route('/prestamos/registrar', methods=['GET', 'POST'])
def registrar_prestamo():
    """
    Registrar un nuevo préstamo.
    - Guarda fecha_prestamo = ahora.
    - Requiere fecha_limite (YYYY-MM-DD); se guarda a las 23:59:59 de ese día.
    - Reserva la copia de forma atómica (evita carreras).
    """
    usuarios = list(biblioteca.db.usuarios.find())
    if not usuarios:
        flash("No hay usuarios registrados. Primero debe agregar usuarios.", "warning")
        return redirect(url_for('agregar_usuario'))

    # Copias disponibles con info de edición/libro
    pipeline = [
        {"$match": {"disponible": True}},
        {"$lookup": {
            "from": "ediciones",
            "localField": "edicion_id",
            "foreignField": "_id",
            "as": "edicion_info"
        }},
        {"$unwind": {"path": "$edicion_info", "preserveNullAndEmptyArrays": True}},
        {"$lookup": {
            "from": "libros",
            "localField": "edicion_info.libro_id",
            "foreignField": "_id",
            "as": "libro_info"
        }},
        {"$unwind": {"path": "$libro_info", "preserveNullAndEmptyArrays": True}}
    ]
    copias_disponibles = list(biblioteca.db.copias.aggregate(pipeline))
    if not copias_disponibles:
        flash("No hay copias disponibles para préstamo.", "warning")
        return redirect(url_for('listar_prestamos_activos'))

    if request.method == 'POST':
        usuario_id = request.form.get('usuario_id')
        copia_id = request.form.get('copia_id')
        fecha_limite_str = (request.form.get('fecha_limite') or '').strip()  # YYYY-MM-DD

        if not usuario_id or not copia_id or not fecha_limite_str:
            flash("Debe seleccionar usuario, copia y fecha límite.", "danger")
            return render_template('prestamos/registrar.html', usuarios=usuarios, copias=copias_disponibles)

        # Parsear fecha límite al final del día (23:59:59)
        try:
            fecha_limite_date = datetime.datetime.strptime(fecha_limite_str, "%Y-%m-%d").date()
            fecha_limite = datetime.datetime.combine(fecha_limite_date, datetime.time(23, 59, 59))
        except ValueError:
            flash("Fecha límite inválida. Use el formato AAAA-MM-DD.", "danger")
            return render_template('prestamos/registrar.html', usuarios=usuarios, copias=copias_disponibles)

        ahora = datetime.datetime.now()
        if fecha_limite < ahora.replace(hour=0, minute=0, second=0, microsecond=0):
            flash("La fecha límite debe ser hoy o posterior.", "danger")
            return render_template('prestamos/registrar.html', usuarios=usuarios, copias=copias_disponibles)

        # Reservar la copia de manera atómica (evita carrera)
        reserva = biblioteca.db.copias.update_one(
            {"_id": ObjectId(copia_id), "disponible": True},
            {"$set": {"disponible": False}}
        )
        if reserva.modified_count == 0:
            flash("La copia seleccionada ya no está disponible.", "danger")
            return redirect(url_for('registrar_prestamo'))

        # Insertar el préstamo
        prestamo_data = {
            "usuario_id": ObjectId(usuario_id),
            "copia_id": ObjectId(copia_id),
            "fecha_prestamo": ahora,
            "fecha_limite": fecha_limite,
            "fecha_devolucion": None
        }
        prestamo_id = biblioteca.db.prestamos.insert_one(prestamo_data).inserted_id

        flash(f"Préstamo registrado correctamente con ID: {prestamo_id}", "success")
        return redirect(url_for('listar_prestamos_activos'))

    return render_template('prestamos/registrar.html', usuarios=usuarios, copias=copias_disponibles)


@app.route('/prestamos/devolver/<prestamo_id>', methods=['GET', 'POST'])
def registrar_devolucion(prestamo_id):
    """
    Registrar la devolución de un préstamo.
    - Marca fecha_devolucion = ahora.
    - Vuelve a marcar la copia como disponible.
    """
    # Obtener préstamo con joins
    pipeline = [
        {"$match": {"_id": ObjectId(prestamo_id)}},
        {"$lookup": {
            "from": "usuarios",
            "localField": "usuario_id",
            "foreignField": "_id",
            "as": "usuario_info"
        }},
        {"$unwind": {"path": "$usuario_info", "preserveNullAndEmptyArrays": True}},
        {"$lookup": {
            "from": "copias",
            "localField": "copia_id",
            "foreignField": "_id",
            "as": "copia_info"
        }},
        {"$unwind": {"path": "$copia_info", "preserveNullAndEmptyArrays": True}},
        {"$lookup": {
            "from": "ediciones",
            "localField": "copia_info.edicion_id",
            "foreignField": "_id",
            "as": "edicion_info"
        }},
        {"$unwind": {"path": "$edicion_info", "preserveNullAndEmptyArrays": True}},
        {"$lookup": {
            "from": "libros",
            "localField": "edicion_info.libro_id",
            "foreignField": "_id",
            "as": "libro_info"
        }},
        {"$unwind": {"path": "$libro_info", "preserveNullAndEmptyArrays": True}}
    ]
    resultado = list(biblioteca.db.prestamos.aggregate(pipeline))
    if not resultado:
        flash("No se encontró el préstamo.", "danger")
        return redirect(url_for('listar_prestamos_activos'))

    prestamo = resultado[0]

    if prestamo.get('fecha_devolucion'):
        flash("Este préstamo ya ha sido devuelto.", "warning")
        return redirect(url_for('listar_prestamos_activos'))

    if request.method == 'POST':
        fecha_devolucion = datetime.datetime.now()

        # Actualizar préstamo
        biblioteca.db.prestamos.update_one(
            {"_id": ObjectId(prestamo_id)},
            {"$set": {"fecha_devolucion": fecha_devolucion}}
        )

        # Liberar copia
        if prestamo.get('copia_info') and prestamo['copia_info'].get('_id'):
            biblioteca.db.copias.update_one(
                {"_id": prestamo['copia_info']['_id']},
                {"$set": {"disponible": True}}
            )

        flash("Devolución registrada correctamente.", "success")
        return redirect(url_for('listar_prestamos_activos'))

    return render_template('prestamos/devolver.html', prestamo=prestamo)



# =================== CONSULTAS ===================
@app.route('/consultas')
def menu_consultas():
    """Menú de consultas"""
    return render_template('consultas/menu.html')
@app.route('/consultas/copias')
def consulta_copias_completas():
    """Mostrar listado de copias con autor, libro, edición y copia"""
    pipeline = [
        {
            "$lookup": {
                "from": "ediciones",
                "localField": "edicion_id",
                "foreignField": "_id",
                "as": "edicion_info"
            }
        },
        { "$unwind": { "path": "$edicion_info", "preserveNullAndEmptyArrays": True }},
        {
            "$lookup": {
                "from": "libros",
                "localField": "edicion_info.libro_id",
                "foreignField": "_id",
                "as": "libro_info"
            }
        },
        { "$unwind": { "path": "$libro_info", "preserveNullAndEmptyArrays": True }},
        { "$unwind": { "path": "$libro_info.autores", "preserveNullAndEmptyArrays": True }},
        {
            "$lookup": {
                "from": "autores",
                "localField": "libro_info.autores.autor_id",
                "foreignField": "_id",
                "as": "autor_info"
            }
        },
        { "$unwind": { "path": "$autor_info", "preserveNullAndEmptyArrays": True }}
    ]

    copias = list(biblioteca.db.copias.aggregate(pipeline))
    return render_template('consultas/copias_completas.html', copias=copias)

@app.route('/consultas/libros', methods=['GET', 'POST'])
def buscar_libros():
    """Buscar libros por título"""
    resultados = []

    # Soporta GET y POST (según cómo envíe el formulario)
    titulo = request.form.get('titulo', '') if request.method == 'POST' else request.args.get('titulo', '')

    if titulo.strip():
        # Búsqueda insensible a mayúsculas
        libros = list(biblioteca.db.libros.find({"titulo": {"$regex": titulo, "$options": "i"}}))

        for libro in libros:
            # Obtener las ediciones asociadas al libro
            ediciones = list(biblioteca.db.ediciones.find({"libro_id": libro["_id"]}))
            libro['ediciones'] = ediciones
            libro['num_ediciones'] = len(ediciones)  # para mostrar en la tabla
            resultados.append(libro)

    return render_template('consultas/buscar_libros.html', resultados=resultados)

@app.route('/consultas/autores', methods=['GET', 'POST'])
def buscar_libros_por_autor():

    """Buscar libros por autor"""
    resultados = []
    nombre_autor = request.args.get('autor', '')

    if nombre_autor.strip():
        # Buscar libros donde el campo autores.nombre coincida con el texto
        resultados = list(biblioteca.db.libros.find(
            {"autores.nombre": {"$regex": nombre_autor, "$options": "i"}}
        ))
        for libro in resultados:
            # Contar ediciones
            libro["num_ediciones"] = biblioteca.db.ediciones.count_documents({"libro_id": libro["_id"]})
            # Contar copias disponibles de todas sus ediciones
            ediciones_ids = biblioteca.db.ediciones.find(
                {"libro_id": libro["_id"]}, {"_id": 1}
            )
            ed_ids = [ed["_id"] for ed in ediciones_ids]
            copias_disponibles = biblioteca.db.copias.count_documents({

                "edicion_id": {"$in": ed_ids},

                "disponible": True
            })
            libro["copias_disponibles"] = copias_disponibles
    return render_template('consultas/buscar_por_autor.html', resultados=resultados)
    

@app.route('/consultas/isbn', methods=['GET', 'POST'])
def buscar_ediciones_por_isbn():
    """Buscar ediciones por ISBN"""
    resultados = []

    # Obtener el ISBN desde el formulario (POST) o URL (GET)
    isbn = request.form.get('isbn', '') if request.method == 'POST' else request.args.get('isbn', '')

    if isbn.strip():
        # Pipeline de agregación para unir con libros y copias
        pipeline = [
            {
                "$match": {"ISBN": {"$regex": isbn, "$options": "i"}}
            },
            {
                "$lookup": {
                    "from": "libros",
                    "localField": "libro_id",
                    "foreignField": "_id",
                    "as": "libro_info"
                }
            },
            {
                "$unwind": {
                    "path": "$libro_info",
                    "preserveNullAndEmptyArrays": True
                }
            },
            {
                "$lookup": {
                    "from": "copias",
                    "localField": "_id",
                    "foreignField": "edicion_id",
                    "as": "copias"
                }
            }
        ]

        # Ejecutar consulta
        resultados = list(biblioteca.db.ediciones.aggregate(pipeline))

        # Calcular cuántas copias están disponibles por edición
        for edicion in resultados:
            edicion['copias_disponibles'] = sum(1 for c in edicion.get('copias', []) if c.get('disponible', False))

    return render_template('consultas/buscar_por_isbn.html', resultados=resultados)

@app.route('/consultas/usuario', methods=['GET', 'POST'])
def buscar_usuario_por_rut():
    """Buscar usuario por RUT"""
    usuario = None
    prestamos_activos = []
    historial_prestamos = []
   
    # Soporta GET y POST
    rut = request.form.get('rut', '') if request.method == 'POST' else request.args.get('rut', '')

    if rut.strip():
        usuario = biblioteca.db.usuarios.find_one({"RUT": rut})

        # Si no lo encuentra, intenta con regex
        if not usuario:
            usuario = biblioteca.db.usuarios.find_one({"RUT": {"$regex": rut, "$options": "i"}})

        if usuario:
            # Préstamos activos
            pipeline_activos = [
                {"$match": {"usuario_id": usuario["_id"], "fecha_devolucion": None}},
                {"$lookup": {"from": "copias", "localField": "copia_id", "foreignField": "_id", "as": "copia_info"}},
                {"$unwind": {"path": "$copia_info", "preserveNullAndEmptyArrays": True}},
                {"$lookup": {"from": "ediciones", "localField": "copia_info.edicion_id", "foreignField": "_id", "as": "edicion_info"}},
                {"$unwind": {"path": "$edicion_info", "preserveNullAndEmptyArrays": True}},
                {"$lookup": {"from": "libros", "localField": "edicion_info.libro_id", "foreignField": "_id", "as": "libro_info"}},
                {"$unwind": {"path": "$libro_info", "preserveNullAndEmptyArrays": True}}
            ]
            prestamos_activos = list(biblioteca.db.prestamos.aggregate(pipeline_activos))

            # Historial de préstamos
            pipeline_historial = [
                {"$match": {"usuario_id": usuario["_id"], "fecha_devolucion": {"$ne": None}}},
                {"$lookup": {"from": "copias", "localField": "copia_id", "foreignField": "_id", "as": "copia_info"}},
                {"$unwind": {"path": "$copia_info", "preserveNullAndEmptyArrays": True}},
                {"$lookup": {"from": "ediciones", "localField": "copia_info.edicion_id", "foreignField": "_id", "as": "edicion_info"}},
                {"$unwind": {"path": "$edicion_info", "preserveNullAndEmptyArrays": True}},
                {"$lookup": {"from": "libros", "localField": "edicion_info.libro_id", "foreignField": "_id", "as": "libro_info"}},
                {"$unwind": {"path": "$libro_info", "preserveNullAndEmptyArrays": True}},
                {"$sort": {"fecha_prestamo": -1}}
            ]
            historial_prestamos = list(biblioteca.db.prestamos.aggregate(pipeline_historial))

    # 🔧 PASAMOS la variable correctamente como "prestamos" al HTML
    return render_template('consultas/buscar_usuario.html',
                           usuario=usuario,
                           prestamos_activos=prestamos_activos,
                           prestamos=historial_prestamos)
    
@app.route('/consultas/estadisticas')
def ver_estadisticas_prestamos():
    """Ver estadísticas de préstamos"""
    from datetime import datetime, timedelta

    total_prestamos = biblioteca.db.prestamos.count_documents({})
    prestamos_activos = biblioteca.db.prestamos.count_documents({"fecha_devolucion": None})
    prestamos_devueltos = biblioteca.db.prestamos.count_documents({"fecha_devolucion": {"$ne": None}})

    # Préstamos atrasados
    fecha_limite = datetime.now() - timedelta(days=30)
    prestamos_atrasados = biblioteca.db.prestamos.count_documents({
        "fecha_devolucion": None,
        "fecha_prestamo": {"$lt": fecha_limite}
    })

    # Libros disponibles
    copias_totales = biblioteca.db.copias.count_documents({})
    copias_prestadas = biblioteca.db.prestamos.count_documents({"fecha_devolucion": None})
    libros_disponibles = copias_totales - copias_prestadas

    # Préstamos por mes
    pipeline_mes = [
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m", "date": "$fecha_prestamo"}},
            "conteo": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    prestamos_por_mes = list(biblioteca.db.prestamos.aggregate(pipeline_mes))
    meses = [item["_id"] for item in prestamos_por_mes]
    datos_prestamos_por_mes = [item["conteo"] for item in prestamos_por_mes]

    # Libros más prestados
    pipeline_libros = [
        {"$lookup": {
            "from": "copias",
            "localField": "copia_id",
            "foreignField": "_id",
            "as": "copia_info"
        }},
        {"$unwind": "$copia_info"},
        {"$lookup": {
            "from": "ediciones",
            "localField": "copia_info.edicion_id",
            "foreignField": "_id",
            "as": "edicion_info"
        }},
        {"$unwind": "$edicion_info"},
        {"$lookup": {
            "from": "libros",
            "localField": "edicion_info.libro_id",
            "foreignField": "_id",
            "as": "libro_info"
        }},
        {"$unwind": "$libro_info"},
        {"$group": {
            "_id": "$libro_info._id",
            "titulo": {"$first": "$libro_info.titulo"},
            "autores": {"$first": "$libro_info.autores"},
            "conteo": {"$sum": 1}
        }},
        {"$sort": {"conteo": -1}},
        {"$limit": 5}
    ]
    libros_populares = list(biblioteca.db.prestamos.aggregate(pipeline_libros))

    # Usuarios más activos
    pipeline_usuarios = [
        {"$lookup": {
            "from": "usuarios",
            "localField": "usuario_id",
            "foreignField": "_id",
            "as": "usuario_info"
        }},
        {"$unwind": "$usuario_info"},
        {"$group": {
            "_id": "$usuario_id",
            "nombre": {"$first": "$usuario_info.nombre"},
            "apellido": {"$first": "$usuario_info.apellido"},
            "RUT": {"$first": "$usuario_info.RUT"},
            "conteo": {"$sum": 1}
        }},
        {"$sort": {"conteo": -1}},
        {"$limit": 5}
    ]
    usuarios_activos = list(biblioteca.db.prestamos.aggregate(pipeline_usuarios))

    return render_template("consultas/estadisticas.html",
                           total_prestamos=total_prestamos,
                           prestamos_activos=prestamos_activos,
                           prestamos_devueltos=prestamos_devueltos,
                           prestamos_atrasados=prestamos_atrasados,
                           libros_disponibles=libros_disponibles,
                           meses=meses,
                           datos_prestamos_por_mes=datos_prestamos_por_mes,
                           libros_populares=libros_populares,
                           usuarios_activos=usuarios_activos)

    
if __name__ == '__main__':
    app.run(debug=True)