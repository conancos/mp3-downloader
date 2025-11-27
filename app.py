# app.py

import os
import sys
import subprocess
import re
import tempfile
from flask import Flask, render_template, request, send_file, jsonify, after_this_request

app = Flask(__name__)

# Función para limpiar el título y que sea un nombre de archivo válido
def sanitize_filename(filename):
    # Reemplaza caracteres inválidos por un guion bajo
    filename = re.sub(r'[\\/*?:"<>|]', '_', filename)
    # Elimina espacios extra al principio y al final
    return filename.strip()

@app.route('/', methods=['GET'])
def index():
    """Sirve la página principal."""
    return render_template('index.html')

@app.route('/get_info', methods=['POST'])
def get_info():
    """Obtiene el título y la miniatura de un video."""
    data = request.get_json()
    video_url = data.get('url')

    if not video_url:
        return jsonify({'error': 'No se proporcionó ninguna URL.'}), 400

    try:
        python_executable_dir = os.path.dirname(sys.executable)
        yt_dlp_executable = os.path.join(python_executable_dir, 'yt-dlp.exe')

        # Comando para obtener solo el título y la miniatura
        command = [
            yt_dlp_executable,
            '--no-playlist',
            '--print', '%(title)s ::: %(thumbnail)s', # Imprime título y thumbnail separados
            '--no-download', # ¡Importante! No descarga nada
            video_url
        ]
        
        result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
        output = result.stdout.strip()

        # Separamos el título y la URL del thumbnail
        parts = output.split(':::')
        title = parts[0].strip()
        thumbnail_url = parts[1].strip()

        return jsonify({'title': title, 'thumbnail': thumbnail_url})

    except subprocess.CalledProcessError as e:
        print(f"Error en yt-dlp al obtener info: {e.stderr}")
        return jsonify({'error': 'No se pudo obtener información del video. La URL podría ser inválida.'}), 404
    except Exception as e:
        print(f"Error inesperado al obtener info: {e}")
        return jsonify({'error': 'Ocurrió un error inesperado.'}), 500

@app.route('/download', methods=['POST'])
def download():
    """Procesa la URL, descarga el audio y lo devuelve."""
    data = request.get_json()
    video_url = data.get('url')
    video_title = data.get('title', 'audio')

    if not video_url:
        return jsonify({'error': 'No se proporcionó ninguna URL.'}), 400

    temp_original_filename = None
    
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".opus") as temp_file:
            temp_original_filename = temp_file.name

        python_executable_dir = os.path.dirname(sys.executable)
        yt_dlp_executable = os.path.join(python_executable_dir, 'yt-dlp.exe')
        ffmpeg_path = r"C:\ffmpeg\bin"

        print(f"--- INICIANDO DESCARGA Y CONVERSIÓN ---")
        print(f"Título: {video_title}")
        print(f"URL: {video_url}")

        # --- PASO 1: DESCARGAR Y EXTRAER A OPUS DIRECTAMENTE ---
        print("--- PASO 1: Descargando y extrayendo audio a .opus ---")
        download_command = [
            yt_dlp_executable,
            '--no-playlist',
            '--extractor-args', 'youtube:player_client=default',
            '--ffmpeg-location', ffmpeg_path,  # Le decimos dónde está ffmpeg/ffprobe
            '--force-overwrites',              # <-- ¡FORZAMOS LA DESCARGA!
            '-x', '--audio-format', 'opus',
            '-o', temp_original_filename,
            video_url
        ]
        
        print(f"Ejecutando: {' '.join(download_command)}")
        subprocess.run(download_command, check=True, text=True, encoding='utf-8')
        print("--- Descarga y extracción completadas ---")

        # --- PASO 2: CONVERTIR DE OPUS A MP3 ---
        print("--- PASO 2: Convirtiendo de .opus a .mp3 con ffmpeg ---")
        temp_final_filename = temp_original_filename.replace('.opus', '.mp3')
        ffmpeg_executable = os.path.join(ffmpeg_path, 'ffmpeg.exe')
        
        convert_command = [
            ffmpeg_executable,
            '-i', temp_original_filename,
            '-q:a', '0',
            temp_final_filename
        ]

        print(f"Ejecutando: {' '.join(convert_command)}")
        subprocess.run(convert_command, check=True, text=True, encoding='utf-8')
        print("--- Conversión completada ---")
        
        # --- LIMPIEZA Y ENVÍO ---
        os.remove(temp_original_filename)
        
        safe_title = sanitize_filename(video_title)
        
        @after_this_request
        def remove_file(response):
            try:
                import time
                time.sleep(1)
                if temp_final_filename and os.path.exists(temp_final_filename):
                    os.remove(temp_final_filename)
            except Exception as e:
                app.logger.error(f"Error al eliminar el archivo temporal (puede ser ignorado): {e}")
            return response

        return send_file(
            temp_final_filename,
            as_attachment=True,
            download_name=f'{safe_title}.mp3',
            mimetype='audio/mpeg'
        )

    except subprocess.CalledProcessError as e:
        error_message = f"Un comando falló con código de salida {e.returncode}."
        print(f"ERROR: {error_message}")
        if temp_original_filename and os.path.exists(temp_original_filename):
            os.remove(temp_original_filename)
        return jsonify({'error': f'No se pudo procesar el video. {error_message}'}), 500
    except Exception as e:
        print(f"ERROR INESPERADO: {e}")
        if temp_original_filename and os.path.exists(temp_original_filename):
            os.remove(temp_original_filename)
        return jsonify({'error': 'Ocurrió un error inesperado en el servidor.'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)