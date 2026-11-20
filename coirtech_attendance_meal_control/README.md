# COIRTECH — Asistencias, comidas y salidas V2

**Odoo 19 · Versión 19.0.2.0.0 · Carpeta técnica: `coirtech_attendance_meal_control`**

Esta versión actualiza el módulo original. Agrega salidas temporales pagadas, bloqueo de nueva entrada tras la salida final y reportes Excel/PDF con filtros por empresa. Conserva el enlace y la identificación del quiosco de Odoo.

## 1. Los seis movimientos

| Botón | Resultado |
|---|---|
| Entrada | Abre la jornada. |
| Salir a comer | Inicia la comida pagada. |
| Regresar de comida | Registra el regreso de comida. |
| Salida de trabajo | Abre una salida temporal pagada. |
| Regreso al trabajo | Cierra esa salida temporal. |
| Salida final | Cierra la jornada y bloquea otra entrada durante el resto de ese día local. |

No es obligatorio usar los seis botones cada día. Puede haber una comida y varias salidas de trabajo dentro de la misma jornada. El empleado se identifica antes de cada movimiento, con el PIN si está configurado o con su credencial compatible.

**Comida y salidas de trabajo cuentan como tiempo trabajado.** El total de una jornada cerrada es el tiempo entre Entrada y Salida final. Esos intervalos ya están incluidos: no se descuentan ni se suman nuevamente.

Ejemplo: entrada 08:00, salida temporal 10:00–10:30, comida 13:00–14:00, segunda salida temporal 15:00–15:45 y salida final 17:00. Resultado: **jornada 09:00**, comida **01:00**, salidas temporales **01:15**.

Las secciones son opcionales. Puedes omitirlas y filtrar por empresa, empleado, departamento y fecha. No se imponen horarios de comida o de salidas temporales ni se agregan alertas por duración, cierres programados o descuentos de nómina.

## 2. Estados y restricciones

| Situación | Botones habilitados |
|---|---|
| Puede iniciar jornada | Entrada |
| Trabajando, antes de comer | Salir a comer, Salida de trabajo, Salida final |
| En comida | Regresar de comida |
| Fuera por trabajo | Regreso al trabajo |
| Trabajando, con comida completada | Salida de trabajo, Salida final |
| Salida final registrada ese día, sin autorización adicional | Ninguno; se indica cuándo puede volver a entrar. |

La comida y las salidas de trabajo no pueden superponerse. **V2 exige registrar el regreso antes de permitir Salida final.** Una omisión puede corregirla Recursos Humanos con motivo.

Este punto cambia V1, que permitía confirmar una salida final sin regreso de comida. Los registros antiguos con esa situación se conservan y se muestran como pendientes; actualizar no inventa regresos.

## 3. Regla precisa del bloqueo y turnos nocturnos

Después de Salida final, otra Entrada queda bloqueada **hasta las 00:00 del siguiente día local**, según la zona horaria efectiva del empleado. Una entrada adicional antes de ese momento requiere una autorización de un solo uso de un administrador de Asistencias.

La **fecha laboral del reporte** corresponde al inicio de la jornada. El **día del bloqueo** corresponde a la fecha local de su salida final.

| Ejemplo | Resultado |
|---|---|
| Entra lunes 08:00 y sale lunes 17:00 | Otra entrada el lunes requiere autorización; el martes puede iniciar normalmente. |
| Entra lunes 23:00 y sigue trabajando el martes | Continúa la misma jornada. Medianoche no crea otra entrada ni salida. |
| Termina ese turno nocturno el martes 07:00 | Otra entrada el martes requiere autorización, incluso si su siguiente turno empieza el martes 23:00. |
| Tiene una autorización para ese día | Puede registrar una entrada adicional; al usarla, la autorización se consume. |

No se necesita configurar horarios de entrada de las secciones. Para turnos nocturnos que terminan y vuelven a comenzar el mismo día local, RH debe autorizar la entrada adicional. El módulo no adivina cuándo empieza otro turno.

El bloqueo se comprueba en el servidor, también al crear asistencias por otros canales. Considera las salidas finales ya registradas ese día, incluso anteriores a la actualización o creadas con el flujo nativo. Una carga histórica legítima puede necesitar una autorización para la fecha de su nueva entrada. Los registros que ya existían no se eliminan.

Revisa la zona horaria del calendario y del empleado. Odoo puede priorizar la del calendario. El bloqueo y los reportes utilizan esa zona efectiva; Excel también incluye los instantes UTC. Las duraciones se calculan entre los instantes reales, respetando cambios de hora del reloj.

## 4. Actualizar desde V1 en `odometro`

**Actualiza el mismo módulo; no desinstales V1.**

1. Descarga y extrae el ZIP V2. Encontrarás la carpeta `coirtech_attendance_meal_control`.
2. En GitHub abre el repositorio conectado a Odoo.sh y selecciona **`odometro`**.
3. Sustituye los archivos de la carpeta existente por los de V2, incluyendo todos los archivos nuevos. Desde la raíz del repositorio puedes usar **Add file → Upload files** y arrastrar la carpeta técnica completa.
4. Comprueba que el manifiesto queda en `coirtech_attendance_meal_control/__manifest__.py` y declara `19.0.2.0.0`.
5. Confirma los cambios y espera a que la compilación termine correctamente.
6. Abre **la base de pruebas de esa rama**. Busca el módulo en Aplicaciones por `coirtech_attendance_meal_control` o **COIRTECH - Asistencias, comidas y salidas**. Si hace falta, activa modo desarrollador, actualiza la lista y elimina el filtro Aplicaciones.
7. En el módulo ya instalado pulsa **Actualizar**. Si Odoo.sh ya actualizó por el cambio de versión, comprueba que aparece `19.0.2.0.0`.
8. Cierra y vuelve a abrir el quiosco. Si conserva la interfaz anterior, recarga sin caché: `Cmd + Shift + R` en Mac o `Ctrl + Shift + R` en Windows.

Conserva el nombre técnico. Evita una carpeta terminada en `_v2`, un sufijo ` 2` o una carpeta idéntica dentro de otra. Subir solo el ZIP no coloca los archivos del módulo en la ruta de addons.

Si nunca instalaste V1, instala directamente V2 con el mismo procedimiento y pulsa **Instalar/Activar**.

## 5. Activar y utilizar

En **Asistencias → Configuración → Ajustes**, selecciona la empresa, conserva desactivada **Salida automática** y activa **Seis movimientos en el quiosco**, dentro de **COIRTECH — Asistencias, comidas y salidas**. La activación de V1 se conserva al actualizar.

Cada empresa utiliza su configuración y su enlace. La pantalla inicial sigue mostrando identificación manual o credencial; **los seis botones aparecen después de identificar al empleado**. Seleccionar un nombre o leer una credencial no marca automáticamente un movimiento.

Una jornada nativa que ya estaba abierta antes de activar COIRTECH mantiene su cálculo original y permite finalizarla. Las funciones de comidas y salidas se aplican a jornadas iniciadas mediante este quiosco. Las jornadas COIRTECH abiertas en V1 siguen abiertas y obtienen las opciones de V2.

## 6. Autorizar una entrada adicional

Con un usuario **Administrador de Asistencias**:

1. Abre **Asistencias → Autorizar nueva entrada → Nuevo**.
2. Selecciona el empleado.
3. Indica la **Fecha local autorizada** según su zona horaria efectiva.
4. Escribe el motivo y guarda.
5. El empleado se identifica de nuevo en el quiosco y pulsa Entrada.

También puedes abrir una jornada cerrada y pulsar **Autorizar nueva entrada**.

La autorización queda registrada con responsable, fecha y motivo. Se vincula a la jornada cuando se consume. Una pendiente puede revocarse; para cambiar sus datos se revoca y se crea otra. Una autorización no cierra jornadas abiertas ni registra una entrada por sí sola.

## 7. Consultar y corregir

En **Asistencias → Control de comidas y salidas** puedes filtrar y agrupar por empresa (cuando tienes acceso a varias), empleado, departamento, fecha y estados. Al abrir una jornada, la pestaña **Salidas de trabajo pagadas** muestra sus intervalos.

El administrador usa **Corregir comida** o **Corregir** en la fila de una salida de trabajo. Se exige motivo y se guarda el historial en la jornada. Las horas deben estar en orden, dentro de la asistencia y sin superposición.

Un intervalo sin regreso no tiene duración confirmada. Una jornada sin salida final permanece abierta, aunque cambie el día. Las correcciones deben basarse en la información disponible; el módulo no completa datos faltantes automáticamente.

## 8. Excel y PDF

1. Abre **Asistencias → Reporte Excel / PDF**.
2. Selecciona **Fecha laboral desde** y **Fecha laboral hasta**, ambas incluidas.
3. Elige una o varias empresas autorizadas y habilitadas en tu sesión.
4. Deja Empleados y Departamentos vacíos para incluir todos los accesibles, o selecciona los que necesitas.
5. Pulsa **Descargar Excel** o **Imprimir PDF**.

También puedes seleccionar jornadas en la lista y abrir **COIRTECH — Reporte Excel y PDF** desde las acciones disponibles. Los filtros se aplicarán dentro de esa selección. El PDF directo está en **Imprimir → COIRTECH — Asistencias y movimientos**.

### Resumen

Una fila por empresa, empleado y fecha laboral: primera entrada, última salida final, número de jornadas abiertas/cerradas, horas de jornadas cerradas, comida y salidas confirmadas, pendientes y revisiones de RH.

Si hay dos jornadas autorizadas el mismo día, se suman sus duraciones. **El hueco entre el cierre de una jornada y la entrada de la siguiente no se cuenta.** Si existe alguna jornada abierta, las horas cerradas se identifican como un subtotal parcial.

### Detalle

Una fila por movimiento: empresa, empleado, departamento, jornada, fecha laboral, tipo, fecha y hora local, zona, instante UTC, referencia, duración confirmada y revisión. Incluye todas las salidas temporales, aunque sean varias.

Las referencias **J**, **C** y **S** identifican jornada, comida y salida temporal. La duración de cada comida o salida se escribe solo en su regreso; las horas de jornada aparecen solo en Salida final. Así no se duplican al sumar columnas.

Las fechas y duraciones son valores numéricos de Excel. Los tiempos usan `[h]:mm`, permitiendo totales mayores de 24 horas. Los intervalos pendientes quedan vacíos y sus estados explican por qué. El archivo incluye filtros y encabezados inmovilizados.

Para imprimir desde Excel, el formato está preparado en horizontal y hasta dos páginas de ancho, repitiendo empresa, empleado y encabezados. El PDF ofrece un resumen más compacto y el detalle cronológico por jornada.

Excel es una fotografía de los registros al descargarlo. Si se corrigen en Odoo, vuelve a generarlo. Los cálculos no modifican las reglas de nómina u horas extra.

## 9. Prueba en tu base y paso a principal

Con un empleado de prueba verifica: identificar y cancelar; jornada con dos salidas temporales y comida; total pagado; bloqueo tras Salida final; autorización de un solo uso; rechazo del cierre durante comida/salida pendiente; filtros por empresa; Excel con dos hojas; PDF con todos los movimientos y conservación de registros V1.

`VALIDACION.md` describe las pruebas técnicas de la entrega. Probar en `odometro` permite comprobar la convivencia con Enterprise, Studio, los demás módulos, tu tableta y lector reales.

Cuando esas pruebas sean correctas, incorpora la misma carpeta a principal y actualiza el módulo allí. Las autorizaciones y registros de una base de pruebas no se trasladan por fusionar código. Configura la activación por empresa cuando corresponda.

## 10. Compatibilidad

Odoo 19 con `hr_attendance`, en Odoo.sh o instalación propia. El generador utiliza XlsxWriter en el entorno de Odoo; no requiere un segundo módulo de reportes. Registro conectado al servidor. Licencia LGPL-3.

Mantiene el nombre técnico y los campos de V1. Las asistencias ajenas a COIRTECH conservan sus cálculos originales; el bloqueo de entradas se aplica en las empresas con el control activado. Los horarios contractuales, reglas de horas extra y nómina siguen administrándose en su configuración correspondiente.
