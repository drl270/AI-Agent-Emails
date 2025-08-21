
import json
import logging
import os
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from bson import ObjectId
from dotenv import load_dotenv

sys.path.append(r"C:\GitHub\Python\AICustomerAgent")
from mongodb_handler import MongoDBHandler

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class MongoDBGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("MongoDB Document Editor")
               
           # Load environment variables
        load_dotenv()
        uri = os.getenv("MONGODB_URI")
        db_name = os.getenv("MONGO_DB_NAME")
        self.collection_name = os.getenv("MONGO_COLLECTION_PROMPTS_NAME")
               
         # Initialize MongoDBHandler
        try:
            self.db_handler = MongoDBHandler(uri, db_name)
        except Exception as e:
            logger.error(f"Failed to initialize MongoDBHandler: {e}")
            messagebox.showerror("Error", f"Failed to connect to MongoDB: {e}")
            return
               
               # GUI Components
        self.mode_var = tk.StringVar(value="set")
               
               # Radio buttons for mode
        ttk.Label(root, text="Operation Mode:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ttk.Radiobutton(root, text="Set All Fields", variable=self.mode_var, value="set").grid(row=0, column=1, padx=5, pady=5)
        ttk.Radiobutton(root, text="New Document", variable=self.mode_var, value="new").grid(row=0, column=2, padx=5, pady=5)
               
               # Text box for document
        ttk.Label(root, text="Edit Document (JSON):").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.text_box = tk.Text(root, height=20, width=60, wrap="word")
        self.text_box.grid(row=2, column=0, columnspan=3, padx=5, pady=5, sticky="nsew")
        self.text_scroll = ttk.Scrollbar(root, orient="vertical", command=self.text_box.yview)
        self.text_scroll.grid(row=2, column=3, sticky="ns")
        self.text_box.config(yscrollcommand=self.text_scroll.set)
               
               # Buttons
        ttk.Button(root, text="Read All Documents", command=self.read_documents).grid(row=3, column=0, padx=5, pady=5)
        ttk.Button(root, text="Apply Changes", command=self.apply_changes).grid(row=3, column=1, padx=5, pady=5)
        ttk.Button(root, text="Delete Document", command=self.delete_document).grid(row=3, column=2, padx=5, pady=5)
               
               # Configure grid resizing
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=1)
        root.columnconfigure(2, weight=1)
        root.rowconfigure(2, weight=1)

    def read_documents(self):
        try:
            documents = self.db_handler.find_documents(self.collection_name)
            if not documents:
                logger.info(f"No documents found in {self.collection_name}")
                print(f"No documents found in {self.collection_name}")
                return
            for doc in documents:
                print(json.dumps(doc, indent=2, default=str))
        except Exception as e:
            logger.error(f"Error reading documents: {e}")
            messagebox.showerror("Error", f"Error reading documents: {e}")

    def apply_changes(self):
        try:
            # Get JSON from text box
            doc_str = self.text_box.get("1.0", tk.END).strip()
            if not doc_str:
                messagebox.showwarning("Warning", "Text box is empty")
                return
            document = json.loads(doc_str)
               
            mode = self.mode_var.get()
            if mode == "set":
                # Update existing document
                if "_id" not in document:
                    messagebox.showerror("Error", "Document must include '_id' for update")
                    return
                self.db_handler.update_document(
                    self.collection_name,
                    {"_id": ObjectId(document["_id"])},
                    {"$set": document}
                )
                messagebox.showinfo("Success", "Document updated successfully")
            else:
                # Insert new document
                self.db_handler.insert_document(self.collection_name, document)
                messagebox.showinfo("Success", "New document inserted successfully")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            messagebox.showerror("Error", f"Invalid JSON: {e}")
        except Exception as e:
            logger.error(f"Error applying changes: {e}")
            messagebox.showerror("Error", f"Error applying changes: {e}")

    def delete_document(self):
        try:
            # Get JSON from text box
            doc_str = self.text_box.get("1.0", tk.END).strip()
            if not doc_str:
                messagebox.showwarning("Warning", "Text box is empty")
                return
            document = json.loads(doc_str)
                  
            if "_id" not in document:
                messagebox.showerror("Error", "Document must include '_id' to delete")
                return
            result = self.db_handler.delete_document(self.collection_name, {"_id": ObjectId(document["_id"])})
            if result > 0:
                messagebox.showinfo("Success", f"Document with _id {document['_id']} deleted successfully")
            else:
                messagebox.showwarning("Warning", f"No document found with _id {document['_id']}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            messagebox.showerror("Error", f"Invalid JSON: {e}")
        except Exception as e:
            logger.error(f"Error deleting document: {e}")
            messagebox.showerror("Error", f"Error deleting document: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = MongoDBGUI(root)
    root.mainloop()
