import logging

from lxml import etree

_logger = logging.getLogger(__name__)

# The previous / next arrows of a carousel (Bootstrap), and what makes them slide it
ARROWS = {
    'carousel-control-prev': 'prev',
    'carousel-control-next': 'next',
}


def _repair_carousel_arrows(env):
    """ Gives back to the arrows of the carousels of the website's pages what makes them slide the carousel, when they
    were saved without it: the arrows of a carousel (`data-bs-target`) without a direction (`data-bs-slide`).
    """
    views = env['ir.ui.view'].with_context(active_test=False).search([
        ('type', '=', 'qweb'),
        ('arch_db', 'ilike', 'carousel-control-'),
    ])
    for view in views:
        try:
            arch = etree.fromstring(view.arch_db)
        except (etree.XMLSyntaxError, ValueError):
            _logger.warning("Carousel arrows not checked in view %s (%s): unreadable arch", view.id, view.key)
            continue
        arrows = [
            (arrow, direction)
            for arrow_class, direction in ARROWS.items()
            for arrow in arch.xpath(
                f'//*[contains(concat(" ", normalize-space(@class), " "), " {arrow_class} ")]'
                '[@data-bs-target][not(@data-bs-slide)]'
            )
        ]
        if not arrows:
            continue
        for arrow, direction in arrows:
            arrow.set('data-bs-slide', direction)
        view.arch = etree.tostring(arch, encoding='unicode')
        _logger.info("Carousel arrows given back their direction in view %s (%s)", view.id, view.key)


def post_init_hook(env):
    _repair_carousel_arrows(env)
