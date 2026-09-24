# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.emi_finance.tools import emi_math

OFFICER = 'emi_finance.group_emi_officer'
MANAGER = 'emi_finance.group_emi_manager'
REVIEWER = 'emi_finance.group_emi_finance_reviewer'


class EmiApplication(models.Model):
    _name = 'emi.application'
    _description = 'EMI Application'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    # Loan terms: editable only while the application is a draft.
    _EMI_DRAFT_ONLY_FIELDS = frozenset({
        'company_id', 'partner_id', 'product_id', 'finance_company_id', 'tenure_plan_id',
        'downpayment_option_id', 'down_payment_amount', 'delivery_address_id', 'delivery_note',
    })
    # Set by the server (computes, snapshots, workflow actions) only.
    _EMI_SERVER_FIELDS = frozenset({
        'name', 'state', 'vendor_id', 'list_price', 'interest_rate_id', 'interest_rate_percent',
        'interest_calc_method', 'tenure_months', 'rejection_reason',
        'reviewed_by', 'reviewed_date', 'approved_by', 'approved_date',
    })

    name = fields.Char(default='New', copy=False, readonly=True)
    company_id = fields.Many2one(
        'res.company', required=True,
        default=lambda self: self.env['res.company']._emi_get_marketplace_company(),
        help="The marketplace company this application was placed through.",
    )
    currency_id = fields.Many2one(related='company_id.currency_id', store=True, readonly=True)

    partner_id = fields.Many2one('res.partner', string='Customer', required=True, tracking=True)

    # --- Product / vendor ---
    product_id = fields.Many2one(
        'product.product', string='Phone', required=True, tracking=True,
        domain="[('product_tmpl_id.listing_state', '=', 'published'), "
               "('product_tmpl_id.vendor_id.state', '=', 'approved')]",
    )
    # Snapshots taken from the product when it is chosen; they depend on
    # product_id only, so later catalog edits do not rewrite past applications.
    vendor_id = fields.Many2one(
        'emi.vendor', compute='_compute_product_snapshot', store=True, readonly=True,
    )
    list_price = fields.Monetary(
        string='Product Price', compute='_compute_product_snapshot', store=True, readonly=True,
    )

    # --- Financing selection ---
    finance_company_id = fields.Many2one('emi.finance.company', required=True, tracking=True)
    tenure_plan_id = fields.Many2one(
        'emi.tenure.plan', required=True, tracking=True,
        domain="[('id', 'in', allowed_tenure_plan_ids)]",
    )
    allowed_tenure_plan_ids = fields.Many2many(
        'emi.tenure.plan', compute='_compute_allowed_tenure_plan_ids',
        help="Technical field: tenures the selected finance company offers.",
    )
    tenure_months = fields.Integer(
        compute='_compute_tenure_months', store=True, readonly=True,
        help="Tenure length frozen from the plan, so editing the plan later cannot change this loan.",
    )

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
        help="Must be at least the minimum down payment. "
             "The customer may choose to pay more than the minimum.",
    )
    financed_amount = fields.Monetary(compute='_compute_financed_amount', store=True)

    # --- Interest snapshot. Resolved on the server from the active rate
    #     while in draft and re-resolved at submission; the dependencies are
    #     frozen after that, so later rate edits do not touch this loan. ---
    interest_rate_id = fields.Many2one(
        'emi.interest.rate', compute='_compute_interest_rate', store=True, readonly=True,
        copy=False, ondelete='restrict',
    )
    interest_rate_percent = fields.Float(
        compute='_compute_interest_snapshot', store=True, readonly=True, copy=False,
    )
    interest_calc_method = fields.Selection(
        [
            ('flat', 'Flat Rate (on original principal)'),
            ('reducing', 'Reducing Balance (on outstanding principal)'),
        ],
        string='Interest Method', compute='_compute_interest_snapshot', store=True, readonly=True,
        copy=False,
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

    # --- KYC (at most one record, enforced on emi.kyc) ---
    kyc_ids = fields.One2many('emi.kyc', 'application_id', string='KYC')
    kyc_verified = fields.Boolean(compute='_compute_kyc_verified', string='KYC Verified')

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
        default='draft', required=True, readonly=True, tracking=True, copy=False,
    )
    rejection_reason = fields.Text(copy=False, readonly=True, tracking=True)
    reviewed_by = fields.Many2one('res.users', readonly=True, copy=False)
    reviewed_date = fields.Datetime(readonly=True, copy=False)
    approved_by = fields.Many2one('res.users', readonly=True, copy=False)
    approved_date = fields.Datetime(readonly=True, copy=False)

    # ------------------------------------------------------------------
    # CRUD guards
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not self.env.su:
                blocked = {
                    f for f in (self._EMI_SERVER_FIELDS - {'name'}) & vals.keys()
                    if not (f == 'state' and vals[f] == 'draft')
                }
                if blocked:
                    raise AccessError(f"These fields are set by the system: {', '.join(sorted(blocked))}.")
            vals['name'] = self.env['ir.sequence'].sudo().next_by_code('emi.application') or 'New'
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            blocked = self._EMI_SERVER_FIELDS & vals.keys()
            if blocked:
                raise AccessError(
                    f"These fields are set by the workflow, not edited directly: {', '.join(sorted(blocked))}."
                )
            if self._EMI_DRAFT_ONLY_FIELDS & vals.keys() and any(rec.state != 'draft' for rec in self):
                raise UserError("Loan terms can only be changed while the application is a draft.")
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_in_progress(self):
        for rec in self:
            if rec.state not in ('draft', 'rejected'):
                raise UserError(f"{rec.name} is {rec.state}: only draft or rejected applications can be deleted.")

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------

    def _get_product_price(self):
        """Price to finance for the selected product. emi_accounting
        overrides this to use the tax-included price."""
        self.ensure_one()
        return self.product_id.lst_price

    @api.depends('product_id')
    def _compute_product_snapshot(self):
        for rec in self:
            rec.vendor_id = rec.product_id.sudo().product_tmpl_id.vendor_id
            rec.list_price = rec._get_product_price() if rec.product_id else 0.0

    @api.depends('finance_company_id')
    def _compute_allowed_tenure_plan_ids(self):
        all_plans = self.env['emi.tenure.plan'].search([])
        for rec in self:
            rec.allowed_tenure_plan_ids = rec.finance_company_id.sudo().tenure_plan_ids or all_plans

    @api.depends('tenure_plan_id')
    def _compute_tenure_months(self):
        for rec in self:
            rec.tenure_months = rec.tenure_plan_id.months

    @api.depends('product_id')
    def _compute_product_tmpl_id_domain(self):
        for rec in self:
            rec.product_tmpl_id_domain = rec.product_id.product_tmpl_id

    @api.depends('finance_company_id', 'tenure_plan_id')
    def _compute_interest_rate(self):
        Rate = self.env['emi.interest.rate'].sudo()
        for rec in self:
            if rec.finance_company_id and rec.tenure_plan_id:
                rec.interest_rate_id = Rate.get_active_rate(rec.finance_company_id.id, rec.tenure_plan_id.id)
            else:
                rec.interest_rate_id = False

    @api.depends('interest_rate_id')
    def _compute_interest_snapshot(self):
        for rec in self:
            rate = rec.interest_rate_id.sudo()
            rec.interest_rate_percent = rate.rate_percent
            rec.interest_calc_method = rate.calc_method

    @api.depends('downpayment_option_id', 'list_price', 'finance_company_id')
    def _compute_min_down_payment_amount(self):
        for rec in self:
            rec.min_down_payment_amount = rec._get_min_down_payment()

    def _get_min_down_payment(self):
        """Selected option's minimum, else the finance company's default
        percentage (products with options must pick one; see action_submit)."""
        self.ensure_one()
        if self.downpayment_option_id:
            return self.downpayment_option_id.sudo().compute_min_amount(self.list_price)
        return self.list_price * (self.finance_company_id.sudo().min_down_payment_percent / 100.0)

    @api.depends('list_price', 'down_payment_amount')
    def _compute_financed_amount(self):
        for rec in self:
            rec.financed_amount = max(rec.list_price - rec.down_payment_amount, 0.0)

    @api.depends('financed_amount', 'interest_rate_percent', 'interest_calc_method', 'tenure_months')
    def _compute_emi_preview(self):
        for rec in self:
            result = emi_math.quote(
                rec.financed_amount, rec.interest_rate_percent or 0.0, rec.tenure_months or 0,
                rec.interest_calc_method,
            )
            rec.total_interest_amount = result['total_interest']
            rec.total_payable_amount = result['total_payable']
            rec.emi_amount = result['emi']

    @api.depends('kyc_ids.verified')
    def _compute_kyc_verified(self):
        for rec in self:
            rec.kyc_verified = bool(rec.kyc_ids) and rec.kyc_ids[0].verified

    @api.onchange('finance_company_id', 'tenure_plan_id')
    def _onchange_finance_tenure(self):
        if self.finance_company_id and self.tenure_plan_id and not self.interest_rate_id:
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

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    @api.constrains('interest_rate_id', 'finance_company_id', 'tenure_plan_id')
    def _check_interest_rate_matches(self):
        for rec in self:
            rate = rec.interest_rate_id
            if rate and (rate.finance_company_id != rec.finance_company_id
                         or rate.tenure_plan_id != rec.tenure_plan_id):
                raise ValidationError("The interest rate does not belong to this finance company and tenure.")

    @api.constrains('company_id', 'finance_company_id')
    def _check_companies(self):
        marketplace = self.env['res.company']._emi_get_marketplace_company()
        for rec in self:
            if marketplace and rec.company_id != marketplace:
                raise ValidationError(
                    f"Applications are placed through the marketplace company ({marketplace.name})."
                )

    @api.constrains('downpayment_option_id', 'product_id')
    def _check_downpayment_option_product(self):
        for rec in self:
            option = rec.downpayment_option_id
            if option and option.product_tmpl_id != rec.product_id.product_tmpl_id:
                raise ValidationError("The down payment option belongs to a different product.")

    @api.constrains('down_payment_amount', 'list_price')
    def _check_down_payment_bounds(self):
        for rec in self:
            if rec.down_payment_amount < 0:
                raise ValidationError("The down payment cannot be negative.")
            if rec.list_price and rec.down_payment_amount >= rec.list_price:
                raise ValidationError("The down payment must be less than the product price; nothing would be financed.")

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------

    def _check_group(self, *xmlids):
        if self.env.su or any(self.env.user.has_group(x) for x in xmlids):
            return
        raise AccessError("You are not allowed to perform this step of the EMI workflow.")

    def _check_finance_company_member(self):
        """Finance reviewers act only for their own finance company."""
        if self.env.su:
            return
        for rec in self:
            if rec.finance_company_id.company_id not in self.env.user.company_ids:
                raise AccessError(f"{rec.name} belongs to another finance company.")

    def _check_kyc_complete(self):
        self.ensure_one()
        if not self.kyc_ids or not self.kyc_ids[0].is_complete():
            raise UserError("KYC information is incomplete. Please fill in all required "
                             "fields and upload citizenship, photo and income proof.")

    def _check_submittable(self):
        self.ensure_one()
        product_tmpl = self.product_id.sudo().product_tmpl_id
        if product_tmpl.listing_state != 'published' or product_tmpl.vendor_id.state != 'approved':
            raise UserError(f"{self.product_id.display_name} is not currently published by an approved vendor.")
        if not self.finance_company_id.active:
            raise UserError(f"{self.finance_company_id.name} is no longer accepting applications.")
        if not self.finance_company_id._offers_tenure(self.tenure_plan_id):
            raise UserError(f"{self.finance_company_id.name} does not offer the {self.tenure_plan_id.name} tenure.")
        if not (self.delivery_address_id or self.delivery_note):
            raise UserError("Choose a delivery address or enter delivery instructions.")
        if product_tmpl.downpayment_option_ids.filtered('active') and not self.downpayment_option_id:
            raise UserError("Choose one of this phone's down payment options.")

    def action_submit(self):
        self._check_group(OFFICER)
        Rate = self.env['emi.interest.rate'].sudo()
        for rec in self:
            if rec.state != 'draft':
                raise UserError("Only draft applications can be submitted.")
            rec._check_submittable()
            rate = Rate.get_active_rate(rec.finance_company_id.id, rec.tenure_plan_id.id)
            if not rate:
                raise UserError("No active interest rate is configured for this finance "
                                 "company and tenure. Please select a different tenure or "
                                 "contact the finance company.")
            # Re-take every snapshot at submission time.
            rec.sudo().write({
                'interest_rate_id': rate.id,
                'interest_rate_percent': rate.rate_percent,
                'interest_calc_method': rate.calc_method,
                'tenure_months': rec.tenure_plan_id.months,
                'vendor_id': rec.product_id.sudo().product_tmpl_id.vendor_id.id,
                'list_price': rec._get_product_price(),
            })
            minimum = rec._get_min_down_payment()
            if rec.down_payment_amount < minimum:
                raise ValidationError(
                    f"Down payment must be at least {rec.currency_id.format(minimum)}."
                )
            rec._check_kyc_complete()
            rec.sudo().write({'state': 'submitted'})

    def action_start_review(self):
        self._check_group(OFFICER)
        for rec in self:
            if rec.state != 'submitted':
                raise UserError("Only submitted applications can enter KYC review.")
        self.sudo().write({
            'state': 'kyc_review',
            'reviewed_by': self.env.user.id,
            'reviewed_date': fields.Datetime.now(),
        })

    def action_verify_kyc(self):
        self._check_group(OFFICER)
        for rec in self:
            if rec.state != 'kyc_review':
                raise UserError("KYC is verified during KYC review.")
            rec._check_kyc_complete()
        self.kyc_ids.sudo().write({'verified': True})

    def action_send_to_finance(self):
        self._check_group(OFFICER)
        for rec in self:
            if rec.state != 'kyc_review':
                raise UserError("Only applications in KYC review can be sent to the finance company.")
            if not rec.kyc_verified:
                raise UserError("KYC documents must be marked as verified before sending "
                                 "this application to the finance company.")
        self.sudo().write({'state': 'pending_finance_approval'})

    def action_return_to_draft(self):
        """Send an application back to the customer/officer for corrections."""
        self._check_group(OFFICER)
        for rec in self:
            if rec.state not in ('submitted', 'kyc_review'):
                raise UserError("Only submitted applications or those in KYC review can be returned to draft.")
        self.kyc_ids.sudo().write({'verified': False})
        self.sudo().write({'state': 'draft', 'reviewed_by': False, 'reviewed_date': False})

    def action_approve(self):
        self._check_group(REVIEWER)
        self._check_finance_company_member()
        for rec in self:
            if rec.state != 'pending_finance_approval':
                raise UserError("Only applications pending finance approval can be approved.")
        self.sudo().write({
            'state': 'approved',
            'approved_by': self.env.user.id,
            'approved_date': fields.Datetime.now(),
        })

    def action_open_reject_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Reject Application',
            'res_model': 'emi.application.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_application_id': self.id},
        }

    def action_reject(self, reason):
        """Officers reject during KYC review, finance reviewers while the
        application waits for their credit decision."""
        if not (reason or '').strip():
            raise UserError("Please provide a rejection reason.")
        for rec in self:
            if rec.state == 'kyc_review':
                rec._check_group(OFFICER)
            elif rec.state == 'pending_finance_approval':
                rec._check_group(REVIEWER)
                rec._check_finance_company_member()
            else:
                raise UserError("Only applications in review can be rejected.")
        self.sudo().write({'state': 'rejected', 'rejection_reason': reason.strip()})

    def action_disburse(self):
        """Marks the application as disbursed. emi_accounting overrides/extends
        this method to post the actual inter-company disbursement entry and
        generate the emi.schedule.line amortization schedule."""
        self._check_group(REVIEWER)
        self._check_finance_company_member()
        for rec in self:
            if rec.state != 'approved':
                raise UserError("Only approved applications can be disbursed.")
        self.sudo().write({'state': 'disbursed'})

    def action_activate(self):
        self._check_group(OFFICER)
        for rec in self:
            if rec.state != 'disbursed':
                raise UserError("Only disbursed applications can be activated.")
        self.sudo().write({'state': 'active'})

    def action_close(self):
        self._check_group(OFFICER)
        for rec in self:
            if rec.state != 'active':
                raise UserError("Only active applications can be closed.")
        self.sudo().write({'state': 'closed'})

    def action_mark_default(self):
        self._check_group(OFFICER)
        for rec in self:
            if rec.state != 'active':
                raise UserError("Only active applications can be marked as defaulted.")
        self.sudo().write({'state': 'defaulted'})


class EmiInterestRate(models.Model):
    _inherit = 'emi.interest.rate'

    def _emi_used_records(self):
        used = super()._emi_used_records()
        apps = self.env['emi.application'].sudo().search([
            ('interest_rate_id', 'in', self.ids), ('state', '!=', 'draft'),
        ])
        return used | apps.interest_rate_id


class EmiTenurePlan(models.Model):
    _inherit = 'emi.tenure.plan'

    def _emi_used_records(self):
        used = super()._emi_used_records()
        apps = self.env['emi.application'].sudo().search([
            ('tenure_plan_id', 'in', self.ids), ('state', '!=', 'draft'),
        ])
        return used | apps.tenure_plan_id
