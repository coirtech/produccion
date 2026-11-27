# Validación de COIRTECH Asistencias V4.3

**Versión 19.0.4.3.0 · Comprobación: 27 de noviembre de 2026.**

Se utilizó Odoo 19 real con PostgreSQL, Asistencias, Tiempo personal y Manufactura. El código oficial de la instalación de prueba corresponde al commit `e06b404aef857d606e302814324e3fb97cdd9aec`. Se instaló además `attendance_multi_company_kiosk` V1.1 para comprobar su compatibilidad.

## Resultado final de las pruebas automáticas

**189 pruebas terminadas: 0 fallos y 0 errores.** Incluyen la suite del módulo principal y 14 pruebas del complemento multiempresa. Se ejecutaron en una base de pruebas limpia, separada de la muestra con columnas personalizadas usada para comprobar la migración.

La entrega incorpora 20 pruebas nuevas para las reglas de V4.3, sus reportes y los permisos de empleados. Las comprobaciones cubren:

- Solicitudes presentadas, primera aprobación y aprobación final.
- Nombre nativo del tipo, sin categoría adicional ni indicación de aprobación pendiente.
- Nombre traducido estable según el idioma de empresa, aunque cambie el contexto del usuario o cron.
- Renombrado del tipo y uso automático de tipos nuevos.
- Intervalos aprobados junto a intervalos sin aprobar: cobertura de ausencia correcta y horas autorizadas solo de los aprobados.
- Solicitudes parciales, superposiciones y revisión de RH conforme a las reglas anteriores.
- Rechazo actual y cancelación histórica sin inventar una FALTA retroactiva.
- Solicitudes futuras ocultas y empleados excluidos en listas, agrupaciones y exportaciones.
- Conservación de marcajes reales, comidas y salidas pagadas, bloqueo después de Salida final y autorización adicional de un solo uso.
- Columnas configurables por empresa/formato, datos numéricos del Excel y plantillas PDF.
- Permisos de lectura, restricciones por empresa y acceso público frente a privado del empleado.

La sintaxis Python y XML de ambos módulos también se comprobó antes del empaquetado.

## Reproducción y corrección del error de Manufactura

Se instaló primero el ZIP V4.2 original. Con un usuario que tenía Manufactura y Asistencias, sin el grupo privado de RH, se reprodujo este error al realizar una lectura normal de empleados sin caché:

> The fields “coir_meal_section_id”, which you are trying to read, are not available for employee public profiles.

La misma comprobación después de actualizar a V4.3 funcionó para usuarios internos, de Asistencias y de Administración de Asistencias. Ninguno necesitó recibir acceso privado a Recursos Humanos. La lectura explícita de campos privados siguió siendo rechazada.

Se comprobó también que RH puede cambiar la sección y que el quiosco guarda correctamente la sección correspondiente a la asistencia, conservando la sección histórica aunque después cambie la del empleado.

Referencia primaria del criterio aplicado: https://github.com/odoo/odoo/blob/19.0/addons/hr/models/hr_employee.py . La clase de Odoo indica que los campos exclusivos del modelo privado deben limitarse al grupo de RH para evitar su precarga desde perfiles públicos.

## Actualización real desde V4.2

En otra base se instaló V4.2, se crearon registros de muestra y se guardaron sus datos antes de actualizar. La actualización ejecutó la migración V4.3, sin desinstalar los complementos.

| Datos de la muestra | Resultado |
|---|---|
| 7 empleados | Identidades, empresas, secciones, exclusión y credencial conservadas. |
| 5 asistencias | Identificadores, entradas, salidas, horas trabajadas y movimientos conservados. |
| 2 salidas temporales | Relaciones y fechas conservadas; una siguió abierta. |
| 1 comida abierta | Permaneció abierta, sin un regreso inventado. |
| 1 autorización adicional consumida | Permaneció consumida y vinculada a su asistencia. |
| 3 solicitudes de Tiempo personal | Estados, fechas, tipo y duración originales conservados. |
| 1 intervalo de exclusión | Historial conservado. |
| 104 definiciones de columnas | Identidades, orden, visibilidad y encabezados personalizados conservados. |
| 2 indicadores anteriores | Identificadores y procedencia conservados. |
| Quiosco multiempresa existente | Enlace, clave, empresas, modo de identificación y cámara conservados. |

La solicitud presentada que V4.2 no mostraba quedó representada con **Permiso para trámite**, con cero horas autorizadas y manteniendo `confirm` en Tiempo personal. La aprobada pasó de su categoría antigua al nombre **Descanso autorizado**, manteniendo sus ocho horas autorizadas. La solicitud futura continuó aprobada en origen y oculta en el reporte. El empleado excluido siguió oculto.

Los únicos encabezados antiguos reemplazados fueron los que coincidían exactamente con los valores predeterminados previstos por la migración. Un encabezado propio del usuario, **Mi periodo personalizado**, y el encabezado **Colaborador conservado**, con su posición personalizada, se conservaron.

No aparecieron asistencias ficticias. La jornada de nueve horas mantuvo sus nueve horas, incluyendo la comida y la salida temporal; la jornada adicional siguió teniendo una hora.

## Descargas reales y revisión visual

Se accedió al servidor local con una sesión HTTP autenticada y se usaron los mismos métodos públicos que los botones de exportación de Odoo.

- **Excel:** descarga real de dos hojas, nombres originales de Tiempo personal, columnas personalizadas y exclusión de solicitudes futuras y empleados excluidos.
- **PDF:** descarga real de tres páginas mediante el motor nativo QWeb y wkhtmltopdf. Se renderizaron e inspeccionaron visualmente las tres páginas; nombres, periodos y horas quedaron legibles, con encabezados repetidos y sin texto superpuesto o cortado.
- **Quiosco:** el enlace multiempresa original abrió su página y compiló sus recursos CSS/JS. La identificación por código de credencial devolvió el empleado y la selección de acciones; identificar y cancelar no creó un marcaje automático.

Los nombres y el logotipo predeterminado de los documentos de comprobación pertenecen a una empresa sintética. No se incluyen esos reportes ni datos de prueba en el ZIP instalable.

## Alcance y límites

Se comprobó el backend de la proyección Gantt y sus permisos. **No se ejecutó la interfaz visual Enterprise `web_gantt`/`hr_attendance_gantt`**, porque sus módulos no están disponibles en este entorno. El código del puente Gantt conserva el de V4.2; solo cambian su versión declarada y documentación. Su prueba `tests/test_enterprise_gantt.py` permanece incluida para una base Enterprise con esas dependencias.

La comprobación de escaneo cubre la identificación del código y los recursos del quiosco; no sustituye probar la cámara o el lector físico de la empresa. Tampoco equivale a haber instalado esta versión en la base del cliente o validado sus personalizaciones Studio. Esas comprobaciones se realizan primero en la rama de pruebas.

## Ejecutar la suite en una base de pruebas

En una base limpia de pruebas con el módulo instalado:

```bash
odoo-bin -d BASE_DE_PRUEBAS -u coirtech_attendance_meal_control --test-enable --test-tags /coirtech_attendance_meal_control --stop-after-init
```

Con el complemento multiempresa disponible e instalado:

```bash
odoo-bin -d BASE_DE_PRUEBAS -u coirtech_attendance_meal_control,attendance_multi_company_kiosk --test-enable --test-tags /coirtech_attendance_meal_control,/attendance_multi_company_kiosk --stop-after-init
```

Para el puente Enterprise, con sus dependencias reales instaladas:

```bash
odoo-bin -d BASE_ENTERPRISE_DE_PRUEBAS -u coirtech_attendance_absence_gantt --test-enable --test-tags /coirtech_attendance_absence_gantt --stop-after-init
```

Los documentos VALIDACION_V4_2.md, VALIDACION_V4.md, VALIDACION_V3.md y VALIDACION_V2.md se conservan como historial de las entregas anteriores.
