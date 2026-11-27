# Validación V4.4 — tipos de Tiempo personal y reportes

## Qué se corrige

- Muestra el tipo real de la solicitud (`hr.leave.holiday_status_id`) en lugar
  de un nombre base inglés conservado en traducciones antiguas.
- Las empresas con país México usan una variante española **activa** para sus
  reportes cuando el idioma del contacto de empresa es inglés. Las demás
  empresas conservan la configuración anterior de idioma.
- Resincroniza las incidencias persistidas mediante la migración sin tocar las
  solicitudes, sus aprobaciones, jornadas ni registros biométricos.

## Pruebas de regresión incluidas

`tests/test_v4_4_leave_labels.py` contempla:

1. Un tipo con nombre base `Home Office` y traducción `Vacaciones` para México;
   cron en inglés y acceso al reporte desde español.
2. Dos tipos distintos `Vacaciones` y `vacaciones` sin mezclar empleados.
3. Valor de incidencia antiguo almacenado como `Home Office` que se corrige
   tras sincronizar y aparece corregido en el reporte diario.
4. Ausencia pendiente sin horas autorizadas ni aviso de aprobación.
5. Confirmación de que los permisos y asistencias originales no se alteran.

## Validación de esta entrega

Revisión de sintaxis de Python, manifiestos, XML, estructura ZIP y comparación
con la V4.3. Las pruebas de integración Odoo 19 están incluidas como código
pero deben ejecutarse en tu staging `odometro` con la base y los idiomas reales.
No se declara validación de base de datos Enterprise ni de cámara física.
