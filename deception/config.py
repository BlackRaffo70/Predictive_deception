import os
import google.generativeai as genai

# ================= CONFIGURAZIONE =================
BIND_IP = '0.0.0.0'
BIND_PORT = 2222
HOST_KEY_FILE = 'host.key'

# Percorsi assoluti o relativi
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, 'output_deception/honeypot_log/mindtrap_log.json')
SCENARIO_PATH = os.path.join(BASE_DIR, "scenarios/ubuntu.json")

# API Key
GOOGLE_API_KEY = os.getenv("GEMINI_API_KEY")

def setup_ai():
    if not GOOGLE_API_KEY:
        print("[ERROR] Export GEMINI_API_KEY environment variable first!")
        exit(1)
    genai.configure(api_key=GOOGLE_API_KEY)