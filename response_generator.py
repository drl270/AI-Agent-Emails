import json
import logging
import os

import openai

from bedrock_api import BedrockAPI
from global_state import (Category, CustomerMessage, Product, State,
                          VerificationResult)

logger = logging.getLogger(__name__)

class ResponseGenerator:
    def __init__(self, prompts, db_handler):
        self.prompts = prompts
        self.db_handler = db_handler
        
    def generate_complaint(self, state: State) -> dict:
        first_name = state.customer_message.first_name
        greeting = f"Dear {first_name}," if first_name else "Dear Customer,"
        customer_message = state.get("customer_message", CustomerMessage())

        response = (
            f"{greeting}\n\n"
            "We are deeply sorry to hear about your concern. Resolving your issue is our highest priority, "
            "and our team is actively looking into it. We will get back to you shortly with a resolution.\n\n"
            "Thank you for your patience,\n"
            "Customer Support"
        )
        
        updated_message = customer_message.model_copy(update={"response": response})
        return {"customer_message": updated_message}
    
    def generate_status(self, state: State) -> dict:
        first_name = state.customer_message.first_name
        greeting = f"Dear {first_name}," if first_name else "Dear Customer,"
        customer_message = state.get("customer_message", CustomerMessage())

        response = (
            f"{greeting}\n\n"
            "Thank you for reaching out regarding your order status. We are working to provide you with the details "
            "as soon as possible and appreciate your patience. Our team is here to support you.\n\n"
            "Best regards,\n"
            "Customer Support"
        )
        
        updated_message = customer_message.model_copy(update={"response": response})
        return {"customer_message": updated_message}

    def generate_unknown(self, state: State) -> dict:
        first_name = state.customer_message.first_name
        greeting = f"Dear {first_name}," if first_name else "Dear Customer,"
        customer_message = state.get("customer_message", CustomerMessage())

        response = (
            f"{greeting}\n\n"
            "Thank you for contacting us. We are reviewing your message and will address your inquiry shortly. "
            "Please bear with us as we ensure we fully understand your needs.\n\n"
            "Kind regards,\n"
            "Customer Support"
        )
        
        updated_message = customer_message.model_copy(update={"response": response})
        return {"customer_message": updated_message}
    
    
    def generate_order(self, state: State) -> dict:
        try:
            customer_message = state.get("customer_message", CustomerMessage())
            system_prompt_doc = self.prompts.get("response_system")
            if not system_prompt_doc or system_prompt_doc.get("role") != "system":
                logger.error("Prompt 'response_system' with role 'system' not found")
                return {"customer_message": customer_message}

            user_prompt_doc = self.prompts.get("order_response")
            if not user_prompt_doc or user_prompt_doc.get("role") != "user":
                logger.error("Prompt 'order_response' with role 'user' not found")
                return {"customer_message": customer_message}

            system_prompt = system_prompt_doc["content"]
            try:
                prompt_json = json.loads(user_prompt_doc["content"])
                actual_prompt = prompt_json["prompt"]
            except (json.JSONDecodeError, KeyError):
                actual_prompt = user_prompt_doc["content"]

            products_purchase_text = ""
            if customer_message.products_purchase:
                products_list = [f"{product.product_name} (quantity: {product.quantity}, price: ${product.price})" for product in customer_message.products_purchase]
                products_purchase_text = ", ".join(products_list)

            products_recommendations_text = ""
            if customer_message.products_recommendations:
                rec_list = [f"{product.product_name}: {product.product_description}, price: ${product.price}" for product in customer_message.products_recommendations]
                products_recommendations_text = ", ".join(rec_list)

            questions_text = ""
            if customer_message.questions:
                questions_text = ", ".join(customer_message.questions)

            user_prompt = actual_prompt.replace(
                "{category}", customer_message.category.value
            ).replace(
                "{first_name}", customer_message.first_name or "none"
            ).replace(
                "{title}", customer_message.title or "none"
            ).replace(
                "{last_name}", customer_message.last_name or "none"
            ).replace(
                "{occasion}", customer_message.occasion or "none"
            ).replace(
                "{products_purchase_list}", products_purchase_text
            ).replace(
                "{products_recommendations_list}", products_recommendations_text
            ).replace(
                "{questions_list}", questions_text
            )

            response = self._call_openai(system_prompt, user_prompt)
            if response:
                updated_message = customer_message.model_copy(update={
                    "response": response,
                    "history": customer_message.history + [response]
                })
                logger.info("Order response successfully generated")
                return {"customer_message": updated_message}
            else:
                logger.error("Invalid or missing response from OpenAI")
                return {"customer_message": customer_message}
                
        except Exception as e:
            logger.error(f"Error in generate_order: {e}")
            return {"customer_message": state.get("customer_message", CustomerMessage())}
    
    def generate_inquiry(self, state: State) -> dict:
        try:
            customer_message = state.get("customer_message", CustomerMessage())
            system_prompt_doc = self.prompts.get("response_system")
            if not system_prompt_doc or system_prompt_doc.get("role") != "system":
                logger.error("Prompt 'response_system' with role 'system' not found")
                return {"customer_message": customer_message}

            user_prompt_doc = self.prompts.get("inquiry_response")
            if not user_prompt_doc or user_prompt_doc.get("role") != "user":
                logger.error("Prompt 'inquiry_response' with role 'user' not found")
                return {"customer_message": customer_message}

            system_prompt = system_prompt_doc["content"]
            try:
                prompt_json = json.loads(user_prompt_doc["content"])
                actual_prompt = prompt_json["prompt"]
            except (json.JSONDecodeError, KeyError):
                actual_prompt = user_prompt_doc["content"]

            products_inquiry_text = ""
            if customer_message.products_inquiry:
                inquiry_list = [f"{product.product_name}: {product.product_description}, price: ${product.price}" for product in customer_message.products_inquiry]
                products_inquiry_text = ", ".join(inquiry_list)

            products_recommendations_text = ""
            if customer_message.products_recommendations:
                rec_list = [f"{product.product_name}: {product.product_description}, price: ${product.price}" for product in customer_message.products_recommendations]
                products_recommendations_text = ", ".join(rec_list)

            questions_text = ""
            if customer_message.questions:
                questions_text = ", ".join(customer_message.questions)

            user_prompt = actual_prompt.replace(
                "{Category.UNKNOWN.value}", customer_message.category.value
            ).replace(
                "{first_name}", customer_message.first_name or "none"
            ).replace(
                "{title}", customer_message.title or "none"
            ).replace(
                "{last_name}", customer_message.last_name or "none"
            ).replace(
                "{occasion}", customer_message.occasion or "none"
            ).replace(
                "{products_inquiry_list}", products_inquiry_text
            ).replace(
                "{products_recommendations_list}", products_recommendations_text
            ).replace(
                "{questions_list}", questions_text
            )

            response = self._call_openai(system_prompt, user_prompt)
            if response:
                updated_message = customer_message.model_copy(update={
                    "response": response,
                    "history": customer_message.history + [response]
                })
                logger.info("Inquiry response successfully generated")
                return {"customer_message": updated_message}
            else:
                logger.error("Invalid or missing response from OpenAI")
                return {"customer_message": customer_message}
                
        except Exception as e:
            logger.error(f"Error in generate_inquiry: {e}")
            return {"customer_message": state.get("customer_message", CustomerMessage())}
    
    def generate_order_inquiry(self, state: State) -> dict:
        try:
            customer_message = state.get("customer_message", CustomerMessage())
            system_prompt_doc = self.prompts.get("response_system")
            if not system_prompt_doc or system_prompt_doc.get("role") != "system":
                logger.error("Prompt 'response_system' with role 'system' not found")
                return {"customer_message": customer_message}

            user_prompt_doc = self.prompts.get("orders_inquiry_response")
            if not user_prompt_doc or user_prompt_doc.get("role") != "user":
                logger.error("Prompt 'orders_inquiry_response' with role 'user' not found")
                return {"customer_message": customer_message}

            system_prompt = system_prompt_doc["content"]
            try:
                prompt_json = json.loads(user_prompt_doc["content"])
                actual_prompt = prompt_json["prompt"]
            except (json.JSONDecodeError, KeyError):
                actual_prompt = user_prompt_doc["content"]
                
            products_purchase_text = ""
            if customer_message.products_purchase:
                purchase_list = [f"{product.product_name}: {product.product_description}, price: ${product.price}" for product in customer_message.products_purchase]
                products_purchase_text = ", ".join(purchase_list)

            products_inquiry_text = ""
            if customer_message.products_inquiry:
                inquiry_list = [f"{product.product_name}: {product.product_description}, price: ${product.price}" for product in customer_message.products_inquiry]
                products_inquiry_text = ", ".join(inquiry_list)

            products_recommendations_text = ""
            if customer_message.products_recommendations:
                rec_list = [f"{product.product_name}: {product.product_description}, price: ${product.price}" for product in customer_message.products_recommendations]
                products_recommendations_text = ", ".join(rec_list)

            questions_text = ""
            if customer_message.questions:
                questions_text = ", ".join(customer_message.questions)

            user_prompt = actual_prompt.replace(
                "{Category.UNKNOWN.value}", customer_message.category.value
            ).replace(
                "{first_name}", customer_message.first_name or "none"
            ).replace(
                "{title}", customer_message.title or "none"
            ).replace(
                "{last_name}", customer_message.last_name or "none"
            ).replace(
                "{occasion}", customer_message.occasion or "none"
            ).replace(
                "{products_purchase_list}", products_purchase_text
            ).replace(
                "{products_inquiry_list}", products_inquiry_text
            ).replace(
                "{products_recommendations_list}", products_recommendations_text
            ).replace(
                "{questions_list}", questions_text
            )

            response = self._call_openai(system_prompt, user_prompt)
            if response:
                updated_message = customer_message.model_copy(update={
                    "response": response,
                    "history": customer_message.history + [response]
                })
                logger.info("Order inquiry response successfully generated")
                return {"customer_message": updated_message}
            else:
                logger.error("Invalid or missing response from OpenAI")
                return {"customer_message": customer_message}
                
        except Exception as e:
            logger.error(f"Error in generate_order_inquiry: {e}")
            return {"customer_message": state.get("customer_message", CustomerMessage())}    

    def _call_openai(self, system_prompt, user_prompt):
        try:
            response = openai.chat.completions.create(
                model=os.getenv('OPEN_AI_CHAT_MODEL'),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=500,
                temperature=0.0,
            )
            # Return plain text, not JSON
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            return None
        
    def call_bedrock(self, system_prompt, user_prompt):
        try:
            response = self.bedrock_api.call_bedrock(
                model_id='amazon.titan-text-express-v1',
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_token_count=128,
                temperature=0.0
            )
            return json.loads(response.choices[0].message.content.strip())
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing OpenAI response: {e}")
            return None
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            return None