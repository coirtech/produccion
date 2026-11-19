# COIRTECH - Horas en odómetro y reportes (Odoo 19.sh Enterprise)

**Nombre técnico:** `coirtech_fleet_odometer_hours`  
**Versión:** `19.0.1.1.0`  
**Dependencia:** `fleet`

## Funciones

1. Agrega **Horas** (`hours`) al campo `fleet.vehicle.odometer_unit`, además de km y mi.
2. En **Flotilla > Reportes > Odómetros**, incorpora filtros **Horas**, **Kilómetros** y **Millas**.
3. En **Flotilla > Reportes > Horas de uso**, abre el análisis mensual con un dominio permanente que solo incluye vehículos con unidad Horas.
4. En **Flotilla > Reportes > Lecturas con unidad**, ofrece una lista detallada con fecha, vehículo, lectura y unidad.
5. En **Flotilla > Odómetros**, selecciona una o más lecturas y usa **Imprimir > Lecturas de odómetro (con unidad)** para producir un PDF. También está en el formulario de la lectura.

No se altera el reporte nativo mediante QWeb ni se cambia la vista SQL que calcula las diferencias mensuales.

## Instalación y actualización

**Si todavía no instalaste el módulo anterior**: sube la carpeta `coirtech_fleet_odometer_hours` del ZIP a la raíz de la rama de pruebas `odometro` y realiza un commit. Espera a que el build de Odoo.sh esté correcto y en Odoo abre Aplicaciones, actualiza la lista de aplicaciones e instala **COIRTECH - Horas en odometro y reportes**.

**Si ya instalaste la versión anterior `19.0.1.0.0`**: REEMPLAZA los archivos de esa MISMA carpeta con los de este ZIP. Mantén el mismo nombre de carpeta. Confirma los cambios en GitHub, espera al nuevo build de Odoo.sh, entra a Odoo (base de pruebas) y usa Aplicaciones > buscar módulo > **Actualizar (Upgrade)**. NO instales una segunda copia del módulo ni lo desinstales.

### Pruebas recomendadas en Staging

1. Crea un vehículo nuevo sin historial, marca Unidad del odómetro = Horas y guarda.
2. Registra dos lecturas (ejemplo 100 h y 112 h en fechas diferentes).
3. Verifica que la lista Flotilla > Odómetros muestre Horas en la columna Unidad.
4. En Flotilla > Reportes > Horas de uso, asegúrate de que solo se muestren lecturas de vehículos en Horas.
5. En Flotilla > Reportes > Lecturas con unidad, selecciona lecturas e imprime el PDF. Comprueba que cada fila diga Horas, km o mi según corresponda.
6. Verifica que los reportes preexistentes de kilómetros se sigan mostrando correctamente.

## Advertencias de datos y reportes

- **No mezcles km, mi y horas en una misma suma ni interpretes esa suma como horas.** En el reporte estándar sin filtros pueden coexistir vehículos con unidades distintas. Usa los filtros de unidad o el menú dedicado Horas de uso.
- El análisis mensual nativo de Odoo 19 calcula diferencias distribuidas/interpoladas entre lecturas; en vehículos configurados en Horas, esas diferencias representan horas de uso estimadas por mes, **no una cuenta de horas reales tomadas continuamente**.
- El PDF imprime **lecturas individuales** (valores acumulados), sin totalizar km, mi ni horas entre sí.
- El campo de unidad de la lectura está relacionado con el vehículo. Cambiar la unidad de un vehículo con historial puede afectar la interpretación de sus registros anteriores, sin convertir valores.
- No se ha realizado una instalación real sobre tu base de datos. Comprueba el resultado en staging antes de modificar producción.
