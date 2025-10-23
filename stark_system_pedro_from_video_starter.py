# STARK_SYSTEM: PEDRO - Protótipo inicial em Python
# Arquivo: stark_system_pedro_starter.py
# Objetivo: começar a criar a IA baseada no vídeo fornecido. Este script é um ponto de partida
# com GUI, reconhecimento de voz, TTS e sistema de comandos modular.

"""
Instruções rápidas (executar no terminal):
1) Crie um ambiente virtual (recomendado):
   python -m venv venv
   source venv/bin/activate   # Linux/Mac
   venv\Scripts\activate    # Windows

2) Instale dependências:
   pip install PySimpleGUI speechrecognition pyttsx3 pyaudio
   # Observações:
   # - pyaudio pode ser difícil de instalar no Windows; verifique rodas pré-compiladas ou use pipwin.
   # - se preferir um STT offline mais robusto use VOSK (pip install vosk) e um modelo local.

3) Rode:
   python stark_system_pedro_starter.py

O que este protótipo faz:
- Janela simples com HUD estilo minimalista (pode ser substituído por uma interface mais estilizada)
- Ouvir microfone e converter fala em texto (reconhecimento contínuo com botão)
- Falar resposta com TTS (pyttsx3)
- Handler básico de comandos (abrir arquivo, dizer hora, executar ação fictícia)
- Ponto de integração para conectar a um modelo de linguagem (OpenAI/Local)

"""

import threading
import time
import queue
import sys
import subprocess
import os
from datetime import datetime

import PySimpleGUI as sg
import speech_recognition as sr
import pyttsx3

# ---------- Configurações ----------
ASSISTANT_NAME = "STARK SYSTEM: PEDRO"
WAKE_WORDS = ["stark", "jarvis", "pedro", "sistema"]

# ---------- TTS Engine ----------
engine = pyttsx3.init()
engine.setProperty('rate', 160)  # velocidade
voices = engine.getProperty('voices')
# escolher voz masculina se disponível
for v in voices:
    if 'male' in v.name.lower() or 'm' in v.id.lower():
        engine.setProperty('voice', v.id)
        break

# ---------- Reconhecimento de voz (thread) ----------
recognizer = sr.Recognizer()
mic = None
try:
    mic = sr.Microphone()
except Exception as e:
    print("Microfone não detectado ou erro: ", e)

listening = False
stt_queue = queue.Queue()


def speak(text):
    """Fala o texto (bloqueante)."""
    engine.say(text)
    engine.runAndWait()


def background_listen_loop():
    global listening
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=1)
        while listening:
            try:
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=8)
                try:
                    text = recognizer.recognize_google(audio, language='pt-BR')
                except sr.RequestError:
                    text = ""  # falha na conexão com serviço
                except sr.UnknownValueError:
                    text = ""
                if text:
                    stt_queue.put(text)
            except sr.WaitTimeoutError:
                continue
            except Exception as e:
                print('Erro no loop de escuta:', e)
                continue

# ---------- Handler de comandos ----------

def is_wake_present(text):
    t = text.lower()
    return any(w in t for w in WAKE_WORDS)


def query_ai(prompt):
    """
    PONTO DE INTEGRAÇÃO: aqui você conecta um modelo de linguagem (ex: OpenAI, local Llama/ggml, etc.).
    Exemplo temporário: respostas simples e comandos pré-programados.
    Substitua por chamada à API quando quiser.
    """
    prompt_lower = prompt.lower()
    if 'hora' in prompt_lower:
        return f'São {datetime.now().strftime("%H:%M")}. '
    if 'abrir' in prompt_lower and 'arquivo' in prompt_lower:
        return 'Abrindo arquivo... (simulação)'
    if 'olá' in prompt_lower or 'oi' in prompt_lower:
        return 'Olá, Pedro. Sistema online.'
    return "Desculpe, ainda estou aprendendo isso. Posso ajudar em outra coisa?"


def handle_text_command(text):
    # chamado sempre que um texto reconhecido chega
    print('Entrada de voz:', text)

    # detectar wake word — se não houver, pode ser opcional dependendo da UX
    if not is_wake_present(text):
        # ignorar ou tratar como conversa aberta
        pass

    # enviar para o modelo / handler
    response = query_ai(text)

    # ações simples baseadas em palavras-chave
    if 'abrir' in text.lower() and 'notepad' in text.lower():
        try:
            if sys.platform.startswith('win'):
                subprocess.Popen(['notepad.exe'])
            else:
                subprocess.Popen(['gedit'])
            response = 'Abrindo o bloco de notas.'
        except Exception as e:
            response = f'Não consegui abrir o bloco de notas: {e}'

    stt_text = f'Você disse: {text}\nResposta: {response}'
    return stt_text, response

# ---------- GUI ----------

def make_window():
    sg.theme('DarkBlue14')
    layout = [
        [sg.Text(ASSISTANT_NAME, font=('Helvetica', 20), justification='center', expand_x=True)],
        [sg.Multiline('', size=(60,10), key='-LOG-', autoscroll=True, disabled=True)],
        [sg.Button('Iniciar Escuta', key='-START-'), sg.Button('Parar Escuta', key='-STOP-', disabled=True), sg.Button('Falar', key='-SAY-'), sg.Button('Fechar')]
    ]
    return sg.Window('STARK SYSTEM: PEDRO - Protótipo', layout, finalize=True)


def main_loop():
    global listening
    window = make_window()

    listener_thread = None

    while True:
        event, values = window.read(timeout=200)
        if event in (sg.WIN_CLOSED, 'Fechar'):
            listening = False
            break
        if event == '-START-':
            if mic is None:
                window['-LOG-'].print('Microfone não disponível.')
                continue
            listening = True
            listener_thread = threading.Thread(target=background_listen_loop, daemon=True)
            listener_thread.start()
            window['-START-'].update(disabled=True)
            window['-STOP-'].update(disabled=False)
            window['-LOG-'].print('Escuta iniciada...')
        if event == '-STOP-':
            listening = False
            window['-START-'].update(disabled=False)
            window['-STOP-'].update(disabled=True)
            window['-LOG-'].print('Escuta parada.')
        if event == '-SAY-':
            txt = sg.popup_get_text('Digite o texto para o assistente falar:', keep_on_top=True)
            if txt:
                window['-LOG-'].print('TTS ->', txt)
                threading.Thread(target=speak, args=(txt,), daemon=True).start()

        # processar fila de STT
        try:
            while not stt_queue.empty():
                recognized = stt_queue.get_nowait()
                display, response = handle_text_command(recognized)
                window['-LOG-'].print(display)
                # falar a resposta
                threading.Thread(target=speak, args=(response,), daemon=True).start()
        except Exception:
            pass

    window.close()


if __name__ == '__main__':
    main_loop()
