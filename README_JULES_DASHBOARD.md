# Estado de la Integración del Dashboard de Jules

**BLOQUEO ARQUITECTÓNICO ACTIVO:** La integración automática mediante un contenedor sidecar (`jules-exporter`) montando únicamente el archivo `jules_jobs.db` vía Docker ha sido abortada.

## Motivo Técnico del Bloqueo

Montar un archivo SQLite directamente en Docker (file-only bind mount) sin montar su directorio adyacente o sus archivos journal impide la consistencia transaccional (ACID).
Aunque la base de datos opere en modo `DELETE` (sin WAL o SHM), SQLite puede ejecutar volcados de caché (spilled pages) al archivo principal antes de un COMMIT definitivo, respaldando los datos originales en el `-journal`.
Si ocurre un crash o lectura paralela y el lector (nuestro sidecar Docker) no tiene acceso al archivo `-journal` para efectuar el rollback, el lector verá datos `UNCOMMITTED` (estado de corrupción lógica). Dado que no podemos ampliar los permisos de seguridad para montar el directorio entero (contiene payloads privados), la arquitectura file-only para DBs vivas está vetada.

## Siguientes Pasos (Propuesta Opción A)

En lugar de extraer la data desde fuera mediante polling en Docker, la exportación deberá ser programada de manera interna y sanitizada atómicamente por el proceso padre (IA-mcp-vps), ya que dicho proceso corre con visibilidad completa del directorio y journals correctos.

1. **Modificación externa:** Se debe programar que el MCP genere periódicamente un volcado (`jules_jobs_public.db`) sanitizado (solo columnas de status).
2. **Reactivación:** Una vez exista dicho volcado, Grafana simplemente montará ese archivo como read-only en el stack de Prometheus.
3. Se conservan temporalmente los archivos de aprovisionamiento de Grafana (`grafana/provisioning/`) en este PR en estado inactivo hasta que el MCP entregue el soporte, a fin de no desechar el esquema visual ya validado.

## Rollback de la UI (Para limpiar instalaciones previas)

Si se desplegaron los dashboards localmente de manera manual, para retirarlos de forma segura sin afectar los otros dashboards:

1. Elimine exclusivamente los archivos nuevos introducidos en el aprovisionamiento original en `/home/ubuntu/prometheus/grafana/provisioning/` (p. ej., `jules_dashboards.yaml`, `dashboards/jules_jobs.json`, `datasources/sqlite.yaml`). NO elimine el directorio entero.
2. Elimine las directivas de volumen y el plugin instalados en `docker-compose.yml` de Grafana.
3. Recree Grafana a su estado original sin afectar a otros contenedores:
   `docker compose -f /home/ubuntu/prometheus/docker-compose.yml up -d --no-deps grafana`
