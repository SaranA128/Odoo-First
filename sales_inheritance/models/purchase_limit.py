from odoo import models, api, fields
from odoo.exceptions import ValidationError


class PurchaseLimit(models.Model):
    _inherit = 'res.partner'

    purchase_limit = fields.Monetary(string="Purchase Limit")


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    purchase_limit_warning = fields.Char('Purchase Limit Warning', compute='_compute_purchase_limit', store=False)

    @api.depends('partner_id', 'amount_total')
    def _compute_purchase_limit(self):
        for order in self:
            limit = order.partner_id.purchase_limit
            if limit > 0:
                if order.amount_total > limit:
                    order.purchase_limit_warning = (f"The Purchase Limit of {order.partner_id.name} is {limit}")
                else:
                    order.purchase_limit_warning = False
            else:
                order.purchase_limit_warning = False

    def button_confirm(self):
        if self.env.context.get('skip_purchase_limit'):
            return super(PurchaseOrder, self).button_confirm()

        for order in self:
            limit = order.partner_id.purchase_limit
            if limit > 0:
                if order.amount_total > limit:
                    if self.env.user._is_admin():
                        return {
                            'name': 'Error Wizard',
                            'type': 'ir.actions.act_window',
                            'view_mode': 'form',
                            'target': 'new',
                            'res_model': 'error.wizard',
                            'context': {'active_id': order.id}
                        }
                    else:
                        raise ValidationError(f"The Purchase Limit for {order.partner_id.name} is only {limit}. "
                                              f"It Exceeds the limit.")
        res = super(PurchaseOrder, self).button_confirm()
        return res

