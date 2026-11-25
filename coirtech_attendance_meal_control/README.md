# COIRTECH Asistencias V4.2

**Odoo 19 · Versión 19.0.4.2.0 · Nombre técnico: `coirtech_attendance_meal_control`**

V4 incorpora la exclusión de empleados del Reporte de asistencia y de las faltas automáticas, lee las ausencias aprobadas de Odoo y presenta incidencias de Recursos Humanos cuando hay permisos parciales sin asistencia. Conserva los marcajes originales, las seis acciones del quiosco y las comidas y salidas temporales pagadas.


## Novedad V4.2: personalizar columnas de Excel y PDF

Esta versión conserva la regla V4.1: **las ausencias futuras permanecen ocultas** en Reporte de asistencia, búsquedas, agrupaciones y nuevas exportaciones. Elegir o renombrar columnas no cambia esa restricción ni la exclusión de empleados.

### Cómo usarlo

1. Entra como **administrador de Asistencias** a **Asistencias → Reporte Excel / PDF**.
2. Selecciona el periodo y las empresas del reporte.
3. En **Columnas del reporte**, elige **Empresa a personalizar** y **Formato a personalizar** (Excel o PDF).
4. Pulsa **Personalizar columnas**. En las pestañas **Resumen** y **Detalle**, marca o desmarca **Mostrar**, escribe el **Encabezado del reporte** y arrastra el control de **Orden**.
5. Pulsa **Guardar**. Descarga Excel o imprime PDF desde el asistente original.

También puedes entrar por **Asistencias → Configuración → Columnas del Reporte de asistencia**. Si creas una configuración desde esa lista, elige empresa y formato y guarda primero para cargar las columnas disponibles.

La configuración es compartida por empresa y formato, no personal por usuario. Los responsables que pueden exportar usan la configuración guardada; solo los administradores de Asistencias la cambian. Cada empresa conserva una configuración de Excel y otra de PDF. **Aplicar también al otro formato** copia títulos, orden y visibilidad al otro formato de esa misma empresa, previa confirmación de reemplazo. **Restaurar valores predeterminados** restaura solo el formato abierto. No modifica asistencias ni solicitudes.

Debe quedar al menos una columna visible en Resumen y una en Detalle. Se ocultan con su casilla, sin eliminar su definición. Los encabezados admiten de 1 a 80 caracteres. El dato original y su significado permanecen identificables en la configuración aunque cambies el título.

### Datos que puedes elegir

| Sección | Columnas disponibles |
|---|---|
| Resumen | Empresa, empleado, departamento, fecha y zona horaria; primera entrada y última salida final; jornadas abiertas/cerradas; horas de jornadas cerradas; duración de comida y salidas; pendientes; estado; revisiones de RH; ausencia/incidencia; periodo y horas autorizadas; motivo de RH. |
| Opcionales del Resumen | Salida a comer, regreso de comida, salida de trabajo, regreso al trabajo, estado de comida, estado de salidas, horas extra aprobadas, tipo de ausencia y columnas combinadas de conteos e incidencia. |
| Detalle | Empresa, empleado, departamento, fecha, jornada, movimiento, hora local y UTC, zona horaria, referencia, duración del intervalo, horas al cierre, estado, revisión y motivo, periodo y horas autorizadas, incidencia de RH; opcionalmente tipo de ausencia y horas extra aprobadas. |

**Resumen** tiene una fila por empresa, empleado y fecha laboral; **Detalle** tiene una fila por movimiento o indicador. En Resumen, comida y salidas de trabajo muestran su último par de salida y regreso del día. Si el último intervalo está abierto, su regreso queda vacío, aunque exista un regreso de una salida anterior. El Detalle conserva todos los movimientos. La columna Primera entrada mantiene la hora real; una FALTA no se convierte en una entrada ficticia.

**Horas extra aprobadas** lee `hr.attendance.validated_overtime_hours` de Odoo, sin añadir una regla de horas extra ni modificar su aprobación. En Resumen suma el valor nativo de las jornadas cerradas; en Detalle lo muestra únicamente en Salida final, para no repetirlo por cada movimiento. Las jornadas abiertas y las filas de ausencia no reciben horas extra calculadas por el reporte. Las horas de comida, salidas, ausencias autorizadas y horas extra no se suman otra vez a las horas de jornada. El signo del valor nativo se conserva.

### Presentación de los archivos

- Con una empresa, Excel conserva **Resumen** y **Detalle**. Con varias, genera un par de hojas por empresa para respetar sus columnas distintas; un número en el nombre evita duplicados.
- Las fechas y duraciones siguen siendo valores numéricos. El archivo declara el sistema de fechas Excel 1904 para representar también duraciones negativas; los lectores deben respetar el sistema de fechas declarado al importar datos.
- PDF divide las configuraciones amplias en bloques de hasta ocho columnas y repite empleado/fecha solo si elegiste esas columnas. Los encabezados y las celdas se ajustan al espacio disponible. Los datos ocultos no reaparecen en encabezados de jornadas.
- La FALTA automática conserva su señal roja. Si ocultas todas las columnas donde normalmente dice FALTA, su fila se identifica en rojo. Vacaciones, incapacidad y permisos aprobados mantienen presentación normal.
- Estas opciones personalizan **los archivos Excel y PDF**. No cambian el nombre de los campos nativos, las columnas de la lista de Odoo ni la apariencia de las asistencias reales en el Gantt.

Al actualizar, el reporte funciona con valores predeterminados hasta que guardes una configuración. No necesitas volver a configurar los tipos de ausencia ni la casilla de exclusión de los empleados.

## 1. Configurar los tipos de ausencia

Requiere las aplicaciones nativas Asistencias (`hr_attendance`) y Ausencias / Tiempo personal (`hr_holidays`). Odoo resuelve esas dependencias al instalar el módulo.

Un administrador de Ausencias abre **Asistencias → Configuración → Tipos de ausencia COIRTECH** y asigna a cada tipo existente una de estas categorías:

| Categoría COIRTECH | Texto del Reporte |
|---|---|
| Vacaciones | VACACIONES |
| Falta con sueldo | FALTA CON SUELDO |
| Falta sin sueldo | FALTA SIN SUELDO |
| Incapacidad | INCAPACIDAD |

La lista muestra los tipos originales de Odoo. Pueden relacionarse varios tipos con una misma categoría. La correspondencia se elige expresamente: el módulo no intenta deducirla a partir del nombre, idioma o importe salarial.

Una solicitud aprobada cuyo tipo aún no tenga categoría se muestra como **AUSENCIA APROBADA — TIPO POR CONFIGURAR**. Sigue protegiendo contra una falta injustificada. Asignar la categoría actualiza la información derivada correspondiente, incluidos los periodos anteriores.

Solo cuenta la aprobación final. Si un tipo exige dos aprobaciones, la primera no basta. Las solicitudes aprobadas automáticamente por la configuración nativa también cuentan. Las asignaciones de saldo no son solicitudes de ausencia.

Las etiquetas del reporte no modifican salarios, descuentos, nómina, saldos ni la aprobación original. El reporte incorpora categoría y periodo; no copia diagnósticos, notas privadas ni documentos adjuntos.

## 2. Excluir a un empleado

En la ficha privada del empleado, dentro de la sección donde aparecen los datos de identificación, está la casilla **Excluir del Reporte de asistencia**. La cambian los usuarios autorizados de Recursos Humanos o de Administración de Asistencias, respetando también los permisos originales sobre la ficha.

Mientras está marcada:

- El empleado se omite del Reporte de asistencia en **todos los periodos**, no solo desde la fecha del cambio.
- Se omiten sus asistencias, permisos e incidencias de la lista, agrupaciones, totales y nuevas exportaciones Excel/PDF.
- Quitar filtros o exportar desde una selección de sus asistencias originales no lo reincorpora al reporte COIRTECH.
- Se detiene la generación de nuevas faltas automáticas. La FALTA vigente de hoy se retira, conservando su motivo e historial.
- Sus registros originales permanecen disponibles en sus modelos y pantallas nativas. Puede seguir utilizando el quiosco y registrar los seis movimientos.

Al desmarcarla reaparecen los datos originales de todos los periodos, incluidos los marcajes hechos durante la exclusión. La política automática vuelve a evaluar el día actual: si ya pasó el corte de las 09:00 y corresponde, puede generar una falta de hoy. **No rellena con faltas las fechas anteriores durante las que estuvo excluido.**

La pestaña **Control COIRTECH** de su perfil conserva quién activó o quitó la exclusión y cuándo. Ese historial es de solo lectura. La casilla está desmarcada por defecto y no se copia al duplicar un empleado.

Archivar y excluir tienen efectos diferentes: un empleado archivado no recibe nuevas faltas; su historial previo se conserva. La casilla es la que oculta todo el historial del Reporte. Los PDF o Excel ya descargados no cambian; deben generarse nuevamente.

## 3. Reglas de resolución

Las fechas y horas se comparan como intervalos reales sobre el horario que correspondía trabajar, descontando descansos y festivos aplicables. Un permiso por horas puede cubrir toda una jornada corta. Dos permisos contiguos no se consideran superpuestos por estar en la misma fecha.

| Situación | Resultado |
|---|---|
| Entrada real, sin permiso que se superponga | Mostrar la hora real y los movimientos. |
| Permiso aprobado que cubre toda la jornada exigible | Mostrar su categoría; no generar FALTA. |
| Permiso parcial aprobado con entrada real | Conservar la hora real y mostrar el periodo autorizado. |
| Permiso parcial aprobado, sin entrada, antes de terminar el último tramo exigible | Mostrar el permiso como parcial. |
| Permiso parcial aprobado, sin entrada, terminado el último tramo exigible | Mostrar su categoría y REVISAR RH; nunca una FALTA automática de día completo. |
| Entrada real durante el intervalo autorizado | Conservar ambos registros y señalar la superposición para RH. |
| Dos permisos aprobados realmente superpuestos | Conservar las categorías, contar una sola vez el intervalo autorizado y pedir revisión de RH. |
| Sin entrada ni permiso aprobado aplicable | Aplicar la regla de FALTA automática cuando corresponda. |
| Solicitud pendiente, rechazada o cancelada | No tratarla como permiso aprobado. |

Ejemplo: jornada de 09:00 a 18:00 y permiso aprobado de 09:00 a 13:00. A las 09:00 aparece el permiso parcial. Si marca entrada a las 13:05, se muestra esa hora real. Si termina el último tramo que debía trabajar y no hay ninguna asistencia, aparece la incidencia de RH.

Una entrada válida resuelve la incidencia cuyo único motivo era la ausencia de marcaje; el permiso se conserva. Una contradicción distinta, como trabajar dentro del periodo autorizado, puede seguir pendiente. RH revisa y corrige la asistencia o solicitud original. V4 no interpreta una diferencia de minutos como descuento salarial ni convierte un déficit de horas en falta completa.

Si el horario no permite determinar la cobertura de un permiso (por ejemplo, un calendario flexible), se muestra la categoría y una incidencia de configuración; las horas autorizadas quedan vacías. En días sin permiso aprobado, los calendarios flexibles conservan el comportamiento nativo utilizado por V3 para la regla de las 09:00.

## 4. Faltas a las 09:00

Configuración: **Asistencias → Configuración → Ajustes → COIRTECH → Faltas automáticas a las 09:00**. Zona de corte inicial por empresa: **America/Mexico_City**.

- Se generan para empleados activos, incluidos en el control, con jornada exigible y sin asistencia real ni permiso aprobado que corresponda.
- El corte se conserva fijo a las 09:00, de lunes a viernes. No se mueve a la hora de entrada de cada turno. Por tanto, un turno que empieza más tarde sigue sujeto a ese corte fijo.
- Sábado y domingo nunca generan nuevas FALTAS automáticas, incluso si el calendario contiene trabajo. Los marcajes reales y los permisos aplicables de esos días sí pueden aparecer en el reporte.
- Los festivos y días sin trabajo exigible no producen falta. Se respetan los periodos de contrato explícitos configurados en Odoo.
- La tarea programada revisa cada minuto. Su ejecución depende del planificador; no se garantiza el segundo exacto.
- Al registrar una entrada real por quiosco, interfaz o importación se retira la falta de esa fecha y se muestra la hora real. Nunca se sustituye por PRESENTE.
- No se crean entradas a las 09:00, salidas ficticias ni horas trabajadas para representar una falta.
- Una asistencia que cruza medianoche puede contar como presencia. Una jornada olvidada abierta desde muchos días antes no evita faltas indefinidamente.

La regla fija de las 09:00 y el bloqueo de reentrada después de la salida final son reglas diferentes. El corte de faltas usa la zona de la compañía; el bloqueo de reentrada usa la zona efectiva del empleado. No se cambian por la zona del navegador.

## 5. Actualizaciones y conservación del historial

Al instalar o actualizar V4 se leen las solicitudes aprobadas existentes. Al activar por primera vez el control de una compañía también se incorporan sus permisos aprobados, incluidos periodos anteriores. Esto no crea faltas automáticas históricas.

La aprobación posterior de una ausencia completa retira una FALTA que ya existiera y presenta el permiso. Si la aprobación es parcial, retira la falta completa y aplica las reglas de revisión. Los indicadores conservan su identidad y procedencia.

Si se cancela o cambia un permiso:

- Para hoy, se vuelve a evaluar la entrada, el horario y el corte.
- En fechas pasadas, solo puede reactivarse una FALTA original que ya hubiera sido registrada y siga correspondiendo.
- Si nunca existió esa falta original, se presenta una incidencia de revisión dentro del periodo seguido por el módulo, sin inventar una falta histórica.
- Se respetan las fechas de exclusión. No se generan faltas para completar periodos excluidos ni para fechas anteriores a la activación del control.

Cuando no existe una fecha de activación histórica comprobable, V4 usa un límite conservador: la primera falta original que conste, o el momento de activación/inicialización si no hay ninguna. Los permisos originales anteriores siguen pudiendo verse.

Los cambios de solicitudes, de categorías y de asistencia actualizan los indicadores afectados. El cron reconcilia hoy y ayer y recupera cierres parciales pendientes anteriores, en lotes limitados, si estuvo detenido. El reporte exportado sincroniza además el periodo solicitado.

## 6. Pantalla, Excel, PDF y colores

El menú sigue siendo **Reporte de asistencia**. La lista presenta los marcajes reales y los permisos/incidencias en filas separadas. Así cada fuente conserva sus permisos originales. Las filas de permisos tienen sus columnas de estado, periodo autorizado, horas autorizadas e incidencia de RH; no aparentan ser marcajes.

El **Resumen** de Excel/PDF reúne por empresa, empleado y fecha laboral la asistencia y los permisos. Las horas autorizadas van separadas y no se suman a las trabajadas. El **Detalle** conserva todos los movimientos y presenta cada indicador una sola vez.

| Elemento | Presentación |
|---|---|
| FALTA automática | Rojo en reporte e indicador del Gantt. |
| Vacaciones, permisos con/sin sueldo e incapacidad aprobados | Presentación estándar. |
| Incidencias nuevas de RH | Presentación estándar con motivo explícito. |
| Estado En comida / Fuera por trabajo | Etiqueta roja en sus indicadores de pantalla. |
| Regreso de comida / trabajo registrado | Etiqueta verde en sus indicadores de pantalla. |
| Asistencia real del Gantt | Apariencia nativa de Odoo. |

FALTA CON SUELDO y FALTA SIN SUELDO aprobadas son categorías de permiso; no heredan el rojo de la FALTA automática por compartir una palabra.

Las nuevas categorías aparecen en el Reporte. El puente Gantt sigue añadiendo únicamente FALTA; no añade nuevas barras de vacaciones ni modifica las barras reales. Una falta actual que deja de corresponder por permiso o exclusión se retira del tablero. La casilla no oculta al empleado de todas las pantallas nativas de Odoo.

Para exportar: **Asistencias → Reporte Excel / PDF**, escoger periodo, empresas y opcionalmente empleados/departamentos. También se puede exportar una selección del Reporte. Una selección totalmente excluida queda sin datos y no se transforma en una exportación general.

Los archivos descargados son una fotografía de los datos de ese momento. Excel conserva fechas numéricas, duraciones [h]:mm, filtros y encabezados; genera las hojas Resumen y Detalle por empresa cuando se incluyen varias. Los textos se escriben como texto para evitar que nombres o notas se interpreten como fórmulas.

## 7. Movimientos del quiosco que se conservan

| Movimiento | Resultado |
|---|---|
| Entrada | Inicia la jornada. |
| Salir a comer | Abre la comida pagada. |
| Regresar de comida | Registra su regreso. |
| Salida de trabajo | Abre una salida temporal pagada. |
| Regreso al trabajo | Cierra esa salida. |
| Salida final | Cierra la jornada y bloquea otra entrada durante el resto del día local. |

Puede haber una comida y varias salidas de trabajo por jornada. Es obligatorio registrar el regreso antes de permitir la salida final. Las omisiones de registros históricos se conservan para corrección por RH con motivo.

Comida y salidas temporales ya forman parte de la duración de una jornada COIRTECH: no se descuentan ni se suman de nuevo. No se imponen horarios de comida ni alertas por duración. Una jornada abierta no recibe una salida automática.

Las columnas Salida de trabajo y Regreso al trabajo corresponden al último par. Si la última salida está abierta, su regreso queda vacío; el detalle conserva todos los pares.

Después de Salida final, la siguiente entrada se permite a las 00:00 del siguiente día local del empleado. RH puede autorizar una entrada adicional de un solo uso para una fecha concreta en **Asistencias → Autorizar nueva entrada**. La autorización no crea una entrada ni cierra una jornada por sí sola.

Una jornada nativa anterior a COIRTECH conserva su cálculo original. Los intervalos pagados de COIRTECH corresponden a jornadas gestionadas por su quiosco.

## 8. Instalar o actualizar en Odoo.sh

El ZIP contiene estas dos carpetas hermanas:

1. `coirtech_attendance_meal_control`: módulo principal.
2. `coirtech_attendance_absence_gantt`: puente para el Gantt nativo Enterprise, dependiente de `hr_attendance_gantt`.

**Actualiza los módulos existentes sin desinstalarlos y sin renombrar sus carpetas.**

1. Extrae el ZIP y coloca ambas carpetas completas en la ruta de addons del repositorio de tu rama Staging. Si ya existen, sustituye sus archivos por esta entrega. No anides una carpeta dentro de otra ni subas únicamente el ZIP.
2. Confirma los cambios y espera la compilación de Odoo.sh.
3. Abre la base de Staging, activa modo desarrollador y actualiza la lista de aplicaciones. Quita el filtro Aplicaciones si no encuentras los complementos.
4. Busca **COIRTECH - Asistencias, comidas y salidas** y pulsa **Actualizar**. Para una instalación desde cero, pulsa **Instalar**. La versión debe ser `19.0.4.2.0`.
5. Si el puente Gantt ya está instalado, actualízalo también a `19.0.4.2.0`. En una instalación nueva está preparado para instalarse automáticamente cuando estén disponibles sus dos dependencias; si no se instaló, instálalo desde Aplicaciones.
6. Revisa en Ajustes la compañía, el control COIRTECH, el corte y la zona. La Salida automática nativa debe estar desactivada para usar el quiosco COIRTECH.
7. Relaciona los tipos de ausencia y marca la casilla de los empleados que deban excluirse. Las configuraciones existentes de empleados no se adivinan ni se activan masivamente.
8. Recarga Odoo y el quiosco. Verifica los casos de tu empresa en Staging antes de aplicar el mismo código a producción.

No es necesario instalar ninguna versión anterior para una instalación desde cero. El módulo principal necesita XlsxWriter disponible en el entorno de Odoo. El ZIP no incluye Odoo ni módulos Enterprise.

## 9. Permisos y validación

La lectura del Reporte y de su proyección Gantt conserva las reglas de las asistencias/indicadores de origen y el acceso por compañía. V4 añade lectura explícita del modelo Gantt a los roles nativos de oficial, lector de todas las asistencias y administrador, además del lector propio. No concede acceso global ni permisos de escritura sobre las proyecciones.

La casilla y su historial no sustituyen las reglas de seguridad de Odoo; son una política de participación en este reporte. Los responsables de Asistencias sin permisos privados de RH pueden usar el selector público de empleados autorizado en los filtros.

Consulta **VALIDACION.md** para las pruebas de V4.2, la actualización real V4.1→V4.2 y el alcance que queda por comprobar en Enterprise. **VALIDACION_V4.md**, **VALIDACION_V3.md** y **VALIDACION_V2.md** conservan los resultados históricos de sus respectivas entregas; no se presentan como pruebas nuevas.

Licencia: LGPL-3.

## V4.1: No adelantar ausencias futuras en el Reporte

En **Reporte de asistencia** solo se proyectan las ausencias e incidencias de
hoy y de fechas anteriores, según la zona horaria efectiva guardada para
cada día/empresa. Aplica por igual a vacaciones, faltas con sueldo,
faltas sin sueldo, incapacidades y ausencias aprobadas sin categoría configurada.

La vista de lista, búsquedas y agrupaciones, y las nuevas exportaciones
Excel/PDF excluyen los días futuros incluso si una selección antigua
contiene IDs de esos indicadores. Al iniciar cada día local, los indicadores
aprobados de ese día se vuelven visibles automáticamente. Los permisos
aprobados permanecen sin cambios en **Ausencias**; no se cancelan ni modifican
sus fechas o aprobaciones. Tampoco se ocultan los marcajes reales de asistencia.

La actualización desde V4 requiere actualizar el módulo principal para
recrear su vista SQL. El complemento Gantt mantiene su funcionalidad previa.

## Referencia nativa de horas extra

La columna de horas extra aprobadas utiliza el valor nativo de aprobación de Odoo 19. Documentación oficial: https://www.odoo.com/documentation/19.0/es/applications/hr/attendances/management.html . No cambia las reglas de horas extra, las aprobaciones ni la nómina.
