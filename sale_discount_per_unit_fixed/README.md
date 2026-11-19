# Descuento fijo por pieza - Odoo 19 SH Enterprise

Modulo para Ventas. Incorpora el campo monetario **Desc. $/pza** en cada linea de producto de la cotizacion, y lo presenta en el PDF y en el portal de cotizaciones. No requiere introducir porcentajes.

## Ejemplo

- Cantidad: 10 piezas
- Precio unitario: $100.00 MXN
- Descuento por pieza: $15.00 MXN
- Subtotal sin impuestos: $850.00 MXN

## Instalacion en Odoo.sh (primero staging)

1. Descomprima el archivo ZIP.
2. Copie la carpeta `sale_discount_per_unit_fixed` dentro de la carpeta de addons personalizados de su repositorio Odoo.sh (por ejemplo `custom_addons/sale_discount_per_unit_fixed`). No copie la carpeta contenedora del ZIP.
3. Haga commit y push a su rama `staging` de Odoo.sh.
4. Compruebe que el build de staging termina correctamente y abra esa base.
5. En Odoo active el modo desarrollador, entre a Aplicaciones, y ejecute **Actualizar lista de aplicaciones** (si la pantalla ofrece esta accion).
6. Quite el filtro predeterminado `Aplicaciones`, busque `Ventas - Descuento monetario por pieza` e instale el modulo.
7. Entre en Ventas > Cotizaciones y pruebe con un pedido nuevo.
8. En la linea de producto capture el descuento en pesos en `Desc. $/pza`. El subtotal se recalcula automaticamente.
9. Compruebe PDF, enlace de portal e impuestos/factura antes de migrar el cambio a produccion.

## Observaciones tecnicas

- Usa el porcentaje interno de Odoo con precision float completa solo para computar subtotales, impuestos y factura; el usuario introduce **pesos por pieza**, y el cliente ve **pesos por pieza** en cotizacion PDF y portal.
- El descuento monetario por unidad reemplaza en esa linea cualquier descuento porcentual de tarifa. Si el campo es cero, el comportamiento de descuentos estandar permanece disponible.
- No se admite descuento fijo negativo ni mayor al precio unitario.
- No modifica el formato PDF de facturas; en una factura Odoo puede mostrar el descuento interno en porcentaje. Si tambien se quiere visualizar el descuento fijo en factura, se requiere una extension adicional.
- No se recomienda usarlo con lineas de producto combo, anticipos o configuraciones de precios especiales sin pruebas adicionales.
- Si utiliza una plantilla de cotizacion QWeb personalizada, puede ser necesario adaptar los selectores XML del reporte a esa plantilla.
- Este paquete ha sido validado a nivel de sintaxis XML y Python, pero **no ha sido instalado ni probado en su instancia de Odoo.sh**.

## Actualizacion 19.0.1.0.1 - correccion QWeb

Se corrigio el error `TypeError: unsupported operand type(s) for +: 'NoneType' and 'int'` al imprimir la cotizacion. En el PDF, la cuenta de columnas ahora se inicializa en el encabezado de la tabla, sin incrementarse dentro de la cabecera condicional `Desc./pieza`.

Para una instalacion previa, edite/sustituya en GitHub el archivo `report/sale_order_report.xml`, haga commit en la rama de pruebas y, tras el build de Odoo.sh, **Actualice** el modulo `sale_discount_per_unit_fixed` desde Aplicaciones. Un commit o build por si solo no vuelve a importar automaticamente el XML del modulo ya instalado.

**Aviso:** corregido por inspeccion de la traza y el XML oficial de Odoo 19; no probado en la base de datos real del usuario.

## Actualizacion 19.0.1.0.2

Para instalaciones existentes: reemplazar report/sale_order_report.xml y aumentar la version en __manifest__.py a 19.0.1.0.2. Hacer commit en la rama de pruebas, esperar el build y Actualizar el modulo desde Aplicaciones. El error viejo despues de modificar el archivo indica que la vista QWeb almacenada en la base de datos no se ha actualizado o que otra vista conserva el codigo viejo.

## Actualización 19.0.1.0.3 (error de XPath al actualizar)

Error corregido: `Element '<xpath expr="//table[hasclass('o_main_table')]/thead/t[@t-set='colspan_count']">' cannot be located in parent view`.
La versión 19.0.1.0.3 elimina ese XPath y evita modificar `colspan_count` dentro del encabezado. Ajusta los `colspan` en las filas de secciones y combos.

Para una instalación existente en la rama `odometro` de Odoo.sh:
1. Reemplazar `report/sale_order_report.xml` en GitHub con el contenido de la versión 19.0.1.0.3.
2. Editar `__manifest__.py` y cambiar la versión a `19.0.1.0.3`.
3. Confirmar los cambios (*commit*) en `odometro`.
4. Esperar a que la nueva compilación termine correctamente; después abrir esa base y, en **Aplicaciones**, hacer clic en **Actualizar (Upgrade)** para el módulo.
5. Probar un pedido simple en PDF, luego cotizaciones con secciones, combos y descuentos mixtos antes de pasarlo a producción.

La instalación real en Odoo.sh no ha sido probada aquí; la validación se ha realizado sobre archivos XML/Python y selectores del reporte estándar de Odoo 19.
