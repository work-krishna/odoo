import { registry } from '@web/core/registry';

registry.category('web_tour.tours').add('website_sale_ncm_address_area', {
    url: '/my/address?address_type=delivery',
    steps: () => [
        { trigger: 'input[name="name"]', run: 'edit Tour NCM Customer' },
        { trigger: 'input[name="email"]', run: 'edit tour.ncm@example.com' },
        { trigger: 'input[name="phone"]', run: 'edit 9841234567' },
        { trigger: 'input[name="street"]', run: 'edit Lakeside Road 6' },
        { trigger: 'input[name="city"]', run: 'edit Pokhara' },
        { content: "Choose Nepal", trigger: 'select[name="country_id"]', run: 'selectByLabel Nepal' },
        { content: "The NCM picker appears", trigger: '#div_ncm_area:not(.d-none)' },
        { trigger: 'input[name="zip"]', run: 'edit 33700' },
        { content: "Choose the district", trigger: 'select[name="ncm_district"]', run: 'selectByLabel Kaski' },
        {
            content: "Its areas are loaded",
            trigger: 'select[name="ncm_area_id"]:has(option:contains(Lakeside))',
        },
        { content: "Choose the area", trigger: 'select[name="ncm_area_id"]', run: 'selectByLabel Lakeside' },
        { content: "Save", trigger: '#save_address', run: 'click', expectUnloadPage: true },
        {
            content: "Back on the address list",
            trigger: 'body:not(:has(#save_address)):contains(Tour NCM Customer)',
        },
    ],
});
