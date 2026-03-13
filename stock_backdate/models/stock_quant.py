from odoo import _, api, models
# from odoo.exceptions import ValidationError
# from odoo.tools import config, float_compare
import logging
_logger = logging.getLogger(__name__)




class StockQuant(models.Model):
    _inherit = "stock.quant"
    
    @api.model
    def check_and_correct_lot_ids(self,pdt_id):
        # Get all stock.quant records for this specified product
        quants = self.env['stock.quant'].sudo().search([('product_id', '=', pdt_id)])
        for quant in quants:
            quant_product = quant.product_id
            quant_lot = quant.lot_id
            # Check if there is a mismatch between the product on quant and lot
            if quant_lot and quant_lot.product_id != quant_product.id:
                # Find the correct lot
                correct_lot = self.env['stock.lot'].search([
                    ('product_id', '=', quant_product.id),
                    ('name', '=', quant_lot.name)
                ], limit=1)

                if correct_lot:
                    # Correct the lot_id on stock.quant                    
                    quant.sudo().write({'lot_id': correct_lot.id})
                    _logger.info('\n\nCorrected lot_id on stock.quant %s for product %s', quant.id, quant_product.name)
                    _logger.info('Prev lot_id %s ---- Updated lot_id %s', quant_lot.id, quant.lot_id.id)
                    
                    
                