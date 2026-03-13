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


class ProductSerial(models.TransientModel):
    _name = "product.serial"
    _description = "Product Serials"
    name = fields.Char(required=True)
    stock_backdate_id = fields.Many2one("stock.backdate.wizard", string="Stock Backdate")
    operation = fields.Selection(
        selection=[
            ("increases", "Increases"),
            ("decreases", "Decreases"),
            ("unchanged", "Skipped"),
        ],
        compute='_compute_operation')
    reason = fields.Char(string="Reason")
    stock_lot_id = fields.Many2one('stock.lot', compute="_compute_stock_lot")
    stoc_quant_id = fields.Many2one('stock.quant', compute="_compute_stock_quant")
    lot_in_system = fields.Boolean(string="Serial in system", compute="_compute_lot_in_system")

    @api.depends("stock_backdate_id", "stock_backdate_id.product_id", 'name')
    def _compute_stock_lot(self):
        for rec in self:
            if rec.stock_backdate_id.product_id:
                rec.stock_lot_id = self.env['stock.lot'].search([('product_id', '=', rec.stock_backdate_id.product_id.id),
                                                                 ('name', '=', rec.name)], limit=1)
            else:
                rec.stock_lot_id = False

    @api.depends('stock_lot_id')
    def _compute_operation(self):
        for rec in self:
            rec.operation = False
            if rec.stock_lot_id:
                common_domain=[('product_id', '=', rec.stock_backdate_id.product_id.id), ('quantity', '>', 0), ('lot_id', 'in', [rec.stock_lot_id.id]), ('state', '=', 'done')]
                related_move_out_domain=[('product_id', '=', rec.stock_backdate_id.product_id.id), ('quantity', '>', 0), ('lot_id', 'in', [rec.stock_lot_id.id]), ('state', '=', 'done')                    ]
                                
                if rec.stock_backdate_id.location_id:
                    common_domain.append(('location_dest_id','=',rec.stock_backdate_id.location_id.id))
                    related_move_out_domain.append(('location_id','=',rec.stock_backdate_id.location_id.id))
                else:
                    common_domain.append(('location_usage', 'not in', ('internal', 'transit')))
                    common_domain.append(('location_dest_usage', 'in', ('internal', 'transit')))

                    related_move_out_domain.append(('location_usage', 'in', ('internal', 'transit')))
                    related_move_out_domain.append(('location_dest_usage', 'not in', ('internal', 'transit')))
                    
                related_move_in_within_range = self.env['stock.move.line'].search(common_domain+[('date', '<=', rec.stock_backdate_id.date)], order='date desc', limit=1)
                related_move_in_out_range = self.env['stock.move.line'].search(common_domain+[('date', '>', rec.stock_backdate_id.date)], order='date desc', limit=1)                                
                related_move_out = self.env['stock.move.line'].search(related_move_out_domain, order='date desc', limit=1)

                rec.operation = "unchanged"
                #check if lot doesnot currently exist in stock quant
                current_stock_quant_rec_domain=[('product_id', '=', rec.stock_backdate_id.product_id.id),('lot_id', '=', rec.stock_lot_id.id),('on_hand', '=', True)]
                current_stock_quant_rec=self.env['stock.quant'].search(current_stock_quant_rec_domain, limit=1)
                if not related_move_in_within_range and not related_move_in_out_range and not current_stock_quant_rec:
                    rec.operation = "increases"

                if related_move_out:
                    # and related_move_out.date <= rec.stock_backdate_id.date and related_move_in.date <= rec.stock_backdate_id.date:
                    rec.operation = "unchanged"
            else:
                rec.operation = "increases"

    @api.depends("stock_lot_id")
    def _compute_stock_quant(self):
        for rec in self:
            if rec.stock_lot_id:
                rec.stoc_quant_id = self.env['stock.quant'].search([('product_id', '=', rec.stock_backdate_id.product_id.id),
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


class StockBackdateWizard(models.TransientModel):
    _name = 'stock.backdate.wizard'
    _description = 'Backdate Wizard'

    product_id = fields.Many2one('product.product', string='Product', required=True)
    tracking = fields.Selection(related='product_id.tracking')    
    date = fields.Datetime(string='Back Date', required=True)
    qty = fields.Float(string='New Quantity')
    qty_at_backdate = fields.Float(string='Quantity at backdate', compute='_compute_qty_at_backdate')
    today_date = fields.Datetime(string='Today Date', default=fields.Datetime.now, readonly=True)
    qty_today = fields.Float(string='Quantity Today',compute='_compute_qty_today')
    location_qty_today = fields.Float(string='Quantity in Location(Today)',compute='_compute_qty_today')
    hide_footer = fields.Boolean(string='Hide Footer')
    product_serial_ids = fields.One2many('product.serial', 'stock_backdate_id', string="Serial Numbers")
    has_serial_numbers = fields.Boolean(compute='_compute_has_serial_numbers')
    qty_from_lines = fields.Integer(string='New Quantity', compute='_compute_qty_from_lines')
    file = fields.Binary('Excel File')
    filename = fields.Char('File Name')
    file_processed = fields.Boolean(string="File Processed")
    serials_to_remove = fields.Many2many('stock.move.line', string="Serials to Remove", compute="_compute_serials_to_remove")
    created_move_ids_case_1 = fields.Many2many('stock.move.line', string="Created Move IDs Case 1")
    increments = fields.Integer(string="Increments", compute="_compute_increments")
    decrements = fields.Integer(string="Decrements", compute="_compute_decrements")
    location_id=fields.Many2one("stock.location", domain=[("usage", "in", ["internal", "transit"])])
    lot_id=fields.Many2one("stock.lot", string="Lot")

    @api.depends('product_serial_ids',)
    def _compute_decrements(self):
        for rec in self:
            rec.decrements = len(rec.serials_to_remove)

    @api.depends('serials_to_remove')
    def _compute_increments(self):
        for rec in self:
            rec.increments = len(rec.product_serial_ids.filtered(
                lambda x: x.operation == "increases"))
    

    @api.depends('product_serial_ids', 'created_move_ids_case_1', 'date')
    def _compute_serials_to_remove(self):
        for rec in self:
            created_moves = rec.created_move_ids_case_1.ids
            quants_to_remove_domain=[('product_id', '=', rec.product_id.id)]
            move_in_domain=[('product_id', '=', rec.product_id.id),('id', 'not in', created_moves), ('quantity', '>', 0),  ('state', '=', 'done'), ('date', '<=', rec.date), ('lot_id', '!=', False)]
            move_out_domain=[('product_id', '=', rec.product_id.id), ('quantity', '>', 0), ('state', '=', 'done'),('date', '>', rec.date)]
            if rec.location_id:
                move_in_domain.append(('location_dest_id','=',rec.location_id.id))
                move_out_domain.append(('location_id','=',rec.location_id.id))
                quants_to_remove_domain.append(('location_id','=',rec.location_id.id))
            else:
                move_in_domain.append( ('location_usage', 'not in', ('internal', 'transit')))
                move_in_domain.append(('location_dest_usage', 'in', ('internal', 'transit')))

                move_out_domain.append( ('location_usage', 'in', ('internal', 'transit')))
                move_out_domain.append( ('location_dest_usage', 'not in', ('internal', 'transit')))
        
             
            move_ins = rec.env['stock.move.line'].search(move_in_domain, order='date desc')
            
            #===========implementation 1===================
            # move_out_domain.append(('lot_id', 'in', [mv_in.lot_id.id for mv_in in move_ins]))
            # move_outs_for_move_ins = rec.env['stock.move.line'].search(move_out_domain, order='date desc')
            
            # # ---> These were used during upto the specified period
            # move_ins_to_remove = move_ins.filtered(lambda x: x.lot_id.id not in [
            #     mv_out.lot_id.id for mv_out in move_outs_for_move_ins])
            
            # #on excel but already in system
            # serials_in_system = rec.product_serial_ids.filtered(lambda x:  x.stock_lot_id)
            # move_ins_to_remove = move_ins_to_remove.filtered(lambda x: x.lot_id.id not in [s.stock_lot_id.id for s in serials_in_system])
            
            # rec.serials_to_remove = move_ins_to_remove.ids
            
            
            #=========implementation 2===================
            quants_to_remove=rec.env['stock.quant'].search(quants_to_remove_domain+[('lot_id', 'in', [mv_in.lot_id.id for mv_in in move_ins])])
            move_ins_to_remove = move_ins.filtered(lambda x: x.lot_id.id in [
                q.lot_id.id for q in quants_to_remove])
            
            uniq_move_ins=[]
            for mv in move_ins_to_remove:
                if mv.lot_id.id not in [m.lot_id.id for m in uniq_move_ins]:
                    uniq_move_ins.append(mv)
                    
            #on excel but already in system
            serials_in_system = rec.product_serial_ids.filtered(lambda x:  x.stock_lot_id)
            _logger.info(f"\n\n\n length of serials_in_system {len(serials_in_system)}\n")
            move_ins_to_remove = list(filter(lambda x: x.lot_id.id not in [s.stock_lot_id.id for s in serials_in_system],uniq_move_ins))
            
            rec.serials_to_remove = [m.id for m in move_ins_to_remove]
            #========== end of implementation 2===================
            
            

    @api.onchange('product_id')
    def _onchange_product_id(self):
        self.product_serial_ids = [(5, 0, 0)]

    @api.onchange('product_serial_ids', 'created_move_ids_case_1', 'date')
    def _onchange_product_serial_ids(self):
        if not self.product_id:
            raise ValidationError(_("Please select the a product first."))
        if not self.date and self.product_serial_ids:
            raise ValidationError(_("Please select the backdate first."))

        created_moves = self.created_move_ids_case_1.ids
        move_in_domain=[('product_id', '=', self.product_id.id),('id', 'not in', created_moves), ('quantity', '>', 0),  ('state', '=', 'done'), ('date', '<=', self.date), ('lot_id', '!=', False)]
        move_out_domain=[('product_id', '=', self.product_id.id), ('quantity', '>', 0), ('state', '=', 'done')]
        if self.location_id:
            move_in_domain.append(('location_dest_id','=',self.location_id.id))
            move_out_domain.append(('location_id','=',self.location_id.id))
        else:
            move_in_domain.append( ('location_usage', 'not in', ('internal', 'transit')))
            move_in_domain.append(('location_dest_usage', 'in', ('internal', 'transit')))

            move_out_domain.append( ('location_usage', 'in', ('internal', 'transit')))
            move_out_domain.append( ('location_dest_usage', 'not in', ('internal', 'transit')))
        move_ins = self.env['stock.move.line'].search(move_in_domain, order='date desc')
        
        move_out_domain.append( ('lot_id', 'in', [mv_in.lot_id.id for mv_in in move_ins]))
        move_outs_for_move_ins = self.env['stock.move.line'].search(move_out_domain, order='date desc')
        # ---> These were used during upto the specified period
        move_ins_to_remove = move_ins.filtered(lambda x: x.lot_id.id not in [
            mv_out.lot_id.id for mv_out in move_outs_for_move_ins])
        serials_in_system = self.product_serial_ids.filtered(lambda x:  x.stock_lot_id)
        move_ins_to_remove = move_ins_to_remove.filtered(
            lambda x: x.lot_id.id not in [s.stock_lot_id.id for s in serials_in_system])
        self.serials_to_remove = move_ins_to_remove.ids

    @api.depends('product_serial_ids')
    def _compute_qty_from_lines(self):
        for rec in self:
            rec.qty_from_lines = len(self.product_serial_ids)

    @api.depends('product_id')
    def _compute_has_serial_numbers(self):
        for rec in self:
            rec.has_serial_numbers = rec.product_id.tracking in ['serial']

    @api.depends('product_id', 'hide_footer','location_id','lot_id')
    def _compute_qty_today(self):
        for rec in self:
            rec.qty_today = False
            if rec.product_id and rec.today_date:
                _logger.info(f"\n\n {rec.location_id}\n\n")
                # to_date = datetime.combine(rec.today_date, time(23, 59, 59)) --> time will be selected
                rec.qty_today = rec.product_id.with_context(to_date=rec.today_date).qty_available
                if rec.product_id.tracking=='lot':
                    rec.location_qty_today = rec.product_id.with_context(to_date=rec.today_date,location=rec.location_id.id,lot_id=rec.lot_id.id).qty_available
                else:
                    rec.location_qty_today = rec.product_id.with_context(to_date=rec.today_date,location=rec.location_id.id).qty_available

    @api.depends('product_id', 'date','location_id','lot_id')
    def _compute_qty_at_backdate(self):
        for rec in self:
            rec.qty_at_backdate = False
            if rec.product_id and rec.date:
                # to_date = datetime.combine(rec.date, time(23, 59, 59)) --> we shall pick current time
                if rec.product_id.tracking=='lot':
                    rec.qty_at_backdate = rec.product_id.with_context(to_date=rec.date,location=rec.location_id.id,lot_id=rec.lot_id.id).qty_available
                else:
                    rec.qty_at_backdate = rec.product_id.with_context(to_date=rec.date,location=rec.location_id.id).qty_available

    def add_product_serial_line(self, serial):
        if self.product_serial_ids.filtered(lambda x: x.name == serial):
            return
        self.product_serial_ids = [(0, 0, {
            'name': serial,
            'stock_backdate_id': self.id
        })]    
                
    def get_new_seq(self,serial):
        incremented_value = int(serial) + 1
        original_length = len(serial)
        # Format the result to match the original length, preserving leading zeros
        new_serial=str(incremented_value)
        if original_length>len(str(incremented_value)):
            new_serial = f"{incremented_value:0{original_length}d}"
        return new_serial    

    def get_journal_updated_name(self, acc_mv, backdate_to_date):
        new_month = backdate_to_date.strftime("%m")        
        latest_seq_rec=self.env['account.move'].search([], order='sequence_number desc', limit=1)
        updated_name=latest_seq_rec.name        
        
        while self.env['account.move'].search([('name','=',updated_name)]):            
            parts = acc_mv.name.rsplit('/', 2)
            updated_name_parts=updated_name.rsplit('/', 2)
            parts[1] = new_month
            parts[2]=self.get_new_seq(updated_name_parts[2])
                        
            #update the year too to match that of backdate
            parts_o=parts[0].split('/')
            parts_o[1]=backdate_to_date.strftime("%Y")
            parts[0]='/'.join(parts_o)
        
            updated_name = '/'.join(parts)
        _logger.info(f"\n\n\nupdated_name-------{updated_name}\n\n")
        return updated_name

    def back_date_journal_entry(self, stock_move, backdate_to_date):
        if stock_move:
            self.ensure_one()
            related_account_move = self.env['account.move.line'].search(
                [('move_id', '=', stock_move.id)], order='date desc', limit=1)
# account.move-->account.move.line, stock_move_id-->move_id
            if related_account_move:
                _logger.info(f"\n\n\nrelated_account_move-------{related_account_move.name}\n\n")
                related_account_move.button_draft()
                period_lock_date = self.env.company.sudo().period_lock_date
                fiscalyear_lock_date = self.env.company.sudo().fiscalyear_lock_date
                tax_lock_date = self.env.company.sudo().tax_lock_date
                self.env.company.sudo().write({
                    'period_lock_date': False,
                    'fiscalyear_lock_date': False,
                    'tax_lock_date': False,
                })
                related_account_move.write({
                    'date':  backdate_to_date,
                    'name': self.get_journal_updated_name(related_account_move, backdate_to_date)
                })
                related_account_move.action_post()
                self.env.company.sudo().write({
                    'period_lock_date': period_lock_date,
                    'fiscalyear_lock_date': fiscalyear_lock_date,
                    'tax_lock_date': tax_lock_date,
                })            

    def back_date_stock_valuation_layer(self, stock_move, backdate_to_date):
        if stock_move:
            related_svl = self.env['stock.valuation.adjustment.lines'].search(
                [('move_id', '=', stock_move.id),('product_id', '=', self.product_id.id)], order='create_date desc', limit=1)
# stock.valuation.layer-->stock.valuation.adjustment.lines stock_move_id --> move_id
            if related_svl:
                query = """
                    UPDATE stock_valuation_adjustment_lines
                    SET create_date = %s
                    WHERE id = %s
                """
                self.env.cr.execute(query, (backdate_to_date, related_svl.id))           

    def action_upload_file(self):
        # Decode the uploaded file
        file_content = base64.b64decode(self.file)
        excel_file = BytesIO(file_content)
        sheets = pd.read_excel(excel_file, sheet_name=None)
        for sheet_name, df in sheets.items():
            if sheet_name.strip() == "Serialized Items":
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

    def increase_serial_qty(self, lot_id, location_id, backdate_to_date):
        # create an adjustment from current stock
        res = self.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': self.product_id.id,
            'location_id': location_id.id,
            'inventory_quantity_auto_apply': 1,
            'lot_id': lot_id.id,
        })
        # backdate related stock move line -- get latest whose qty is the difference
        stock_move_line = self.env['stock.move.line'].search( [('product_id', '=', self.product_id.id), ('state', '=', 'done')], order='date desc', limit=1)
        stock_move_line.write({'date':  backdate_to_date})

        # update date on related stock move
        stock_move = self.env['stock.move'].search([('product_id', '=', self.product_id.id), ('state', '=', 'done')], order='date desc', limit=1)
        stock_move.write({'date':  backdate_to_date})

        # update date on related Journal entry
        self.back_date_journal_entry(stock_move, backdate_to_date)
        self.back_date_stock_valuation_layer(stock_move, backdate_to_date)
        return stock_move_line.id

    def decrease_serial_qty(self, lot_id, location_id, backdate_to_date):
        # create an adjustment from current stock
        stock_quant = self.env['stock.quant'].search(
            [('product_id', '=', self.product_id.id), ('location_id', '=', location_id.id),  ('lot_id', '=', lot_id.id)])

        stock_quant.write({
            'inventory_quantity': 0
        })
        stock_quant.action_apply_inventory()

        # backdate related stock move line -- get latest whose qty is the difference
        stock_move_line = self.env['stock.move.line'].search(
            [('product_id', '=', self.product_id.id), ('state', '=', 'done')], order='date desc', limit=1)
        stock_move_line.write({'date':  backdate_to_date})

        # update date on related stock move
        stock_move = self.env['stock.move'].search(
            [('product_id', '=', self.product_id.id), ('state', '=', 'done')], order='date desc', limit=1)
        stock_move.write({'date':  backdate_to_date})

        # update date on related Journal entry
        self.back_date_journal_entry(stock_move, backdate_to_date)
        self.back_date_stock_valuation_layer(stock_move, backdate_to_date)
        
    def get_location_to_use(self):
        company_id = self.product_id.company_id.id if self.product_id.company_id else self.env.company.id
        location_id = self.env['stock.warehouse'].search([('company_id', '=', company_id)], limit=1).lot_stock_id
        return self.location_id if self.location_id else location_id

    def action_back_date_with_serials(self):
        '''
            # get all moves history  serial numbers for the specified date and product  --> existing
            # compare with entered serial numbers  --> new
            # if the serial number in new is not in existing, create a stock quant for it
            # if the serial number in existing is not in new, set its quant to 0 by this date if its quant was 1
            # skip for serials whose quantity was set to 0
        '''

        backdate_to_date = self.date
        location_id=self.get_location_to_use()

        '''case 1
        entered serial number string is not in system --> stock_lot_id is false on the lines
        here just create the new serial number, create a stock quant for it then back date
        '''
        non_existing = self.product_serial_ids.filtered(lambda x: not x.stock_lot_id)
        created_moves = []
        _logger.info("\n\n Case 1: Non existing started \n\n")
        for product_serial_id in non_existing:
            _logger.info(f"\n\n **** {product_serial_id.name} ** \n")
            lot_id = self.env['stock.lot'].create({
                'name': product_serial_id.name,
                'product_id': self.product_id.id
            })
            id = self.increase_serial_qty(lot_id, location_id, backdate_to_date)
            if id:
                created_moves.append(id)
                _logger.info("\n\n created new stock quant \n\n")
        self.created_move_ids_case_1 = created_moves
        
        _logger.info("\n\n Non existing finished \n\n")

        '''case 2 --> Reducing quantity by detecting serials ommitted while entering new ones
        entered serial number string is in system. But it existed by the given date though its not included in entered list
        here set its quant to 0 if it exists in stock quant 
        '''
        _logger.info("\n\n Case 2: started \n\n")
        for move_in in self.serials_to_remove:
            lot_id = move_in.lot_id
            # _logger.info(f"\n\n **** {lot_id.name} ** \n")
            self.decrease_serial_qty(lot_id, location_id, backdate_to_date)


        '''case 3 --> increasing quantity by detecting additional serials included 
        entered serial number string is in system. But it didnt exist by the given date though its included in entered list
        here set its quant to 0 if it exists in stock quant 
        '''
        _logger.info("\n\n Case 3: Non existing started \n\n")
        additional_serials = self.product_serial_ids.filtered(
            lambda x: x.operation == "increases")
        for product_serial_id in additional_serials:
            lot_id = product_serial_id.stock_lot_id
            # _logger.info(f"\n\n **** {lot_id.name} ** \n")
            self.increase_serial_qty(lot_id, location_id, backdate_to_date)

    def action_back_date_without_serials(self):
        # backdate_to_date = datetime.combine(self.date, time(9, 00, 00)) --> take the selected time and date
        backdate_to_date = self.date
        current_qty = self.qty_today
        difference = self.qty-self.qty_at_backdate        
        qty_to_apply = (current_qty+difference) if not self.location_id else (self.location_qty_today+difference)

        location_id=self.get_location_to_use()
        if qty_to_apply < 0:
            raise ValidationError(
                _(f"Invalid Operation. The stock level of the product {self.product_id.name} as of today ({self.today_date.strftime('%d/%m/%Y')}) would become negative ({round(qty_to_apply, 2)}). \nPlease first adjust the current quantity ({self.qty_today}) to atleast ({abs(difference)})."))

        # create an adjustment from current stock
        stock_quant = self.env['stock.quant'].search([('product_id', '=', self.product_id.id), ('location_id', '=', location_id.id)])
        if not stock_quant:
            self.env['stock.quant'].with_context(inventory_mode=True).create({
                'product_id': self.product_id.id,
                'location_id': location_id.id,
                'inventory_quantity_auto_apply': qty_to_apply,
            })
        else:
            stock_quant.write({
                'inventory_quantity': qty_to_apply
            })
            stock_quant.action_apply_inventory()

        # backdate related stock move line -- get latest whose qty is the difference
        stock_move_line = self.env['stock.move.line'].search([('product_id', '=', self.product_id.id), ('state', '=', 'done'), ('quantity', '=', abs(difference))], order='date desc', limit=1)
        stock_move_line.write({'date':  backdate_to_date})

        # update date on related stock move
        stock_move = self.env['stock.move'].search([('product_id', '=', self.product_id.id), ('state', '=', 'done'), ('product_uom_qty', '=', abs(difference))], order='date desc', limit=1)
        stock_move.write({'date':  backdate_to_date})
        self.back_date_journal_entry(stock_move, backdate_to_date)
        self.back_date_stock_valuation_layer(stock_move, backdate_to_date)
    # replaced qty_done with quantity
    def action_back_date_with_lots(self):
        if not self.lot_id:
            raise ValidationError(_("Please select a lot first."))
        backdate_to_date = self.date
        current_qty = self.qty_today
        difference = self.qty-self.qty_at_backdate        
        qty_to_apply = (current_qty+difference) if not self.location_id else (self.location_qty_today+difference)

        location_id=self.get_location_to_use()
        if qty_to_apply < 0:
            raise ValidationError(
                _(f"Invalid Operation. The stock level of the product {self.product_id.name} as of today ({self.today_date.strftime('%d/%m/%Y')}) would become negative ({round(qty_to_apply, 2)}). \nPlease first adjust the current quantity ({self.qty_today}) to atleast ({abs(difference)})."))

        # create an adjustment from current stock
        stock_quant = self.env['stock.quant'].search([('product_id', '=', self.product_id.id), ('location_id', '=', location_id.id), ('lot_id', '=', self.lot_id.id)])
        if not stock_quant:
            self.env['stock.quant'].with_context(inventory_mode=True).create({
                'product_id': self.product_id.id,
                'location_id': location_id.id,
                'lot_id': self.lot_id.id,
                'inventory_quantity_auto_apply': qty_to_apply,
            })
        else:
            stock_quant.write({
                'inventory_quantity': qty_to_apply
            })
            stock_quant.action_apply_inventory()

        # backdate related stock move line -- get latest whose qty is the difference
        stock_move_line = self.env['stock.move.line'].search([('product_id', '=', self.product_id.id), ('state', '=', 'done'), ('quantity', '=', abs(difference))], order='date desc', limit=1)
        stock_move_line.write({'date':  backdate_to_date})

        # update date on related stock move
        stock_move = self.env['stock.move'].search([('product_id', '=', self.product_id.id), ('state', '=', 'done'), ('product_uom_qty', '=', abs(difference))], order='date desc', limit=1)
        stock_move.write({'date':  backdate_to_date})
        self.back_date_journal_entry(stock_move, backdate_to_date)
        self.back_date_stock_valuation_layer(stock_move, backdate_to_date)

    def action_process_file(self):
        if not self.file:
            return
        self.action_upload_file()
        self.file_processed = True
        return {
            'type': 'ir.actions.act_window',
            'name': 'Backdate Wizard',
            'view_mode': 'form',
            'res_model': 'stock.backdate.wizard',
            'target': 'new',
            'res_id': self.id,
        }

    def action_back_date(self):
        if self.product_id.tracking == 'lot':
            self.action_back_date_with_lots()
        else:
            if self.has_serial_numbers:
                self.action_back_date_with_serials()
            else:
                self.action_back_date_without_serials()
        self.hide_footer = True
        return {
            'type': 'ir.actions.act_window',
            'name': 'Backdate Wizard',
            'view_mode': 'form',
            'res_model': 'stock.backdate.wizard',
            'target': 'new',
            'res_id': self.id,
        }
