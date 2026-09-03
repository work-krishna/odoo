import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PaymentFonepay } from "@pos_payment_fonepay/app/payment_fonepay";

patch(PosStore.prototype, {
    async processServerData() {
        await super.processServerData();
        for (const paymentMethod of this.models["pos.payment.method"].getAll()) {
            if (paymentMethod.payment_method_type === "fonepay") {
                paymentMethod.payment_terminal = new PaymentFonepay(this, paymentMethod);
            }
        }
    },
});
