# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api

class ProductTemplate(models.Model):
    _inherit = "product.template"
    
    hide_bulk_creation=fields.Boolean(string="Hide Bulk Creation",compute="_compute_hide_bulk_creation")

    @api.depends('tracking') # added api.depends
    def _compute_hide_bulk_creation(self):
        for rec in self:
            rec.hide_bulk_creation=rec.tracking != 'serial'
    
    def open_bulk_serial_create_wizard(self):
        self.ensure_one()
        product = self.env['product.product'].search([('product_tmpl_id', '=', self.id)], limit=1)
        self.env['bulk.serial.create.lines'].search([]).unlink()
        self.env['bulk.serial.create.lines.add'].search([]).unlink()
        self.env['bulk.serial.create.lines.exist'].search([]).unlink()
        self.env['bulk.serial.create.lines.duplicate'].search([]).unlink()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bulk Serial Creation Wizard',
            'view_mode': 'form',
            'res_model': 'bulk.serial.create.wizard',
            'target': 'new',
            'context': {
                'default_product_id': product.id,
                'default_total_serials_before_creation':self.env['stock.lot'].search_count([('product_id', '=', product.id)]),
            }
        }

    def open_backdate_wizard(self):
        self.ensure_one()
        product = self.env['product.product'].search([('product_tmpl_id', '=', self.id)], limit=1)
        self.env['product.serial'].search([]).unlink()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Backdate Wizard',
            'view_mode': 'form',
            'res_model': 'stock.backdate.wizard',
            'target': 'new',
            'context': {
                'default_product_id': product.id,
            }
        }
    
    def action_backdate_non_serialized(self):
        wizard=self.env['multi.stock.backdate.wizard'].create({
            'is_serialized': False,
            'is_non_serialized': True,
            'serialized_count': len(self.filtered(lambda x: x.tracking == 'serial')),
            'non_serialized_count': len(self.filtered(lambda x: x.tracking != 'serial')),
            'product_lines': [(0, 0, {
                'product_id': product.id,
                'qty': 0,
                'date': False,
            }) for product in self.filtered(lambda x: x.tracking != 'serial').product_variant_ids]
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Backdate Multiple Products',
            'view_mode': 'form',
            'res_model': 'multi.stock.backdate.wizard',
            'target': 'new',
            'res_id': wizard.id,
        }
    
    
    def action_backdate_serialized(self):
        pass
