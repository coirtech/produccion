{
    'name': 'Abastecimiento Manual al Confirmar Venta (Compra o Fabricación)',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Permite elegir entre generar Cotización de Compra o Fabricación al confirmar una venta.',
    'author': 'Custom',
    'license': 'LGPL-3',
    'depends': [
        'sale_management',
        'sale_stock',
        'purchase_stock',
        'mrp',
        'sale_mrp',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/purchase_order_views.xml',
        'views/sale_order_views.xml',
        'views/sale_procurement_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
}
