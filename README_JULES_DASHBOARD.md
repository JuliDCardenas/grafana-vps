# Integración del Dashboard de Encargos Jules

Esta es una guía breve de despliegue, validación y rollback para añadir el dashboard de lectura de encargos de Jules preservando la seguridad y los datos actuales.

## Preflight Checklist (Antes del despliegue)

1. Verificar que la ruta de la base de datos origen es exactamente `/home/ubuntu/.local/share/ia-mcp-vps/coding-jobs/jules_jobs.db`. **Nota de seguridad:** La exportación usando File Bind mounts en modo RO es compatible de forma natural SOLO con esquemas journal en modo `DELETE`. El soporte aislado de archivos `.db-wal` de forma consistente requiere permisos mayores que no se asumen acá. Si el esquema VPS usa `WAL`, esta solución puede reportar `SOURCE_UNAVAILABLE` o lecturas opacas temporalmente, en cuyo caso debe abstenerse de desplegarlo.
2. Verificar que los permisos del archivo `jules_jobs.db` permiten lectura.
3. Verificar la versión activa de Grafana en el sistema y asegurar la compatibilidad con el plugin `frser-sqlite-datasource` (versión 4.0.6 fijada).
4. Sugerencia: Revisar la allowlist del monitor de MCP en `config.yaml` si aplica, pero no editar `.env`.

## Despliegue Selectivo (Patch)

Dado que no queremos destruir o regenerar completamente el stack en `/home/ubuntu/prometheus/docker-compose.yml`, seguiremos estos pasos:

1. Respaldar la configuración actual y los provisionamientos:
   `cp /home/ubuntu/prometheus/docker-compose.yml /home/ubuntu/prometheus/docker-compose.yml.bak`
   `cp -r /home/ubuntu/prometheus/grafana/provisioning /home/ubuntu/prometheus/grafana/provisioning.bak`
2. Modificar el archivo `docker-compose.yml` en producción para:
   - Añadir el bloque `jules-exporter` tal como está en el `compose.yaml` versionado de este repo.
   - Añadir el volumen `jules_jobs_exported` al bloque `volumes:`.
   - Modificar *solo* el servicio `grafana` existente añadiendo las variables de entorno para descargar el plugin (`GF_INSTALL_PLUGINS: frser-sqlite-datasource 4.0.6`) y los nuevos mapeos de volúmenes para `./grafana/provisioning:/etc/grafana/provisioning:ro` y `jules_jobs_exported:/var/lib/grafana-sqlite:ro`.
3. Copiar recursivamente los contenidos de `grafana/provisioning/` de este repositorio a `/home/ubuntu/prometheus/grafana/provisioning/` (usar nombres únicos, como `jules_dashboards.yaml`, para no sobrescribir configuraciones existentes). Copiar la carpeta `jules_exporter`.
4. Construir la nueva imagen localmente:
   `docker compose -f /home/ubuntu/prometheus/docker-compose.yml build jules-exporter`
5. Validar la nueva configuración sin aplicarla:
   `docker compose -f /home/ubuntu/prometheus/docker-compose.yml config`
6. Recrear únicamente los contenedores afectados sin afectar al resto:
   `docker compose -f /home/ubuntu/prometheus/docker-compose.yml up -d --no-deps jules-exporter grafana`

## Smoke Test (Validación posterior)

1. Abrir Grafana y revisar el origen de datos (Datasources) "SQLite_Jules" (uid = SQLite_Jules).
2. Abrir Dashboards y localizar el dashboard "Encargos Jules".
3. Validar que la tabla muestra datos reales sin los campos de evento, log, o payload.
4. Revisar que la estadística superior reporte "Exportación Exitosa" con fecha reciente en el huso horario correcto, o que reporte un error clasificado en caso de falla (y nunca un mensaje de sistema o de ruta privada).

## Rollback Selectivo

Para deshacer los cambios sin afectar los datos de Prometheus/Grafana históricos:

1. Restaurar el archivo compose original y el provisioning original:
   `mv /home/ubuntu/prometheus/docker-compose.yml.bak /home/ubuntu/prometheus/docker-compose.yml`
   `rm -rf /home/ubuntu/prometheus/grafana/provisioning`
   `mv /home/ubuntu/prometheus/grafana/provisioning.bak /home/ubuntu/prometheus/grafana/provisioning`
2. Detener y eliminar explícitamente el exportador introducido:
   `docker stop jules-exporter && docker rm jules-exporter`
3. Recrear Grafana a su estado original sin afectar a otros contenedores:
   `docker compose -f /home/ubuntu/prometheus/docker-compose.yml up -d --no-deps grafana`
4. Opcional: Borrar el volumen exportador temporal si existe (no contiene data única persistente):
   `docker volume rm prometheus_jules_jobs_exported`
