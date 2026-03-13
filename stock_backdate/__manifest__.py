# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Stock Back date',
    'version': '19.0.0.0',
    'summary': 'backdate your stock',
    'website': 'https://kolapro.com',
    # 'depends': ['stock'],
    'category': 'Inventory/Inventory',
    'sequence': 1,
    'demo': [
        # 'data/stock_backdate_demo.xml',

    ],
    'depends': [
        'stock',
        # 'account',
        'mrp'   ,
        'purchase',
        'sale',        
        'hr_expense',
        # 'sale_subscription',
        'product',
        ],
    'data': [
        'security/stock_backdate_security.xml',
        'security/ir.model.access.csv',

        # 'data/data.xml',

        # 'report/report.xml',

        # 'wizard/wizard.xml',
        'wizard/views/bulk_serial_create.xml',
        'wizard/views/multi_stock_backdate_wizard.xml',
        'wizard/views/stock_backdate_wizard.xml',

        'views/product_template.xml',
        'views/actions.xml',
        

    ],
    # 'installable': True,
    # 'assets': {
    #     'web.assets_backend': [
    #         # 'stock_backdate/static/src/**/*.js',
    #         # 'stock_backdate/static/src/**/*.xml',
    #     ],
    #     'web.assets_frontend': [
    #         # 'stock_backdate/static/src/scss/stock_backdate.scss',
    #     ],
    # },
    'license': 'LGPL-3',
    "installable": True,
    "application": False,
    'auto_install': False,
}
