import { PaymentInterface } from "@point_of_sale/app/utils/payment/payment_interface";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { FonepayQrPopup } from "@pos_payment_fonepay/app/components/fonepay_qr_popup/fonepay_qr_popup";

const POLL_INTERVAL_MS = 3000;
// A backstop only: the provider-side payment timeout (configured on the Fonepay payment
// provider, and enforced server-side) is what actually ends a stale QR. This just keeps a
// forgotten/abandoned tab from polling forever.
const MAX_POLLS = 200;

/**
 * Pay a Point of Sale order with Fonepay: request a QR code and show it directly on the POS
 * screen (and, automatically, on any connected customer display), then poll for confirmation.
 *
 * Unlike a physical payment terminal, there is nothing to "talk to" here other than Odoo's own
 * server, which in turn talks to Fonepay's API — see `payment_fonepay`'s `_fonepay_request_qr`
 * and `_fonepay_check_qr_status` for that side of the flow.
 */
export class PaymentFonepay extends PaymentInterface {
    setup() {
        super.setup(...arguments);
        this._cancelled = false;
        this._resolveResult = null;
    }

    async sendPaymentRequest(uuid) {
        const line = this.pos.models["pos.payment"].get(uuid);
        if (!line) {
            return false;
        }

        let qrData;
        try {
            qrData = await this.pos.data.call("pos.payment.method", "fonepay_request_qr", [
                [this.payment_method_id.id],
                line.amount,
                line.pos_order_id.name || line.pos_order_id.uuid,
            ]);
        } catch (error) {
            this._showError(error?.data?.message || _t("Could not generate the Fonepay QR code."));
            return false;
        }

        this._cancelled = false;
        const resultPromise = new Promise((resolve) => {
            this._resolveResult = resolve;
        });

        const closer = this.pos.dialog.add(
            FonepayQrPopup,
            {
                qrCode: qrData.qr_code,
                amount: this.pos.env.utils.formatCurrency(line.amount),
                cancel: () => this._resolveResult?.(false),
            },
            { onClose: () => this._resolveResult?.(false) }
        );

        this._poll(qrData.reference);

        const result = await resultPromise;
        this._cancelled = true;
        closer();
        return result;
    }

    async sendPaymentCancel() {
        this._cancelled = true;
        this._resolveResult?.(false);
        return true;
    }

    async _poll(reference) {
        for (let i = 0; i < MAX_POLLS && !this._cancelled; i++) {
            await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
            if (this._cancelled) {
                return;
            }
            let status;
            try {
                status = await this.pos.data.call("pos.payment.method", "fonepay_check_status", [
                    [this.payment_method_id.id],
                    reference,
                ]);
            } catch {
                continue; // Transient error: retry on the next tick.
            }
            if (status?.state === "done") {
                this._resolveResult?.(true);
                return;
            }
            if (status?.state === "cancel" || status?.state === "error") {
                this._resolveResult?.(false);
                return;
            }
        }
    }

    _showError(message) {
        this.pos.dialog.add(AlertDialog, {
            title: _t("Fonepay Payment"),
            body: message,
        });
    }
}
