# -*- coding: utf-8 -*-
{
    'name': 'Desactivar Firma Automática en Portal',
    'version': '19.0.1.1.0',
    'category': 'Sales/Sales',
    'summary': 'Oculta la firma automática, abre Dibujar por defecto y guarda la firma sin confirmar la orden.',
    'depends': ['web', 'portal', 'sale'],
    'assets': {
        'web.assets_frontend': [
            'portal_disable_auto_sign/static/src/core/signature/name_and_signature.css',
            'portal_disable_auto_sign/static/src/core/signature/name_and_signature.js',
        ],
        'web.assets_backend': [
            'portal_disable_auto_sign/static/src/core/signature/name_and_signature.css',
            'portal_disable_auto_sign/static/src/core/signature/name_and_signature.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
