{
    'name': 'Ventas - Descuento monetario por pieza',
    'version': '19.0.1.0.3',
    'category': 'Sales/Sales',
    'summary': 'Descuento fijo por unidad visible en cotizacion PDF y portal',
    'author': 'COIRTECH',
    'license': 'LGPL-3',
    'depends': ['sale_management'],
    'data': [
        'views/sale_order_views.xml',
        'report/sale_order_report.xml',
        'views/sale_portal_templates.xml',
    ],
    'application': False,
    'installable': True,
}
