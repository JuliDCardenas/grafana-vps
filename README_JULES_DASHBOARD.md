# Integración del Dashboard de Encargos Jules

Esta es una guía breve de despliegue, validación y rollback para añadir el dashboard de lectura de encargos de Jules preservando la seguridad y los datos actuales.

## Preflight Checklist (Antes del despliegue)

1. Verificar que la ruta de la base de datos origen es exactamente `/home/ubuntu/.local/share/ia-mcp-vps/coding-jobs/jules_jobs.db` y que cuenta con sus archivos WAL si están activos (`.db-wal`, `.db-shm`).
2. Verificar que los permisos de los archivos permiten lectura (RO).
3. Verificar la versión activa de Grafana en el sistema y asegurar la compatibilidad con el plugin `frser-sqlite-datasource` (versión 4.0.6 fijada).
4. No auto-aplicar cambios al `.env` (allowlist MCP).

## Despliegue Selectivo (Patch)

Dado que no queremos destruir o regenerar completamente el stack en `/home/ubuntu/prometheus/docker-compose.yml`, seguiremos estos pasos:

1. Respaldar la configuración actual:
   `cp /home/ubuntu/prometheus/docker-compose.yml /home/ubuntu/prometheus/docker-compose.yml.bak`
2. Modificar el archivo `docker-compose.yml` en producción para:
   - Añadir el bloque `jules-exporter` tal como está en el `compose.yaml` versionado de este repo.
   - Añadir el volumen `jules_jobs_exported` al bloque `volumes:`.
   - Modificar *solo* el servicio `grafana` existente añadiendo las variables de entorno para descargar el plugin (`GF_INSTALL_PLUGINS: frser-sqlite-datasource 4.0.6`) y los nuevos mapeos de volúmenes para `/etc/grafana/provisioning` y `/var/lib/grafana-sqlite`.
3. Copiar las carpetas `grafana/provisioning` y `jules_exporter` a `/home/ubuntu/prometheus/`.
4. Construir la nueva imagen localmente:
   `docker compose build jules-exporter`
5. Validar la nueva configuración sin aplicarla:
   `docker compose config`
6. Recrear únicamente los contenedores afectados:
   `docker compose up -d jules-exporter grafana`

## Smoke Test (Validación posterior)

1. Abrir Grafana y revisar el origen de datos (Datasources) "SQLite_Jules" (uid = SQLite_Jules).
2. Abrir Dashboards y localizar el dashboard "Encargos Jules".
3. Validar que la tabla muestra datos reales sin los campos de evento, log, o payload.
4. Revisar que la estadística superior reporte "Exportación Exitosa" con fecha reciente en el huso horario correcto, o que reporte un error clasificado en caso de falla (y nunca un mensaje de sistema o de ruta privada).

## Rollback Selectivo

Para deshacer los cambios sin afectar los datos de Prometheus/Grafana históricos:

1. Restaurar el archivo compose original:
   `mv /home/ubuntu/prometheus/docker-compose.yml.bak /home/ubuntu/prometheus/docker-compose.yml`
2. Remover el exportador y recrear Grafana a su estado base:
   `docker compose up -d --remove-orphans`
3. Opcional: Borrar el volumen exportador temporal si existe (no contiene data única persistente):
   `docker volume rm prometheus_jules_jobs_exported`
