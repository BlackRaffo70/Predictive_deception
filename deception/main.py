import socket
import threading
import json
import config
from session_handler import handle_connection

def main():
    # Setup Configurazione AI
    config.setup_ai()

    # Caricamento Scenario Iniziale
    try:
        with open(config.SCENARIO_PATH, "r") as f:
            SCENARIO_CONFIG = json.load(f)
        print(f"[*] Loaded Scenario: {SCENARIO_CONFIG['hostname']} ({SCENARIO_CONFIG['type']})")
    except Exception as e:
        print(f"[FATAL] Cannot load scenario {config.SCENARIO_PATH}: {e}")
        exit(1)

    # Setup Socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((config.BIND_IP, config.BIND_PORT))
    sock.listen(5)
    print(f"[*] MindTrap Active on port {config.BIND_PORT}")
    
    while True:
        try:
            client, addr = sock.accept()
            # Passiamo lo scenario e il client al thread
            t = threading.Thread(target=handle_connection, args=(client, addr, SCENARIO_CONFIG))
            t.daemon = True
            t.start()
        except KeyboardInterrupt:
            print("\n[!] Shutting down...")
            break
        except Exception as e:
            print(f"[ERROR] Main loop: {e}")

if __name__ == "__main__":
    main()