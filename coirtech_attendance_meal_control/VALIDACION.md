# Verificación de la versión 19.0.2.0.0

**Fecha:** 20 de noviembre de 2026. **Módulo:** `coirtech_attendance_meal_control`.

## Entorno y alcance

Instalación aislada real de Odoo 19 Community, código oficial `odoo/odoo`, rama `19.0`, revisión `e06b404aef857d606e302814324e3fb97cdd9aec`. Python 3.12, PostgreSQL 17 y wkhtmltopdf 0.12.6.1 con Qt parcheado. Se instalaron Asistencias y sus dependencias reales.

No se accedió ni se modificó la base de COIRTECH. La comprobación en `odometro` permite revisar la convivencia con Enterprise, Studio, los demás módulos y el dispositivo y lector reales.

## Actualización de V1

Se instaló V1, se prepararon registros y se actualizó el mismo módulo a V2 con sus vistas, permisos, asistentes, reportes y recursos del quiosco. Se comprobaron estos cuatro casos antes y después:

| Registro anterior | Resultado |
|---|---|
| Jornada COIRTECH completa con comida pagada | Conserva horarios y total de nueve horas. |
| Jornada V1 cerrada sin regreso de comida | Conserva el regreso vacío y su condición pendiente. |
| Jornada COIRTECH abierta, en comida | Permanece abierta con sus horarios registrados. |
| Asistencia histórica nativa | Conserva el cálculo original de Odoo. |

La actualización no inventa movimientos faltantes. Las nuevas jornadas aplican las restricciones de V2, incluida la obligación de regresar antes de Salida final.

## Pruebas automatizadas

La ejecución integrada terminó con **35 pruebas, 0 fallos y 0 errores**:

| Archivo incluido | Pruebas | Cobertura |
|---|---:|---|
| `tests/test_meal_control.py` | 13 | Comida pagada, historial, secuencias, correcciones, secciones y protección de datos. |
| `tests/test_v2_workflow.py` | 17 | Salidas temporales, bloqueo, autorizaciones, permisos y cambios de fecha. |
| `tests/test_v2_reports.py` | 5 | Excel real, datos pendientes, suma de jornadas, PDF, filtros y permisos. |

Después de reforzar la protección de campos calculados almacenados, se volvió a cargar el código final y se repitió el caso afectado: **1 prueba, 0 fallos y 0 errores**.

Casos verificados:

- Jornada de 08:00 a 17:00 con comida y varias salidas temporales: nueve horas, sin descontar ni duplicar los intervalos pagados.
- Una comida o salida temporal abierta solo acepta su regreso. No se superponen ni permiten cerrar la jornada.
- Bloqueo tras Salida final durante esa fecha local, también desde la creación nativa, con `sudo`, valores predeterminados y cargas por lotes en orden inverso.
- Uso de la zona horaria efectiva del empleado. Una jornada nocturna sigue abierta al cambiar de día; el cierre bloquea el día local de la salida.
- Autorización de un solo uso, fecha y motivo, responsable asignado por el servidor y consumo registrado. Las revocadas o de fecha incorrecta no desbloquean.
- Rechazo de solicitudes antiguas, incluso después de una salida y regreso que devuelven al mismo estado de trabajo.
- Correcciones de RH con motivo, auditoría, límites de jornada y ausencia de superposiciones.
- Protección frente a modificación directa, reasignación y borrado de movimientos.
- Empresas con el control desactivado conservan el funcionamiento nativo.

Las pruebas usan registros reales de Odoo; algunos casos fijan la hora para reproducir jornadas de forma determinista.

## HTTP y formulario administrativo

Se probaron sesiones y solicitudes reales: identificación sin marcar asistencia, PIN, aislamiento por empresa, acciones vinculadas a sesión e identidad, rechazo de reenvíos y bloqueo del marcado nativo antiguo mientras COIRTECH está activo.

El recorrido V2 incluyó los seis movimientos y dos salidas temporales dentro de una sola asistencia. Se verificaron el rechazo de cierre con regreso pendiente, bloqueo de nueva entrada y consumo único de una autorización.

Dos intentos simultáneos de entrada produjeron **una sola asistencia**. Se comprobó también la creación de una autorización con la utilidad `Form` de Odoo y la vista real: el servidor completa empresa y datos de auditoría.

## Quiosco

Se validó la extensión con la clase, plantillas y compilador Owl oficiales de Odoo 19. Las pruebas de componentes en JSDOM cubrieron identificación manual, PIN y credencial sin marcado automático; seis botones según estado; comida; salidas repetidas; jornada cerrada; limpieza de identidad; configuración desactivada y fallos de comunicación/configuración.

Odoo compiló y sirvió los paquetes JavaScript y CSS reales de V2.

**Las pruebas de componentes no equivalen a una prueba visual de extremo a extremo en una tableta real.** Chromium no pudo ejecutarse en este entorno por una restricción de sockets. Debe comprobarse el dispositivo y lector habituales en la rama de pruebas.

## Excel y PDF

Se descargó un `.xlsx` real desde el asistente autenticado. Se verificaron las hojas **Resumen** y **Detalle**, fechas y duraciones numéricas, todos los movimientos, intervalos pendientes vacíos, sumas sin duplicación y texto que no se interpreta como fórmula. Ambas hojas se revisaron visualmente.

La descarga anónima fue rechazada. Los filtros y permisos impidieron solicitar datos de una empresa ajena. Varias jornadas del mismo día suman sus duraciones cerradas sin contar el hueco entre ellas. Las jornadas abiertas se identifican y no se presentan como horas completas confirmadas.

El PDF se generó con el controlador real, QWeb y wkhtmltopdf. Se revisaron las páginas renderizadas: legibilidad, columnas completas y agrupación de jornadas con sus movimientos. Incluye resumen y detalle cronológico, con varias salidas temporales.

Los archivos de muestra, datos y credenciales de prueba no se incluyen en el ZIP.

## Reproducir las pruebas incluidas

En una base de pruebas, con el módulo en `addons_path`, un administrador técnico puede ejecutar:

```bash
odoo-bin -d BASE_DE_PRUEBAS -u coirtech_attendance_meal_control --test-enable --test-tags /coirtech_attendance_meal_control --stop-after-init
```

En primera instalación se usa `-i` en lugar de `-u`. Configuración de PostgreSQL, rutas y demás parámetros dependen del entorno. XlsxWriter debe estar disponible en el Python de Odoo.

## Comprobación en odometro

Con un empleado de prueba: identificar y cancelar; registrar comida y dos salidas de trabajo; comprobar total pagado; cerrar; intentar otra entrada; autorizar una nueva entrada una sola vez; generar Excel/PDF filtrados por empresa; revisar registros anteriores.

Si hay turnos nocturnos, comprobar la regla de `README.md`: una salida final por la mañana bloquea el resto de ese día local; otro turno nocturno de ese mismo día requiere autorización.

La validación cubre asistencia, movimientos, permisos, actualización y reportes. No certifica reglas de nómina, horas extra o faltas, que el módulo no implementa. La base de pruebas, el servidor Odoo y sus dependencias no forman parte de la entrega.
