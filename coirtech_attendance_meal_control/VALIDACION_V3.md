# Validación de COIRTECH V3 — Odoo 19

**Versión:** 19.0.3.0.0. **Fecha:** 23 de noviembre de 2026.

## Resultado ejecutado

Se instaló y actualizó el módulo base en Odoo 19 Community real, con PostgreSQL 17.12 y Python 3.12. Código oficial de Odoo, rama 19.0, revisión `e06b404aef857d606e302814324e3fb97cdd9aec`. Base de pruebas aislada; no se accedió a la instancia de COIRTECH.

**77 pruebas automatizadas: 0 fallos, 0 errores.** La última ejecución y la actualización V2→V3 terminaron con código de salida 0, sin advertencias de instalación en los logs finales.

| Archivo | Casos | Cobertura principal |
|---|---:|---|
| test_meal_control.py | 13 | Comida pagada, secuencias, correcciones y políticas guardadas. |
| test_v2_workflow.py | 17 | Salidas temporales, regresos, bloqueo y autorizaciones. |
| test_v2_reports.py | 5 | Excel/PDF originales, cálculos pagados, permisos y filtros. |
| test_v3_absences.py | 22 | Corte de las 09:00, zona horaria, fin de semana, calendarios, permisos, contratos, entrada tardía y seguridad. |
| test_v3_reports.py | 6 | Solo faltas, Excel con rojo y horas vacías, PDF, llegada tardía y selección. |
| test_v3_day.py | 6 | Lista unificada, última pareja salida/regreso, etiquetas de estado y permisos fuente. |
| test_gantt_projection.py | 8 | Datos SQL del Gantt, ausencia de asistencias ficticias, valores nativos y acceso. |

El contador interno de estadísticas del framework incluye tareas adicionales de preparación; los 77 casos corresponden al resultado final explícito del ejecutor de pruebas.

## Prueba de actualización de V2 a V3

Se instaló por separado el ZIP original V2, se generaron datos reales con sus APIs y se actualizó a esta versión sin desinstalar. El comparador antes/después confirmó:

- Cuatro asistencias conservadas exactamente.
- Dos salidas de trabajo conservadas.
- Una autorización consumida conservada, que sigue sin permitir una segunda reutilización.
- Jornada de nueve horas pagadas con comida y salidas temporales.
- Jornada abierta que sigue en comida.
- Asistencia histórica nativa con sus horas originales.
- Ninguna falta histórica creada por la actualización.

Versiones comprobadas: **19.0.2.0.0 → 19.0.3.0.0**.

## Qué se comprobó en la pantalla y los reportes

Las vistas XML se cargaron y validaron en Odoo real. Se verificaron el nombre **Reporte de asistencia**, los campos de salida/regreso de trabajo y las decoraciones nativas de las etiquetas: rojo estando fuera y verde tras regresar. Se usan los componentes badge de Odoo, sin reemplazarlos con JavaScript.

Se generaron archivos XLSX reales en las pruebas y se inspeccionaron sus celdas, formatos de color y valores numéricos. FALTA queda en rojo, sin una entrada a las 09:00 ni una duración inventada. Se renderizó QWeb del PDF con faltas y sin asistencias. No se entregan archivos de muestra ni datos de prueba.

La fuente del Gantt preservó los nombres, colores, fechas y horas de asistencias reales abiertas y cerradas. Los indicadores tienen cero horas y existen únicamente en una proyección de lectura: no se insertan filas ficticias en hr.attendance. Se comprobaron las restricciones de escritura y las reglas de registro originales, incluidas reglas adicionales de los modelos fuente.

## Límite de la validación del Gantt

**No se ejecutó el tablero visual de Odoo 19 Enterprise en este entorno.** El complemento coirtech_attendance_absence_gantt está incluido y contiene una prueba para el servidor Enterprise real. Esa prueba y la comprobación visual siguen pendientes en Staging. Las ocho pruebas de la proyección no equivalen a una prueba del frontend Enterprise.

El complemento utiliza la implementación get_gantt_data de hr_attendance_gantt instalado; no sustituye las plantillas ni los colores de las asistencias reales. Otras extensiones pueden añadir campos calculados almacenados a hr.attendance, en cuyo caso la proyección necesita revisar esos campos. La prueba Enterprise detecta esa condición.

Al abrir una falta desde un diálogo que intente tratarla como asistencia, se muestra una explicación. El registro de ausencia real se consulta en **Asistencias → Faltas**. No se puede arrastrar una falta para convertirla en asistencia ni modificarle horas.

## Límites operativos

- El planificador revisa cada minuto a partir de las 09:00; depende de que las acciones programadas estén activas y de la disponibilidad de Odoo.
- Sólo se genera el día actual. Una interrupción que abarque un día completo no se rellena automáticamente como falta histórica.
- Se usa la zona horaria configurada por empresa para el corte; los movimientos conservan su zona efectiva original.
- Se respetan los intervalos del calendario. Los horarios flexibles usan la interpretación nativa de Odoo; sin calendario no hay generación automática. Para días y turnos definidos, configura un horario fijo.
- Los permisos aprobados deben estar representados en el calendario de Odoo; no se infieren justificaciones de texto o mensajes.
- La configuración nativa de ausencia/horas extra queda administrada por Odoo. Si está activa, Odoo puede generar sus propios registros técnicos; este módulo no los genera ni los confunde con una asistencia real.
- Si la pantalla ya estaba abierta, recarga la vista para consultar los cambios. Un Excel/PDF descargado se actualiza al volver a generarlo.

## Ejecutar las pruebas en Odoo.sh

En una base de pruebas, después de colocar las carpetas en addons_path:

```bash
odoo-bin -d BASE_DE_PRUEBAS -u coirtech_attendance_meal_control --test-enable --test-tags /coirtech_attendance_meal_control --stop-after-init
```

En Enterprise, con el complemento instalado, ejecuta también:

```bash
odoo-bin -d BASE_DE_PRUEBAS -u coirtech_attendance_absence_gantt --test-enable --test-tags /coirtech_attendance_absence_gantt --stop-after-init
```

Las rutas y los parámetros de conexión dependen de tu proyecto. En primera instalación usa -i en lugar de -u.

## Comprobación antes de pasar a producción

En Staging, usa un empleado de prueba con calendario laboral. Después de las 09:00 de lunes a viernes, verifica FALTA en lista y Gantt; marca entrada real y recarga para comprobar la retirada. Registra comida y regreso, después salida y regreso de trabajo: sólo sus etiquetas cambian de rojo a verde. Revisa una segunda salida temporal para confirmar que el regreso permanece vacío hasta registrar ese regreso. Genera Excel/PDF y revisa la conservación de tus registros anteriores.
