import logging

from global_state import (CustomerMessage, OrderStatus, Product, State,
                          VerificationResult)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class InventoryManager:
    def __init__(self, processed_catalog_df):
        self.processed_catalog_df = processed_catalog_df
        
    def check_inventory(self, state: State) -> dict:
        customer_message = state.get("customer_message", CustomerMessage())
        inquiry_update = []
        for inquiry in customer_message.products_inquiry:
            if inquiry.product_id and inquiry.product_id != "none":
                product = self.processed_catalog_df[self.processed_catalog_df['product_id'] == inquiry.product_id]
                if not product.empty:
                    updated_dict = {"quantity": inquiry.quantity} if inquiry.quantity > 0 else {"quantity": 1}
                    updated_dict["filled"] = min(product.iloc[0]['stock'], updated_dict["quantity"])
                    updated_dict["unfilled"] = updated_dict["quantity"] - updated_dict["filled"]
                    if updated_dict["filled"] > 0 and updated_dict["unfilled"] == 0:
                        updated_dict["order_status"] = OrderStatus.FILLED
                    elif updated_dict["filled"] > 0 and updated_dict["unfilled"] > 0:
                        updated_dict["order_status"] = OrderStatus.PARTIAL
                    else:
                        updated_dict["order_status"] = OrderStatus.NONE
                    inquiry_update.append(inquiry.model_copy(update=updated_dict))
                else:
                    inquiry_update.append(inquiry.model_copy(update={"order_status": OrderStatus.NONE}))
            else:
                # Skip products without a valid product_id
                continue
        
        order_update = []
        for purchase in customer_message.products_purchase:
            if purchase.product_id and purchase.product_id != "none":
                product = self.processed_catalog_df[self.processed_catalog_df['product_id'] == purchase.product_id]
                if not product.empty:
                    updated_dict = {"quantity": purchase.quantity} if purchase.quantity > 0 else {"quantity": 1}
                    updated_dict["filled"] = min(product.iloc[0]['stock'], updated_dict["quantity"])
                    updated_dict["unfilled"] = updated_dict["quantity"] - updated_dict["filled"]
                    if updated_dict["filled"] > 0 and updated_dict["unfilled"] == 0:
                        updated_dict["order_status"] = OrderStatus.FILLED
                        self.processed_catalog_df.loc[product.index[0], 'stock'] = product.iloc[0]['stock'] - updated_dict["filled"]
                    elif updated_dict["filled"] > 0 and updated_dict["unfilled"] > 0:
                        updated_dict["order_status"] = OrderStatus.PARTIAL
                        # Update inventory
                        self.processed_catalog_df.loc[product.index[0], 'stock'] = product.iloc[0]['stock'] - updated_dict["filled"]
                    else:
                        updated_dict["order_status"] = OrderStatus.NONE
                    order_update.append(purchase.model_copy(update=updated_dict))
                else:
                    order_update.append(purchase.model_copy(update={"order_status": OrderStatus.NONE}))
            else:
                # Skip products without a valid product_id
                continue
        
        updated_message = customer_message.model_copy(update={
            "products_inquiry": inquiry_update,
            "products_purchase": order_update
        })
        logger.info("Inventory updated successfully")
        return {"customer_message": updated_message}
                