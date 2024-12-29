import streamlit as st
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import yagmail
import pandas as pd
from bson import ObjectId
from io import BytesIO
from fpdf import FPDF
import cv2
import json
from pyzbar.pyzbar import decode
import os
import time
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables for Google Gemini API
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel(model_name="gemini-1.5-flash")

# MongoDB connection
uri = "your_mongodb_connection_string"
client = MongoClient(uri, server_api=ServerApi('1'))
db = client.get_database('inventory')
products_collection = db.products

# Function to generate PDF report from inventory data
def generate_pdf(data):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    # Add table headings
    pdf.cell(200, 10, txt="Inventory Data", ln=True, align='C')
    pdf.cell(40, 10, txt="Product Name", border=1)
    pdf.cell(40, 10, txt="Quantity", border=1)
    pdf.cell(40, 10, txt="Price per Unit", border=1)
    pdf.cell(60, 10, txt="Category", border=1)
    pdf.ln(10)

    # Add table data
    for _, row in data.iterrows():
        pdf.cell(40, 10, txt=row['Product Name'], border=1)
        pdf.cell(40, 10, txt=str(row['Quantity']), border=1)
        pdf.cell(40, 10, txt=str(row['Price per Unit']), border=1)
        pdf.cell(60, 10, txt=row['Category'], border=1)
        pdf.ln(10)

    # Save the PDF to a BytesIO buffer
    buffer = BytesIO()
    pdf.output(dest='S').encode('latin1')  # Get PDF as string
    pdf_string = pdf.output(dest='S').encode('latin1')  # Get the PDF as a byte string
    buffer.write(pdf_string)
    buffer.seek(0)
    return buffer

# Email alert setup
def send_stock_alert(product_name, current_stock):
    threshold=10
    try:
        yag = yagmail.SMTP(user='pragyansrivastavaeinstein', password='rdhy mhvp bsfs ovib')
        subject = f"Stock Alert for {product_name}"
        contents = [
            f"Urgent: Stock Alert for {product_name}!\n\n"
            f"Current stock is critically low: {current_stock} units remaining.\n"
            f"The Minimum quantities required is {threshold} units.\n"
            f"Please restock as soon as possible to avoid stockouts."
        ]
        yag.send('pragyansrivastavaofficial616@gmail.com', subject, contents)
        st.success(f"Stock alert sent for {product_name}.")
    except Exception as e:
        st.error(f"Failed to send stock alert: {e}")

# Function to check the stock for all products and send email if the quantity is below threshold
def check_and_send_alerts():
    threshold = 10
    products = list(products_collection.find({}))
    
    for product in products:
        if product["quantity"] < threshold:
            send_stock_alert(product["name"], product["quantity"])

# Helper function to decode QR code
def decode_qr_code(image_path):
    try:
        img = cv2.imread(image_path)
        gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        decoded_objects = decode(gray_img)

        if not decoded_objects:
            return {"error": "No QR code found or unreadable QR code"}

        for obj in decoded_objects:
            data = obj.data.decode('utf-8')
            try:
                product_info = json.loads(data)
                if all(key in product_info for key in ['product_name', 'quantity', 'price']):
                    return {
                        "product_name": product_info["product_name"],
                        "quantity": product_info["quantity"],
                        "price": product_info["price"]
                    }
                else:
                    return {"error": "QR code does not contain the required fields (product_name, quantity, price)"}
            except json.JSONDecodeError:
                return {"error": "QR code does not contain valid JSON"}
    except Exception as e:
        return {"error": f"Failed to process QR code image: {str(e)}"}

# Function to handle user input for the chatbot and get response from Gemini API
def chat_with_gemini(prompt):
    try:
        # Get inventory data
        products = list(products_collection.find({}))
        inventory_info = ""
        for product in products:
            inventory_info += f"Product: {product['name']}, Quantity: {product['quantity']}, Price per unit: {product['price_per_unit']}, Category: {product['category']}\n"

        # Build the enhanced prompt with inventory data
        enhanced_prompt = f"""
        Below is the list of products in the inventory. Use this information to answer the question asked by the user:

        {inventory_info}

        The user has asked: "{prompt}"

        Please provide an answer based on the available inventory.
        """
        
        # Using generate_content to send the input prompt
        response = model.generate_content([enhanced_prompt])
        return response.text
    except Exception as e:
        return f"Error: {str(e)}"


# Function to view inventory
def view_inventory():
    st.title("Inventory Dashboard")
    search_query = st.text_input("Search Products", placeholder="Search by name or category")

    if search_query:
        products = list(products_collection.find({
            "$or": [
                {"name": {"$regex": search_query, "$options": 'i'}},
                {"category": {"$regex": search_query, "$options": 'i'}}
            ]
        }))
    else:
        products = list(products_collection.find({}))

    if products:
        data = []
        for product in products:
            data.append({
                "Product Name": product["name"],
                "Quantity": product["quantity"],
                "Price per Unit": product["price_per_unit"],
                "Category": product["category"],
                "Delete": f"Delete_{product['_id']}"
            })

        df = pd.DataFrame(data)
        st.subheader("Inventory Table")

        for index, row in df.iterrows():
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.write(row["Product Name"])
            with col2:
                st.write(row["Quantity"])
            with col3:
                st.write(row["Price per Unit"])
            with col4:
                st.write(row["Category"])
            with col5:
                if st.button("Delete", key=row["Delete"]):
                    products_collection.delete_one({"_id": ObjectId(row["Delete"].split("_")[1])})
                    st.success(f"Deleted {row['Product Name']}")
                    check_and_send_alerts()  # Check and send alert after deletion
                    

        csv = df.drop(columns=["Delete"]).to_csv(index=False)
        st.download_button("Download CSV", data=csv, file_name="inventory.csv", mime="text/csv")

        pdf_buffer = generate_pdf(df.drop(columns=["Delete"]))
        st.download_button("Download PDF", data=pdf_buffer, file_name="inventory.pdf", mime="application/pdf")
    else:
        st.warning("No products found.")


# Function to add a new product
def add_product():
    st.title("Add New Product")
    with st.form("Add Product Form"):
        name = st.text_input("Product Name", placeholder="Enter product name")
        quantity = st.number_input("Quantity", min_value=1, step=1, value=1)
        price_per_unit = st.number_input("Price per Unit", min_value=0.0, step=0.01, value=0.0)
        category = st.text_input("Category", placeholder="Enter product category")
        submitted = st.form_submit_button("Add Product")

        if submitted:
            if not name or not category:
                st.error("Please fill in all fields.")
                return

            existing_product = products_collection.find_one({"name": name})

            if existing_product:
                updated_quantity = existing_product['quantity'] + quantity
                products_collection.update_one(
                    {"_id": existing_product['_id']},
                    {"$set": {
                        "quantity": updated_quantity,
                        "price_per_unit": price_per_unit,
                        "category": category
                    }}
                )
                # Check stock level after update
                check_and_send_alerts()
            else:
                products_collection.insert_one({
                    "name": name,
                    "quantity": quantity,
                    "price_per_unit": price_per_unit,
                    "category": category
                })
                # Check stock level after insertion
                check_and_send_alerts()
            st.success(f"Product {name} added/updated successfully.")


# Function to scan a QR code
def scan_qr():
    st.title("Scan QR Code")
    uploaded_file = st.file_uploader("Upload a QR Code", type=["png", "jpg", "jpeg"])
    if uploaded_file:
        temp_path = f"temp_{uploaded_file.name}"
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        result = decode_qr_code(temp_path)
        if "error" in result:
            st.error(result["error"])
        else:
            st.success(f"Product Name: {result['product_name']}")
            st.info(f"Quantity: {result['quantity']}")
            st.info(f"Price: {result['price']}")

            # Automatically add/update product in the inventory
            existing_product = products_collection.find_one({"name": result["product_name"]})
            if existing_product:
                updated_quantity = existing_product['quantity'] + result['quantity']
                products_collection.update_one(
                    {"_id": existing_product['_id']},
                    {"$set": {"quantity": updated_quantity, "price_per_unit": result['price']}}
                )
                st.success(f"Updated quantity of {result['product_name']} to {updated_quantity}")
            else:
                products_collection.insert_one({
                    "name": result["product_name"],
                    "quantity": result["quantity"],
                    "price_per_unit": result["price"],
                    "category": "Unknown"
                })
                st.success(f"Added new product {result['product_name']}")
            
            # Check stock level after updating/adding product
            check_and_send_alerts()


# Chatbot interaction
def chat_interface():
    st.title("Chat with the Inventory Assistant")
    user_input = st.text_input("Ask a question or provide a prompt")
    if user_input:
        response = chat_with_gemini(user_input)
        st.write(f"Gemini's Response: {response}")

# Display a welcome message when the page is first loaded
if st.session_state.get("first_load", True):
    st.session_state.first_load = False  # Set this to False to avoid showing the message again on refresh
    welcome_message = st.empty()  # Create an empty placeholder for the message
    welcome_message.title("Welcome to the Inventory Management System!")  # Display the message
    time.sleep(2)  # Wait for 2 seconds
    welcome_message.empty()  # Remove the message

# Streamlit navigation
st.sidebar.title("Navigation")
options = ["View Inventory", "Add Product", "Scan QR Code", "Chat with Assistant"]
choice = st.sidebar.radio("Go to", options)

if choice == "View Inventory":
    view_inventory()
elif choice == "Add Product":
    add_product()
elif choice == "Scan QR Code":
    scan_qr()
elif choice == "Chat with Assistant":
    chat_interface()
