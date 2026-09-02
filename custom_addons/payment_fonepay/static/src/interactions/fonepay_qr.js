import { ConnectionLostError, rpc, RPCError } from '@web/core/network/rpc';
import { registry } from '@web/core/registry';
import { Interaction } from '@web/public/interaction';

/**
 * Poll the Fonepay QR payment status while its QR code is displayed on the payment status page.
 *
 * Fonepay pushes payment notifications over a WebSocket connection rather than a webhook that
 * Odoo could receive server-side. Instead of keeping a persistent WebSocket connection open in
 * an Odoo worker, the customer's browser periodically asks the server to check the payment
 * status with Fonepay's "Check QR Request Status" API. Once the transaction leaves the 'pending'
 * state, the generic `payment.payment_post_processing` polling (already running on this page)
 * picks up the change and redirects the customer.
 */
export class FonepayQrPolling extends Interaction {
    static selector = 'div[name="o_fonepay_qr_wrapper"]';

    setup() {
        this.reference = this.el.dataset.reference;
        this.pollCount = 0;
        // Stop polling after a while so an abandoned tab doesn't hammer the server forever.
        this.maxPolls = 200;
    }

    start() {
        this.poll();
    }

    poll() {
        const timeout = this.pollCount === 0 ? 3000 : Math.min(3000 + this.pollCount * 1000, 10000);
        this.pollCount++;
        this.waitForTimeout(async () => {
            try {
                const { state } = await this.waitFor(rpc('/payment/fonepay/poll', {
                    reference: this.reference,
                }));
                if (state === 'pending' && this.pollCount < this.maxPolls) {
                    this.poll();
                }
                // Otherwise, let the generic status polling redirect the customer.
            } catch (error) {
                const isConnectionLostError = error instanceof ConnectionLostError;
                if (isConnectionLostError && this.pollCount < this.maxPolls) {
                    this.poll();
                } else if (!(error instanceof RPCError)) {
                    throw error;
                }
            }
        }, timeout);
    }
}

registry
    .category('public.interactions')
    .add('payment_fonepay.fonepay_qr_polling', FonepayQrPolling);
