import { onWillUnmount, useState } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";

/**
 * Shows the Fonepay QR code to scan, with a single "Cancel Payment" button. There is no manual
 * "Confirm" action: confirmation happens automatically once the background poll started by
 * `PaymentFonepay.sendPaymentRequest` detects the payment succeeded, at which point the caller
 * closes this dialog itself.
 *
 * The countdown shown below the QR is a display-only mirror of the provider's configured
 * timeout; the actual expiry is enforced server-side (see `_fonepay_has_timed_out`) and reaches
 * this dialog the same way a successful payment does: through the regular poll detecting the
 * transaction turned 'cancel' and the caller closing this dialog.
 */
export class FonepayQrPopup extends ConfirmationDialog {
    static template = "pos_payment_fonepay.FonepayQrPopup";
    static props = {
        ...ConfirmationDialog.props,
        qrCode: String,
        amount: String,
        timeout: { type: Number, optional: true },
    };
    static defaultProps = {
        ...ConfirmationDialog.defaultProps,
        title: _t("Fonepay Payment"),
        cancelLabel: _t("Cancel Payment"),
        confirm: () => {}, // Unreachable: the confirm button is hidden in the template.
    };

    setup() {
        super.setup();
        this.props.body = _t("Scan this QR code with your mobile banking or wallet app.");

        this.state = useState({ remaining: this.props.timeout || 0 });
        if (this.props.timeout) {
            const timer = setInterval(() => {
                this.state.remaining = Math.max(0, this.state.remaining - 1);
                if (this.state.remaining <= 0) {
                    clearInterval(timer);
                }
            }, 1000);
            onWillUnmount(() => clearInterval(timer));
        }
    }

    get formattedRemaining() {
        const total = Math.max(0, this.state.remaining);
        const minutes = Math.floor(total / 60);
        const seconds = String(total % 60).padStart(2, "0");
        return `${minutes}:${seconds}`;
    }
}
