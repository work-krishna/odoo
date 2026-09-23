# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class EmiApplication(models.Model):
    _name = 'emi.application'
    _description = 'EMI Application'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(default='New', copy=False, readonly=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        help="The marketplace company this application was placed through.",
    )
    currency_id = fields.Many2one(related='company_id.currency_id', store=True, readonly=True)

    partner_id = fields.Many2one('res.partner', string='Customer', required=True, tracking=True)

    # --- Product / vendor ---
    product_id = fields.Many2one(
        'product.product', string='Phone', required=True, tracking=True,
        domain="[('product_tmpl_id.listing_state', '=', 'published')]",
    )
    vendor_id = fields.Many2one(
        related='product_id.product_tmpl_id.vendor_id', store=True, readonly=True,
    )
    list_price = fields.Monetary(
        string='Product Price', compute='_compute_list_price', store=True, readonly=True,
    )

    # --- Financing selection ---
    finance_company_id = fields.Many2one('emi.finance.company', required=True, tracking=True)
    tenure_plan_id = fields.Many2one('emi.tenure.plan', required=True, tracking=True)

    downpayment_option_id = fields.Many2one(
        'emi.downpayment.option', string='Down Payment Option',
        domain="[('product_tmpl_id', '=', product_tmpl_id_domain), ('active', '=', True)]",
    )
    product_tmpl_id_domain = fields.Many2one(
        'product.template', compute='_compute_product_tmpl_id_domain',
        help="Technical field used only to build the down payment option domain.",
    )
    min_down_payment_amount = fields.Monetary(compute='_compute_min_down_payment_amount')
    down_payment_amount = fields.Monetary(
        string='Down Payment', tracking=True,
        help="Must be at least the selected down payment option's minimum. "
             "The customer may choose to pay more than the minimum.",
    )
    financed_amount = fields.Monetary(compute='_compute_financed_amount', store=True)

    # --- Interest snapshot (frozen at submission so later rate changes
    #     don't retroactively affect an in-flight application) ---
    interest_rate_id = fields.Many2one('emi.interest.rate', readonly=True, copy=False)
    interest_rate_percent = fields.Float(readonly=True, copy=False)
    interest_calc_method = fields.Selection(
        related='interest_rate_id.calc_method', string='Interest Method', store=True, readonly=True,
    )

    # --- EMI preview (informational; emi_accounting builds the authoritative schedule) ---
    total_interest_amount = fields.Monetary(compute='_compute_emi_preview', store=True)
    total_payable_amount = fields.Monetary(compute='_compute_emi_preview', store=True)
    emi_amount = fields.Monetary(
        compute='_compute_emi_preview', store=True, string='Estimated Monthly EMI',
    )

    # --- Delivery ---
    delivery_address_id = fields.Many2one(
        'res.partner', string='Delivery Address',
        domain="[('type', '=', 'delivery'), ('parent_id', 'child_of', partner_id)]",
        help="Choose a saved delivery address, or leave empty and use the note below.",
    )
    delivery_note = fields.Text(help="Free-text delivery instructions if no saved address is used.")

    # --- KYC ---
    kyc_ids = fields.One2many('emi.kyc', 'application_id', string='KYC')

    # --- Workflow ---
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('kyc_review', 'KYC Review'),
            ('pending_finance_approval', 'Pending Finance Approval'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('disbursed', 'Disbursed'),
            ('active', 'Active'),
            ('closed', 'Closed'),
            ('defaulted', 'Defaulted'),
        ],
        default='draft', required=True, tracking=True, copy=False,
    )
    rejection_reason = fields.Text(copy=False)
    reviewed_by = fields.Many2one('res.users', readonly=True, copy=False)
    reviewed_date = fields.Datetime(readonly=True, copy=False)
    approved_by = fields.Many2one('res.users', readonly=True, copy=False)
    approved_date = fields.Datetime(readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('emi.application') or 'New'
        return super().create(vals_list)

    @api.depends('product_id')
    def _compute_list_price(self):
        for rec in self:
            rec.list_price = rec.product_id.lst_price if rec.product_id else 0.0

    @api.depends('product_id')
    def _compute_product_tmpl_id_domain(self):
        for rec in self:
            rec.product_tmpl_id_domain = rec.product_id.product_tmpl_id

    @api.depends('downpayment_option_id', 'list_price')
    def _compute_min_down_payment_amount(self):
        for rec in self:
            if rec.downpayment_option_id:
                rec.min_down_payment_amount = rec.downpayment_option_id.compute_min_amount(rec.list_price)
            else:
                rec.min_down_payment_amount = 0.0

    @api.depends('list_price', 'down_payment_amount')
    def _compute_financed_amount(self):
        for rec in self:
            rec.financed_amount = max(rec.list_price - rec.down_payment_amount, 0.0)

    @api.depends('financed_amount', 'interest_rate_percent', 'interest_calc_method', 'tenure_plan_id')
    def _compute_emi_preview(self):
        for rec in self:
            principal = rec.financed_amount
            months = rec.tenure_plan_id.months or 0
            annual_rate = rec.interest_rate_percent or 0.0
            if not principal or not months:
                rec.total_interest_amount = 0.0
                rec.total_payable_amount = 0.0
                rec.emi_amount = 0.0
                continue

            if not annual_rate:
                emi = principal / months
                total_interest = 0.0
            elif rec.interest_calc_method == 'reducing':
                monthly_rate = (annual_rate / 100.0) / 12.0
                factor = (1 + monthly_rate) ** months
                emi = principal * monthly_rate * factor / (factor - 1)
                total_interest = (emi * months) - principal
            else:  # flat
                total_interest = principal * (annual_rate / 100.0) * (months / 12.0)
                emi = (principal + total_interest) / months

            rec.total_interest_amount = total_interest
            rec.total_payable_amount = principal + total_interest
            rec.emi_amount = emi

    @api.onchange('finance_company_id', 'tenure_plan_id')
    def _onchange_finance_tenure(self):
        if self.finance_company_id and self.tenure_plan_id:
            rate = self.env['emi.interest.rate'].get_active_rate(
                self.finance_company_id.id, self.tenure_plan_id.id,
            )
            if rate:
                self.interest_rate_id = rate
                self.interest_rate_percent = rate.rate_percent
            else:
                self.interest_rate_id = False
                self.interest_rate_percent = 0.0
                return {
                    'warning': {
                        'title': 'No interest rate configured',
                        'message': (
                            "This finance company has no active interest rate for the "
                            "selected tenure. The application cannot be submitted until "
                            "one is configured."
                        ),
                    }
                }

    def _check_kyc_complete(self):
        self.ensure_one()
        if not self.kyc_ids or not self.kyc_ids[0].is_complete():
            raise UserError("KYC information is incomplete. Please fill in all required "
                             "fields and upload citizenship, photo and income proof.")

    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError("Only draft applications can be submitted.")
            if not rec.interest_rate_id:
                raise UserError("No active interest rate is configured for this finance "
                                 "company and tenure. Please select a different tenure or "
                                 "contact the finance company.")
            if rec.downpayment_option_id and rec.down_payment_amount < rec.min_down_payment_amount:
                raise ValidationError(
                    f"Down payment must be at least {rec.min_down_payment_amount} "
                    f"for the selected option."
                )
            rec._check_kyc_complete()
            rec.state = 'submitted'

    def action_start_review(self):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError("Only submitted applications can enter KYC review.")
            rec.state = 'kyc_review'
            rec.reviewed_by = self.env.user
            rec.reviewed_date = fields.Datetime.now()

    def action_send_to_finance(self):
        for rec in self:
            if rec.state != 'kyc_review':
                raise UserError("Only applications in KYC review can be sent to the finance company.")
            if not rec.kyc_ids or not rec.kyc_ids[0].verified:
                raise UserError("KYC documents must be marked as verified before sending "
                                 "this application to the finance company.")
            rec.state = 'pending_finance_approval'

    def action_approve(self):
        for rec in self:
            if rec.state != 'pending_finance_approval':
                raise UserError("Only applications pending finance approval can be approved.")
            rec.state = 'approved'
            rec.approved_by = self.env.user
            rec.approved_date = fields.Datetime.now()

    def action_reject(self):
        for rec in self:
            if rec.state not in ('kyc_review', 'pending_finance_approval'):
                raise UserError("Only applications in review can be rejected.")
            if not rec.rejection_reason:
                raise UserError("Please provide a rejection reason before rejecting.")
            rec.state = 'rejected'

    def action_disburse(self):
        """Marks the application as disbursed. emi_accounting overrides/extends
        this method to post the actual inter-company disbursement entry and
        generate the emi.schedule.line amortization schedule."""
        for rec in self:
            if rec.state != 'approved':
                raise UserError("Only approved applications can be disbursed.")
            rec.state = 'disbursed'

    def action_activate(self):
        for rec in self:
            if rec.state != 'disbursed':
                raise UserError("Only disbursed applications can be activated.")
            rec.state = 'active'

    def action_close(self):
        for rec in self:
            if rec.state != 'active':
                raise UserError("Only active applications can be closed.")
            rec.state = 'closed'

    def action_mark_default(self):
        for rec in self:
            if rec.state != 'active':
                raise UserError("Only active applications can be marked as defaulted.")
            rec.state = 'defaulted'
