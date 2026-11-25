# Quiosco Multiempresa — Odoo 19

**Versión:** 19.0.1.1.0 — corrección del diseño y del escaneo  
**Nombre técnico:** `attendance_multi_company_kiosk`  
**Dependencia:** `coirtech_attendance_meal_control` con seis movimientos. Integración verificada con Asistencias 19.0.4.2.0.

## 1. Qué agrega

Un enlace compartido de asistencia para las empresas que selecciones dentro de una misma base de Odoo. Puedes empezar con tres y agregar o retirar otras en el futuro, sin cambiar el código ni el enlace.

Esta versión recupera **el quiosco original de Odoo y el selector de seis movimientos del módulo de Asistencias que ya utilizas**. Conserva su fondo, reloj, tarjetas con foto, búsqueda, departamentos, paginación, teclado de PIN, lectura de credenciales y escaneo con cámara. La versión anterior había creado una pantalla distinta y omitido la cámara; esta entrega corrige ambas cosas.

Se agrega el nombre real de la empresa junto al empleado para distinguir fichas de empresas diferentes. En el enlace compartido se ocultan los logotipos y la marca fija, como se solicitó. Si una empresa se llama COIRTECH, su nombre real sí aparece como empresa del empleado. No se renombran las empresas ni se cambian sus datos fiscales.

Se instala como complemento. Usa los modelos y reglas de Asistencias que ya tienes: no sustituye su carpeta, no crea una segunda tabla de asistencias y no reimplementa faltas, permisos ni cálculos de horas. Sus registros llegan a los mismos reportes Excel/PDF, con las opciones y filtros del módulo principal.

Los enlaces individuales originales continúan disponibles con su interfaz y sus ajustes. Las adaptaciones multiempresa se cargan únicamente en el enlace compartido.

## 2. Movimientos y horas

| Movimiento | Resultado |
|---|---|
| Entrada | Inicia una jornada mediante el módulo de Asistencias. |
| Salir a comer | Abre el intervalo de comida pagada. |
| Regresar de comida | Cierra ese intervalo. |
| Salida de trabajo | Abre una salida temporal pagada. |
| Regreso al trabajo | Cierra esa salida temporal. |
| Salida final | Termina la jornada y aplica el bloqueo de nueva entrada. |

Identificar un nombre, introducir un PIN o leer una credencial **no registra una entrada ni una salida por sí solo**. El empleado debe seleccionar un movimiento. Los seis botones aparecen, pero solo se habilitan los que permite su estado actual.

La comida y las salidas temporales permanecen dentro del tiempo trabajado. Se permiten varias salidas temporales en una jornada, sin descontarlas ni sumar sus horas dos veces. Se conserva una comida por jornada y la obligación de registrar el regreso antes de Salida final.

No hay horarios obligatorios de comida ni salidas, alertas por duración, secciones obligatorias o nuevos cierres automáticos. El complemento conserva las reglas del módulo principal sobre faltas, permisos y exclusión de reportes.

En la versión 4.2 revisada, Salida final bloquea otra entrada hasta las 00:00 del siguiente día local del empleado. Una nueva jornada durante el mismo día necesita la autorización de un solo uso de RH que ya ofrece el módulo principal. Un turno abierto continúa al pasar medianoche. Si se cierra por la mañana y comienza otro turno esa misma noche, necesita dicha autorización.

Una asistencia antigua iniciada fuera del flujo de movimientos conserva su política original: el quiosco permite cerrarla, pero no convierte retroactivamente su comida o sus horas. Si solo se habilita Salida final, revisa si la jornada actual es de ese tipo.

## 3. Requisitos

- Odoo 19 en Odoo.sh o instalación propia, con las empresas dentro de la misma base.
- Módulo principal `coirtech_attendance_meal_control` instalado y con los seis movimientos. Esta entrega se comprobó con la versión 19.0.4.2.0. El instalador comprueba la API necesaria; no instala una versión más reciente del módulo principal por sí solo.
- En cada empresa participante: **Seis movimientos en el quiosco** activado y **Salida automática** desactivada en los ajustes de Asistencias.
- Un administrador de Asistencias con acceso a todas las empresas participantes.
- Navegador actualizado y conexión al servidor en la computadora, tableta o celular compartido.

El complemento opcional de Gantt no es una dependencia de este quiosco. Puedes conservarlo si ya lo utilizas.

## 4. Actualizar la versión que ya tienes instalada

**Actualiza `attendance_multi_company_kiosk`; no lo desinstales ni crees otro quiosco.** La actualización conserva el enlace, las empresas seleccionadas y las asistencias existentes.

1. Descarga y extrae el ZIP. Obtendrás una sola carpeta: `attendance_multi_company_kiosk`.
2. En GitHub abre el repositorio conectado a Odoo.sh y selecciona la rama de pruebas, por ejemplo `odometro`.
3. Desde la raíz del repositorio usa **Add file → Upload files** y arrastra la carpeta completa. Debe reemplazar los archivos de la carpeta `attendance_multi_company_kiosk` que ya existe y quedar al mismo nivel que los otros módulos personalizados.
4. Comprueba esta ruta exacta:

   `attendance_multi_company_kiosk/__manifest__.py`

5. Confirma los cambios y espera a que la compilación de Odoo.sh termine correctamente.
6. Abre la base de esa misma rama. Activa el modo desarrollador si necesitas actualizar la lista de aplicaciones.
7. En **Aplicaciones**, quita el filtro predeterminado **Aplicaciones** si impide encontrar complementos. Busca **Quiosco Multiempresa** o `attendance_multi_company_kiosk`.
8. En el menú del módulo pulsa **Actualizar / Upgrade**. Actualizar únicamente la lista de aplicaciones no sustituye la actualización del módulo instalado.
9. Cierra la pestaña del quiosco y vuelve a abrir **el mismo enlace**. En una computadora también puedes usar una recarga completa para obtener los nuevos recursos.
10. En **Asistencias → Configuración → Quiosco Multiempresa**, abre tu registro existente. Comprueba el campo **Fuente del escaneo**, descrito abajo, y prueba una credencial en el dispositivo habitual.

No renombres la carpeta con un sufijo ` 2` o `_v1_1`, no la coloques dentro de otra idéntica y no subas únicamente el ZIP. El ZIP contiene solo este complemento; el módulo principal debe continuar en el repositorio y en la base. No hay que reemplazar la carpeta `coirtech_attendance_meal_control`.

El manifiesto nuevo deja de cargar los antiguos `kiosk.js` y `kiosk.css`. Si esos archivos permanecen en GitHub después de subir los nuevos, ya no se usan: lo necesario es haber reemplazado el manifiesto y todos los archivos incluidos en este ZIP.

Para una instalación por primera vez, sigue la misma carga de archivos, actualiza la lista de aplicaciones y pulsa **Activar / Instalar**. En ese caso crea el enlace como se indica en la sección siguiente.

## 5. Configurar el enlace y la cámara

Si ya tenías un quiosco creado, ábrelo y conserva ese registro. Los pasos de creación solo se necesitan la primera vez.

1. En el selector de empresas de la parte superior de Odoo, activa las tres empresas que quieres incluir.
2. Entra en **Asistencias → Configuración → Quiosco Multiempresa**.
3. Pulsa **Nuevo**.
4. Deja como nombre **Control de asistencia**, o escribe un nombre neutro para el punto de registro.
5. Mantén **Activo** marcado.
6. En **Empresas participantes**, selecciona las tres empresas.
7. En **Identificación**, elige:

   - **Nombre y PIN, según la empresa:** búsqueda manual; se solicita PIN si la empresa del empleado lo tiene activado.
   - **Credencial con cámara o lector:** identificación mediante cámara o lector compatible.
   - **Nombre/PIN y credencial con cámara o lector:** ambos métodos disponibles.

8. Cuando permitas credenciales, elige **Fuente del escaneo**:

   | Opción | Comportamiento |
   |---|---|
   | Usar la configuración de la primera empresa | Predeterminada al actualizar. Utiliza el ajuste nativo de escaneo de la primera empresa participante disponible, ordenada por su ID en Odoo. |
   | Cámara frontal | Usa el componente nativo de Odoo con la cámara frontal. |
   | Cámara trasera | Usa el mismo componente con la cámara trasera. |
   | Lector de código de barras / RFID | Usa un lector que envía la credencial como teclado. |

9. Guarda.
10. Abre **Enlace del quiosco** en el dispositivo compartido. También puedes usar **Abrir quiosco**. Si lo actualizaste, el enlace es el que ya tenías.

Si las empresas usan cámaras distintas en sus enlaces individuales, selecciona explícitamente la cámara que necesita **este dispositivo compartido**. La elección afecta a este enlace, no cambia los ajustes originales de cada empresa. Recarga la pestaña después de cambiar el modo o la fuente del escaneo.

Para administrar un quiosco, todas sus empresas deben estar activadas en tu sesión y permitidas a tu usuario. Si no aparece en la lista, revisa el selector superior; si está desactivado, usa el filtro **Desactivados**.

El enlace es propio de esta base. Usa el enlace de pruebas en `odometro` y el que genere producción cuando instales y configures allí.

## 6. Agregar una cuarta empresa más adelante

1. Crea o configura esa empresa en Odoo mediante sus opciones habituales y asigna correctamente sus empleados.
2. Activa los seis movimientos y desactiva Salida automática en los ajustes de Asistencias de esa empresa.
3. Dale acceso a la empresa al administrador que gestiona el quiosco y actívala en el selector superior, junto con las participantes actuales.
4. Abre el registro de **Quiosco Multiempresa** que ya utilizas.
5. En **Empresas participantes**, agrega la nueva empresa y guarda.

**El enlace permanece igual.** No necesitas modificar GitHub, reinstalar ni regenerarlo. El nuevo personal aparecerá al volver al inicio del quiosco o recargarlo. Las identificaciones que estaban pendientes antes del cambio deben realizarse de nuevo.

## 7. Retirar una empresa

1. Abre la configuración del quiosco con todas sus empresas activadas en tu sesión.
2. Quita la etiqueta de la empresa en **Empresas participantes**.
3. Guarda.

Desde ese momento, el servidor rechaza sus movimientos a través del enlace compartido, incluso si alguien dejó abierta una pantalla de selección anterior. El enlace de las demás empresas se mantiene.

Sus empleados, asistencias, permisos y reportes anteriores **no se eliminan**. Tampoco se cierra automáticamente ninguna jornada abierta. Si aún hay una comida, salida temporal o jornada pendiente, puede completarse con el enlace individual de esa empresa, o revisarse por RH en el módulo principal.

Para suspender el quiosco completo, desmarca **Activo**. Para quitar la última empresa, desactiva primero el quiosco. Puedes volver a activarlo o volver a agregar una empresa después; el historial se conserva.

## 8. Cómo se determina la empresa

En búsqueda manual, cada tarjeta muestra el nombre del empleado y su empresa. Tras verificar el PIN, cuando corresponda, se muestra la misma empresa en la pantalla de movimientos.

La empresa se toma de la ficha seleccionada y se valida en el servidor; no se envía un campo editable de empresa al registrar una acción. Una credencial identifica una ficha de empleado concreta. No se identifica a alguien únicamente por su PIN.

Si una persona tiene dos fichas en empresas distintas, ambas aparecen diferenciadas por empresa. Debe seleccionar la ficha correspondiente o utilizar la credencial vinculada a ella. El módulo no puede adivinar para qué empresa trabaja ese día ni combina los historiales de dos fichas.

La seguridad de este enlace se limita a las empresas elegidas por el administrador. El acceso a reportes y edición de asistencias sigue sujeto a los permisos de Odoo.

## 9. Uso en el dispositivo

Abre el enlace en un navegador. Busca el nombre o utiliza una credencial; verifica nombre y empresa; introduce el PIN si se solicita; selecciona el movimiento habilitado. Tras la confirmación, pulsa **Listo** o espera al retorno a la pantalla inicial.

Para usar la cámara, selecciona una fuente de cámara, abre el enlace HTTPS y pulsa el botón de escaneo del quiosco original. Permite el acceso a la cámara cuando lo solicite el navegador. Se reutiliza el lector nativo de Odoo, incluida su selección de cámara frontal o trasera.

Para usar un lector externo de código de barras/RFID, debe enviar el identificador de la credencial como teclado y estar configurado con la distribución de teclado del dispositivo. Se mantiene el servicio de códigos de barras de Odoo. La lectura identifica al empleado y después muestra los seis movimientos; no marca asistencia por sí sola.

La identificación manual conserva las tarjetas con foto, el buscador, los departamentos y la paginación originales. Los departamentos de varias empresas se distinguen por el nombre de su empresa. El PIN se solicita de acuerdo con la empresa de cada empleado y usa el teclado original.

Estas funciones corresponden a un navegador de computadora, tableta o teléfono. Este complemento no agrega una integración con huella, reconocimiento facial o terminales biométricas sin navegador.

La fecha y hora del encabezado corresponden al reloj del dispositivo. La hora guardada y la confirmación del movimiento provienen del servidor de Odoo. Mantén correcta la hora del dispositivo para que la referencia visual sea coherente.

Por privacidad, una identificación pendiente vuelve al inicio después de aproximadamente 110 segundos sin registrar un movimiento. Esto no cierra una jornada ni constituye una alerta por duración de comida.

Si se pierde una respuesta al guardar, el quiosco no repite automáticamente el movimiento. Vuelve a identificar al empleado y comprueba su estado antes de intentarlo otra vez.

## 10. Enlace y configuración

Agregar o quitar empresas mantiene la URL. **Regenerar enlace** es una acción distinta: crea una URL nueva e invalida la anterior. Úsala cuando realmente necesites cambiar el acceso; después abre la nueva URL en los dispositivos.

Cambiar empresas, método de identificación, fuente del escaneo, activación o enlace invalida las identificaciones pendientes. No afecta los movimientos ya guardados ni las jornadas abiertas. Después de cambiar empresas, recarga el quiosco para actualizar también el menú de departamentos.

El quiosco contiene los datos mínimos para identificar empleados. El PIN no se guarda en la pantalla ni se exporta. Las claves de enlaces individuales de otras empresas no se entregan al navegador del enlace unificado.

## 11. Reportes y paso a producción

Los movimientos utilizan los mismos registros de Asistencias del módulo principal. Para reportes, usa sus opciones habituales de Excel/PDF y los filtros por empresa. La configuración de columnas, exclusiones y ausencias de la versión 4.2 permanece en ese módulo.

Antes de instalar en principal, comprueba en tu base de pruebas:

- Identificación de un empleado de cada empresa sin marcado automático.
- Una jornada con comida y dos salidas temporales pagadas.
- Bloqueo después de Salida final y autorización de nueva entrada por RH.
- Agregar una cuarta empresa y retirar otra conservando el mismo enlace e historial.
- Rechazo de una selección que quedó abierta antes de retirar la empresa.
- Funcionamiento de un enlace individual y de los reportes actuales.
- Cámara o lector habitual, fotos, PIN y pantalla original en el dispositivo compartido.

Después incorpora únicamente la carpeta del complemento a principal. Si ya está instalado allí, **actualízalo**; si nunca se instaló, instálalo y configura el enlace. La configuración y los registros de la base de pruebas no se trasladan al fusionar el código. Cada base conserva su propio enlace.

Consulta `VALIDACION.md` para el alcance real de las comprobaciones técnicas de esta entrega.

Referencia del funcionamiento nativo del escaneo: [Quioscos — documentación oficial de Odoo 19](https://www.odoo.com/documentation/19.0/es/applications/hr/attendances/kiosks.html).

Licencia LGPL-3.
