{
    'name': 'Product Brands',
    'version': '19.0.1.0.0',
    'summary': "Every product has a brand (Apple, Samsung, ...), \"No Brand\" by default",
    'description': """
Adds a Brand to every product. Brands are managed as their own records
(name, sequence, archiving) and each product links to one.

A product always has a brand: new products get "No Brand" unless another
brand is chosen, and the products that exist when this module is installed
are set to "No Brand" as well. "No Brand" itself can be renamed but not
archived or deleted, and a brand still used by products cannot be deleted.

Menus to manage the brands come with the modules using them, e.g.
website_sale_product_brand.
""",
    'category': 'Sales/Sales',
    'author': 'EMI Platform',
    'license': 'LGPL-3',
    'depends': ['product'],
    'data': [
        'security/ir.model.access.csv',
        'data/product_brand_data.xml',
        'views/product_brand_views.xml',
        'views/product_template_views.xml',
    ],
    'installable': True,
}
