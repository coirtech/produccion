# COIRTECH — Faltas en el Gantt original

**V4.2 · Odoo 19 · Versión 19.0.4.2.0**

Complemento para Odoo 19 Enterprise. Se instala automáticamente cuando están
instalados `coirtech_attendance_meal_control` y `hr_attendance_gantt`.

Mantiene la acción, los filtros, las plantillas y el JavaScript de Odoo. Las
asistencias reales conservan sus horas, etiqueta y color nativos. Añade al
origen de datos una proyección de las faltas activas: etiqueta **FALTA**, color
rojo y cero horas trabajadas. Los intervalos visuales no se insertan en
`hr.attendance` ni se utilizan como horas trabajadas.

La proyección aplica las reglas de acceso de los modelos originales, incluidas
las restricciones adicionales que existan en cada base. El usuario no puede
editar, mover o borrar el indicador. Si el Gantt solicita abrirlo como una
asistencia, se muestra un mensaje explicativo; no se abre un formulario con
horas ficticias. Cuando Odoo usa la acción de formulario del registro, se abre
el detalle de la falta.

V4 conserva este alcance: los permisos aprobados y las incidencias de RH se
presentan en el Reporte de asistencia. No agrega nuevas barras de vacaciones
al Gantt. Al retirar una FALTA actual por exclusión o por permiso aprobado,
deja de mostrarse su indicador; las asistencias originales permanecen.

La actualización del módulo principal concede lectura explícita de la
proyección a los grupos nativos de oficial, lector de todas las asistencias y
administrador, además del lector propio. Esto evita depender únicamente de
que el grupo de lector propio sea heredado por todos esos usuarios. Se
conservan las reglas por compañía y de cada modelo de origen, sin permisos
globales ni de escritura. Para actualizar una instalación con ambos módulos,
actualiza el principal y este puente.

## Validación

El modelo SQL se puede probar con el ORM real de Odoo 19 Community, sin simular
Enterprise. El puente requiere **validación visual en Odoo 19 Enterprise**:
esta entrega no dispone del runtime `web_gantt`/`hr_attendance_gantt`.

En Staging, comprobar una falta de un empleado sin asistencias, una asistencia
abierta, una cerrada, la llegada después de las 09:00, agrupación por empleado,
permisos por empresa y apertura del indicador. No se han sustituido ni
supuesto nombres de métodos privados del JavaScript Gantt.

`tests/test_enterprise_gantt.py` incluye el acceso de los tres roles nativos
sin la implicación del grupo de lector propio. Esa prueba debe ejecutarse
con el módulo Enterprise real; el resultado de las pruebas Community del
modelo SQL no sustituye su ejecución ni la comprobación visual en Staging.

La prueba de aceptación también comprueba que ningún complemento de la base
añada cálculos almacenados a la proyección. Los campos almacenados calculados
del Odoo 19 verificado se leen como columnas: la proyección nunca debe intentar
recalcular ni guardar una columna de la vista SQL. Si otra extensión añade
campos de ese tipo, hay que declarar sus equivalentes de solo lectura antes de
dar por validada esa combinación de módulos.

V4.2 incorpora la personalización de columnas Excel/PDF en el módulo principal. El código del puente Gantt y la apariencia de las asistencias reales se conservan.
