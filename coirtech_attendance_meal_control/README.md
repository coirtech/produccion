# COIRTECH Asistencias V4.4

**Odoo 19 · Versión 19.0.4.4.0 · Nombre técnico: `coirtech_attendance_meal_control`**

Esta actualización muestra las solicitudes de Tiempo personal con el nombre de su tipo original, aunque todavía no tengan aprobación final. Corrige además el error de acceso a `coir_meal_section_id` al consultar empleados desde Manufactura u otras aplicaciones con un usuario sin acceso privado a Recursos Humanos.

## Corrección V4.4 — Vacaciones mostrado erróneamente como Home Office

- El nombre mostrado se extrae siempre del `holiday_status_id` de la solicitud original (`hr.leave`) del empleado, sin buscar tipos por nombre ni ignorar mayúsculas/minúsculas. `Vacaciones` y `vacaciones` se mantienen como tipos separados.
- Cuando la empresa pertenece a México, el reporte usa la traducción activa `es_MX` (o `es_419`/`es_ES` si no está disponible), incluso si el contacto de la empresa conserva `en_US`. Esto evita mostrar un texto traducido al inglés, como `Home Office`, cuando el tipo se ve como `Vacaciones` en Tiempo personal. Para empresas fuera de México se conserva el idioma de la empresa.
- Al actualizar, una migración vuelve a sincronizar los indicadores previamente guardados desde las solicitudes originales; no cambia solicitudes, estados de aprobación, asistencias ni periodos reales.
- La columna Ausencia/Incidencia, la vista de reporte y Excel/PDF comparten el valor corregido. Se conservan solicitudes pendientes sin texto «Pendiente de aprobación» y las futuras ocultas.
- Si al actualizar no cambia el texto, revisa en la ficha de la **empresa** el campo País (México), el idioma instalado y las traducciones del tipo de Tiempo personal; no elimines ni renombres solicitudes.

## 1. Cambios de esta versión

### Nombre original de Tiempo personal

La columna **Ausencia / incidencia** utiliza el nombre del tipo de Tiempo personal asociado a la solicitud. Por ejemplo, si el tipo se llama **Permiso para trámite**, ese nombre aparece en el reporte. Respeta las mayúsculas y minúsculas del nombre original. Si el tipo tiene traducciones, utiliza el idioma del contacto de la empresa del empleado; si está vacío, utiliza el nombre original en inglés. Así el reporte compartido no cambia de idioma según el usuario o la tarea automática que lo actualice.

Ya no es necesario asignar una categoría adicional entre Vacaciones, Falta con sueldo, Falta sin sueldo o Incapacidad. Se retira el menú de correspondencias COIRTECH. Los tipos originales de Odoo y sus solicitudes se conservan; un tipo nuevo puede utilizarse sin configurar una correspondencia. El campo de correspondencia anterior se conserva oculto por compatibilidad, pero no decide el texto del reporte.

Cambiar el nombre del tipo en Tiempo personal actualiza la información derivada de las solicitudes vigentes. El reporte solo copia el tipo y el periodo; no copia notas privadas, diagnósticos ni adjuntos.

### Solicitudes sin aprobación final

Se incluyen las solicitudes presentadas que están por aprobar, las que requieren una segunda aprobación y las aprobadas. El reporte no añade **Pendiente de aprobación** ni genera una alerta por ese estado. Las solicitudes rechazadas o canceladas dejan de representar una ausencia vigente.

Esto no aprueba la solicitud en Odoo: su flujo de aprobación, saldos y efectos nativos permanecen a cargo de Tiempo personal. Las asignaciones de saldo no son solicitudes de ausencia y no se muestran como tales.

| Dato del reporte | Qué representa |
|---|---|
| Ausencia / incidencia | Nombre original del tipo, con PARCIAL o REVISAR RH cuando corresponda por las reglas existentes. |
| Tipo de ausencia | Nombre original, sin indicar si está por aprobar. |
| Periodo de ausencia | Intervalos de las solicitudes vigentes, incluidas las presentadas sin aprobación final. |
| Horas autorizadas | Solo intervalos con aprobación final, sin duplicar periodos superpuestos. |
| Horas de jornadas cerradas | Tiempo de las asistencias reales; incluye las comidas y salidas temporales pagadas de jornadas COIRTECH. |

Las horas de una solicitud sin aprobar no se convierten en horas autorizadas ni trabajadas. Las horas autorizadas tampoco se suman a las horas de jornada. El estado visible **Ausencia registrada** describe el indicador del reporte, no una aprobación de Tiempo personal.

### Corrección de perfiles públicos

`coir_meal_section_id` queda limitado al perfil privado de Recursos Humanos. Esto evita que las consultas públicas de empleados intenten leerlo. Se conservan las secciones existentes, sus asignaciones y la sección guardada en cada asistencia. Los usuarios de Manufactura no necesitan recibir permisos adicionales de RH para corregir este error.

El quiosco sigue usando sus servicios de identificación autorizados. Las acciones de comida, salidas temporales, escaneo y reportes utilizan el mismo flujo anterior.

## 2. Reglas de ausencia e incidencia

Se comparan intervalos reales con el calendario del empleado, sus descansos y festivos. Una solicitud parcial puede cubrir una jornada corta completa. Las solicitudes contiguas no se consideran superpuestas únicamente por compartir fecha.

| Situación | Resultado |
|---|---|
| Entrada real sin una solicitud superpuesta | Conserva la hora real y los movimientos. |
| Solicitud vigente que cubre toda la jornada exigible | Muestra el nombre del tipo; evita generar una FALTA de día completo. |
| Solicitud parcial con entrada real | Conserva ambos registros y el periodo de ausencia. |
| Solicitud parcial sin entrada, antes de concluir el tramo que debía trabajar | Muestra el tipo y PARCIAL. |
| Solicitud parcial sin entrada, concluido el tramo que debía trabajar | Muestra el tipo y REVISAR RH, sin crear una FALTA automática de día completo. |
| Entrada durante el intervalo solicitado o solicitudes superpuestas | Conserva las fuentes y muestra el motivo de revisión de RH. |
| Sin entrada ni solicitud vigente aplicable | Aplica la regla de FALTA automática cuando corresponda. |
| Solicitud rechazada o cancelada | Retira su indicador vigente y reevalúa la fecha siguiendo las reglas de historial. |

La revisión RH por una inconsistencia de asistencia se conserva. No se añade una revisión solo por faltar la aprobación de la solicitud.

Si se cancela o rechaza una solicitud de hoy y ya se cumplen las condiciones de falta, puede generarse la FALTA de hoy. Para una fecha anterior solo se reactiva una FALTA automática que realmente existió y siga siendo procedente. Si no existió esa falta original, puede generarse una revisión RH dentro del periodo de seguimiento; no se inventa una falta retroactiva. Se respetan los periodos de exclusión.

Una entrada válida resuelve la incidencia cuyo único motivo era la ausencia de marcaje. Una superposición diferente puede seguir requiriendo revisión. El módulo no convierte un déficit de minutos en un descuento salarial ni cambia la nómina.

### Fechas futuras

Solo aparecen ausencias e incidencias de hoy y días anteriores, según la zona horaria efectiva del indicador. La restricción se aplica en la lista, búsquedas, agrupaciones y nuevas exportaciones Excel/PDF, incluso al seleccionar identificadores antiguos directamente.

Las solicitudes futuras siguen guardadas en Tiempo personal. Al llegar su fecha, su información puede aparecer sin reinstalarlas ni aprobarlas de nuevo. Los marcajes reales de asistencia conservan su comportamiento anterior.

### Faltas automáticas

Se conserva el corte fijo de las **09:00, de lunes a viernes**, en la zona horaria configurada por empresa. La tarea programada revisa cada minuto según el planificador de Odoo; no garantiza ejecutar exactamente al segundo. No se crean faltas de sábado o domingo. Se respetan los días no laborables, festivos y periodos de contrato contemplados por la versión anterior.

El corte no cambia por sección ni se adapta al inicio de un turno que comienza más tarde. Esta entrega conserva esa regla existente. La fecha de comienzo del seguimiento limita las revisiones históricas.

## 3. Exclusión de empleados

En la ficha privada del empleado se conserva **Excluir del Reporte de asistencia**. Su modificación requiere los permisos de Recursos Humanos o Administración de Asistencias y el acceso original a la ficha.

Mientras esté marcada, el empleado se omite del reporte COIRTECH y sus nuevos Excel/PDF en todos los periodos. Sus marcajes, solicitudes y otros registros originales no se borran, y puede seguir usando el quiosco. Se detienen nuevas faltas automáticas y se retira la falta vigente de hoy conservando el historial.

Al desmarcarla reaparecen los datos y se evalúa hoy; no se rellenan con faltas los días anteriores en que estuvo excluido. El historial registra quién cambió la exclusión y cuándo. Archivar a un empleado detiene nuevas faltas, pero no oculta automáticamente su historial anterior.

Los archivos ya descargados no cambian. Hay que volver a exportarlos.

## 4. Quiosco y horas trabajadas

Se mantienen las seis acciones:

1. Entrada.
2. Salida a comer.
3. Regreso de comida.
4. Salida de trabajo.
5. Regreso al trabajo.
6. Salida final.

La comida y las salidas temporales de trabajo siguen siendo pagadas. No se añaden horarios obligatorios ni alertas de comida. Un intervalo abierto debe cerrarse mediante su regreso antes de finalizar la jornada; sus movimientos se conservan en el detalle.

Después de Salida final se bloquea otra entrada durante el mismo día local. RH puede crear una autorización adicional de un solo uso para una fecha concreta. La autorización no registra una entrada por sí sola. Una asistencia nativa anterior a COIRTECH conserva su cálculo original.

Esta entrega no modifica los archivos de diseño ni escaneo del quiosco. Es compatible con el complemento **attendance_multi_company_kiosk V1.1** y conserva la selección de empresas y el enlace existente. Ese complemento no está incluido de nuevo en este ZIP y no necesita reemplazarse por este cambio.

## 5. Reportes Excel y PDF

En **Asistencias → Reporte Excel / PDF**, selecciona el periodo, empresas y filtros disponibles. El resumen tiene una fila por empresa, empleado y fecha laboral. El detalle conserva cada movimiento o indicador. Una falta no se convierte en una hora de entrada ficticia.

Con una empresa, Excel genera Resumen y Detalle. Con varias, genera un par de hojas por empresa. Las fechas y duraciones son valores numéricos; el archivo usa el sistema de fechas Excel 1904 para representar también duraciones negativas. Los lectores que importen esos valores deben respetar ese sistema.

La FALTA automática mantiene su señal roja. Los tipos de Tiempo personal conservan su presentación normal. Los intervalos aún abiertos de comida o trabajo mantienen su señalización anterior, independiente de la aprobación de una solicitud de ausencia.

### Personalizar columnas

1. Entra como administrador de Asistencias al asistente **Reporte Excel / PDF**.
2. Selecciona la empresa y el formato que quieres personalizar.
3. Pulsa **Personalizar columnas**.
4. En Resumen y Detalle elige Mostrar, cambia el encabezado y ajusta el orden.
5. Guarda y exporta de nuevo.

También puedes usar **Asistencias → Configuración → Columnas del Reporte de asistencia**. La configuración se comparte por empresa y formato; Excel y PDF son independientes. Se requiere al menos una columna visible en Resumen y otra en Detalle. Los títulos admiten de 1 a 80 caracteres.

**Aplicar también al otro formato** copia los títulos, orden y visibilidad de esa empresa al otro formato. **Restaurar valores predeterminados** restaura solo el formato abierto. Estas operaciones no modifican asistencias ni solicitudes.

Al actualizar se conservan las configuraciones guardadas. Solo se cambian los títulos predeterminados exactos **Periodo autorizado → Periodo de ausencia** y **Ausencia aprobada / revisión RH → Ausencia / revisión RH**. Si escribiste otro encabezado personalizado, permanece tal como lo guardaste.

Las columnas opcionales incluyen salida/regreso de comida y trabajo, sus estados, tipo de ausencia y horas extra aprobadas nativas. Estas últimas se leen de Odoo para jornadas cerradas, una sola vez por jornada; no se suman nuevamente al tiempo trabajado. En el resumen se muestra el último par de salida y regreso; si el último intervalo está abierto, no se toma el regreso de otro intervalo anterior.

El PDF divide configuraciones amplias en bloques de hasta ocho columnas. Conserva los encabezados elegidos y solo repite empleado y fecha cuando esas columnas están habilitadas.

## 6. Actualizar en Odoo.sh

El ZIP contiene dos carpetas de módulos, una junto a otra:

- **coirtech_attendance_meal_control**: módulo principal.
- **coirtech_attendance_absence_gantt**: complemento para el Gantt nativo Enterprise.

1. Descomprime **coirtech_asistencias_odoo19_v4_4.zip**.
2. En tu rama de pruebas —por ejemplo **odometro**— reemplaza los archivos dentro de esas mismas carpetas. No cambies los nombres técnicos ni agregues un sufijo de versión a la carpeta.
3. Confirma los cambios en GitHub y espera la compilación de Odoo.sh.
4. Abre la base de esa rama. En Aplicaciones, con modo desarrollador, actualiza la lista si hace falta y quita el filtro Aplicaciones para encontrar los complementos.
5. Busca **COIRTECH - Asistencias, comidas y salidas** y pulsa **Actualizar**. La versión es **19.0.4.4.0**.
6. Si **COIRTECH - Faltas en el Gantt original** ya está instalado, actualízalo también. Su código de funcionamiento se conserva; el manifiesto identifica esta entrega como **19.0.4.4.0**.
7. Recarga Odoo y genera reportes nuevos para revisar los cambios.

**No desinstales los módulos para actualizarlos.** No subas solo el ZIP ni dejes una carpeta con la versión conteniendo otra carpeta igual. El complemento multiempresa existente permanece en su propia carpeta.

La migración recalcula la información derivada de Tiempo personal y conserva los registros originales y sus identificadores. Las solicitudes presentadas previamente también quedan contempladas. No necesitas repetir sus aprobaciones ni volver a asignar secciones.

Para una instalación nueva, instala directamente esta versión. Depende de Asistencias, Tiempo personal y la biblioteca Python XlsxWriter. El complemento Gantt requiere los módulos Enterprise correspondientes y puede instalarse automáticamente si sus dependencias están disponibles. El paquete no incluye Odoo ni esos módulos Enterprise.

## 7. Comprobación en tu base

Después de actualizar en pruebas, comprueba un permiso presentado sin validar: el reporte debe mostrar su nombre original sin estado de aprobación, y sus horas aún no deben sumarse en Horas autorizadas. Comprueba también un permiso aprobado, una fecha futura que siga oculta y un usuario de Manufactura que antes veía el error del campo.

Revisa una jornada con comida y salida temporal, el escaneo de credencial, el bloqueo tras la salida final, tus columnas personalizadas y la exportación Excel/PDF. Son las operaciones relevantes para comprobar la integración con otras personalizaciones de tu propia base antes de llevar la rama a producción.

Consulta **VALIDACION.md** para los resultados ejecutados en esta entrega y sus límites. Los documentos VALIDACION_V4_2.md, VALIDACION_V4.md, VALIDACION_V3.md y VALIDACION_V2.md conservan resultados históricos y no representan pruebas nuevas.

Referencia técnica: código oficial Odoo 19 de empleados y perfiles públicos: https://github.com/odoo/odoo/blob/19.0/addons/hr/models/hr_employee.py . El campo privado sigue la regla de acceso indicada por ese modelo.

Licencia: LGPL-3.
