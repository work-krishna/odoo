import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";

/**
 * Shows the Fonepay QR code to scan, with a single "Cancel Payment" button. There is no manual
 * "Confirm" action: confirmation happens automatically once the background poll started by
 * `PaymentFonepay.sendPaymentRequest` detects the payment succeeded, at which point the caller
 * closes this dialog itself.
 */
export class FonepayQrPopup extends ConfirmationDialog {
    static template = "pos_payment_fonepay.FonepayQrPopup";
    static props = {
        ...ConfirmationDialog.props,
        qrCode: String,
        amount: String,
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
    }
}
