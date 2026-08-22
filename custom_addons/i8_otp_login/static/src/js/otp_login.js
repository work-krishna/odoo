/** @odoo-module **/
import publicWidget from "@web/legacy/js/public/public_widget";
import {rpc} from "@web/core/network/rpc";

publicWidget.registry.OTPLogin = publicWidget.Widget.extend({
    selector: '#otp-login-form',
    events: {
        'click #btn-send-otp': '_onSendOTP',
        'keydown #otp-email': '_onEmailKeydown',
        'click #btn-verify-otp': '_onVerifyOTP',
        'click #btn-resend-otp': '_onResendOTP',
        'input .otp-digit': '_onDigitInput',
        'keydown .otp-digit': '_onDigitKeydown',
        'paste .otp-digit': '_onDigitPaste',
    },

    /**
     * Initialize widget and cache local elements
     */
    start() {
        this.$otpInputs = this.$('.otp-digit');
        this.$emailInput = this.$('#otp-email');
        this.$emailStep = this.$('#email-step');
        this.$otpStep = this.$('#otp-step');
        const $resetModal = $('#otpModalReset');
        if ($resetModal.length) {
            $resetModal.on('shown.bs.modal', () => {
                // Grab email from the 'login' input field on the reset page
                const resetEmail = $('input[name="login"]').val();
                if (resetEmail) {
                    this.$emailInput.val(resetEmail);
                }
                this.$emailInput.focus();
            });
        }
        // Kill browser's native validation for this container only
        this.$el.attr('novalidate', 'novalidate');
        setTimeout(() => {
            if (this.$emailInput.length && this.$emailInput.is(':visible')) {
                this.$emailInput.focus();
            }
        }, 500);
        const $modal = $('#otpModal');
        if ($modal.length) {
            $modal.on('shown.bs.modal', () => {
                if (this.$emailInput.length) {
                    this.$emailInput.focus();
                }
            });
        }

        this.timer = null;
        return this._super(...arguments);
    },
    _onEmailKeydown(ev) {
        if (ev.key === 'Enter') {
            ev.preventDefault(); // Prevent form submission
            this._onSendOTP(ev);
        }
    },
    _getDivineSpinner(text) {
        return `<div class="chakra-spinner me-2"></div> <span class="fw-bold text-uppercase">${text}</span>`;
    },

    /**
     * Timer logic for Resend Link
     */
    _startResendTimer() {
        let seconds = 60;
        const $timerSpan = this.$('#otp-timer');
        const $timerText = this.$('#resend-timer-text');
        const $resendBtn = this.$('#btn-resend-otp');

        $resendBtn.addClass('d-none');
        $timerText.removeClass('d-none');
        if (this.timer) clearInterval(this.timer);

        this.timer = setInterval(() => {
            seconds--;
            if ($timerSpan.length) $timerSpan.text(seconds);
            if (seconds <= 0) {
                clearInterval(this.timer);
                $timerText.addClass('d-none');
                $resendBtn.removeClass('d-none');
            }
        }, 1000);
    },

    /**
     * Manual Email Validation (Prevents browser crash on hidden fields)
     */
    _validateEmail() {
        const emailInput = this.$emailInput[0];
        if (!emailInput) return false;

        const email = emailInput.value.trim();
        const $errorMsg = this.$('#otp-email-msg');
        const emailRegex = /^[a-zA-Z0-9]([a-zA-Z0-9._%+-]*[a-zA-Z0-9])?@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
        if (!email || !emailRegex.test(email)) {
            $errorMsg.text("Please enter a valid email address (e.g. name@domain.com)");
            this.$emailInput.addClass('is-invalid');
            return false;
        }

        this.$emailInput.removeClass('is-invalid');
        $errorMsg.text("");
        return email;
    },
    /**
     * Action: Send OTP
     */
    async _onSendOTP(ev) {
        ev.preventDefault();
        ev.stopPropagation(); // Stop Odoo login form from intercepting

        const email = this._validateEmail();
        if (!email) return;

        const $btn = this.$(ev.currentTarget);
        $btn.prop('disabled', true).addClass('btn-divine-loading').html(this._getDivineSpinner('Invoking OTP'));

        try {
            const res = await rpc('/otp-login/send', {email});
            if (res.status === 'success') {

                // --- CRITICAL FIX: Disable browser validation before hiding ---
                this.$emailInput.removeAttr('required').prop('required', false);
                this.$emailInput.attr('name', 'old_email_prevent_focus');

                this.$emailStep.fadeOut(300, () => {
                    this.$otpStep.removeClass('d-none').hide().fadeIn(300);
                    this._startResendTimer();
                    setTimeout(() => this.$otpInputs.first().focus(), 200);
                });
            } else {
                this.$('#otp-email-msg').text(res.message || "Failed to send OTP");
                $btn.prop('disabled', false).removeClass('btn-divine-loading').text('Verify');
            }
        } catch (e) {
            $btn.prop('disabled', false).removeClass('btn-divine-loading').text('Verify');
        }
    },

    /**
     * Action: Verify OTP
     */
    async _onVerifyOTP(ev) {
        if (ev) {
            ev.preventDefault();
            ev.stopPropagation();
        }

        const $verifyMsg = this.$('#otp-verify-msg');
        const code = this.$otpInputs.map((i, el) => $(el).val()).get().join('');

        this.$otpInputs.removeClass('is-invalid border-danger');
        $verifyMsg.text("");

        if (code.length < 6) {
            $verifyMsg.text("Please enter all 6 digits");
            this.$otpInputs.addClass('is-invalid border-danger');
            return;
        }

        const $btn = this.$('#btn-verify-otp');
        $btn.prop('disabled', true).addClass('btn-divine-loading').html(this._getDivineSpinner('Verifying'));

        const urlParams = new URLSearchParams(window.location.search);
        let targetRedirect = urlParams.get('redirect') || this.$el.data('redirect') || '/';

        const badPaths = ['/web/login', '/web/reset_password', '/otp-login'];
        if (badPaths.some(path => targetRedirect.includes(path))) {
            targetRedirect = '/';
        }

        try {
            const res = await rpc('/otp-login/verify', {
                code,
                redirect: targetRedirect
            });
            if (res.status === 'success') {
                if (this.timer) clearInterval(this.timer);
                this.$otpStep.fadeOut(200, () => {
                    this.$('#otp-success').removeClass('d-none').fadeIn(200);
                    setTimeout(() => {
                        // Use the redirect returned by the server (which we just sent)
                        window.location.replace(res.redirect || '/');
                    }, 300);
                });
            } else {
                $verifyMsg.text(res.message || "Incorrect code");
                this.$otpInputs.addClass('is-invalid border-danger').val('');
                $btn.prop('disabled', false).removeClass('btn-divine-loading').text('Verify OTP');
                this.$otpInputs.first().focus();
            }
        } catch (e) {
            $btn.prop('disabled', false).removeClass('btn-divine-loading').text('Verify OTP');
        }
    },
    /**
     * Action: Resend OTP
     */
    async _onResendOTP(ev) {
        ev.preventDefault();
        ev.stopPropagation();

        const email = this.$emailInput.val().trim();
        const $link = this.$(ev.currentTarget);
        $link.addClass('pe-none opacity-50').html(this._getDivineSpinner('Resending'));

        try {
            const res = await rpc('/otp-login/send', {email});
            if (res.status === 'success') {
                this._startResendTimer();
                this.$otpInputs.val('').removeClass('is-invalid border-danger');
                this.$otpInputs.first().focus();
            }
        } finally {
            $link.removeClass('pe-none opacity-50').text('Resend OTP');
        }
    },

    /**
     * Input Handling: Move to next box
     */
    _onDigitInput(ev) {
        const $target = this.$(ev.target);
        $target.val($target.val().replace(/\D/g, ''));

        if ($target.val().length === 1) {
            $target.next('.otp-digit').focus();
        }

        const currentCode = this.$otpInputs.map((i, el) => $(el).val()).get().join('');
        if (currentCode.length === 6) {
            this._onVerifyOTP();
        }
    },

    _onDigitKeydown(ev) {
        if (ev.key === 'Backspace' && !this.$(ev.target).val()) {
            this.$(ev.target).prev('.otp-digit').focus();
        }
    },

    _onDigitPaste(ev) {
        ev.preventDefault();
        const data = (ev.originalEvent.clipboardData || window.clipboardData).getData('text');
        const digits = data.replace(/\D/g, '').split('').slice(0, 6);
        this.$otpInputs.each((i, el) => {
            if (digits[i]) this.$(el).val(digits[i]);
        });
        if (digits.length === 6) this._onVerifyOTP();
    }
});