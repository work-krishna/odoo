import { registry } from '@web/core/registry';

const nav = 'header#top #o_main_nav';
const search = `${nav} > .o_header_boxed_search`;
const menu = `${nav} > .top_menu:not(.o_menu_loading)`;

// The field goes from the end of the menu to the icons on the right, and the
// menu items are not cut
function checkLayout() {
    const menuEl = document.querySelector(menu);
    const fieldEl = document.querySelector(search);
    const [menuBox, fieldBox, iconsBox] = [menuEl, fieldEl, fieldEl.nextElementSibling].map(
        (el) => el.getBoundingClientRect()
    );
    if (Math.abs(fieldBox.left - menuBox.right) > 1 || Math.abs(fieldBox.right - iconsBox.left) > 1) {
        throw new Error(
            `The search field goes from ${fieldBox.left} to ${fieldBox.right} instead of filling the space between the menu (${menuBox.right}) and the icons (${iconsBox.left})`
        );
    }
    if (menuEl.scrollWidth > menuEl.clientWidth + 1) {
        throw new Error(`The menu items are cut: ${menuEl.scrollWidth}px in ${menuEl.clientWidth}px`);
    }
    return fieldBox.width;
}

// Once the field is clicked, the focus ring goes around the field and its
// search button, as one pill
function focusRingSteps(field) {
    return [
        {
            content: 'Click the search field',
            trigger: `${field} input[name="search"]`,
            run: 'click',
        },
        {
            content: 'The focus ring is around the field and its button',
            trigger: `${field} .input-group:focus-within`,
            run() {
                const group = document.querySelector(`${field} .input-group`);
                const input = group.querySelector('input[name="search"]');
                const button = group.querySelector('.oe_search_button');
                if (getComputedStyle(group).boxShadow === 'none') {
                    throw new Error('No focus ring around the field and its button');
                }
                if (getComputedStyle(input).boxShadow !== 'none') {
                    throw new Error('Still a focus ring around the field alone');
                }
                const box = group.getBoundingClientRect();
                const buttonBox = button.getBoundingClientRect();
                if (buttonBox.left < box.left || buttonBox.right > box.right + 0.5) {
                    throw new Error('The search button is outside the ring');
                }
                if (parseFloat(getComputedStyle(group).borderTopRightRadius) < box.height / 2) {
                    throw new Error('The ring is not round at the end of the button');
                }
            },
        },
    ];
}

registry.category('web_tour.tours').add('website_header_boxed_search', {
    url: '/',
    steps: () => [
        {
            content: 'A search field, no search icon',
            trigger: `${search} form.o_searchbar_form input[name="search"]`,
            run() {
                if (document.querySelector('header#top [data-bs-target="#o_search_modal"]')) {
                    throw new Error('The search icon is still there');
                }
                if (document.querySelectorAll(`${search} > li`).length !== 1) {
                    throw new Error('Icons (cart, ...) came along with the search field');
                }
            },
        },
        {
            content: 'The whole menu is shown and the field takes the rest of the bar',
            trigger: `${menu}:not(:has(.o_extra_menu_items))`,
            run: checkLayout,
        },
        ...focusRingSteps(search),
        {
            content: 'Search from the field',
            trigger: `${search} input[name="search"]`,
            run: 'edit Contact',
        },
        {
            content: 'Its suggestions',
            trigger: `${search} .o_dropdown_menu a.dropdown-item:contains(Contact)`,
        },
    ],
});

// With more menu items than the bar can show
registry.category('web_tour.tours').add('website_header_boxed_search_long_menu', {
    url: '/',
    steps: () => [
        {
            content: 'The last items are in the "+" dropdown',
            trigger: `${menu} > li.o_extra_menu_items`,
        },
        {
            content: 'The field keeps its minimum width and fills the space left',
            trigger: search,
            run() {
                const width = checkLayout();
                const minWidth = 12 * parseFloat(getComputedStyle(document.documentElement).fontSize);
                if (width < minWidth - 1) {
                    throw new Error(`The search field is ${width}px wide, less than its ${minWidth}px`);
                }
            },
        },
    ],
});

// The search field of the mobile menu
registry.category('web_tour.tours').add('website_header_boxed_search_mobile', {
    url: '/',
    steps: () => [
        {
            content: 'Open the mobile menu',
            trigger: 'header#top .o_header_mobile [data-bs-target="#top_menu_collapse_mobile"]',
            run: 'click',
        },
        {
            content: 'The menu is open',
            trigger: '#top_menu_collapse_mobile.show',
        },
        ...focusRingSteps('#top_menu_collapse_mobile'),
    ],
});
