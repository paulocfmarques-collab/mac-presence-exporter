#!/usr/bin/env python3

from datetime import datetime, timedelta
import json
import logging
from logging import DEBUG
from logging.handlers import RotatingFileHandler
import subprocess
import time
from time import perf_counter
from prometheus_client import Gauge, start_http_server
import os
import psycopg2
from psycopg2 import sql


# Arquivo JSON fornecido
MAC_FILE = "/home/pmarques/dvl/gera_targets/mac_dictionary.json"
MAC_LOCALHOST = "dc:a6:32:b3:64:70"
STATE_FILE = "/home/pmarques/dvl/gera_targets/device_state.json"
LOG_FILE = "/home/pmarques/dvl/gera_targets/mac_presence_exporter.log"
CONFIG_FILE = "/home/pmarques/dvl/gera_targets/config.json"
SECTION = "mac_presence_exporter"
DATABASE_INFO = "database_server"

DEBUG = False  # Ativa o modo de depuração
TIME_ACTIVE = 1814400
RESET_TIME = 1814400

# Porta do exporter
EXPORTER_PORT = 9101

# Intervalo de atualização
SCAN_INTERVAL = 60

# Métrica Prometheus
device_status = Gauge(
    "network_device_online",
    "Status do dispositivo na rede (1=online, 0=offline)",
    ["mac", "device_name"]
)

max_online_time = Gauge(
    "network_device_max_online_seconds",
    "Maior tempo online registrado em segundos",
    ["mac", "device_name"]
)

max_offline_time = Gauge(
    "network_device_max_offline_seconds",
    "Maior tempo offline registrado em segundos",
    ["mac", "device_name"]
)

current_online_time = Gauge(
    "network_device_current_online_seconds",
    "Tempo online atual em segundos",
    ["mac", "device_name"]
)

current_offline_time = Gauge(
    "network_device_current_offline_seconds",
    "Tempo offline atual em segundos",
    ["mac", "device_name"]
)

device_active = Gauge(
    "network_device_active",
    "Dispositivo na rede ativo na rede (1=ativo, 0=desativado)",
    ["mac", "device_name"]
)


handler = RotatingFileHandler(
    LOG_FILE, 
    maxBytes=10*1024*1024, 
    backupCount=5, 
    encoding='utf-8'
)

def str_to_bool(value):
    return str(value).strip().lower() in ("true", "1", "yes", "on")

def setup_logging():
    """
    Configura o logging para registrar informações em um arquivo.
    """
    logging.basicConfig(
        handlers=[handler],
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

def load_config_file():
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
        logging.info(f"Loaded {len(data)} records from {CONFIG_FILE}.")
        return data
    except FileNotFoundError:
        logging.error(f"Input file {CONFIG_FILE} not found.")
        return []
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from {CONFIG_FILE}: {e}")
        return []

# Carrega dicionário MAC -> Nome
def load_mac_dictionary(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_state(file_path):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Erro ao carregar estado: {e}")

    return {}

def save_state(file_path, device_history):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(device_history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logging.error(f"Erro ao salvar estado: {e}")

def scan_network():
    """
    Executa arp-scan e retorna um conjunto com os MACs encontrados.
    """
    found_macs = set()

    logging.info("Iniciando scan de rede...")

    try:
        for counter  in range(5):  # Tenta 5 vezes
            result = subprocess.run(
                ["sudo", "arp-scan", "--localnet"],
                capture_output=True,
                text=True,
                timeout=10
            )

            for line in result.stdout.splitlines():
                parts = line.split()

                if len(parts) >= 2:
                    mac = parts[1].lower()
                    found_macs.add(mac)

            found_macs.add(MAC_LOCALHOST.lower())  # Adiciona o MAC do localhost
            logging.info(f"Scan de rede parcial. MACs encontrados: {len(found_macs)}")

        logging.info(f"Scan de rede concluído. Total de MACs encontrados: {len(found_macs)}")
        return found_macs

    except Exception as e:
        logging.error(f"Erro no scan: {e}")
        return set()

def print_device_history(device_history):
    logging.info("Histórico de dispositivos:")
    for mac, history in device_history.items():
        logging.info(f"MAC: {mac}, Name: {history['Name']}, Status: {'Online' if history['current_status'] == 1 else 'Offline'}, Max Online: {history['max_online']}, Max Offline: {history['max_offline']} Online: {history['current_online']} Offline: {history['current_offline']}")
    logging.info("\n\n")

def update_metrics():
    devices = load_mac_dictionary(MAC_FILE)
    device_history = load_state(STATE_FILE)  # Carrega o estado salvo
    found_macs = scan_network()

    if DEBUG:
        print_device_history(device_history)

    now = time.time()

    for mac, name in devices.items():

        mac = mac.lower()
        status = 1 if mac in found_macs else 0

        # Inicialização do histórico
        if mac not in device_history:
            logging.info(f"Novo dispositivo detectado: MAC: {mac}, Name: {name}, Status: {'Online' if status == 1 else 'Offline'}")
            device_history[mac] = {
                "Name": name,
                "first_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "current_status": status,
                "start_time": now,
                "max_online": 0,
                "max_offline": 0,
                "current_online": 0,
                "current_offline": 0,
                "active": 1,
                "times_reset": 0
            }

        history = device_history[mac]

        # Mudança de estado
        if history["current_status"] != status:
            duration = now - history["start_time"]
            writeDatabase(name, status, duration)

            if history["current_status"] == 1:
                history["max_online"] = max(
                    history["max_online"],
                    duration
                )
                history["current_online"] = 0  # Reset current online time
            else:
                history["max_offline"] = max(
                    history["max_offline"],
                    duration
                )
                history["current_offline"] = 0  # Reset current offline time

            history["current_status"] = status
            history["start_time"] = now
        else:
            duration = now - history["start_time"]

            if status == 1:
                history["current_online"] = duration
                history["max_online"] = max(history["max_online"], duration)
                history["current_offline"] = 0  # Reset current offline time
            else:
                history["current_offline"] = duration
                history["max_offline"] = max(history["max_offline"], duration)
                history["current_online"] = 0  # Reset current online time

        #Mudanca de nome
        if history["Name"] != name:
            logging.info("Nome do dispositivo (%s) atualizado de %s para %s", mac, history["Name"], name)
            history["Name"] = name

        update_Prometheus(mac, history)
        device_history[mac] = history  # Atualiza o histórico do dispositivo

    if DEBUG:
        print_device_history(device_history)
    save_state(STATE_FILE, device_history)  # Salva o estado atualizado

def writeDatabase(name, status, duration):
    config = load_config_file()
    if config:
        config_info = config[DATABASE_INFO]
        try:
            conn = psycopg2.connect(
                host=config_info["host"],
                port=5432,
                database=config_info["database"],
                user=config_info["user"],
                password=config_info["password"]
            )
        except Exception as e:
            logging.error("Nao consegui abrir o banco de dados - %e",e)
            return
        try:
            cur = conn.cursor()
        except Exception as e:
            logging.error("Problemas alocando o cursor - %s", e)
            return
        try:
            cur.execute("""
                INSERT INTO eventos_dispositivos
                (nome_dispositivo, status, tempo)
                VALUES (%s, %s, %s)
                """, (name, "online" if not status else "offline", duration)
            )
        except Exception as e:
            logging.error("Problemas escrevendo os dados no banco - %s", e)
            return
        
        conn.commit()
        cur.close()
        conn.close()
        logging.info("dispositivo=%s status=%s tempo=%d", name,"online" if not status else "offline", duration)

def update_history():
    logging.info("Atualizando %s...", STATE_FILE)
    device_history = load_state(STATE_FILE)  # Carrega o estado salvo
    logging.info("Carregados: %d dispositivos - %s", len(device_history), STATE_FILE)

    for mac in device_history:
        history = device_history[mac]

        try:
            active = history["active"]
        except Exception as e:
            logging.error("Adicionando o active no dispositivo %s - %s", mac, e)
            history["active"] = 1
            active = 1

        if active == 1 and not history["current_status"] and history["current_offline"] > TIME_ACTIVE:
            history["active"] = 0
            remove_metrics(mac, history)
        elif not active :
            if history["current_status"]:
                old_history = history
                try:
                    times_reset = history["times_reset"]
                except Exception as e:
                    times_reset = 0
                    logging.error("Não encontrei a variável  %s - %s(%s)", e, old_history["Name"], mac)
                history = {
                    "Name": old_history["Name"],
                    "first_seen": old_history["first_seen"],
                    "current_status": old_history["current_status"],
                    "start_time": time.time(),
                    "max_online": 0,
                    "max_offline": 0,
                    "current_online": 0,
                    "current_offline": 0,
                    "active": 1,
                    "times_reset": times_reset
                }
                logging.info("Depois de muito tempo se ativou de novo de %s(%s)", history["Name"], mac)
            elif history["current_offline"] < TIME_ACTIVE:
                history["active"] = 1
                logging.info("Mudou a variavel TIME_ACTIVE e está ativo novamente %s(%s)", history["Name"], mac)
        elif history["active"] and history["current_status"] and history["current_online"] > RESET_TIME:
            old_history = history
            try:
                times_reset = history["times_reset"] + 1
            except Exception as e:
                logging.error("Zerando os tempos pela primeira vez  %s - %s", mac, e)
                history["times_reset"] = 1
                times_reset = history["times_reset"]
            
            history = {
                "Name": old_history["Name"],
                "first_seen": old_history["first_seen"],
                "current_status": old_history["current_status"],
                "start_time": time.time(),
                "max_online": 0,
                "max_offline": 0,
                "current_online": 0,
                "current_offline": 0,
                "active": 1,
                "times_reset": times_reset
            }
            logging.info("O %s(%s) foi resetado pela %d vez.", history["Name"], mac, history["times_reset"])

        update_Prometheus(mac, history) 

        device_history[mac] = history

    if DEBUG:
        print_device_history(device_history)
    save_state(STATE_FILE, device_history)  # Salva o estado atualizado

def remove_metrics(mac, history):
    name = history["Name"]
    logging.info("removendo a metrica de %s(%s)", name, mac)
    safe_remove(device_status, mac, name) 
    safe_remove(max_offline_time, mac, name)
    safe_remove(max_online_time, mac, name)
    safe_remove(current_offline_time, mac, name)
    safe_remove(current_online_time, mac, name)
    safe_remove(device_active, mac, name)

def update_Prometheus(mac, history):
    device_status.labels(
        mac=mac,
        device_name=history["Name"]
    ).set(history["current_status"])

    max_online_time.labels(
        mac=mac,
        device_name=history["Name"]
    ).set(history["max_online"])

    max_offline_time.labels(
        mac=mac,
        device_name=history["Name"]
    ).set(history["max_offline"])

    current_online_time.labels(
        mac=mac,
        device_name=history["Name"]
    ).set(history["current_online"])

    current_offline_time.labels(
        mac=mac,
        device_name=history["Name"]
    ).set(history["current_offline"])

    device_active.labels(
        mac=mac,
        device_name=history["Name"]
    ).set(history["active"])

def safe_remove(metric, mac, name):
    try:
        metric.remove(mac, name)
    except KeyError:
        pass

def remove_history_state():
    mac_dictionary = load_mac_dictionary(MAC_FILE)
    device_state = load_state(STATE_FILE)  # Carrega o estado salvo

    valid_macs = {mac.lower() for mac in mac_dictionary.keys()}
        
    device_state_filtrado = {
        mac: data
        for mac, data in device_state.items()
        if mac.lower() in valid_macs
    }

    removidos = [
        mac for mac in device_state
        if mac.lower() not in valid_macs
    ]    

    if removidos:
        logging.info("Removidos %d dispositivos: ", len(removidos))
        for mac in removidos:
            logging.info("Removido %s(%s)", device_state[mac].get("Name"), mac)
            remove_metrics(mac, device_state[mac])
            writeDatabaseRecord("removidos", mac, device_state[mac])
    else:
        logging.info("Nenhum dispositivo removido. Todos os MACs existem no %s.", MAC_FILE)

    save_state(STATE_FILE, device_state_filtrado)  # Salva o estado atualizado

def writeDatabaseRecord(DBase, mac, history):
    config = load_config_file()
    if config:
        config_info = config[DATABASE_INFO]
        try:
            conn = psycopg2.connect(
                host=config_info["host"],
                port=5432,
                database=config_info["database"],
                user=config_info["user"],
                password=config_info["password"]
            )
        except Exception as e:
            logging.error("Nao consegui abrir o banco de dados - %e",e)
            return
        try:
            cur = conn.cursor()
        except Exception as e:
            logging.error("Problemas alocando o cursor - %s", e)
            return
        try:
            query = sql.SQL("""
                INSERT INTO {} (
                    mac_address,
                    nome,
                    first_seen,
                    current_status,
                    start_time,
                    max_online,
                    max_offline,
                    current_online,
                    current_offline,
                    active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (mac_address)
                DO UPDATE SET
                    nome = EXCLUDED.nome,
                    current_status = EXCLUDED.current_status,
                    start_time = EXCLUDED.start_time,
                    max_online = EXCLUDED.max_online,
                    max_offline = EXCLUDED.max_offline,
                    current_online = EXCLUDED.current_online,
                    current_offline = EXCLUDED.current_offline,
                    active = EXCLUDED.active
            """).format(sql.Identifier(DBase))

            cur.execute(query, (
                mac,
                history["Name"],
                history["first_seen"],
                bool(history["current_status"]),
                history["start_time"],
                history["max_online"],
                history["max_offline"],
                history["current_online"],
                history["current_offline"],
                bool(history["active"])
            ))
        except Exception as e:
            logging.error("Problemas escrevendo os dados no banco - %s", e)
            return
        
        conn.commit()
        cur.close()
        conn.close()

def DatabaseBackup():
    logging.info("Fazendo o backup no SQL")
    device_state = load_state(STATE_FILE)  # Carrega o estado salvo
    config = load_config_file()
    if config:
        config_info = config[DATABASE_INFO]
        try:
            conn = psycopg2.connect(
                host=config_info["host"],
                port=5432,
                database=config_info["database"],
                user=config_info["user"],
                password=config_info["password"]
            )
        except Exception as e:
            logging.error("Nao consegui abrir o banco de dados - %e",e)
            return
        try:
            cur = conn.cursor()
        except Exception as e:
            logging.error("Problemas alocando o cursor - %s", e)
            return
    for mac, data in device_state.items():
        try:
            query = sql.SQL("""
                INSERT INTO {} (
                    mac_address,
                    nome,
                    first_seen,
                    current_status,
                    start_time,
                    max_online,
                    max_offline,
                    current_online,
                    current_offline,
                    active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (mac_address)
                DO UPDATE SET
                    nome = EXCLUDED.nome,
                    current_status = EXCLUDED.current_status,
                    start_time = EXCLUDED.start_time,
                    max_online = EXCLUDED.max_online,
                    max_offline = EXCLUDED.max_offline,
                    current_online = EXCLUDED.current_online,
                    current_offline = EXCLUDED.current_offline,
                    active = EXCLUDED.active
            """).format(sql.Identifier("device_state"))

            cur.execute(query, (
                mac,
                data["Name"],
                data["first_seen"],
                bool(data["current_status"]),
                data["start_time"],
                data["max_online"],
                data["max_offline"],
                data["current_online"],
                data["current_offline"],
                bool(data["active"])
            ))
        except Exception as e:
            logging.error("Problemas escrevendo os dados no banco - %s", e)
            return
    conn.commit()
    cur.close()
    conn.close()
    logging.info("Backup realizado com sucesso - %d registros", len(device_state))

if __name__ == "__main__":
    setup_logging()
    start_http_server(EXPORTER_PORT)
    logging.info(f"Prometheus Exporter iniciado na porta {EXPORTER_PORT}")

    while True:
        init_timer = perf_counter()
        logging.info("Atualizando métricas...")
        config = load_config_file()
        if not config:
            logging.warning("No configuration available. Skipping send_file().")
        else:
            config_info = config[SECTION]
            DEBUG = str_to_bool(config_info["debug"])
            TIME_ACTIVE = config_info["time_active"]
            RESET_TIME = config_info["time_online_to_reset"]
            logging.info(f"TIME_ACTIVE: {TIME_ACTIVE} - RESET_TIME: {RESET_TIME}")

        update_metrics()
        update_history()
        remove_history_state()
        DatabaseBackup()
        exec_time = timedelta(seconds=int(perf_counter()-init_timer))
        logging.info(f"Métricas atualizadas em {exec_time}. Aguardando próximo scan...")
        time.sleep(SCAN_INTERVAL)
