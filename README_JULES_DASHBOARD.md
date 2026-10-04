# Integración del Dashboard de Encargos Jules

Esta es una guía breve de despliegue, validación y rollback para añadir el dashboard de lectura de encargos de Jules preservando la seguridad y los datos actuales.

## Despliegue Manual (Preflight)

1. Verificar que el volumen donde existe la base original tenga la ruta esperada (`/home/ubuntu/.local/share/ia-mcp-vps/coding-jobs`). Si es distinta, ajustar en el volumen del servicio `jules-exporter` en `compose.yaml`.
2. Validar que la configuración actual es válida comparándola contra el entorno existente.
3. Ejecutar `docker compose pull` y `docker compose up -d` para desplegar el exportador y aplicar los cambios.
4. Grafana auto-descargará el plugin `frser-sqlite-datasource` por la variable de entorno y aprovisionará el origen de datos.

## Smoke Test (Validación posterior)

1. Abrir Grafana y revisar el origen de datos (Datasources) "SQLite_Jules". No se puede modificar ni editar desde UI porque es provisionado por archivo.
2. Abrir Dashboards y localizar la carpeta General o la que defina provisionings con el dashboard "Encargos Jules".
3. Validar que la tabla muestra datos reales sin los campos de evento, log, o payload.
4. Revisar que la estadística superior (Estado registrado por el MCP) reporte Exportación Exitosa con hora reciente.

## Rollback

Para deshacer los cambios, limítese a revertir el archivo `compose.yaml` (borrando los bloques de `jules-exporter`, `jules_jobs_exported`, y los nuevos volúmenes/variables de entorno de `grafana`) y reinicie el stack con `docker compose up -d`.

No es necesario borrar volúmenes de forma manual, pero en caso estricto puede eliminarse `prometheus_jules_jobs_exported` sin riesgo, ya que sus datos son puramente temporales y regenerables.
