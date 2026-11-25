{
    'name': 'Quiosco Multiempresa',
    'summary': 'El quiosco original, con escaneo y un enlace para varias empresas.',
    'description': 'Amplía el quiosco original de Asistencias con un enlace multiempresa sin logotipos. Conserva su diseño, cámara, lectura de credenciales, selección manual, PIN y los seis movimientos del módulo de Asistencias instalado.',
    'version': '19.0.1.1.0',
    'category': 'Human Resources/Attendances',
    'author': 'Desarrollo personalizado',
    'license': 'LGPL-3',
    'depends': ['coirtech_attendance_meal_control'],
    'data': [
        'security/kiosk_security.xml',
        'security/ir.model.access.csv',
        'views/kiosk_views.xml',
        'views/kiosk_templates.xml',
    ],
    'assets': {
        'attendance_multi_company_kiosk.assets_kiosk': [
            ('include', 'hr_attendance.assets_public_attendance'),
            'attendance_multi_company_kiosk/static/src/kiosk/native_bridge.js',
            'attendance_multi_company_kiosk/static/src/kiosk/native_bridge.xml',
            'attendance_multi_company_kiosk/static/src/kiosk/native_bridge.scss',
        ],
    },
    'application': False,
    'installable': True,
    'post_init_hook': 'post_init_hook',
}
