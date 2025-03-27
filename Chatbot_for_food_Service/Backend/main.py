from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import db_helper
import generic_helper

app = FastAPI()

inprogress_orders = {}

@app.post("/")
async def handle_request(request: Request):
    try:
        payload = await request.json()   #Reads the JSON request body sent from Dialogflow.

        # ✅ Handle missing or empty outputContexts
        # output_contexts are temporary memory that allows Dialogflow to remember information across multiple user queries.
        output_contexts = payload['queryResult'].get('outputContexts', [])
        if not output_contexts:
            return JSONResponse(content={
                "fulfillmentText": "Session error. Please try again."
            })

        intent = payload['queryResult']['intent']['displayName']
        parameters = payload['queryResult']['parameters']
        session_id = generic_helper.extract_session_id(output_contexts[0]["name"])

        # ✅ Handle unknown intents gracefully
        intent_handler_dict = {
            'order.add - context: ongoing-order': add_to_order,
            'order.remove - context: ongoing order': remove_from_order,
            'order.complete - context: ongoing-order': complete_order,
            'track.order - context: ongoing-tracking': track_order
        }

        handler = intent_handler_dict.get(intent, handle_unknown_intent)
        return handler(parameters, session_id)

    except Exception as e:
        # ✅ Return user-friendly error messages
        return JSONResponse(content={
            "fulfillmentText": f"Error: {str(e)}"
        })

# ✅ Fallback for unknown intents
def handle_unknown_intent(parameters: dict, session_id: str):
    return JSONResponse(content={
        "fulfillmentText": "Sorry, I didn't understand that. Please try again."
    })

def save_to_db(order: dict):
    next_order_id = db_helper.get_next_order_id()

    for food_item, quantity in order.items():
        rcode = db_helper.insert_order_item(
            food_item,
            quantity,
            next_order_id
        )
        if rcode == -1:
            return -1

    db_helper.insert_order_tracking(next_order_id, "in progress")
    return next_order_id

def complete_order(parameters: dict, session_id: str):
    if session_id not in inprogress_orders:
        fulfillment_text = "I'm having trouble finding your order. Sorry! Can you place a new order please?"
    else:
        order = inprogress_orders[session_id]
        order_id = save_to_db(order)
        if order_id == -1:
            fulfillment_text = "Sorry, I couldn't process your order due to a backend error. Please try again."
        else:
            order_total = db_helper.get_total_order_price(order_id)
            fulfillment_text = f"Awesome! We have placed your order. Here is your order ID #{order_id}. Your order total is {order_total}. You can pay at the time of delivery."

        del inprogress_orders[session_id]

    return JSONResponse(content={
        "fulfillmentText": fulfillment_text
    })

def add_to_order(parameters: dict, session_id: str):
    food_items = parameters.get("food-item", [])
    quantities = parameters.get("number", [])

    if len(food_items) != len(quantities):
        fulfillment_text = "Sorry, I didn't understand. Please specify food items and quantities clearly."
    else:
        new_food_dict = dict(zip(food_items, quantities))

        if session_id in inprogress_orders:
            current_food_dict = inprogress_orders[session_id]
            current_food_dict.update(new_food_dict)
        else:
            inprogress_orders[session_id] = new_food_dict

        order_str = generic_helper.get_str_from_food_dict(inprogress_orders[session_id])
        fulfillment_text = f"So far you have: {order_str}. Do you need anything else?"

    return JSONResponse(content={
        "fulfillmentText": fulfillment_text
    })

def remove_from_order(parameters: dict, session_id: str):
    if session_id not in inprogress_orders:
        return JSONResponse(content={
            "fulfillmentText": "I'm having trouble finding your order. Sorry! Can you place a new order please?"
        })

    food_items = parameters.get("food-item", [])
    current_order = inprogress_orders[session_id]

    removed_items = []
    no_such_items = []

    for item in food_items:
        if item not in current_order:
            no_such_items.append(item)
        else:
            removed_items.append(item)
            del current_order[item]

    fulfillment_text = ""
    if removed_items:
        fulfillment_text += f"Removed {', '.join(removed_items)} from your order. "
    if no_such_items:
        fulfillment_text += f"Your current order does not have {', '.join(no_such_items)}. "

    if not current_order:
        fulfillment_text += "Your order is now empty."
    else:
        order_str = generic_helper.get_str_from_food_dict(current_order)
        fulfillment_text += f"Here is what is left in your order: {order_str}"

    return JSONResponse(content={
        "fulfillmentText": fulfillment_text
    })

def track_order(parameters: dict, session_id: str):
    try:
        order_id = int(parameters.get('order_id', 0))
        if not order_id:
            fulfillment_text = "Please provide a valid order ID."
        else:
            order_status = db_helper.get_order_status(order_id)
            if order_status:
                fulfillment_text = f"The order status for order ID {order_id} is: {order_status}"
            else:
                fulfillment_text = f"No order found with order ID {order_id}."
    except (TypeError, ValueError):
        fulfillment_text = "Invalid order ID format."

    return JSONResponse(content={
        "fulfillmentText": fulfillment_text
    })
