# Validación de COIRTECH Asistencias V4

**Versión entregada: 19.0.4.0.0 · Fecha: 23 de noviembre de 2026**

## Resultado

**123 pruebas reales ejecutadas en el ORM de Odoo 19: 0 fallos, 0 errores.**

La instalación del módulo, sus modelos, vistas XML, ACL y reglas se realizó en una base PostgreSQL aislada. Se ejecutaron las regresiones de versiones anteriores junto con las nuevas pruebas V4. El contador de 143 que aparece en las estadísticas internas incluye preparación de clases; el resultado de pruebas funcionales post-install es 123.

| Grupo | Pruebas |
|---|---:|
| Comidas originales | 13 |
| Seis movimientos, bloqueo y autorización V2 | 17 |
| Reportes V2 | 5 |
| Faltas V3 | 22 |
| Reportes V3 | 6 |
| Vista unificada V3 | 6 |
| Proyección Gantt y permisos, incluidas mejoras V4 | 12 |
| Exclusión y ausencias aprobadas V4 | 28 |
| Reportes V4 | 8 |
| Vista diaria V4 | 6 |
| **Total** | **123** |

Se corrigieron durante la validación la lectura de filas excluidas que ya estaban cargadas, el uso del selector de empleados para usuarios sin permisos privados de RH y los escenarios de prueba que debían respetar las restricciones nativas de solicitudes superpuestas y versiones de empleado.

## Runtime utilizado

- Código oficial de Odoo 19 Community, commit `e06b404aef857d606e302814324e3fb97cdd9aec`.
- Python 3.12 y PostgreSQL 17.12, ejecutados en un entorno de prueba local.
- Módulos nativos completos `hr_attendance`, `hr_holidays`, `calendar` y sus dependencias y puentes automáticos aplicables, incluido `hr_holidays_attendance`.
- Los 851 archivos de los nueve módulos oficiales adicionales necesarios para Ausencias se cotejaron mediante hash de objeto Git contra ese commit.
- No se crearon módulos ficticios para sustituir Ausencias, Asistencias ni Enterprise.

## Casos comprobados

- Casilla desmarcada por defecto; control de escritura por RH/Administración de Asistencias; historial con responsables y fechas.
- Exclusión del Reporte en todos los periodos, búsquedas, agrupaciones, selecciones nativas, IDs previamente cargados, lectura de IDs solos, Excel y PDF.
- Una selección totalmente excluida queda vacía; no pasa a incluir a todos los empleados.
- Empleados archivados sin nuevas faltas; reincorporación de excluidos sin crear faltas de los días excluidos.
- Conservación de entradas y uso del quiosco mientras el empleado está excluido del reporte.
- Cuatro categorías explícitas, tipo aprobado sin correspondencia, solicitudes pendientes de aprobación y de segunda aprobación.
- Ausencias reales por día, medio día y horas; permiso por horas que cubre una jornada corta completa.
- Permiso parcial antes del cierre, revisión después del último tramo exigible y resolución por una entrada real.
- Solapes reales entre solicitudes o entre asistencia y permiso; intervalos contiguos sin falso conflicto; horas autorizadas sin doble conteo.
- Aprobaciones retroactivas, cancelación actual e histórica, preservación del indicador original y ausencia de relleno automático del pasado.
- Activación del control cuando ya existían permisos aprobados; sincronización inicial y recuperación de cierres parciales pendientes tras una interrupción de viernes a lunes.
- Corte fijo de las 09:00, fines de semana, festivos, contratos explícitos y conservación de la política V3 para calendarios flexibles sin permiso aprobado.
- Permisos por compañía, responsables de Asistencias sin permisos privados de RH, filtros de empleados mediante el mixin nativo de Odoo 19 y acceso denegado a portal.
- Campos de permisos sanitizados: sin diagnósticos, descripciones privadas ni documentos en el reporte.
- La proyección Gantt reconoce los roles nativos sin depender de la implicación del lector propio y conserva las reglas de los modelos originales.

## Actualización real V3 → V4

Se instaló la V3 original en una base separada y se guardó una muestra antes de actualizar. Se comprobó después:

| Registro o condición | Resultado |
|---|---|
| 4 asistencias originales | Conservadas, con sus campos y horas. |
| 2 salidas de trabajo | Conservadas. |
| 1 autorización adicional consumida | Conservada; continúa bloqueando otra entrada. |
| 2 solicitudes nativas ya aprobadas antes de V4 | Conservadas e incorporadas al reporte. |
| 11 indicadores originales V3 | Conservan identidad, empleado, compañía, fecha y fecha de detección. |
| Jornada de 9 horas con comida y salidas | Conserva las 9 horas pagadas, sin sumar ni descontar dos veces. |
| Comida abierta | Permanece abierta. |
| Permiso completo con falta anterior | Se muestra VACACIONES tras la correspondencia del tipo. |
| Permiso parcial con falta anterior y sin asistencia | Se muestra FALTA CON SUELDO — REVISAR RH. |
| Faltas históricas nuevas o asistencias ficticias durante la actualización | Ninguna. |

Estos datos pertenecen exclusivamente a la muestra de prueba, no a la base de producción del cliente.

## Descargas reales y revisión visual

Se inició el servidor HTTP de la base de prueba y se utilizaron los controladores reales de Odoo:

- Lectura autenticada de 15 filas del Reporte con horas reales, FALTA, VACACIONES y revisión de RH.
- Descarga real XLSX con hojas Resumen y Detalle, categorías y duraciones separadas.
- Descarga real PDF a través de QWeb y wkhtmltopdf 0.12.6.1.
- El acceso anónimo al archivo Excel fue rechazado.
- Se renderizaron y revisaron visualmente las seis páginas A4 horizontales del PDF de prueba. Las columnas nuevas, periodos y motivos caben en las tablas; no se observaron texto superpuesto, columnas cortadas ni encabezados de jornada separados de su tabla. Solo las FALTAS automáticas usan el rojo de falta.

Los archivos con datos de prueba, bases, servidores y dependencias del runtime no se incluyen en el ZIP instalable.

## Alcance que requiere Odoo 19 Enterprise real

Las pruebas anteriores validan el backend y la proyección SQL de Gantt, incluidos sus permisos. **No se ejecutó la interfaz visual nativa de `web_gantt`/`hr_attendance_gantt` Enterprise**, porque ese runtime no está disponible en este entorno.

El puente incluye `tests/test_enterprise_gantt.py`, que debe ejecutarse en una base Enterprise de Staging con sus módulos reales. Comprueba el `get_gantt_data` nativo, los roles de Asistencias, las faltas virtuales y la ausencia de nuevos campos calculados almacenados que intenten escribir en la vista SQL.

Antes de aplicar la actualización a producción, comprobar en Staging el tablero original con los perfiles reales de la empresa, la llegada posterior a las 09:00, la exclusión, un permiso aprobado y la convivencia con Studio u otros complementos instalados. Esta entrega corrige la ACL del módulo, pero no sustituye la comprobación de reglas adicionales particulares de esa base.

## Comandos de referencia para un entorno de pruebas Odoo

```bash
odoo-bin -d BASE_DE_PRUEBAS -u coirtech_attendance_meal_control --test-enable --test-tags /coirtech_attendance_meal_control --stop-after-init
```

En Enterprise, con el puente y sus dependencias instalados:

```bash
odoo-bin -d BASE_ENTERPRISE_DE_PRUEBAS -u coirtech_attendance_absence_gantt --test-enable --test-tags /coirtech_attendance_absence_gantt --stop-after-init
```

No ejecutar pruebas automatizadas sobre una base de producción.
