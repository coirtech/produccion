# COIRTECH - Límite de recepciones por demanda

**Odoo 19 SH Enterprise** | Versión `19.0.1.0.0`  
**Nombre técnico:** `coirtech_receipt_qty_limit`  
**Dependencias:** Inventario (`stock`) y Compras/Inventario (`purchase_stock`).

## Qué hace

- Si la **Demanda** de una línea de recepción es **100**, no deja **Validar** si se intenta recibir **101**. **100 o menos** sí se permite.
- Si la recepción viene de una **orden de compra**, también verifica el acumulado de esa línea exacta: 80 ya recibidas + 21 nuevas, en una orden de 100, se bloquean. 80 + 20 se permite.
- El mensaje es una ventana de error de Odoo que comienza con **«No puedes exceder la cantidad ordenada»** y muestra el producto y las cantidades.
- Acepta **recepciones parciales** y sus pendientes, siempre que no excedan lo ordenado.
- Maneja **unidades de medida**: compara cada movimiento con su propia UoM y convierte al UoM de la orden para el acumulado.
- Usa el valor recibido neto (`qty_received`) de Odoo, por lo que contempla las devoluciones a proveedor que reduzcan lo recibido.
- Aplica a **entradas desde ubicaciones Proveedor o Tránsito** (`incoming`). No modifica entregas a clientes, traslados internos, ajustes de inventario ni devoluciones de clientes.
- No cambia las pantallas ni los reportes. Es un **bloqueo al validar**, no un bloqueo al escribir un número en la casilla.

## Ejemplo de mensaje

> No puedes exceder la cantidad ordenada.
>
> Recepción: WH/IN/00001  
> Producto: Producto A  
> Demanda: 100 Unidades  
> Intentas recibir: 101 Unidades  
>
> Reduce la cantidad recibida antes de validar.

## Instalación de prueba (rama `odometro`)

1. Descarga el ZIP y **descomprímelo**.
2. En GitHub abre `coirtech/produccion`, selecciona `odometro`, y verifica que sea tu entorno de pruebas en Odoo.sh.
3. Sube **una sola carpeta** `coirtech_receipt_qty_limit` (con `__manifest__.py` dentro) a la raíz del repositorio, junto a tus otros módulos. No la subas dentro de otra carpeta con el mismo nombre.
4. Confirma los cambios (`Commit changes`). Verifica en Odoo.sh que la compilación de `odometro` finalice.
5. En la base de prueba, activa el modo desarrollador y entra a **Aplicaciones > Actualizar lista de aplicaciones**. Quita el filtro de Aplicaciones si es necesario.
6. Busca `coirtech_receipt_qty_limit` e **instala**.
7. Prueba los casos de abajo. Solo después de comprobarlos, considera despliegue a producción con copia de seguridad y un PR que incluya **solo este módulo**.

## Pruebas obligatorias

| Escenario | Resultado esperado |
|---|---|
| Demanda 100, recibido 100 | Permite validar |
| Demanda 100, recibido 101 | Mensaje de bloqueo |
| Demanda 100, recibido 60 | Permite validar, deja pendiente 40 si se genera backorder |
| OC por 100: previamente recibidas 80, nuevas 20 | Permite validar |
| OC por 100: previamente recibidas 80, nuevas 21 | Bloquea |
| OC con 2 líneas del mismo producto | Control independiente por línea de OC |
| Unidades distintas en OC y recepción | Compara tras conversión de UoM |
| Entrega de ventas o traslado interno | Sin cambios |

## Notas

- Si alguien **modifica la cantidad de la orden de compra** antes de recibir, se usa la cantidad vigente de dicha orden. Este módulo no restringe la edición de órdenes de compra.
- En recepciones **sin orden de compra**, el límite es la Demanda de cada línea del movimiento. Una persona con permiso de editar la Demanda aún podría aumentarla; para prohibir esa edición se necesita una regla adicional.
- El control se realiza al pulsar **Validar** y también al completar movimientos desde procesos internos. No modifica los reportes.
- Conviene validar en Staging los flujos con códigos de barras, recepciones de varios pasos, devoluciones, compras multicompañía y unidades de medida personalizadas antes de Production.
