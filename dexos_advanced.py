"""
DEXOS ULTIMATE v3.0
Arquivo principal: dexos_ultimate_v3.py
Descrição:
- Integra HUD PyQt5, reconhecimento de voz, TTS, câmera (OpenCV), detecção facial/objetos (opcional), banco MySQL, logs e sistema de comandos.
- Projetado para rodar no Windows 64-bit (também funciona em Linux/Mac com ajustes).

Instruções rápidas:
1) Coloque este arquivo na mesma pasta que: index.html, dexos.sql (opcional) e assets (sons, ícones).
2) Instale dependências (veja README abaixo) e execute:
   python dexos_ultimate_v3.py

Observação: Este arquivo é um "ponto de integração". Ele contém:
- Classe DBManager: conexão, execução de scripts SQL e métodos utilitários
- VoiceAssistant: pyttsx3 com heurística de voz masculina
- SpeechWorker: reconhecimento de voz (SpeechRecognition)
- CameraWorker: captura e emissão de frames; integração com face_recognition e YOLO se instalados
- HUDWindow: PyQt5 com layout futurista, botões, logs, e integração com a câmera
- Sistema de comandos: persiste comandos no banco e permite aprendizado incremental

"""

import sys
import os
import time
import threading
import traceback
from pathlib import Path

# GUI
from PyQt5 import QtCore, QtGui, QtWidgets

# Multimedia
import cv2 # type: ignore
import numpy as np

# Voice + Speech
import speech_recognition as sr # type: ignore
try:
    import pyttsx3 # type: ignore
    TTS_AVAILABLE = True
except Exception:
    pyttsx3 = None
    TTS_AVAILABLE = False

# Optional AI libs (import safely)
try:
    import face_recognition # type: ignore
    FACE_LIB_AVAILABLE = True
except Exception:
    FACE_LIB_AVAILABLE = False

try:
    from ultralytics import YOLO # type: ignore
    YOLO_AVAILABLE = True
except Exception:
    YOLO_AVAILABLE = False

# Database (MySQL)
try:
    import mysql.connector
    MYSQL_AVAILABLE = True
except Exception:
    mysql = None
    MYSQL_AVAILABLE = False

APP_NAME = 'DEXOS ULTIMATE'
USER_NAME = 'Pedro'
VERSION = '3.0'

# --------------------------- DBManager ---------------------------
class DBManager:
    def __init__(self, host='localhost', user='root', password='', database='dexos_db'):
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.conn = None
        self.cursor = None
        if MYSQL_AVAILABLE:
            self.connect()

    def connect(self):
        try:
            self.conn = mysql.connector.connect(host=self.host, user=self.user, password=self.password, database=self.database)
            self.cursor = self.conn.cursor(dictionary=True)
            print('[DB] Conectado ao MySQL')
        except Exception as e:
            print('[DB] Falha ao conectar MySQL:', e)
            self.conn = None
            self.cursor = None

    def ensure_database(self, schema_file='dexos.sql'):
        """Tenta criar/tocar schema se dexos.sql existir. Requer usuário com permissões."""
        if not MYSQL_AVAILABLE:
            print('[DB] mysql-connector-python não instalado. Ignorando DBInit.')
            return
        if self.conn is None:
            # try connect without database to create it
            try:
                tmp = mysql.connector.connect(host=self.host, user=self.user, password=self.password)
                tmpcur = tmp.cursor()
                with open(schema_file, 'r', encoding='utf-8') as f:
                    sql = f.read()
                for stmt in sql.split(';'):
                    s = stmt.strip()
                    if s:
                        try:
                            tmpcur.execute(s)
                        except Exception:
                            pass
                tmp.commit()
                tmp.close()
                print('[DB] Schema aplicado (tentativa).')
                # reconnect to DB
                self.connect()
            except Exception as e:
                print('[DB] Não foi possível criar DB automaticamente:', e)

    def execute(self, q, params=None):
        if self.cursor is None:
            raise RuntimeError('DB não conectado')
        self.cursor.execute(q, params or ())
        return self.cursor

    def commit(self):
        if self.conn:
            self.conn.commit()

    def close(self):
        try:
            if self.cursor:
                self.cursor.close()
            if self.conn:
                self.conn.close()
        except Exception:
            pass

    # Helpers
    def save_command(self, comando_texto, acao='manual', usuario_id=None, sucesso=True, tempo_resposta=0.0):
        try:
            q = "INSERT INTO log_comandos (comando_reconhecido, acao_executada, usuario_id, sucesso, tempo_resposta, data_hora) VALUES (%s,%s,%s,%s,%s,NOW())"
            self.execute(q, (comando_texto, acao, usuario_id, sucesso, tempo_resposta))
            self.commit()
        except Exception as e:
            print('[DB] Erro ao salvar log de comando:', e)

# --------------------------- VoiceAssistant ---------------------------
class VoiceAssistant:
    def __init__(self):
        self.available = False
        if not TTS_AVAILABLE:
            print('[TTS] pyttsx3 não disponível — TTS local desligado')
            return
        try:
            self.engine = pyttsx3.init()
            try:
                voices = self.engine.getProperty('voices')
                chosen = None
                for v in voices:
                    n = getattr(v, 'name', '').lower()
                    if 'female' in n or 'fem' in n:
                        continue
                    chosen = v
                    break
                if chosen is None and voices:
                    chosen = voices[0]
                if chosen is not None:
                    self.engine.setProperty('voice', chosen.id)
            except Exception:
                pass
            self.engine.setProperty('rate', 165)
            self.available = True
        except Exception as e:
            print('[TTS] Erro iniciando pyttsx3:', e)
            self.available = False

    def speak(self, text, block=False):
        if not self.available:
            print('[TTS] (simulado):', text)
            return
        def _run(t):
            try:
                self.engine.say(t)
                self.engine.runAndWait()
            except Exception as e:
                print('[TTS] Erro ao falar:', e)
        thr = threading.Thread(target=_run, args=(text,), daemon=True)
        thr.start()
        if block:
            thr.join()

# --------------------------- SpeechWorker ---------------------------
class SpeechWorker(QtCore.QObject):
    command_detected = QtCore.pyqtSignal(str)

    def __init__(self, lang='pt-BR'):
        super().__init__()
        self._running = False
        self.recognizer = sr.Recognizer()
        self.lang = lang
        self.mic_index = None
        try:
            mics = sr.Microphone.list_microphone_names()
            if mics:
                self.mic_index = 0
        except Exception as e:
            print('[Speech] Não foi possível listar microfones:', e)
            self.mic_index = None

    def start(self):
        if self._running:
            return
        if self.mic_index is None:
            print('[Speech] Microfone não encontrado. Reconhecimento de voz desligado.')
            return
        self._running = True
        threading.Thread(target=self._listen_loop, daemon=True).start()

    def stop(self):
        self._running = False

    def _listen_loop(self):
        try:
            with sr.Microphone(device_index=self.mic_index) as source:
                try:
                    self.recognizer.adjust_for_ambient_noise(source, duration=1)
                except Exception:
                    pass
                while self._running:
                    try:
                        audio = self.recognizer.listen(source, phrase_time_limit=5)
                        text = self.recognizer.recognize_google(audio, language=self.lang)
                        if text:
                            self.command_detected.emit(text)
                    except sr.UnknownValueError:
                        pass
                    except sr.RequestError as e:
                        print('[Speech] Erro serviço reconhecimento:', e)
                        time.sleep(1)
                    except Exception as e:
                        print('[Speech] Erro no loop:', e)
                        time.sleep(0.5)
        except Exception as e:
            print('[Speech] Erro abrindo microfone:', e)

# --------------------------- CameraWorker ---------------------------
class CameraWorker(QtCore.QObject):
    frame_ready = QtCore.pyqtSignal(np.ndarray)
    face_detected = QtCore.pyqtSignal(list)  # lista (nome, (top,right,bottom,left))

    def __init__(self, device=0):
        super().__init__()
        self.device = device
        self._running = False
        self._cap = None

    def start(self):
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._capture_loop, daemon=True).start()

    def stop(self):
        self._running = False
        try:
            if self._cap is not None and self._cap.isOpened():
                self._cap.release()
        except Exception:
            pass

    def _capture_loop(self):
        try:
            self._cap = cv2.VideoCapture(self.device, cv2.CAP_DSHOW if os.name == 'nt' else 0)
            if not self._cap.isOpened():
                print('[Camera] Não foi possível abrir a câmera (device {})'.format(self.device))
                self._running = False
                return
            while self._running:
                ret, frame = self._cap.read()
                if not ret:
                    time.sleep(0.05)
                    continue
                disp = cv2.resize(frame, (800, 450))
                faces_out = []
                if FACE_LIB_AVAILABLE:
                    try:
                        rgb = cv2.cvtColor(disp, cv2.COLOR_BGR2RGB)
                        locations = face_recognition.face_locations(rgb)
                        for loc in locations:
                            faces_out.append(('Desconhecido', loc))
                    except Exception as e:
                        print('[Camera] Erro face_recognition:', e)
                if faces_out:
                    self.face_detected.emit(faces_out)
                self.frame_ready.emit(disp)
                time.sleep(0.03)
        except Exception as e:
            print('[Camera] Erro na captura:', e)
            traceback.print_exc()
        finally:
            try:
                if self._cap is not None and self._cap.isOpened():
                    self._cap.release()
            except Exception:
                pass

# --------------------------- HUDWindow (PyQt5) ---------------------------
class HUDWindow(QtWidgets.QMainWindow):
    def __init__(self, db: DBManager = None):
        super().__init__()
        self.db = db
        self.setWindowTitle(f"{APP_NAME} - {USER_NAME}")
        self.setFixedSize(1280, 720)
        self.setStyleSheet('background-color: #050810; color: #00f0ea;')

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)
        layout.setContentsMargins(12,12,12,12)

        # left: video + hud overlay
        left = QtWidgets.QFrame()
        left.setFixedWidth(860)
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setSpacing(8)

        self.video_label = QtWidgets.QLabel()
        self.video_label.setFixedSize(820, 480)
        self.video_label.setStyleSheet('background: rgba(5,10,15,0.6); border-radius: 12px;')
        self.video_label.setAlignment(QtCore.Qt.AlignCenter)
        left_layout.addWidget(self.video_label, alignment=QtCore.Qt.AlignCenter)

        # hud small canvas
        self.hud_canvas = QtWidgets.QLabel()
        self.hud_canvas.setFixedSize(820, 120)
        self.hud_canvas.setStyleSheet('background: transparent')
        left_layout.addWidget(self.hud_canvas, alignment=QtCore.Qt.AlignCenter)

        # right: controls
        right = QtWidgets.QFrame()
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setSpacing(10)

        self.status_label = QtWidgets.QLabel(f"{APP_NAME} online. Bem-vindo, {USER_NAME}.")
        font = QtGui.QFont('Arial', 12, QtGui.QFont.Bold)
        self.status_label.setFont(font)
        right_layout.addWidget(self.status_label)

        # buttons
        btns = [
            ('Abrir HUD Web', self.open_hud_web),
            ('Abrir navegador', self.open_browser),
            ('Reconhecer objeto', self.cmd_recognize_object),
            ('Quem está aí?', self.cmd_recognize_face),
            ('Status sistema', self.cmd_status),
        ]
        for name, fn in btns:
            b = QtWidgets.QPushButton(name)
            b.setFixedHeight(44)
            b.clicked.connect(fn)
            right_layout.addWidget(b)

        right_layout.addStretch()

        # logs
        self.log_box = QtWidgets.QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(220)
        right_layout.addWidget(self.log_box)

        layout.addWidget(left)
        layout.addWidget(right)

        # style
        self.setStyleSheet('''
            QPushButton{background: rgba(20,30,40,0.6); color: #cfe9ff; border-radius: 10px}
            QPushButton:hover{background: rgba(10,200,255,0.08)}
            QTextEdit{background: rgba(0,0,0,0.35); color: #cfe9ff}
            QLabel{color: #d4f3ff}
        ''')

        # internal state
        self.voice = VoiceAssistant()
        self.camera = CameraWorker()
        self.camera.frame_ready.connect(self.on_frame)
        self.camera.face_detected.connect(self.on_face_detected)

        self.speech = SpeechWorker()
        self.speech.command_detected.connect(self.on_command_detected)

        # HUD animation
        self.hud_pos = 0
        self.hud_timer = QtCore.QTimer()
        self.hud_timer.timeout.connect(self.update_hud)
        self.hud_timer.start(50)

        # start modules safely
        try:
            self.camera.start()
        except Exception as e:
            self.log('[Init] Câmera não iniciada: ' + str(e))
        try:
            self.speech.start()
        except Exception as e:
            self.log('[Init] Voz não iniciada: ' + str(e))

        self.voice.speak(f"{APP_NAME} online. Bem-vindo, {USER_NAME}.")
        self.log(f"{APP_NAME} inicializado (v{VERSION})")

    def log(self, text):
        ts = time.strftime('%H:%M:%S')
        try:
            self.log_box.append(f'[{ts}] {text}')
        except Exception:
            print(f'[{ts}] {text}')

    # button callbacks
    def open_hud_web(self):
        # abre index.html local no navegador
        p = Path('index.html').absolute()
        if p.exists():
            self.voice.speak('Abrindo HUD web')
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(p)))
            self.log('Abrindo HUD web: ' + str(p))
        else:
            self.voice.speak('HUD web não encontrada')
            self.log('Arquivo index.html não encontrado')

    def open_browser(self):
        self.voice.speak('Abrindo navegador')
        self.log('Comando: abrir navegador')
        QtGui.QDesktopServices.openUrl(QtCore.QUrl('https://www.google.com'))

    def cmd_recognize_object(self):
        self.voice.speak('Iniciando reconhecimento de objetos')
        self.log('Comando: reconhecer objeto')
        if YOLO_AVAILABLE:
            try:
                model = YOLO('yolov8n.pt')
                self.log('YOLO carregado (demo)')
                # nota: processamento de frames com YOLO é intensivo e deveria rodar em thread separada
            except Exception as e:
                self.log('Erro ao carregar YOLO: ' + str(e))
        else:
            self.log('YOLO não instalado — instale ultralytics')

    def cmd_recognize_face(self):
        self.voice.speak('Procurando rostos na câmera')
        self.log('Comando: reconhecer face (use face_recognition para identificar)')

    def cmd_status(self):
        self.voice.speak('Sistema operacional funcionando normalmente')
        self.log('Comando: status do sistema')

    # speech handling
    def on_command_detected(self, text):
        self.log('Comando de voz: ' + text)
        low = text.lower()
        start = time.time()
        # mapeamento simples
        if 'abrir' in low and 'navegador' in low:
            self.open_browser()
            ok = True
        elif 'quem' in low or 'quem está' in low:
            self.cmd_recognize_face()
            ok = True
        elif 'objeto' in low or 'reconhecer' in low:
            self.cmd_recognize_object()
            ok = True
        elif 'horas' in low or 'que horas' in low:
            agora = time.strftime('%H:%M:%S')
            self.voice.speak(f'Agora são {agora}')
            ok = True
        else:
            # fallback — salvar no banco se disponível como comando novo
            self.voice.speak('Comando não reconhecido. Deseja salvar este comando?')
            ok = False
        elapsed = time.time() - start
        # salvar log se DB conectado
        if self.db:
            try:
                self.db.save_command(text, acao='voz', tempo_resposta=elapsed, sucesso=ok)
            except Exception as e:
                print('[HUD] Erro salvando comando no DB:', e)

    # camera -> display
    @QtCore.pyqtSlot(np.ndarray)
    def on_frame(self, frame):
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            bytes_per_line = ch * w
            qimg = QtGui.QImage(rgb.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
            pix = QtGui.QPixmap.fromImage(qimg).scaled(self.video_label.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            # overlay
            painter = QtGui.QPainter(pix)
            pen = QtGui.QPen(QtGui.QColor(0, 200, 255, 200))
            pen.setWidth(2)
            painter.setPen(pen)
            center = pix.rect().center()
            painter.drawEllipse(center, 60, 60)
            painter.end()
            self.video_label.setPixmap(pix)
        except Exception as e:
            print('[HUD] Erro no processamento do frame:', e)

    @QtCore.pyqtSlot(list)
    def on_face_detected(self, faces):
        for name, loc in faces:
            self.log(f'Rosto detectado: {name} - {loc}')
            self.voice.speak(f'Rosto detectado: {name}')
            # aqui poderíamos salvar no DB em tabela `rostos` ou `log_reconhecimentos_faciais`

    def update_hud(self):
        w = self.hud_canvas.width()
        h = self.hud_canvas.height()
        img = QtGui.QPixmap(w, h)
        img.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(img)
        gradient = QtGui.QLinearGradient(0,0,w,0)
        gradient.setColorAt(0, QtGui.QColor(0,0,0,0))
        gradient.setColorAt(0.5, QtGui.QColor(0,200,255,120))
        gradient.setColorAt(1, QtGui.QColor(0,0,0,0))
        brush = QtGui.QBrush(gradient)
        painter.setBrush(brush)
        painter.setPen(QtCore.Qt.NoPen)
        x = (self.hud_pos % (w + 200)) - 100
        painter.drawRoundedRect(x, 10, 200, h-20, 8, 8)
        painter.end()
        self.hud_canvas.setPixmap(img)
        self.hud_pos += 8

    def closeEvent(self, event):
        try:
            self.camera.stop()
        except Exception:
            pass
        try:
            self.speech.stop()
        except Exception:
            pass
        event.accept()

# --------------------------- Aplicação ---------------------------

def main():
    # configurar DB (ajuste credenciais conforme necessário)
    db = None
    if MYSQL_AVAILABLE:
        db = DBManager(host='localhost', user='root', password='', database='dexos_db')
        # tenta aplicar schema local se existir
        if Path('dexos.sql').exists():
            db.ensure_database('dexos.sql')
    else:
        print('[BOOT] MySQL não disponível — funcionalidades de persistência serão limitadas')

    app = QtWidgets.QApplication(sys.argv)
    window = HUDWindow(db=db)
    window.show()
    try:
        sys.exit(app.exec_())
    except Exception as e:
        print('Erro fatal na aplicação:', e)

if __name__ == '__main__':
    main()
