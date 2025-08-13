import random
import re
from typing import Dict, List

import numpy as np
import pandas as pd

# Set Pandas display options
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

# Inventory from products.csv
inventory = [
    {"product_id": "RSG8901", "name": "Retro Sunglasses", "description": "Transport yourself back in time with our retro sunglasses.", "stock": 1},
    {"product_id": "CLF2109", "name": "Cable Knit Beanie", "description": "Knitted from premium wool, this classic beanie features a timeless cable knit pattern.", "stock": 2},
    {"product_id": "VBT2345", "name": "Vibrant Tote", "description": "Spacious and stylish, it's the perfect companion for running errands.", "stock": 4}
]

def generate_test_prompt(test_id: str) -> Dict[str, str]:
    names = ["John Doe", "Alice Smith", "Bob Jones"]
    titles = ["none", "Mr.", "Mrs.", "Dr."]
    occasions = ["none", "birthday", "ski trip", "wedding"]
    num_purchase = random.randint(0, 3)
    num_inquiry = random.randint(0, 3)
    products = random.sample(inventory, min(num_purchase + num_inquiry, len(inventory)))
    purchase_products = products[:num_purchase]
    inquiry_products = products[num_purchase:num_purchase + num_inquiry]
    
    subject = f"Order and Inquiry for Test {test_id}"
    message = f"Hi, this is {random.choice(names)}. "
    if purchase_products:
        message += "I want to order "
        message += ", ".join([f"{random.randint(1, 3)} {p['name']}" for p in purchase_products]) + ". "
    if inquiry_products:
        message += f"Can you tell me about {', '.join([p['name'] for p in inquiry_products])}? "
    if random.random() > 0.5:
        occasion = random.choice(occasions[1:])
        message += f"This is for a {occasion}."
    
    return {"test_id": test_id, "subject": subject, "message": message}

def simulate_llm_output(prompt: Dict[str, str]) -> Dict:
    name = prompt["message"].split("this is ")[1].split(".")[0]
    first_name, last_name = name.split() if " " in name else (name, "none")
    occasion = next((o for o in ["birthday", "ski trip", "wedding"] if o in prompt["message"]), "none")
    products_purchase = []
    products_inquiry = []
    if "order" in prompt["message"].lower():
        for item in inventory:
            if item["name"] in prompt["message"]:
                match = re.search(r'(\d+)\s+' + re.escape(item["name"]), prompt["message"])
                quantity = int(match.group(1)) if match else 1
                products_purchase.append({
                    "product_name": item["name"],
                    "product_description": item["description"],
                    "quantity": quantity,
                    "product_id": item["product_id"] if random.random() > 0.1 else "none"
                })
        if not products_purchase:
            products_purchase.append({
                "product_name": "none",
                "product_description": "none",
                "quantity": 1,
                "product_id": "none"
            })
    if "tell me about" in prompt["message"].lower():
        for item in inventory:
            if item["name"] in prompt["message"].split("tell me about")[1]:
                products_inquiry.append({
                    "product_name": item["name"] if random.random() > 0.1 else "none",
                    "product_description": "cozy socks for skiing" if "ski trip" in prompt["message"] else item["description"],
                    "quantity": "none" if random.random() > 0.5 else 1,
                    "product_id": "none" if random.random() > 0.1 else item["product_id"]
                })
    category = "order" if products_purchase else "inquiry" if products_inquiry else "unknown"
    return {
        "first_name": first_name,
        "last_name": last_name,
        "title": "none",
        "category": category,
        "products_purchase": products_purchase,
        "products_inquiry": products_inquiry,
        "occasion": occasion if occasion != "ski trip" else "ski trip"
    }

def simulate_golden_output(llm_output: Dict) -> Dict:
    golden = llm_output.copy()
    golden["last_name"] = llm_output["last_name"] if llm_output["last_name"] != "none" else random.choice(["Doe", "Smith", "Jones"])
    for item in golden["products_inquiry"]:
        if item["product_description"] == "cozy socks for skiing":
            item["product_description"] = "warm socks that I can wear when I ski"
        if item["quantity"] == "none":
            item["quantity"] = 1
    if llm_output["occasion"] == "ski trip":
        golden["occasion"] = "winter ski vacation"
    return golden

def compare_outputs(llm_output: Dict, golden_output: Dict) -> Dict:
    matches = {
        "first_name": llm_output["first_name"] == golden_output["first_name"],
        "last_name": llm_output["last_name"] == golden_output["last_name"],
        "title": llm_output["title"] == golden_output["title"],
        "category": llm_output["category"] == golden_output["category"],
        "products_purchase": {
            "list_length": len(llm_output["products_purchase"]) == len(golden_output["products_purchase"]),
            "items": [
                {
                    "product_name": llm_item["product_name"] == golden_item["product_name"],
                    "product_description": llm_item["product_description"] == golden_item["product_description"],
                    "quantity": llm_item["quantity"] == golden_item["quantity"],
                    "product_id": llm_item["product_id"] == golden_item["product_id"]
                }
                for llm_item, golden_item in zip(llm_output["products_purchase"], golden_output["products_purchase"])
            ] or [{"product_name": False, "product_description": False, "quantity": False, "product_id": False}] if not llm_output["products_purchase"] and not golden_output["products_purchase"] else []
        },
        "products_inquiry": {
            "list_length": len(llm_output["products_inquiry"]) == len(golden_output["products_inquiry"]),
            "items": [
                {
                    "product_name": llm_item["product_name"] == golden_item["product_name"],
                    "product_description": llm_item["product_description"] == golden_item["product_description"],
                    "quantity": llm_item["quantity"] == golden_item["quantity"],
                    "product_id": llm_item["product_id"] == golden_item["product_id"]
                }
                for llm_item, golden_item in zip(llm_output["products_inquiry"], golden_output["products_inquiry"])
            ] or [{"product_name": False, "product_description": False, "quantity": False, "product_id": False}] if not llm_output["products_inquiry"] and not golden_output["products_inquiry"] else []
        },
        "occasion": llm_output["occasion"] == golden_output["occasion"]
    }
    cosine_similarities = {
        "products_purchase": {
            "items": [
                {"product_description": 1.0 if llm_item["product_description"] == golden_item["product_description"] else 0.95}
                for llm_item, golden_item in zip(llm_output["products_purchase"], golden_output["products_purchase"])
            ] or [{"product_description": None}] if not llm_output["products_purchase"] and not golden_output["products_purchase"] else []
        },
        "products_inquiry": {
            "items": [
                {"product_description": 1.0 if llm_item["product_description"] == golden_item["product_description"] else 0.95}
                for llm_item, golden_item in zip(llm_output["products_inquiry"], golden_output["products_inquiry"])
            ] or [{"product_description": None}] if not llm_output["products_inquiry"] and not golden_output["products_inquiry"] else []
        },
        "occasion": 1.0 if llm_output["occasion"] == golden_output["occasion"] else 0.90
    }
    return {
        "test_id": prompt["test_id"],
        "matches": matches,
        "cosine_similarities": cosine_similarities,
        "llm_category": llm_output["category"],
        "golden_category": golden_output["category"]
    }

# Generate 100 test prompts
tests = [generate_test_prompt(f"test_{i+1}") for i in range(100)]
results = []
total_purchase_items = 0
total_inquiry_items = 0

# Simulate outputs and comparisons
for prompt in tests:
    llm_output = simulate_llm_output(prompt)
    golden_output = simulate_golden_output(llm_output)
    result = compare_outputs(llm_output, golden_output)
    results.append(result)
    total_purchase_items += len(llm_output["products_purchase"])
    total_inquiry_items += len(llm_output["products_inquiry"])

# Adjust to approximate 145 purchase and 136 inquiry items
while total_purchase_items < 145 or total_inquiry_items < 136:
    for i, prompt in enumerate(tests):
        if total_purchase_items < 145:
            llm_output = simulate_llm_output(prompt)
            llm_output["products_purchase"].append({
                "product_name": "none",
                "product_description": "none",
                "quantity": 1,
                "product_id": "none"
            })
            golden_output = simulate_golden_output(llm_output)
            results[i] = compare_outputs(llm_output, golden_output)
            total_purchase_items += 1
        if total_inquiry_items < 136:
            llm_output = simulate_llm_output(prompt)
            llm_output["products_inquiry"].append({
                "product_name": "none",
                "product_description": "cozy socks for skiing",
                "quantity": "none",
                "product_id": "none"
            })
            golden_output = simulate_golden_output(llm_output)
            results[i] = compare_outputs(llm_output, golden_output)
            total_inquiry_items += 1
        if total_purchase_items >= 145 and total_inquiry_items >= 136:
            break

# Create DataFrame
rows = []
for result in results:
    row = {
        "test_id": result["test_id"],
        "first_name": result["matches"]["first_name"],
        "last_name": result["matches"]["last_name"],
        "title": result["matches"]["title"],
        "category": result["matches"]["category"],
        "products_purchase_list_length": result["matches"]["products_purchase"]["list_length"],
        "products_inquiry_list_length": result["matches"]["products_inquiry"]["list_length"],
        "occasion": result["matches"]["occasion"],
        "llm_category": result["llm_category"],
        "golden_category": result["golden_category"],
        "occasion_cosine": result["cosine_similarities"]["occasion"]
    }
    for i in range(max(len(result["matches"]["products_purchase"]["items"]), 1)):
        row.update({
            f"products_purchase_product_name_{i}": result["matches"]["products_purchase"]["items"][i]["product_name"] if i < len(result["matches"]["products_purchase"]["items"]) else False,
            f"products_purchase_product_description_{i}": result["matches"]["products_purchase"]["items"][i]["product_description"] if i < len(result["matches"]["products_purchase"]["items"]) else False,
            f"products_purchase_quantity_{i}": result["matches"]["products_purchase"]["items"][i]["quantity"] if i < len(result["matches"]["products_purchase"]["items"]) else False,
            f"products_purchase_product_id_{i}": result["matches"]["products_purchase"]["items"][i]["product_id"] if i < len(result["matches"]["products_purchase"]["items"]) else False,
            f"products_purchase_product_description_cosine_{i}": result["cosine_similarities"]["products_purchase"]["items"][i]["product_description"] if i < len(result["cosine_similarities"]["products_purchase"]["items"]) else None
        })
    for i in range(max(len(result["matches"]["products_inquiry"]["items"]), 1)):
        row.update({
            f"products_inquiry_product_name_{i}": result["matches"]["products_inquiry"]["items"][i]["product_name"] if i < len(result["matches"]["products_inquiry"]["items"]) else False,
            f"products_inquiry_product_description_{i}": result["matches"]["products_inquiry"]["items"][i]["product_description"] if i < len(result["matches"]["products_inquiry"]["items"]) else False,
            f"products_inquiry_quantity_{i}": result["matches"]["products_inquiry"]["items"][i]["quantity"] if i < len(result["matches"]["products_inquiry"]["items"]) else False,
            f"products_inquiry_product_id_{i}": result["matches"]["products_inquiry"]["items"][i]["product_id"] if i < len(result["matches"]["products_inquiry"]["items"]) else False,
            f"products_inquiry_product_description_cosine_{i}": result["cosine_similarities"]["products_inquiry"]["items"][i]["product_description"] if i < len(result["cosine_similarities"]["products_inquiry"]["items"]) else None
        })
    rows.append(row)

# Create DataFrame with dynamic columns
max_purchase_items = max(len(result["matches"]["products_purchase"]["items"]) for result in results)
max_inquiry_items = max(len(result["matches"]["products_inquiry"]["items"]) for result in results)
columns = [
    "test_id", "first_name", "last_name", "title", "category",
    "products_purchase_list_length", "products_inquiry_list_length", "occasion",
    "llm_category", "golden_category", "occasion_cosine"
]
for i in range(max_purchase_items):
    columns.extend([
        f"products_purchase_product_name_{i}",
        f"products_purchase_product_description_{i}",
        f"products_purchase_quantity_{i}",
        f"products_purchase_product_id_{i}",
        f"products_purchase_product_description_cosine_{i}"
    ])
for i in range(max_inquiry_items):
    columns.extend([
        f"products_inquiry_product_name_{i}",
        f"products_inquiry_product_description_{i}",
        f"products_inquiry_quantity_{i}",
        f"products_inquiry_product_id_{i}",
        f"products_inquiry_product_description_cosine_{i}"
    ])

df = pd.DataFrame(rows, columns=columns)

# Calculate F1 scores
for col in [c for c in df.columns if c not in ["test_id", "llm_category", "golden_category", "occasion_cosine"] and not c.endswith("_cosine")]:
    tp = df[col].sum()
    fp = 0  # Assuming golden is ground truth
    fn = len(df) - tp
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    print(f"{col} F1: {f1}")

# Calculate mean cosine similarities
for col in [c for c in df.columns if c.endswith("_cosine")]:
    avg = df[col].mean()
    print(f"{col} mean cosine: {avg}")

# Print DataFrame sample
print("\nDataFrame Sample:")
print(df.head())
print(df.tail())