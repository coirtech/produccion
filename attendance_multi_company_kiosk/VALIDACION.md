# Validación — Quiosco Multiempresa 19.0.1.1.0

**Fecha:** 24 de noviembre de 2026.  
**Alcance:** corrección del diseño y del escaneo, conservando la configuración y los registros de la versión 19.0.1.0.0.

## Entorno utilizado

Odoo 19 Community con el código oficial `odoo/odoo` de la revisión `e06b404aef857d606e302814324e3fb97cdd9aec`, Python 3.12, PostgreSQL 17 y las dependencias reales de Asistencias y Ausencias.

El módulo principal fue `coirtech_attendance_meal_control` **19.0.4.2.0**, procedente del ZIP previamente entregado `coirtech_asistencias_odoo19_v4_2.zip`. Su código no se modificó. El complemento opcional de Gantt no es necesario para instalar este quiosco.

Las comprobaciones se realizaron en una base aislada. No se accedió ni se modificó la base, el repositorio o la rama principal del usuario.

## Actualización real desde la versión anterior

Se actualizó el complemento de **19.0.1.0.0 a 19.0.1.1.0**, sobre una base que ya tenía un quiosco configurado y ocho asistencias.

Una comparación de los datos antes y después confirmó igualdad en:

- Token y URL del quiosco existente.
- Nombre, modo de identificación, revisión y empresas participantes.
- Los ocho registros de asistencia, incluidos sus campos y relaciones.
- Identidades de empleados.
- Configuración y claves de los quioscos individuales.

El campo nuevo `barcode_source` quedó en `company`: hereda el ajuste nativo de la primera empresa participante elegible. La actualización no regeneró el enlace ni creó otro quiosco.

## Pruebas del modelo

Las **12 pruebas automatizadas de Odoo** terminaron con **0 fallos y 0 errores**. Incluyen agregar o retirar empresas manteniendo enlace e historial, requisitos de activación, permisos administrativos, protección de la selección de empresas, generación de claves en servidor, regeneración voluntaria, duplicación, creación mediante la vista real, desactivación y las opciones nuevas de escaneo.

Las pruebas de escaneo comprueban la herencia de la configuración nativa, la elección explícita de cámara frontal, trasera o lector sin cambiar el enlace y la fuente predeterminada cuando no hay empresas elegibles.

## Servidor y recorridos HTTP

Pasaron **19 grupos de comprobaciones** contra el servidor real. Tras los últimos cambios se ejecutó un pase concreto de **cinco grupos adicionales**, también satisfactorio.

Se comprobó lo siguiente:

- El enlace unificado inicia el quiosco público original de Odoo y la extensión original de seis movimientos.
- Las listas conservan fotos, nombre de la empresa, búsqueda, departamentos y paginación.
- La lectura de datos del PIN y la identificación no crean ni cierran asistencias.
- La selección de empresas se aplica también en consultas, filtros y acciones.
- PIN incorrecto, empleado ajeno, filtros no permitidos y contexto JSON-RPC falsificado se rechazan.
- Las credenciales producen una identificación vinculada a la sesión y de un solo uso.
- Entrada, comida, regreso, salidas temporales repetidas y salida final usan las reglas existentes.
- Comida y salidas temporales permanecen dentro del tiempo pagado.
- Se exige el regreso pendiente y se mantiene el bloqueo después de Salida final.
- La autorización de RH para una entrada adicional se consume una sola vez.
- Dos entradas simultáneas generan una sola asistencia.
- Cancelar descarta la identificación sin marcar asistencia.
- Una cancelación tardía de un ticket anterior no borra la identificación más reciente.
- Confirmaciones y coordenadas no válidas se rechazan sin saltarse las reglas del módulo principal.
- Retirar una empresa invalida sus identificaciones pendientes y conserva historial y enlace.
- Se puede agregar una cuarta empresa o reincorporar otra.
- Cambiar la empresa de una ficha invalida su identificación anterior.
- Los enlaces individuales conservan sus rutas, arranque y configuración.
- Desactivar/reactivar o regenerar el enlace tiene el efecto correspondiente.
- Los generadores existentes de Excel y PDF siguen funcionando con sus filtros y acceso autenticado.

El servidor compiló y sirvió los recursos finales de JavaScript y CSS. Incluyen los componentes nativos de cámara, el servicio de código de barras/RFID, las tarjetas, el teclado PIN y los seis movimientos. El paquete de los enlaces individuales no incluye el puente multiempresa.

## Componentes originales de la interfaz

Pasaron **14 escenarios de Owl/JSDOM**, usando las clases reales de Odoo 19 y el compilador oficial de plantillas:

1. Fondo, reloj y botón de cámara originales.
2. Método nativo de apertura de cámara frontal y entrega del código leído a identificación.
3. Selector original de acciones y ubicación según la empresa del empleado.
4. Bus nativo USB/RFID, sin doble lectura mientras se elige movimiento.
5. Cancelación serializada antes de otra identificación.
6. Tarjetas, fotografías, búsqueda, empresa y departamentos.
7. Respuestas de búsqueda atrasadas, lista no disponible y ventanas de poca altura.
8. Paginador nativo con sus filtros.
9. Teclado PIN numérico original.
10. Comida pagada y bloqueo después de salida final.
11. Error de escritura sin reintento automático.
12. Cámara trasera, cancelación del escáner y departamentos en pantalla pequeña.
13. Configuración no válida sin recurrir al marcado automático nativo.
14. Enlaces individuales con sus rutas y enlace de instalación originales.

Se aplicaron correctamente las **11 expresiones XPath** de las extensiones que participan en las pantallas. La comparación de los subárboles originales verificó que no se reemplazaron el escáner, el reloj y su contenedor, el paginador, el teclado PIN ni la cuadrícula y pie de los seis botones.

Se agregaron leyendas con la empresa y se ocultaron logos/marca fija mediante reglas limitadas al enlace unificado.

## Límite de estas comprobaciones

Las pruebas de componentes simulan las respuestas RPC, los servicios del navegador y la captura de cámara. Se ejecutaron los métodos reales del escáner y sus callbacks con un código de prueba. **No se probó una cámara física, un lector físico ni la apariencia en píxeles en la tableta del usuario.**

La corrección reutiliza la cámara nativa; los permisos y el funcionamiento del dispositivo real deben comprobarse al abrir el enlace actualizado. La compatibilidad con personalizaciones Enterprise/Studio específicas se comprueba en la rama de pruebas del usuario.

## Reproducir las pruebas de configuración incluidas

Con el módulo principal y este complemento disponibles en las rutas de addons de una base de pruebas:

```bash
odoo-bin -d BASE_DE_PRUEBAS -u attendance_multi_company_kiosk --test-enable --test-tags /attendance_multi_company_kiosk --stop-after-init
```

Para instalar por primera vez se utiliza `-i` en lugar de `-u`. Los parámetros de conexión y las rutas corresponden a cada instalación.

El ZIP contiene el complemento, su documentación y las pruebas de configuración. No incluye bases de datos, credenciales, sesiones ni empleados de prueba.

## Referencias

- [Código oficial de Odoo 19 utilizado](https://github.com/odoo/odoo/tree/e06b404aef857d606e302814324e3fb97cdd9aec/addons/hr_attendance).
- [Configuración de quioscos y escaneo — Odoo 19](https://www.odoo.com/documentation/19.0/es/applications/hr/attendances/kiosks.html).

