You are an expert Odoo 19 Community Edition full-stack developer, Odoo framework architect, PostgreSQL developer, eCommerce specialist, and system architect.

I am running Odoo 19 Community Edition and want to implement the following eCommerce/product/variant customizations.

Your job is to analyze the existing Odoo 19 architecture and implement these requirements professionally, preferably through custom modules rather than modifying Odoo core source code.

Critical Instructions

Before writing or modifying any code:

Inspect the existing Odoo 19 Community Edition implementation relevant to:
product.template
product.product
product attributes and variants
eCommerce product pages
cart
checkout
sale orders
taxes
invoices / bills
website product templates
product images
variant combination handling
inventory/stock availability
website/eCommerce controllers and JavaScript components
Determine the correct Odoo 19-native extension points.
Do NOT modify Odoo core files unless absolutely unavoidable.
Prefer custom addons.
Use inheritance.
Use XML views/templates inheritance.
Use Python model inheritance.
Use OWL/JavaScript extension mechanisms where appropriate.
Keep the implementation upgrade-friendly.
Before implementation, explain:
Which Odoo models are involved.
Which existing fields/features can be reused.
Which new fields are required.
Which website templates/components need modification.
Which controllers/routes need modification, if any.
Which JavaScript/OWL components need modification.
How the implementation will remain compatible with Odoo 19 Community Edition.
Do not blindly assume that an Odoo Enterprise feature exists in Community Edition. If a required capability is Enterprise-only, explicitly identify it and implement an appropriate Community-compatible solution.
Do not use hacks such as:
modifying Odoo source files directly
database triggers unless absolutely necessary
JavaScript DOM manipulation when a proper OWL/template extension exists
hard-coded product IDs
hard-coded website IDs
hard-coded tax IDs
hard-coded attribute IDs
duplicated business logic
Preserve existing Odoo functionality unless explicitly changed below.
REQUIREMENT 1 — eCommerce Checkout: VAT-Inclusive Total Display

Current requirement:

During:

eCommerce → Checkout → Order Summary / Bill

I want the checkout total to clearly indicate that the displayed price includes VAT/tax.

Desired behavior

Instead of displaying a separate tax term/line such as:

Subtotal          Rs. 1,000
VAT               Rs. 130
Total             Rs. 1,130

I want the customer-facing checkout bill to display approximately:

Total             Rs. 1,130
                  Incl. VAT

Where:

Total remains the primary/larger text.
Incl. VAT appears immediately below or beside the total.
Incl. VAT must use a smaller font than the Total.
The actual calculated total must remain correct.
The tax must NOT be removed from the underlying sale order/accounting calculation.
This is primarily a customer-facing presentation change.
Do not break tax computation.
Do not alter accounting/tax records.
Do not remove VAT from the sale order internally.
Important

The implementation should correctly handle:

products with VAT
products without VAT
multiple tax rates
multiple products with different taxes
tax-excluded pricing configuration
tax-included pricing configuration
fiscal positions
applicable website/customer tax configuration

If the tax is actually included in the displayed total, display:

Incl. VAT

If no applicable VAT/tax exists, do not misleadingly display "Incl. VAT".

Also investigate whether Odoo 19 already provides a native mechanism for tax-inclusive website pricing and reuse it where possible.

REQUIREMENT 2 — Brand Category on Every Product

I want every product to have a Brand.

Add a brand field/category to products.

Requirements

Every product should have a brand value.

Example:

Brand:
- Apple
- Samsung
- Xiaomi
- OnePlus
- Sony
- ...
- No Brand

There must be a default:

No Brand
Important behavior

When creating a new product:

Brand = No Brand

should be automatically selected unless the user chooses another brand.

Existing products that do not currently have a brand must also become:

No Brand

Do NOT leave existing products with NULL/empty brand unless there is a very strong architectural reason.

Architecture

Determine whether Brand should be:

a Many2one model such as product.brand
a category-like model
or another appropriate Odoo architecture.

Prefer a proper reusable model if appropriate.

For example:

product.brand
    id
    name
    active
    sequence
    ...

The exact model/field naming should follow Odoo conventions.

The brand must be manageable from the backend.

REQUIREMENT 3 — Display Brand on eCommerce Product Page

I want the brand name displayed on the eCommerce product page, immediately below the product rating.

Example:

★★★★★ 4.8
Apple

iPhone 17 Pro
Rs. 189,999
Requirements

Brand should appear:

below the rating and above the product title or in the most appropriate location according to the existing Odoo 19 product-page structure.

However, the exact placement should be determined after inspecting Odoo 19's current website product template.

Product-level display control

While creating or editing a product, I want a checkbox:

Display Brand on eCommerce
[✓]

For example:

Brand:
Apple

Display Brand on eCommerce:
☑

If enabled:

Apple

is displayed on the website.

If disabled:

The brand is still assigned to the product internally, but the brand name is NOT displayed on eCommerce.

Important

This visibility control must be:

per product
editable from backend
respected by the website
independent from the actual brand assignment

For example:

Product: iPhone 17 Pro
Brand: Apple
Display Brand: Yes

shows:

Apple

But:

Product: Internal OEM Product
Brand: Xiaomi
Display Brand: No

does not show the brand publicly.

REQUIREMENT 4 — Variant-Level Inventory / Stock Management

This is extremely important.

I want inventory to be managed at the product variant level, not merely at the product/template level.

Example:

Product:

Phone

Attributes:

Color:
- Black
- Blue
- Red

Storage:
- 128 GB
- 256 GB

The actual sellable inventory must be maintained for each variant combination.

For example:

Phone / Black / 128 GB     Stock = 10
Phone / Black / 256 GB     Stock = 4
Phone / Blue / 128 GB      Stock = 7
Phone / Blue / 256 GB      Stock = 2
Phone / Red / 128 GB       Stock = 0
Phone / Red / 256 GB       Stock = 0
Problem to solve

Suppose:

Phone
Colors:
- Black
- Blue

Customer selects:

Red

but Red has no inventory.

The customer must NOT be able to purchase the unavailable variant.

The website must accurately communicate availability.

Important requirement

This must work for:

one attribute
two attributes
three or more attributes
arbitrary combinations of attributes
dynamically created variants
variants created later
variants archived/removed
different inventory quantities per variant

Example:

T-Shirt
Color: Red / Blue / Black
Size: S / M / L / XL
Material: Cotton / Polyester

Inventory must be based on the complete variant combination.

Expected website behavior

If:

Red + M

has:

Stock = 0

then that exact combination must be unavailable.

The user should not be able to add that combination to the cart.

Ideally, the unavailable combination should also be visually indicated/disabled where Odoo's existing variant selector supports it.

Important architectural requirement

Do NOT create a second custom inventory system if Odoo's native:

product.product
stock.quant
stock.move
stock.location

architecture can already support this.

Investigate how Odoo 19 Community Edition already manages stock per product.product.

If native variant-level inventory exists, integrate with it correctly instead of duplicating it.

REQUIREMENT 5 — Variant-Specific Product Images

I want product images to depend on the selected variant.

Example:

Product:

iPhone

Variants:

Black
Blue
Red

Images:

Black → black-phone.jpg
Blue  → blue-phone.jpg
Red   → red-phone.jpg

When the customer selects:

Blue

the product image/gallery should automatically change to the Blue product image.

When:

Red

is selected:

red-phone.jpg

should be displayed.

Critical requirement

This must work not only for variants created initially, but also for variants created later.

For example:

Product is created.
Variants are generated.
Later, a new variant is created.
User assigns an image to that specific variant.
Website should immediately use that image when that variant is selected.
Image assignment

The backend must provide an intuitive way to associate images with variants.

Use Odoo's existing product image architecture where possible.

Do not create unnecessary duplicate image storage if Odoo already supports variant-specific images.

REQUIREMENT 6 — Variant Image on Hover

I also want an additional UX behavior.

When the customer is selecting a variant, if that particular variant has a different image configured, then hovering over the variant option should temporarily show that variant's image.

Example:

Variants:

Black
Blue
Red

Images:

Black → black.jpg
Blue → blue.jpg
Red → red.jpg

Current selected variant:

Black

Main product image:

black.jpg

When user moves mouse over:

Blue

the main product image should temporarily change to:

blue.jpg

When the mouse leaves:

return to the currently selected variant's image.

When the user clicks/selects:

Blue

then Blue becomes the selected variant and its image remains displayed.

Important behavior

Hover preview should happen ONLY when:

the hovered variant has a specifically associated image

If no variant-specific image exists:

do not change the image
preserve the currently displayed image

This must work with all variant attribute types.

For example:

Color
Size
Storage
Material
Finish

and combinations thereof.

Combination behavior

For products with multiple attributes, determine the correct architecture for image resolution.

Example:

Color = Blue
Storage = 256 GB

If the exact variant has an image:

Blue / 256 GB → blue-256.jpg

use that image.

If only a partial/attribute-level image exists, determine whether Odoo's existing image behavior should be respected.

Document the resolution priority clearly.

GENERAL ARCHITECTURAL REQUIREMENTS

The final implementation should be production quality.

1. Custom module architecture

Prefer creating one or more custom modules such as:

custom_product_brand
custom_ecommerce_variant
custom_ecommerce_tax_display

or a logically organized single module if that is cleaner.

You must decide the best architecture after inspecting the existing project.

Explain why.

2. Odoo compatibility

Target:

Odoo 19 Community Edition

Do not write code based on Odoo 16/17/18 APIs unless verified to still be valid in Odoo 19.

Pay particular attention to changes in:

OWL
website_sale
product variant combination logic
QWeb templates
controllers
asset bundles
JavaScript modules
product image handling
3. Backend UI

The backend product form should be clean and intuitive.

For example:

Product
────────────────────────

Product Name
[ iPhone 17 Pro ]

Brand
[ Apple ▼ ]

☑ Display Brand on eCommerce

Variant management should remain compatible with Odoo's existing product variant UI.

4. Security

Follow Odoo's:

access rights
record rules
sudo usage rules
website/public-user restrictions

Do not expose backend-only information to public website users.

Do not use sudo() unnecessarily.

5. Performance

The website may contain thousands of products and many variants.

Avoid:

N+1 database queries
unnecessary RPC calls
querying every variant repeatedly
loading full image data when unnecessary
excessive JavaScript requests

Use appropriate:

ORM prefetching
computed fields where justified
stored fields where justified
JSON data passed to frontend when appropriate
efficient variant combination logic
asset bundling
IMPLEMENTATION PROCESS

Follow this exact process.

PHASE 1 — Inspect

First inspect the existing Odoo installation and identify:

Odoo version
website_sale implementation
product models
variant models
stock models
product image models
checkout templates
product page templates
variant JavaScript/OWL implementation
tax display implementation

Do not immediately start writing code.

First explain your findings.

PHASE 2 — Architecture

Create a detailed implementation plan.

For each requirement provide:

Requirement
Odoo model(s)
Existing Odoo functionality reused
New fields/models
Backend changes
Frontend changes
JavaScript/OWL changes
XML/QWeb changes
Controller changes
Database impact
Potential compatibility concerns
PHASE 3 — Implementation

Implement the solution using proper Odoo inheritance.

Provide the complete module structure.

Example:

custom_module/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── product_brand.py
│   ├── product_template.py
│   └── product_image.py
├── views/
│   ├── product_brand_views.xml
│   ├── product_template_views.xml
│   └── website_sale_templates.xml
├── static/
│   └── src/
│       ├── js/
│       ├── xml/
│       └── scss/
├── security/
│   ├── ir.model.access.csv
│   └── ...
└── data/
    └── ...

The actual structure may differ if your architectural analysis determines a better solution.

CODE QUALITY REQUIREMENTS

For every code file:

Give the exact file path.
Give the complete file contents.
Do not give pseudo-code when actual implementation is possible.
Do not omit important imports.
Do not use placeholder comments such as:
# implement this
# existing code here
# etc.
Make the code directly usable.
Follow Odoo coding conventions.
Add comments only where they improve maintainability.
TESTING REQUIREMENTS

After implementation, create a comprehensive test plan.

Test at minimum:

Brand
New product defaults to No Brand.
Existing products receive No Brand.
Brand can be changed.
Brand can be managed.
Display Brand checkbox works.
Brand appears correctly on website.
Brand does not appear when disabled.
VAT
VAT product.
Non-tax product.
Multiple tax rates.
Mixed-tax cart.
Fiscal position.
Tax-inclusive pricing.
Tax-exclusive pricing.
Correct total.
Correct "Incl. VAT" behavior.
Variants

Test:

1 attribute
2 attributes
3+ attributes

Test combinations:

available
out of stock
partially available
non-existing combination

Ensure customers cannot purchase an unavailable variant.

Images

Test:

Variant with image
Variant without image
Variant created later
Variant image changed later
Multiple attribute combinations
Hover preview
Click/select variant
Hover → leave
Hover variant with no image
Regression

Ensure:

Add to cart still works.
Cart updates correctly.
Quantity updates work.
Checkout works.
Sale orders remain correct.
Taxes remain correct.
Stock reservations remain correct.
Product pages remain responsive.
Mobile website works.
IMPORTANT QUESTIONS YOU MUST ANSWER

Before finalizing the implementation, explicitly explain:

Question 1

Does Odoo 19 Community already maintain inventory at product.product variant level?

If yes, explain how your implementation uses the native mechanism.

Question 2

How does Odoo 19 associate images with variants?

Use the existing architecture if possible.

Question 3

How will the frontend determine the image for the currently selected combination?

Question 4

How will hover preview work without causing excessive server requests?

Question 5

How will the solution handle products with multiple attributes?

Question 6

How will "No Brand" be represented?

Should it be:

product.brand record

or:

NULL + frontend fallback

Explain your decision.

Question 7

Where exactly is the Odoo 19 checkout tax/total template located, and what is the safest inheritance mechanism?

Question 8

Which JavaScript/OWL component handles variant selection in Odoo 19 Community?

Question 9

Which assets must be added to the website frontend?

Question 10

What happens if a product has thousands of variants?

Provide a performance-safe solution.

FINAL DELIVERABLE

At the end provide:

A. Architecture Summary

A concise explanation of the final architecture.

B. Module Structure

Complete directory tree.

C. Complete Code

Every required file with exact path and full contents.

D. Installation

Exact commands to install/update the module.

For example:

./odoo-bin -d DATABASE_NAME -u MODULE_NAME --stop-after-init

Adjust commands to the actual environment.

E. Configuration

Explain any required:

Odoo settings
website settings
product settings
tax settings
inventory settings
F. Testing Checklist

A practical checklist that can be followed by QA.

G. Migration / Existing Data

Explain how existing products will be migrated to:

Brand = No Brand

and how existing product variants/images/inventory will be preserved.

H. Risks / Limitations

Clearly identify anything that cannot be implemented cleanly using standard Odoo 19 Community mechanisms.

MOST IMPORTANT RULE

Do not simply give me a conceptual answer.

I need a production-oriented Odoo 19 Community Edition implementation.

First inspect and understand Odoo 19's actual architecture, then design the solution, and finally provide the complete implementation.

Do not assume APIs or template names from older Odoo versions.

If you discover that one of my requirements conflicts with Odoo's existing architecture, explain the conflict and provide the cleanest Odoo-native solution rather than implementing a fragile workaround.