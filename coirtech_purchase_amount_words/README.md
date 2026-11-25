# COIRTECH - Importe con letra en ordenes de compra (Odoo 19)

**Nombre tecnico:** `coirtech_purchase_amount_words`  
**Version:** `19.0.2.0.0`  
**Compatible con:** Odoo 19 SH Enterprise  
**Dependencia:** `purchase` (Compras). Es un modulo independiente del modulo de Ventas.

## Funcionamiento

El PDF **Orden de compra** muestra debajo del bloque de totales, con fuente de 14 px,
la leyenda **Importe con letra:** o **Amount in words:** seguida del total con impuestos en el idioma del proveedor.
Usa la moneda de la orden y conserva el mismo estilo de conversion que el modulo
COIRTECH de Ventas V6.

- MXN 1,250.60 -> MIL DOSCIENTOS CINCUENTA PESOS 60/100 M.N.
- USD 500.25 -> QUINIENTOS DÓLARES 25/100 USD
- MXN 10,000.00 -> DIEZ MIL PESOS 00/100 M.N.
- Las monedas distintas de MXN y USD no generan esa leyenda.
- El idioma se toma de `purchase.order.partner_id.lang`, independientemente de la moneda.
- Ingles (en_US, en_GB y otras variantes en_*): etiqueta y texto en ingles.
- Espanol y cualquier idioma distinto del ingles, incluido un idioma no definido: conserva el espanol original.
- Ejemplo proveedor en_US, USD 1,250.60: ONE THOUSAND TWO HUNDRED FIFTY DOLLARS 60/100 USD.
- Ejemplo proveedor en_US, MXN 1,250.60: ONE THOUSAND TWO HUNDRED FIFTY MEXICAN PESOS 60/100 MXN.
- Para cambiarlo, abre la ficha del proveedor (Contactos), selecciona su Idioma, guarda y vuelve a generar el PDF. Si el ingles no aparece, instala/activa el idioma desde Ajustes > Traducciones > Idiomas (o el asistente de agregar idiomas).
- Los PDF previamente descargados o adjuntos no cambian retroactivamente.
- No modifica precios, impuestos, descuentos ni pagos, y no modifica el modulo de Ventas.
- El campo calculado (no almacenado) es `purchase.order.coir_purchase_amount_total_in_words`.

**Alcance del PDF:** amplia la plantilla estandar `purchase.report_purchaseorder_document`
que contiene el precio y total. La plantilla independiente **Solicitud de presupuesto/RFQ**
`purchase.report_purchasequotation_document` no muestra precios ni total por diseno
estandar, por lo que NO se modifica. Si usas una copia personalizada del PDF de compra,
debera revisarse para asegurarse de que hereda la plantilla estandar.

## Instalacion o actualizacion (primero Staging)

1. Descomprime el ZIP.
2. En GitHub, selecciona la rama de pruebas `odometro` de `coirtech/produccion`.
3. Arrastra una sola carpeta `coirtech_purchase_amount_words` a la raiz del repositorio.
   Asegurate de que `__manifest__.py` quede directamente dentro de esa carpeta.
   Evita duplicados con sufijos ` 2` o carpetas anidadas.
4. Haz **Commit changes** y revisa en Odoo.sh que la compilacion de Staging sea correcta.
5. Entra con **Connect** > **Aplicaciones** > **Actualizar lista de aplicaciones**.
6. Quita el filtro predeterminado, busca `coirtech_purchase_amount_words` y pulsa Actualizar si ya esta instalado, o Activar si es nuevo. No desinstales la version anterior.
7. Abre **Compras > Ordenes de compra**, imprime **Orden de compra** y verifica
   ejemplos MXN, USD, centavos .00, con IVA y proveedores en espanol e ingles.
8. Solo cuando se haya probado, lleva exclusivamente este modulo a `main`
   (rama de Production previamente confirmada) con respaldo y revision del cambio.

## Sobre reportes personalizados

Este modulo usa el XPath estable `//div[@id='total']` del reporte estandar Odoo 19.
Si una vista de Odoo Studio o un reporte personalizado reemplaza ese bloque,
Odoo puede mostrar un error al instalar o la leyenda podria no aparecer en la
plantilla alternativa. Primero prueba en Staging, y no cambies la rama Production
si no se ha verificado el PDF resultante.

## Validacion de esta version

Se comprobaron las conversiones con pruebas locales de Python, la eleccion del idioma,
la asignacion de ambos campos con objetos simulados y la sintaxis XML. No se instalo
ni se ejecuto esta version en una instancia Odoo 19 Enterprise durante esta revision.
Valida el PDF real en Staging, especialmente si utilizas un reporte personalizado.
