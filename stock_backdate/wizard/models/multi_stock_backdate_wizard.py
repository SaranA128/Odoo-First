from odoo import models, fields, api
from datetime import datetime
from odoo.exceptions import ValidationError

class MultiStockBackdateWizard(models.TransientModel):
    _name = 'multi.stock.backdate.wizard'
    _description = 'Multi Stock Backdate Wizard'

    date_today = fields.Datetime(string='Date Today', default=lambda self: fields.Datetime.now(),readonly=True)
    back_date = fields.Datetime(string='Back Date')
    is_serialized = fields.Boolean(string='Serialized Products Only',readonly=True)
    is_non_serialized = fields.Boolean(string='Unserialized Products Only',readonly=True)    
    hide_footer = fields.Boolean(string='Hide Footer')
    serialized_count = fields.Integer(string='Serialized Count', default=0, readonly=True,
     # compute='_compute_serailized_count' 
     )
    non_serialized_count = fields.Integer(
     string='Non-Serialized Count', default=0, readonly=True,
     compute='_compute_non_serailized_count' 
     )
    product_lines = fields.One2many('multi.stock.backdate.line', 'wizard_id', string='Product Lines')
    
    # @api.depends('product_lines')
    # def _compute_serailized_count(self):
    #     for record in self:
    #         record.serailized_count = len(self.product_lines.filtered(lambda x: x.is_serialized))
            
    @api.depends('product_lines')
    def _compute_non_serailized_count(self):
        for record in self:
            record.non_serialized_count = len(record.product_lines.filtered(lambda x: not x.has_serial_numbers)) # Updated self --> record
    
    
    @api.onchange('product_lines')
    def _onchange_product_lines(self):
        for record in self:        
            record.non_serialized_count = len(record.product_lines.filtered(lambda x: not x.has_serial_numbers)) # Updated self --> record
  

    @api.onchange('back_date')
    def _onchange_back_date(self):
        if self.back_date:
         self.product_lines.date=self.back_date
       
    def action_backdate_all(self):     
        if not self.product_lines:
            raise ValidationError('No products added for backdating.')
        if any(not rec.date for rec in self.product_lines):
            raise ValidationError('Back Date is not set for one or more products.')
        for rec in self.product_lines:
            backdate_wizard=self.env['stock.backdate.wizard'].create({
            'product_id':rec.product_id.id,
            'qty':rec.qty,
            'date':rec.date
            })
            backdate_wizard.action_back_date()
        self.hide_footer = True
        return {
                'type': 'ir.actions.act_window',
                'name': 'Backdate Multiple Products',
                'view_mode': 'form',
                'res_model': 'multi.stock.backdate.wizard',
                'target': 'new',
                'res_id': self.id,
            }
     
    
class MultiStockBackdateLine(models.TransientModel):
    _name = 'multi.stock.backdate.line'
    _description = 'Multi Stock Backdate Line'

    wizard_id = fields.Many2one('multi.stock.backdate.wizard', string='Wizard Reference', required=True)
    product_id = fields.Many2one('product.product', string='Product', required=True)
    qty = fields.Float(string='New Quantity', required=True)
    qty_at_backdate = fields.Float(string='Quantity at backdate', compute='_compute_qty_at_backdate')
    qty_today = fields.Float(string='Quantity Today',compute='_compute_qty_today')
    date = fields.Datetime(string='Backdate Date')
    has_serial_numbers = fields.Boolean(compute='_compute_has_serial_numbers')
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id and len(self.wizard_id.product_lines.filtered(lambda x: x.product_id.id == self.product_id.id)) > 1: # Updated 2 --> 1
            raise ValidationError('Product already exists in the list.')
    
    @api.depends('product_id')
    def _compute_qty_today(self):
        for rec in self:
            rec.qty_today = 0  # False is changed to 0 because qty_done is a float value
            if rec.product_id and rec.wizard_id.date_today:
                rec.qty_today = rec.product_id.with_context(to_date=rec.wizard_id.date_today).qty_available
        
    @api.depends('product_id')
    def _compute_has_serial_numbers(self):
        for rec in self:
            rec.has_serial_numbers = rec.product_id.tracking == 'serial'
    
    @api.depends('product_id', 'date')
    def _compute_qty_at_backdate(self):
        for rec in self:
            rec.qty_at_backdate = 0
            if rec.product_id and rec.date:
                rec.qty_at_backdate = rec.product_id.with_context(to_date=rec.date).qty_available
