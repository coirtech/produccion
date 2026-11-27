# Validación de COIRTECH Asistencias V4.2

**Versión entregada: 19.0.4.2.0 · Fecha: 23 de noviembre de 2026**

## Resultado funcional

**157 pruebas funcionales ejecutadas en el ORM real de Odoo 19: 0 fallos, 0 errores.**

Se probó la instalación desde cero en una base aislada y la actualización de una segunda base que tenía instalada la V4.1 original. Ambas cargaron los modelos, vistas, permisos y reglas correctamente. Después de corregir únicamente la paginación visual del PDF, se repitieron las **35 pruebas de reportes y visibilidad de ausencias**, también con 0 fallos y 0 errores. La modificación visual no cambió el código Python, los datos ni los permisos.

| Grupo | Pruebas funcionales |
|---|---:|
| Comidas originales | 13 |
| Seis movimientos, bloqueo y autorización V2 | 17 |
| Reportes V2 | 5 |
| Faltas V3 | 22 |
| Reportes V3 | 6 |
| Vista unificada V3 | 6 |
| Proyección Gantt y permisos | 12 |
| Exclusión y ausencias aprobadas V4 | 28 |
| Reportes V4 | 8 |
| Vista diaria V4 | 6 |
| Ausencias futuras V4.1, ampliadas | 5 |
| Configuración de columnas y formularios V4.2 | 15 |
| Acceso a la configuración desde el asistente V4.2 | 3 |
| Excel/PDF y nuevos campos opcionales V4.2 | 11 |
| **Total** | **157** |

El contador interno de 185 de la primera ejecución incluye preparación de clases; no representa 185 pruebas funcionales. Los documentos VALIDACION_V4.md, VALIDACION_V3.md y VALIDACION_V2.md conservan evidencia histórica de sus respectivas versiones y no sustituyen esta comprobación.

## Entorno utilizado

- Código oficial de Odoo 19 Community, commit `e06b404aef857d606e302814324e3fb97cdd9aec`.
- Python 3.12, PostgreSQL 17.12 y módulos nativos completos Asistencias, Ausencias y sus dependencias.
- Mismo conjunto oficial de nueve módulos adicionales de Ausencias verificado en V4; no se utilizaron sustitutos ficticios de Odoo o Enterprise.
- PDF generado por QWeb y wkhtmltopdf 0.12.6.1 a través de los controladores HTTP reales.
- Las bases y los empleados utilizados son datos sintéticos del entorno aislado, sin conexión con la base de producción del cliente.

## Personalización comprobada

- Lectura de valores predeterminados sin crear configuraciones automáticamente.
- Configuraciones independientes por empresa, Excel/PDF y Resumen/Detalle.
- Ocultar, renombrar, ordenar, guardar y volver a abrir conserva las elecciones.
- Creación desde el menú y edición mediante el formulario nativo `Form` de Odoo, incluidos los campos de las dos tablas de columnas.
- Vista del asistente compilada para administrador y responsable de Asistencias sin acceso privado al perfil de empleado.
- Copiar al otro formato y restaurar solo el formato seleccionado.
- Validación de encabezados vacíos o mayores de 80 caracteres y de una sección sin columnas visibles.
- Sustitución de la última columna visible en una sola operación de guardado, sin rechazar un estado intermedio del formulario.
- Catálogo cerrado: se rechaza mover columnas entre configuraciones, editar claves internas o introducir expresiones/campos arbitrarios.
- Administradores autorizados para configurar; responsables autorizados para leer/exportar; límites de compañía y acceso mediante IDs conocidos.
- Excel con nombres de hoja únicos, encabezados literales, ausencia de fórmulas inyectadas, fechas/duraciones numéricas y valores negativos nativos correctamente conservados.
- PDF con encabezados escapados, columnas ocultas sin reaparecer en títulos o pie nativo y bloques de hasta ocho columnas.
- Última salida y regreso correspondientes: un intervalo nuevo abierto nunca hereda el regreso de uno anterior.
- Horas extra aprobadas nativas mostradas una sola vez por jornada cerrada, sin añadirlas otra vez a las horas trabajadas ni incluir las pendientes de aprobación.
- FALTA roja conservada, con identificación alternativa de la fila cuando se ocultan sus columnas de estado; permisos aprobados con aspecto normal.

## Ausencias futuras y reglas anteriores

Se ejecutaron las reglas de V1–V4 junto con las de la versión actual. En particular:

- Las cuatro categorías futuras se omiten de búsquedas, conteos, agrupaciones, IDs conocidos, selecciones guardadas, Excel y PDF, incluso en solicitudes directas de exportación.
- Una solicitud que abarca pasado, hoy y futuro conserva sus fuentes y solo muestra las filas hasta hoy según la zona horaria guardada del indicador.
- La zona del usuario o un cambio posterior de zona de compañía no adelanta una fecha del indicador ya registrado.
- Ausencias sin categoría, permisos parciales e incidencias RH futuras siguen la misma restricción de presentación.
- La exclusión por empleado oculta todos los periodos sin borrar registros; los empleados archivados no reciben nuevas faltas.
- Corte fijo de las 09:00 de lunes a viernes, sin faltas automáticas en sábado/domingo; la entrada real resuelve la falta.
- Permiso parcial sin asistencia: revisión RH al concluir el tramo exigible, nunca una falta automática de día completo.
- Comidas/salidas pagadas, seis movimientos, bloqueo tras Salida final, autorización adicional y permisos del Gantt continúan funcionando.

Los archivos de lógica de ausencias, asistencia, empleados, comidas/salidas, quiosco y puente Gantt se compararon con la base V4.1: permanecen sin cambios. La actualización añade configuración y presentación de exportaciones sobre esos datos.

## Actualización real V4.1 → V4.2

Se instaló el ZIP V4.1 original antes de crear una muestra y guardar sus valores. Después se actualizó a V4.2 y se compararon de nuevo los registros:

| Registros de la muestra | Conservados |
|---|---:|
| Asistencias originales | 7 |
| Salidas de trabajo | 3 |
| Autorización adicional ya consumida | 1 |
| Solicitudes nativas aprobadas | 4 |
| Empleados y casillas de exclusión | 11 |
| Intervalo de historial de exclusión | 1 |
| Indicadores diarios originales | 8 |

Se conservaron identidad, fechas, horas, política COIRTECH, relaciones y estados pertinentes. La jornada COIRTECH de nueve horas mantuvo nueve horas; la nativa mantuvo ocho. Una comida y una salida de trabajo abiertas continuaron pendientes. La autorización consumida siguió impidiendo una entrada adicional. El historial excluido permaneció disponible en origen y oculto en el Reporte.

Los dos indicadores futuros de la incapacidad siguieron existiendo con su aprobación original, sin mostrarse en la vista ni en los archivos. Guardar columnas, copiar entre formatos y restaurar no alteró los registros originales. No aparecieron asistencias ficticias ni faltas automáticas históricas nuevas.

## Descargas reales y revisión visual final

Se utilizó una sesión HTTP autenticada en el servidor de prueba, mediante los botones y métodos públicos que usa la interfaz de Odoo. Se abrieron configuraciones desde el asistente, guardaron encabezados/orden/visibilidad y comprobaron sus valores al volver a abrirlas.

| Configuración | Excel real | PDF real | Revisión visual |
|---|---|---:|---|
| Valores predeterminados, una empresa | 2 hojas | 4 páginas | Todas aprobadas |
| Dos empresas con encabezados y columnas distintos | 4 hojas | 5 páginas | Todas aprobadas |
| Todas las columnas, muestra reducida | Cubierto por pruebas del exportador | 7 páginas | Todas aprobadas |
| Una sola columna y encabezado largo | 2 hojas | 2 páginas | Todas aprobadas |

**Se renderizaron e inspeccionaron las 18 páginas finales.** Se corrigió un título que quedaba aislado al pie de página colocándolo dentro del encabezado repetido de su tabla. Tras regenerar los archivos se confirmó que los títulos acompañan a las tablas y se repiten con las columnas en sus continuaciones. No quedaron textos superpuestos, columnas cortadas ni encabezados aislados en las cuatro muestras.

Las descargas comprobaron además:

- Doce filas visibles en el Reporte de la muestra, conservando las horas reales, FALTA e incidencias.
- Configuraciones distintas de las dos empresas, sin mezclar encabezados ni datos.
- Solicitud PDF con IDs futuros o excluidos proporcionados directamente: esas fuentes no aparecen.
- Los dos días futuros de incapacidad siguen aprobados en origen y permanecen ocultos en los archivos.
- Los datos privados de la solicitud de ausencia no se exportan.
- Los archivos Excel mantienen textos literales, fechas/duraciones numéricas y sus encabezados elegidos.
- El intento de descargar el Excel sin autenticación fue rechazado.
- Asistencias y solicitud aprobada de la muestra conservadas después de las operaciones de configuración y exportación.

El logotipo y nombres de empresa de los PDF de comprobación pertenecen a la muestra sintética. El módulo utiliza el diseño documental configurado para cada empresa en Odoo.

## Alcance de Enterprise

Las pruebas cubren el backend real y la proyección SQL del Gantt, incluidos sus permisos. **No se ejecutó la interfaz visual Enterprise `web_gantt`/`hr_attendance_gantt`**, porque esos módulos no están disponibles en el entorno de prueba. El código del puente se conserva respecto de V4.1.

El complemento incluye `tests/test_enterprise_gantt.py` para ejecutarlo en una base Enterprise de Staging con sus dependencias reales. La prueba visual de ese tablero y de cualquier personalización Studio u otro complemento de la base del cliente corresponde a ese entorno.

## Comandos de referencia

Sobre una base de pruebas:

```bash
odoo-bin -d BASE_DE_PRUEBAS -u coirtech_attendance_meal_control --test-enable --test-tags /coirtech_attendance_meal_control --stop-after-init
```

En Enterprise, con el puente y sus dependencias instalados:

```bash
odoo-bin -d BASE_ENTERPRISE_DE_PRUEBAS -u coirtech_attendance_absence_gantt --test-enable --test-tags /coirtech_attendance_absence_gantt --stop-after-init
```

Los archivos de prueba HTTP, credenciales sintéticas, bases de datos y dependencias del entorno no se incluyen en el ZIP instalable.
