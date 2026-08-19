# MAC Presence Exporter

Sistema de monitoramento de presença de dispositivos em rede local utilizando ARP, PostgreSQL, Prometheus e Grafana.

## Visão Geral

O MAC Presence Exporter identifica dispositivos conectados à rede através do endereço MAC, registra o histórico de presença em banco de dados PostgreSQL e exporta métricas para monitoramento no Prometheus e visualização em dashboards Grafana.

## Funcionalidades

- Descoberta de dispositivos utilizando arp-scan
- Identificação de dispositivos via MAC Address
- Verificação complementar utilizando nmap
- Histórico de presença
- Persistência em PostgreSQL
- Exportação para Prometheus
- Dashboards Grafana

## Arquitetura

```text
┌─────────────────┐
│ Dispositivos    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ MAC Presence    │
│ Exporter        │
└───────┬─────────┘
        │
        ├─────────────► PostgreSQL
        │
        ▼
   Prometheus
        │
        ▼
     Grafana
```

## Tecnologias

- Python 3
- PostgreSQL
- Prometheus
- Grafana
- Linux
- Raspberry Pi

## Estrutura do Projeto

```text
.
├── mac_presence_exporter.py
├── config.json
├── requirements.txt
├── device_state.json
├── mac_dictionary.json
└── README.md
```

## Pré-requisitos

Antes de instalar o projeto, certifique-se de que os seguintes componentes estejam disponíveis no sistema:

### Sistema Operacional

- Linux (testado em Raspberry Pi OS)

### Aplicativos necessários

- Python 3
- PostgreSQL
- nmap
- arp-scan

Instalação no Debian/Raspberry Pi OS:

```bash
sudo apt update

sudo apt install -y \
    python3 \
    python3-pip \
    nmap \
    arp-scan \
    postgresql-client
```

Verifique a instalação:

```bash
nmap --version
arp-scan --version
python3 --version
```

## Instalação

Clone o repositório:

```bash
git clone git@github.com:paulocfmarques-collab/mac-presence-exporter.git

cd mac-presence-exporter
```

Instale as dependências Python:

```bash
pip3 install -r requirements.txt
```

## Configuração

Configure os parâmetros de acesso ao PostgreSQL no arquivo:

```text
config.json
```

Exemplo:

```json
{
  "database": {
    "host": "localhost",
    "database": "presence",
    "user": "postgres",
    "password": "senha"
  }
}
```

## Execução

```bash
python3 mac_presence_exporter.py
```

## Métricas Exportadas

Exemplos de métricas disponibilizadas:

```text
device_online
device_current_online
device_current_offline
device_max_online
device_max_offline
```

## Dashboard Grafana

### Visão Geral

```text
docs/
```

Exemplo:

```markdown
docs/dashboard.png
```

## Casos de Uso

- Monitoramento residencial
- Controle de presença de dispositivos
- Inventário de equipamentos conectados
- Observabilidade de redes domésticas e pequenas empresas
- Projetos educacionais com Raspberry Pi

## Roadmap

- [ ] API REST
- [ ] Integração com MQTT
- [ ] Alertas via Telegram
- [ ] Descoberta automática de fabricantes
- [ ] Dashboard avançado

## Autor

**Paulo César Furlanetto Marques**

GitHub: https://github.com/paulocfmarques-collab
