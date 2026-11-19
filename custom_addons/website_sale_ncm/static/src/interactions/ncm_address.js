import { rpc } from '@web/core/network/rpc';
import { patch } from '@web/core/utils/patch';
import { patchDynamicContent } from '@web/public/utils';
import { CustomerAddress } from '@portal/interactions/address';

/**
 * NCM delivery area picker of the address form: shown for Nepal addresses only; choosing a
 * district loads its areas.
 */
patch(CustomerAddress.prototype, {
    setup() {
        super.setup();
        this.ncmBlock = this.el.querySelector('#div_ncm_area');
        if (!this.ncmBlock) {
            return;
        }
        this.ncmDistrictSelect = this.ncmBlock.querySelector('select[name="ncm_district"]');
        this.ncmAreaSelect = this.ncmBlock.querySelector('select[name="ncm_area_id"]');
        patchDynamicContent(this.dynamicContent, {
            'select[name="ncm_district"]': { 't-on-change': this.onChangeNcmDistrict.bind(this) },
        });
    },

    async _onChangeCountry() {
        const result = await super._onChangeCountry(...arguments);
        this._toggleNcmArea();
        return result;
    },

    _toggleNcmArea() {
        if (!this.ncmBlock) {
            return;
        }
        const isNepal = this._getSelectedCountryCode() === 'NP';
        this.ncmBlock.classList.toggle('d-none', !isNepal);
        if (!isNepal) {
            this.ncmDistrictSelect.value = '';
            this.ncmAreaSelect.value = '';
        }
    },

    async onChangeNcmDistrict() {
        const district = this.ncmDistrictSelect.value;
        this.ncmAreaSelect.options.length = 1; // Keep the "Area..." placeholder.
        if (!district) {
            return;
        }
        const areas = await this.waitFor(rpc('/website_sale_ncm/areas', { district }));
        if (this.ncmDistrictSelect.value !== district) {
            return; // The customer picked another district meanwhile.
        }
        for (const area of areas) {
            this.ncmAreaSelect.appendChild(new Option(area.label, area.id));
        }
    },
});
