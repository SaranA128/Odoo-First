# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models, api
from datetime import datetime, time
from odoo.exceptions import ValidationError
import base64
import pandas as pd
from io import BytesIO

import logging
_logger = logging.getLogger(__name__)


class BulkSerialCreateLines(models.AbstractModel):
    _name = "bulk.serial.create.lines.fields"
    _description = "Product Serials"
    name = fields.Char(required=True)
    bulk_serial_create_id = fields.Many2one("bulk.serial.create.wizard", string="Related Wizard")

    stock_lot_id = fields.Many2one('stock.lot', compute="_compute_stock_lot")
    stoc_quant_id = fields.Many2one(
        'stock.quant', compute="_compute_stock_quant")
    lot_in_system = fields.Boolean(
        string="Serial in system", compute="_compute_lot_in_system")
    lot_create_date=fields.Datetime(string="Created On", related="stock_lot_id.create_date")

    @api.depends("bulk_serial_create_id", "bulk_serial_create_id.product_id", 'name')
    def _compute_stock_lot(self):
        for rec in self:
            if rec.bulk_serial_create_id.product_id:
                rec.stock_lot_id = self.env['stock.lot'].search([('product_id', '=', rec.bulk_serial_create_id.product_id.id),('name', '=', rec.name)], limit=1) # added limit = 1
            else:
                rec.stock_lot_id = False
   
    @api.depends("stock_lot_id")
    def _compute_stock_quant(self):
        for rec in self:
            if rec.stock_lot_id:
                rec.stoc_quant_id = self.env['stock.quant'].search([('product_id', '=', rec.bulk_serial_create_id.product_id.id),
                                                                    ('lot_id', '=', rec.stock_lot_id.id)], limit=1)
            else:
                rec.stoc_quant_id = False

    @api.depends("stock_lot_id")
    def _compute_lot_in_system(self):
        for rec in self:
            if rec.stock_lot_id:
                rec.lot_in_system = True
            else:
                rec.lot_in_system = False
    
class BulkSerialCreateLines(models.TransientModel):
    _name = "bulk.serial.create.lines"
    _inherit = ["bulk.serial.create.lines.fields"]

class BulkSerialCreateLinesAdd(models.TransientModel):
        _name = "bulk.serial.create.lines.add"
        _inherit = ["bulk.serial.create.lines.fields"]

class BulkSerialCreateLinesExisting(models.TransientModel):
        _name = "bulk.serial.create.lines.exist"
        _inherit = ["bulk.serial.create.lines.fields"]

class BulkSerialCreateLinesDuplicates(models.TransientModel):
        _name = "bulk.serial.create.lines.duplicate"
        _inherit = ["bulk.serial.create.lines.fields"]

class BulkSerialCreateWizard(models.TransientModel):
    _name = 'bulk.serial.create.wizard'
    _description = 'Bulk Serial Create Wizard'

    product_id = fields.Many2one(
        'product.product', string='Product', required=True,readonly=True)
    hide_footer = fields.Boolean(string='Hide Footer')
    product_serial_ids = fields.One2many('bulk.serial.create.lines', 'bulk_serial_create_id', string="Serial Numbers") 
    file = fields.Binary('Excel File')
    filename = fields.Char('File Name')
    file_processed = fields.Boolean(string="File Processed")
    
    serials_to_add = fields.One2many('bulk.serial.create.lines.add','bulk_serial_create_id', string="Serials to Create")
    existing_serials = fields.One2many('bulk.serial.create.lines.exist','bulk_serial_create_id', string="Existing Serials",readonly=True)
    duplicate_serials = fields.One2many('bulk.serial.create.lines.duplicate','bulk_serial_create_id' ,string="Duplicates Serials Found",readonly=True)
    
    total_to_create = fields.Integer(string="To Create", compute="_compute_total_to_create")
    total_existing = fields.Integer(string="Existing", compute="_compute_total_existing")
    total_duplicate_serials = fields.Integer(string="Duplicates", compute="_compute_total_duplicate_serials")
    total_serials_uploaded= fields.Integer(string="Total Serials Uploaded", compute="_compute_total_serials_uploaded")
    total_serials_before_creation= fields.Integer(string="Total Serials Before Creation")
    total_serials_after_creation= fields.Integer(string="Total Serials After Creation")    
    total_created= fields.Integer(string="Total Created")
    
    @api.depends('product_serial_ids', 'duplicate_serials','hide_footer')
    def _compute_total_serials_uploaded(self):
        for rec in self:
            rec.total_serials_uploaded = len(rec.product_serial_ids) + len(rec.duplicate_serials)

    @api.depends('existing_serials','hide_footer')
    def _compute_total_existing(self):
        for rec in self:
            rec.total_existing = len(rec.existing_serials)

    @api.depends('serials_to_add','hide_footer')
    def _compute_total_to_create(self):
        for rec in self:            
            rec.total_to_create = len(rec.serials_to_add.filtered(lambda x: not x.lot_in_system))

    @api.depends('duplicate_serials','hide_footer')
    def _compute_total_duplicate_serials(self):
        for rec in self:            
            rec.total_duplicate_serials = len(rec.duplicate_serials)
            

    def add_product_serial_line(self, serial):
        if self.product_serial_ids.filtered(lambda x: x.name == serial):
            self.duplicate_serials = [(0, 0, {
                'name': serial,
                'bulk_serial_create_id': self.id
             })] 
            return
        self.product_serial_ids = [(0, 0, {
            'name': serial,
            'bulk_serial_create_id': self.id
        })]    
        
    def prepare_final_data(self):
        self.existing_serials = [(0,0,{            
            'name': r.name,
            'bulk_serial_create_id': self.id
        }) for r in self.product_serial_ids.filtered(lambda x: x.lot_in_system)]
        self.serials_to_add =[(0,0,{
            'name': r.name,
            'bulk_serial_create_id': self.id
        }) for r in  self.product_serial_ids.filtered(lambda x: not x.lot_in_system)]
                
    def action_upload_file(self):
        self.ensure_one()
        # Decode the uploaded file
        file_content = base64.b64decode(self.file)
        excel_file = BytesIO(file_content)
        sheets = pd.read_excel(excel_file, sheet_name=None)
        for sheet_name, df in sheets.items():
            if sheet_name.strip() == "New Serial Numbers":
                columns = [col.strip() for col in df.columns]
                if self.product_id.name in columns:
                    column_values = df[self.product_id.name].tolist()
                    for value in column_values:
                        if str(value) != 'nan':
                            serial = value
                            if isinstance(serial, float) or isinstance(serial, int):
                                serial = int(value)
                            serial = str(serial).strip()
                            self.add_product_serial_line(serial)
                else:
                    raise ValidationError(
                        f"Column with name '{self.product_id.name}' not found on sheet {sheet_name}.")
                break       
        

    def action_process_file(self):
        self.ensure_one()
        if not self.file:
            return
        self.action_upload_file()
        self.file_processed = True
        self.prepare_final_data()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bulk Serial Creation Wizard',
            'view_mode': 'form',
            'res_model': 'bulk.serial.create.wizard',
            'target': 'new',
            'res_id': self.id,
        }

    def action_create_bulk_serials(self):
        serials_to_create = self.serials_to_add.filtered(lambda x: not x.lot_in_system)
        if not serials_to_create:
            raise ValidationError("No serials to create")
        for rec in serials_to_create:
            lot_id = self.env['stock.lot'].create({
                'name': rec.name,
                'product_id': self.product_id.id
            })
        
        
    def action_create(self):
        self.ensure_one()
        self.action_create_bulk_serials()
        self.hide_footer = True        
        all_serials=self.env['stock.lot'].search([('product_id', '=', self.product_id.id)])
        self.total_serials_after_creation = len(all_serials)
        self.total_created = self.total_serials_after_creation - self.total_serials_before_creation
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bulk Serial Creation Wizard',
            'view_mode': 'form',
            'res_model': 'bulk.serial.create.wizard',
            'target': 'new',
            'res_id': self.id,
        }
