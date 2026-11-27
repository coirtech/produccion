{
    'name': 'Abastecimiento Manual al Confirmar Venta (Compra o Fabricación)',
    'version': '19.0.2.0.0',
    'category': 'Sales/Sales',
    'summary': 'Permite elegir de forma sencilla entre Cotización de Compra u Orden de Fabricación al confirmar una venta.',
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
