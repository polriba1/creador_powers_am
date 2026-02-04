#!/usr/bin/env python3
"""
MENAG Presentation Generator - Web Interface
=============================================
Interfície web per generar presentacions PowerPoint i xuletes d'estudi.

Ús:
    python app.py

Després obre http://localhost:5000 al navegador.
"""
import os
import sys
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, send_file, jsonify, redirect, url_for
from werkzeug.utils import secure_filename
import threading
import uuid

# Afegir directori arrel al path
sys.path.insert(0, str(Path(__file__).parent))

from config import OUTPUT_DIR, INPUT_DIR
from extractors import extract_text, extract_images
from processors import describe_images, structure_presentation, generate_missing_images
from generators import create_presentation, create_study_guide
from database import (
    init_db, get_api_keys, set_api_keys, has_valid_keys,
    get_session_stats, get_global_stats, increment_presentations, log_usage,
    register_user, create_session_with_user, update_user_stats,
    get_user_stats, get_all_users_stats
)

# Inicialitzar base de dades
init_db()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB màxim
app.config['UPLOAD_FOLDER'] = str(INPUT_DIR)

# Estat de les tasques en curs
tasks = {}


def allowed_file(filename):
    """Verifica si el fitxer és un PDF."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'


def process_presentation(task_id, pdf_path, chapter_name, group_name, skip_images, api_keys=None, user_name=None):
    """Processa la presentació en segon pla."""
    try:
        tasks[task_id]['status'] = 'processing'
        tasks[task_id]['progress'] = 'Extraient text del PDF...'

        # Obtenir API keys
        anthropic_key = api_keys.get('anthropic') if api_keys else None
        google_key = api_keys.get('google') if api_keys else None

        # 1. Extreure text
        chapter_text = extract_text(pdf_path)
        tasks[task_id]['progress'] = f'Text extret ({len(chapter_text.split())} paraules)'

        # 2. Extreure imatges
        image_catalog = []
        tasks[task_id]['progress'] = 'Extraient imatges del PDF...'
        images = extract_images(pdf_path)
        tasks[task_id]['progress'] = f'Extretes {len(images)} imatges'

        if images:
            tasks[task_id]['progress'] = 'Analitzant imatges amb Gemini...'
            image_catalog = describe_images(images, session_id=task_id, api_key=google_key)

        # 3. Estructurar amb Opus 4.5
        tasks[task_id]['progress'] = 'Estructurant presentació amb Claude Opus 4.5...'
        plan = structure_presentation(
            chapter_text,
            image_catalog,
            chapter_name,
            group_name,
            session_id=task_id,
            api_key=anthropic_key
        )
        tasks[task_id]['progress'] = f'Generades {len(plan.slides)} diapositives'

        # 4. Generar imatges (si cal)
        if not skip_images:
            tasks[task_id]['progress'] = 'Generant imatges amb Nano Banana...'
            plan = generate_missing_images(plan, image_catalog, session_id=task_id, api_key=google_key)

        # 5. Crear fitxers
        tasks[task_id]['progress'] = 'Generant PowerPoint...'
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_base = OUTPUT_DIR / f"{chapter_name}_{group_name}_{timestamp}"

        pptx_path = create_presentation(plan, f"{output_base}.pptx")
        # docx_path = create_study_guide(plan, f"{output_base}_xuleta.docx")  # DESACTIVAT

        # Incrementar comptador de presentacions
        increment_presentations(task_id)

        # Obtenir estadístiques de la sessió
        session_stats = get_session_stats(task_id)
        session_cost = session_stats.get('total_cost_usd', 0)

        # Actualitzar estadístiques de l'usuari
        if user_name:
            update_user_stats(user_name, session_cost, presentations=1)

        # Completat
        tasks[task_id]['status'] = 'completed'
        tasks[task_id]['progress'] = 'Completat!'
        tasks[task_id]['pptx_path'] = str(pptx_path)
        tasks[task_id]['docx_path'] = None  # DESACTIVAT
        tasks[task_id]['slides_count'] = len(plan.slides)
        tasks[task_id]['cost_usd'] = session_cost

    except Exception as e:
        tasks[task_id]['status'] = 'error'
        tasks[task_id]['error'] = str(e)
        tasks[task_id]['progress'] = f'Error: {str(e)}'


@app.route('/')
def index():
    """Pàgina principal."""
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    """Puja un PDF i comença el processament."""
    if 'pdf_file' not in request.files:
        return jsonify({'error': 'No s\'ha seleccionat cap fitxer'}), 400

    file = request.files['pdf_file']
    if file.filename == '':
        return jsonify({'error': 'No s\'ha seleccionat cap fitxer'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Només es permeten fitxers PDF'}), 400

    # Obtenir paràmetres
    chapter_name = request.form.get('chapter_name', 'KWC00')
    group_name = request.form.get('group_name', 'GRUP')
    skip_images = request.form.get('skip_images', 'false') == 'true'
    user_name = request.form.get('user_name', '').strip()

    # Validar nom d'usuari
    if not user_name:
        return jsonify({'error': 'Has d\'introduir el teu nom'}), 400

    # Registrar usuari
    register_user(user_name)

    # Guardar fitxer
    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_filename = f"{timestamp}_{filename}"
    pdf_path = Path(app.config['UPLOAD_FOLDER']) / unique_filename
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    file.save(str(pdf_path))

    # Obtenir API keys (de la request o de la BD)
    api_keys = {
        'anthropic': request.form.get('anthropic_key') or get_api_keys().get('anthropic'),
        'google': request.form.get('google_key') or get_api_keys().get('google')
    }

    # Crear tasca
    task_id = str(uuid.uuid4())

    # Crear sessió associada a l'usuari
    create_session_with_user(task_id, user_name)

    tasks[task_id] = {
        'id': task_id,
        'status': 'queued',
        'progress': 'En cua...',
        'chapter_name': chapter_name,
        'group_name': group_name,
        'pdf_filename': filename,
        'user_name': user_name,
        'cost_usd': 0
    }

    # Iniciar processament en segon pla
    thread = threading.Thread(
        target=process_presentation,
        args=(task_id, pdf_path, chapter_name, group_name, skip_images, api_keys, user_name)
    )
    thread.start()

    return jsonify({'task_id': task_id})


@app.route('/status/<task_id>')
def get_status(task_id):
    """Retorna l'estat d'una tasca."""
    if task_id not in tasks:
        return jsonify({'error': 'Tasca no trobada'}), 404
    return jsonify(tasks[task_id])


@app.route('/download/<task_id>/<file_type>')
def download_file(task_id, file_type):
    """Descarrega el fitxer generat."""
    if task_id not in tasks:
        return jsonify({'error': 'Tasca no trobada'}), 404

    task = tasks[task_id]
    if task['status'] != 'completed':
        return jsonify({'error': 'La tasca encara no ha acabat'}), 400

    if file_type == 'pptx':
        file_path = task.get('pptx_path')
        mimetype = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
    elif file_type == 'docx':
        file_path = task.get('docx_path')
        mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    else:
        return jsonify({'error': 'Tipus de fitxer no vàlid'}), 400

    if not file_path or not Path(file_path).exists():
        return jsonify({'error': 'Fitxer no trobat'}), 404

    return send_file(
        file_path,
        as_attachment=True,
        download_name=Path(file_path).name,
        mimetype=mimetype
    )


# ============================================================================
# ENDPOINTS PER GESTIÓ D'API KEYS
# ============================================================================

@app.route('/api/keys', methods=['GET'])
def get_keys():
    """Retorna l'estat de les API keys (sense mostrar les keys completes)."""
    keys = get_api_keys()
    return jsonify({
        'anthropic': {
            'configured': bool(keys.get('anthropic')),
            'masked': mask_key(keys.get('anthropic', ''))
        },
        'google': {
            'configured': bool(keys.get('google')),
            'masked': mask_key(keys.get('google', ''))
        },
        'valid': has_valid_keys()
    })


@app.route('/api/keys', methods=['POST'])
def save_keys():
    """Guarda les API keys."""
    data = request.get_json()
    anthropic_key = data.get('anthropic_key')
    google_key = data.get('google_key')

    set_api_keys(anthropic_key=anthropic_key, google_key=google_key)

    return jsonify({
        'success': True,
        'valid': has_valid_keys()
    })


def mask_key(key: str) -> str:
    """Emmascara una API key per mostrar només els últims 4 caràcters."""
    if not key or len(key) < 8:
        return ''
    return f"{'*' * (len(key) - 4)}{key[-4:]}"


# ============================================================================
# ENDPOINTS PER ESTADÍSTIQUES D'ÚS
# ============================================================================

@app.route('/api/stats')
def get_stats():
    """Retorna estadístiques globals d'ús."""
    stats = get_global_stats()
    stats['users'] = get_all_users_stats()
    return jsonify(stats)


@app.route('/api/stats/<session_id>')
def get_session_usage(session_id):
    """Retorna estadístiques d'una sessió específica."""
    return jsonify(get_session_stats(session_id))


@app.route('/api/users')
def get_users():
    """Retorna estadístiques de tots els usuaris."""
    return jsonify(get_all_users_stats())


@app.route('/api/users/<user_name>')
def get_user(user_name):
    """Retorna estadístiques d'un usuari específic."""
    return jsonify(get_user_stats(user_name))


@app.route('/settings')
def settings_page():
    """Pàgina de configuració."""
    return render_template('settings.html')


@app.route('/stats')
def stats_page():
    """Pàgina d'estadístiques."""
    return render_template('stats.html')


# Crear directori de templates si no existeix
templates_dir = Path(__file__).parent / 'templates'
templates_dir.mkdir(exist_ok=True)

# Template HTML
INDEX_HTML = '''<!DOCTYPE html>
<html lang="ca">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MENAG Presentation Generator</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
        }

        .container {
            max-width: 600px;
            margin: 0 auto;
        }

        .card {
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }

        h1 {
            color: #E07A2F;
            text-align: center;
            margin-bottom: 10px;
            font-size: 2em;
        }

        .subtitle {
            text-align: center;
            color: #666;
            margin-bottom: 20px;
        }

        .nav {
            display: flex;
            justify-content: center;
            gap: 20px;
            margin-bottom: 30px;
        }
        .nav a {
            color: #E07A2F;
            text-decoration: none;
            font-weight: 600;
            padding: 10px 20px;
            border-radius: 8px;
            transition: background 0.3s;
        }
        .nav a:hover { background: #fff5ef; }
        .nav a.active { background: #E07A2F; color: white; }

        .form-group {
            margin-bottom: 20px;
        }

        label {
            display: block;
            margin-bottom: 8px;
            color: #333;
            font-weight: 600;
        }

        input[type="text"],
        input[type="file"] {
            width: 100%;
            padding: 12px 15px;
            border: 2px solid #ddd;
            border-radius: 10px;
            font-size: 16px;
            transition: border-color 0.3s;
        }

        input[type="text"]:focus,
        input[type="file"]:focus {
            outline: none;
            border-color: #E07A2F;
        }

        .file-upload {
            border: 2px dashed #E07A2F;
            border-radius: 10px;
            padding: 30px;
            text-align: center;
            cursor: pointer;
            transition: background 0.3s;
        }

        .file-upload:hover {
            background: #fff5ef;
        }

        .file-upload input {
            display: none;
        }

        .file-upload-label {
            color: #E07A2F;
            font-weight: 600;
        }

        .file-name {
            margin-top: 10px;
            color: #666;
            font-size: 14px;
        }

        .checkbox-group {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .checkbox-group input {
            width: 20px;
            height: 20px;
            accent-color: #E07A2F;
        }

        button {
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, #E07A2F 0%, #c96a25 100%);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }

        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(224, 122, 47, 0.4);
        }

        button:disabled {
            background: #ccc;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }

        .progress-container {
            display: none;
            margin-top: 30px;
        }

        .progress-bar {
            height: 10px;
            background: #eee;
            border-radius: 5px;
            overflow: hidden;
            margin-bottom: 10px;
        }

        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #E07A2F, #f5a623);
            width: 0%;
            transition: width 0.5s;
            animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }

        .progress-text {
            text-align: center;
            color: #666;
            font-size: 14px;
        }

        .results {
            display: none;
            margin-top: 30px;
            padding: 20px;
            background: #f0fff0;
            border-radius: 10px;
            border: 2px solid #4CAF50;
        }

        .results h3 {
            color: #4CAF50;
            margin-bottom: 15px;
            text-align: center;
        }

        .download-buttons {
            display: flex;
            gap: 10px;
        }

        .download-btn {
            flex: 1;
            padding: 12px;
            border-radius: 8px;
            text-decoration: none;
            text-align: center;
            font-weight: 600;
            transition: transform 0.2s;
        }

        .download-btn:hover {
            transform: translateY(-2px);
        }

        .download-pptx {
            background: #E07A2F;
            color: white;
        }

        .download-docx {
            background: #2196F3;
            color: white;
        }

        .error {
            display: none;
            margin-top: 20px;
            padding: 15px;
            background: #ffebee;
            border-radius: 10px;
            border: 2px solid #f44336;
            color: #c62828;
        }

        .info-box {
            background: #e3f2fd;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 20px;
            font-size: 14px;
            color: #1565c0;
        }

        .row {
            display: flex;
            gap: 15px;
        }

        .row .form-group {
            flex: 1;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>MENAG Generator</h1>
            <p class="subtitle">Genera presentacions i xuletes automaticament</p>

            <nav class="nav">
                <a href="/" class="active">Generador</a>
                <a href="/settings">Configuracio</a>
                <a href="/stats">Estadistiques</a>
            </nav>

            <div class="info-box">
                Puja el PDF del capítol del llibre Koontz i obtindràs un PowerPoint
                amb ~20 diapositives i un Word amb la xuleta per estudiar.
            </div>

            <form id="uploadForm">
                <div class="form-group">
                    <label>El teu nom *</label>
                    <input type="text" id="userName" name="user_name"
                           placeholder="Introdueix el teu nom" required>
                </div>

                <div class="form-group">
                    <label>PDF del Capitol</label>
                    <div class="file-upload" onclick="document.getElementById('pdfFile').click()">
                        <input type="file" id="pdfFile" name="pdf_file" accept=".pdf" required>
                        <span class="file-upload-label">Clica o arrossega el PDF aqui</span>
                        <div class="file-name" id="fileName"></div>
                    </div>
                </div>

                <div class="row">
                    <div class="form-group">
                        <label>Nom del Capitol</label>
                        <input type="text" id="chapterName" name="chapter_name"
                               placeholder="ex: KWC04" value="KWC" required>
                    </div>

                    <div class="form-group">
                        <label>Nom del Grup</label>
                        <input type="text" id="groupName" name="group_name"
                               placeholder="ex: GRUPG" value="GRUPG" required>
                    </div>
                </div>

                <div class="form-group">
                    <div class="checkbox-group">
                        <input type="checkbox" id="skipImages" name="skip_images">
                        <label for="skipImages" style="margin: 0; font-weight: normal;">
                            Saltar generació d'imatges (més ràpid)
                        </label>
                    </div>
                </div>

                <button type="submit" id="submitBtn">Generar Presentació</button>
            </form>

            <div class="progress-container" id="progressContainer">
                <div class="progress-bar">
                    <div class="progress-fill" id="progressFill"></div>
                </div>
                <p class="progress-text" id="progressText">Processant...</p>
            </div>

            <div class="results" id="results">
                <h3>Presentació generada!</h3>
                <p style="text-align: center; margin-bottom: 15px;" id="resultsInfo"></p>
                <div class="download-buttons">
                    <a href="#" class="download-btn download-pptx" id="downloadPptx">
                        Descarregar PPT
                    </a>
                    <a href="#" class="download-btn download-docx" id="downloadDocx">
                        Descarregar Xuleta
                    </a>
                </div>
            </div>

            <div class="error" id="errorBox"></div>
        </div>
    </div>

    <script>
        const form = document.getElementById('uploadForm');
        const pdfFile = document.getElementById('pdfFile');
        const fileName = document.getElementById('fileName');
        const submitBtn = document.getElementById('submitBtn');
        const progressContainer = document.getElementById('progressContainer');
        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');
        const results = document.getElementById('results');
        const resultsInfo = document.getElementById('resultsInfo');
        const errorBox = document.getElementById('errorBox');

        // Funcio per fer polling d'una tasca
        function pollTask(task_id) {
            progressContainer.style.display = 'block';
            results.style.display = 'none';
            submitBtn.disabled = true;
            let progress = 10;

            const pollInterval = setInterval(async () => {
                try {
                    const statusResponse = await fetch(`/status/${task_id}`);
                    if (!statusResponse.ok) {
                        // Tasca no trobada (pot ser que el servidor s'hagi reiniciat)
                        clearInterval(pollInterval);
                        localStorage.removeItem('active_task');
                        progressContainer.style.display = 'none';
                        submitBtn.disabled = false;
                        return;
                    }
                    const status = await statusResponse.json();

                    progressText.textContent = status.progress;

                    if (status.status === 'processing' || status.status === 'queued') {
                        progress = Math.min(progress + 2, 90);
                        progressFill.style.width = progress + '%';
                    } else if (status.status === 'completed') {
                        clearInterval(pollInterval);
                        localStorage.removeItem('active_task');
                        progressFill.style.width = '100%';
                        progressContainer.style.display = 'none';

                        // Mostrar resultats
                        results.style.display = 'block';
                        const cost = status.cost_usd ? status.cost_usd.toFixed(4) : '0.0000';
                        resultsInfo.innerHTML = `${status.slides_count} diapositives generades<br><span style="color:#E07A2F; font-weight:bold;">Cost: $${cost}</span>`;
                        document.getElementById('downloadPptx').href = `/download/${task_id}/pptx`;
                        document.getElementById('downloadDocx').href = `/download/${task_id}/docx`;
                        submitBtn.disabled = false;
                    } else if (status.status === 'error') {
                        clearInterval(pollInterval);
                        localStorage.removeItem('active_task');
                        progressContainer.style.display = 'none';
                        errorBox.style.display = 'block';
                        errorBox.textContent = status.error || 'Error desconegut';
                        submitBtn.disabled = false;
                    }
                } catch (e) {
                    // Error de xarxa, continuar intentant
                    console.log('Error polling:', e);
                }
            }, 2000);
        }

        // Comprovar si hi ha una tasca activa al carregar la pagina
        const activeTask = localStorage.getItem('active_task');
        if (activeTask) {
            console.log('Recuperant tasca activa:', activeTask);
            pollTask(activeTask);
        }

        pdfFile.addEventListener('change', function() {
            if (this.files.length > 0) {
                fileName.textContent = this.files[0].name;
            }
        });

        form.addEventListener('submit', async function(e) {
            e.preventDefault();

            // Reset UI
            progressContainer.style.display = 'block';
            results.style.display = 'none';
            errorBox.style.display = 'none';
            submitBtn.disabled = true;
            progressFill.style.width = '10%';

            // Preparar dades
            const formData = new FormData();
            formData.append('pdf_file', pdfFile.files[0]);
            formData.append('user_name', document.getElementById('userName').value);
            formData.append('chapter_name', document.getElementById('chapterName').value);
            formData.append('group_name', document.getElementById('groupName').value);
            formData.append('skip_images', document.getElementById('skipImages').checked);

            try {
                // Pujar fitxer
                const uploadResponse = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });

                if (!uploadResponse.ok) {
                    const error = await uploadResponse.json();
                    throw new Error(error.error || 'Error pujant el fitxer');
                }

                const { task_id } = await uploadResponse.json();

                // Guardar task_id a localStorage per recuperar-lo si es refresca
                localStorage.setItem('active_task', task_id);

                // Iniciar polling
                pollTask(task_id);

            } catch (error) {
                progressContainer.style.display = 'none';
                errorBox.style.display = 'block';
                errorBox.textContent = error.message;
                submitBtn.disabled = false;
            }
        });
    </script>
</body>
</html>
'''

# Guardar template
with open(templates_dir / 'index.html', 'w', encoding='utf-8') as f:
    f.write(INDEX_HTML)


if __name__ == '__main__':
    print("=" * 60)
    print("MENAG PRESENTATION GENERATOR - Web Interface")
    print("=" * 60)
    print()

    # Inicialitzar directoris
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Comprovar si hi ha API keys configurades
    keys_status = has_valid_keys()
    if keys_status.get('anthropic') and keys_status.get('google'):
        print("API keys configurades a la base de dades")
    else:
        print("NOTA: Les API keys es poden configurar a /settings")
        print("      o via variables d'entorn (.env)")

    print()
    print("Servidor web iniciat!")
    print("Obre el navegador a: http://localhost:5000")
    print()
    print("Pagines disponibles:")
    print("  /          - Generador de presentacions")
    print("  /settings  - Configuracio d'API keys")
    print("  /stats     - Estadistiques d'us")
    print()
    print("Prem Ctrl+C per aturar el servidor.")
    print()

    # Obtenir port de variable d'entorn (per Render, Railway, etc.)
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
