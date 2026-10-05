# Integración del Dashboard de Encargos Jules (Contrato V1)

Esta es una guía breve de integración, validación y rollback para añadir el dashboard de lectura de encargos de Jules a la instancia activa de Grafana, asumiendo la arquitectura de Contrato V1.

**Arquitectura V1:**
En lugar de extraer la data en tiempo real mapeando archivos SQLite directamente, el proceso MCP (`IA-mcp-vps`) está programado de manera independiente para escribir una base de datos sanitizada `exported_jobs.db` en un directorio exclusivo. Grafana se limita a montar este directorio como read-only, evitando riesgos de seguridad (sin acceso a logs o secretos) e integridad (sin problemas de concurrencia ACID de archivos ocultos).

## Preflight Checklist (Antes del despliegue)

1. Verificar que el proceso MCP en la máquina host esté configurado y generando correctamente los volcados en la ruta: `/home/ubuntu/.local/share/ia-mcp-vps/jules-observability/`. Si la salida no existe o no está lista en este directorio, detenga el despliegue.
2. Verificar la versión activa de Grafana en el sistema y asegurar la compatibilidad con el plugin `frser-sqlite-datasource` (versión 4.0.6 fijada).
3. Asegúrese de NO auto-aplicar credenciales o cambios al `.env` del host. Revise la *allowlist* en `config.yaml` de manera manual si es aplicable.

## Despliegue Selectivo (Patch)

Dado que no queremos destruir o regenerar completamente el stack histórico, seguiremos estos pasos:

1. Respaldar la configuración actual:
   `cp /home/ubuntu/prometheus/docker-compose.yml /home/ubuntu/prometheus/docker-compose.yml.bak`
2. Modificar el archivo `docker-compose.yml` en el host añadiendo la instalación del plugin y el nuevo volumen al servicio `grafana`:
   ```yaml
   # Fragmento para agregar bajo grafana > environment:
   GF_INSTALL_PLUGINS: frser-sqlite-datasource 4.0.6

   # Fragmentos para agregar bajo grafana > volumes:
   - ./grafana/provisioning_jules:/etc/grafana/provisioning_jules:ro
   - type: bind
     source: /home/ubuntu/.local/share/ia-mcp-vps/jules-observability
     target: /var/lib/grafana-sqlite
     read_only: true
     bind:
       create_host_path: false
   ```
3. Copiar recursivamente la carpeta `grafana/provisioning_jules` desde este repositorio hacia `/home/ubuntu/prometheus/grafana/provisioning_jules`. **Nota:** Se utiliza una carpeta independiente (`provisioning_jules`) y se añade un volumen separado de lectura para no interferir con las rutas de `provisioning` nativas o ya configuradas de Grafana.
4. Validar la nueva configuración de Compose sin aplicarla globalmente:
   `docker compose -f /home/ubuntu/prometheus/docker-compose.yml config`
5. Recrear únicamente el contenedor de Grafana de forma aislada:
   `docker compose -f /home/ubuntu/prometheus/docker-compose.yml up -d --no-deps grafana`

## Smoke Test (Validación posterior)

1. Abrir Grafana y revisar que el origen de datos (Datasources) "SQLite_Jules" cargó exitosamente y señala a `/var/lib/grafana-sqlite/exported_jobs.db`.
2. Abrir Dashboards y localizar el dashboard "Encargos Jules".
3. Validar que la tabla muestra datos reales correspondientes al status, remote_state, repository y fechas.
4. Revisar que la estadística superior reporte el estado (ej. "Exportación Exitosa", "Error: SOURCE_UNAVAILABLE", o "Desactualizado" si los volcados del backend se estancaron en el tiempo).

## Rollback Selectivo

Para deshacer los cambios limitándonos a remover solo lo introducido por Jules y sin afectar la data general del stack:

1. Restaurar el archivo compose original:
   `mv /home/ubuntu/prometheus/docker-compose.yml.bak /home/ubuntu/prometheus/docker-compose.yml`
2. Eliminar el directorio inerte de provisión:
   `rm -rf /home/ubuntu/prometheus/grafana/provisioning_jules`
3. Recrear Grafana a su estado original sin afectar el resto de componentes (Prometheus, etc) y sin emitir flags `--remove-orphans`:
   `docker compose -f /home/ubuntu/prometheus/docker-compose.yml up -d --no-deps grafana`
