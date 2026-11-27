{
    'name': 'Abastecimiento Manual al Confirmar Venta (Compra o Fabricación)',
    'version': '19.0.4.0.0',
    'category': 'Sales/Sales',
    'summary': 'Menú compacto al confirmar venta para elegir Cotización de Compra u Orden de Fabricación.',
    'author': 'Custom',
    'license': 'LGPL-3',
    'depends': [
        'sale_management',
        'sale_stock',
        'sale_purchase',
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
