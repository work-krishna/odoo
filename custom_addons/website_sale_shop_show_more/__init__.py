from . import models
from .models.website import SHOP_PPG_BY_PPR


def post_init_hook(env):
    """ The websites that already exist show the number of products of their columns """
    for website in env['website'].search([]):
        if website.shop_ppr in SHOP_PPG_BY_PPR:
            website.shop_ppg = SHOP_PPG_BY_PPR[website.shop_ppr]
