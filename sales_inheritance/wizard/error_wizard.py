from odoo import models, fields, api

class ErrorWizard(models.TransientModel):
    _name = 'error.wizard'

    def action_confirm_button(self):
        po_id = self.env.context.get('active_id')
        po_record = self.env['purchase.order'].browse(po_id)
        if po_record.exists():
            return po_record.with_context(skip_purchase_limit=True).button_confirm()


    def action_cancel_button(self):
        print("Button Cancel Clicked")
        return {
            'type': 'ir.actions.act_window_close',
            'name': 'Purchase Order Wizard Cancellation Button',
            'res_model': 'purchase.order',
            'view_mode': 'form',
            'target': 'current',
        }

        # def button_confirm(self):
        #     for order in self:
        #         if order.state not in ['draft', 'sent']:
        #             continue
        #         order.order_line._validate_analytic_distribution()
        #         order._add_supplier_to_product()
        #         # Deal with double validation process
        #         if order._approval_allowed():
        #             order.button_approve()
        #         else:
        #             order.write({'state': 'to approve'})
        #         if order.partner_id not in order.message_partner_ids:
        #             order.message_subscribe([order.partner_id.id])
        #     return True
        # purchase_order.button_confirm()

        # if po_id:
        #     po_record = self.env['purchase.order'].browse(po_id)
        #     if po_record:
        #         # result = po_record.button_confirm(po_record)
        #         # return result
        #         print("Button Confirm Clicked")
        #         # po_record.button_confirm()
        #         res = po_record.button_confirm()
        #         return res
        #         # return po_record.button_confirm()
        #         # return super(type(po_record),po_record).button_confirm()
        #         # super(po_record).button_confirm()
        #         # return {
        #         #     'type': 'ir.actions.act_window_close',
        #         # }
        #     print(po_id)
        print("Button Confirm Clicked")

        # return po_record.button_confirm()

        # def action_cancel_button(self):
        # po_id = self.env.context.get('active_id')
        # if po_id:
        #     po_record = self.env['purchase.order'].browse(po_id)
        #     po_record.button_cancel()
        # print(po_id)
