# COIRTECH - Importe con letra en ventas (MXN / USD)

**Modulo tecnico:** `coirtech_sale_amount_words`  
**Version:** `19.0.1.0.5`  
**Compatible con:** Odoo 19 SH Enterprise  
**Dependencia:** `sale`

## Formato actualizado (V6)

El total de la cotizacion/orden de venta se escribe en letras en espanol y los
centavos se representan al final en formato `00/100`, `01/100`, `25/100`, etc.
**Incluso si el total es entero, se muestra `00/100`.**
Se anade `M.N.` al texto de importes en pesos mexicanos y `USD` al de dolares.
La moneda del documento sigue determinando si se escribe PESOS o DOLARES.

| Moneda | Importe | Texto en el PDF |
|---|---:|---|
| MXN | 100.00 | CIEN PESOS 00/100 M.N. |
| MXN | 1250.60 | MIL DOSCIENTOS CINCUENTA PESOS 60/100 M.N. |
| USD | 500.25 | QUINIENTOS DÓLARES 25/100 USD |
| USD | 500.00 | QUINIENTOS DÓLARES 00/100 USD |

El texto del importe con letra se presenta en el PDF con **14 px** (antes 11 px).
Solo modifica ese bloque del reporte; no cambia el tamanio del resto de la cotizacion.

El importe es el **total con impuestos y descuentos** de la orden. Las monedas
distintas de MXN y USD no muestran este texto. Las cotizaciones y ordenes de venta
usan la misma plantilla QWeb `sale.report_saleorder_document`; el modulo inserta
la leyenda despues de `so_total_summary`. No modifica los calculos ni las lineas.

## Instalacion nueva (sin versiones anteriores instaladas)

1. Descomprime el ZIP.
2. Sube **solo una carpeta** `coirtech_sale_amount_words` a la raiz del repositorio
   de GitHub en tu rama de pruebas `odometro`.
3. Confirma los cambios con Commit changes; comprueba el build en Odoo.sh.
4. En Staging: modo desarrollador > Aplicaciones > Actualizar lista > busca
   `coirtech_sale_amount_words` (sin filtro de Aplicaciones) > Instalar.
5. Prueba PDF de Cotizacion y Orden en MXN y USD, con y sin centavos.

## Si ya instalaste una version anterior

1. **No crees una carpeta nueva.** Reemplaza estos archivos dentro del modulo
   `coirtech_sale_amount_words` existente:
   - `report/sale_order_report.xml`
   - `__manifest__.py`
   No es necesario reemplazar la conversion numerica.
2. Haz commit en la rama de pruebas; espera el build de Odoo.sh.
3. En Aplicaciones, busca el modulo instalado y selecciona **Actualizar (Upgrade)**.
4. Comprueba el PDF. Pasa a produccion solo despues de validar y revisar un respaldo.

**Nota:** No modifica las facturas ni reportes personalizados independientes de la
plantilla estandar de venta. Las vistas personalizadas por Studio deben probarse
siempre en Staging.
