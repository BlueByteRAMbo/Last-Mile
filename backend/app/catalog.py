"""The product catalog — shared by order generation (simulator), inventory seeding (seed_data),
and the /catalog + /catalog/availability endpoints (main)."""

CATALOG = [
    {"sku": "SKU-MILK", "name": "Milk 1L", "category": "Dairy", "price": 60, "emoji": "🥛", "weight_kg": 0.5},
    {"sku": "SKU-CURD", "name": "Curd 400g", "category": "Dairy", "price": 35, "emoji": "🍶", "weight_kg": 0.4},
    {"sku": "SKU-PANEER", "name": "Paneer 200g", "category": "Dairy", "price": 90, "emoji": "🧀", "weight_kg": 0.2},
    {"sku": "SKU-EGGS", "name": "Eggs (12)", "category": "Dairy", "price": 84, "emoji": "🥚", "weight_kg": 0.6},
    {"sku": "SKU-BREAD", "name": "Bread Loaf", "category": "Bakery", "price": 45, "emoji": "🍞", "weight_kg": 0.3},
    {"sku": "SKU-BUNS", "name": "Burger Buns (4)", "category": "Bakery", "price": 40, "emoji": "🥐", "weight_kg": 0.25},
    {"sku": "SKU-BANANA", "name": "Banana (6)", "category": "Produce", "price": 48, "emoji": "🍌", "weight_kg": 0.6},
    {"sku": "SKU-TOMATO", "name": "Tomato 1kg", "category": "Produce", "price": 40, "emoji": "🍅", "weight_kg": 1.0},
    {"sku": "SKU-ONION", "name": "Onion 1kg", "category": "Produce", "price": 35, "emoji": "🧅", "weight_kg": 1.0},
    {"sku": "SKU-POTATO", "name": "Potato 1kg", "category": "Produce", "price": 30, "emoji": "🥔", "weight_kg": 1.0},
    {"sku": "SKU-RICE", "name": "Rice 5kg", "category": "Staples", "price": 450, "emoji": "🍚", "weight_kg": 5.0},
    {"sku": "SKU-ATTA", "name": "Wheat Atta 5kg", "category": "Staples", "price": 250, "emoji": "🌾", "weight_kg": 5.0},
    {"sku": "SKU-DAL", "name": "Toor Dal 1kg", "category": "Staples", "price": 140, "emoji": "🫘", "weight_kg": 1.0},
    {"sku": "SKU-OIL", "name": "Sunflower Oil 1L", "category": "Staples", "price": 150, "emoji": "🫙", "weight_kg": 1.0},
    {"sku": "SKU-SUGAR", "name": "Sugar 1kg", "category": "Staples", "price": 45, "emoji": "🧂", "weight_kg": 1.0},
    {"sku": "SKU-SNACK", "name": "Snack Pack", "category": "Snacks", "price": 20, "emoji": "🍿", "weight_kg": 0.2},
    {"sku": "SKU-CHIPS", "name": "Potato Chips", "category": "Snacks", "price": 30, "emoji": "🍟", "weight_kg": 0.15},
    {"sku": "SKU-CHOCO", "name": "Chocolate Bar", "category": "Snacks", "price": 50, "emoji": "🍫", "weight_kg": 0.1},
    {"sku": "SKU-COLA", "name": "Cola 750ml", "category": "Beverages", "price": 40, "emoji": "🥤", "weight_kg": 0.8},
    {"sku": "SKU-JUICE", "name": "Orange Juice 1L", "category": "Beverages", "price": 110, "emoji": "🧃", "weight_kg": 1.0},
    {"sku": "SKU-SOAP", "name": "Soap Bar", "category": "Personal Care", "price": 35, "emoji": "🧼", "weight_kg": 0.15},
    {"sku": "SKU-SHAMPOO", "name": "Shampoo 200ml", "category": "Personal Care", "price": 180, "emoji": "🧴", "weight_kg": 0.25},
]

CATALOG_BY_SKU = {c["sku"]: c for c in CATALOG}
