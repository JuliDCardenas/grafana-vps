# grafana-vps

Configuración versionada del stack de monitoreo del VPS:

- Prometheus
- Node Exporter
- cAdvisor
- Grafana
- MCP oficial de Grafana

## Seguridad

- El archivo `.env` nunca se versiona.
- `.env.example` contiene únicamente placeholders.
- Notion AI se conecta al MCP mediante HTTPS y un Bearer token independiente.
- El MCP accede a Grafana mediante una cuenta de servicio.
- No se incluyen volúmenes, métricas, bases de datos ni credenciales del VPS.

## Preparación

```bash
cp .env.example .env
chmod 600 .env
```

Completar en `.env`:

- `GF_SECURITY_ADMIN_PASSWORD`
- `GRAFANA_SERVICE_ACCOUNT_TOKEN`
- `MCP_GRAFANA_SERVER_TOKEN`

## Despliegue previsto

```bash
docker compose config
docker compose pull
docker compose up -d
```

Antes del despliegue real se debe comparar esta configuración con el stack activo y crear backup de los archivos actuales.

## Endpoint MCP previsto

```text
https://mcp-grafana.julidcardenas.site/mcp
```
