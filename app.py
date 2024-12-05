import os
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from docx import Document
import re
from flask_cors import CORS 
# Load environment variables
load_dotenv()

# Set up the Flask app
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "http://localhost:3000"}})

# Get the XAI API key from the environment variables
XAI_API_KEY = os.getenv("XAI_API_KEY")

# Function to extract text from a Word file
def extract_text_from_word(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    doc = Document(file_path)
    text = []
    for para in doc.paragraphs:
        text.append(para.text)
    return '\n'.join(text)

# Function to handle markdown-style links and emails
def handle_links(line):
    link_pattern = re.compile(r'\[(.*?)\]\((.*?)\)')
    line = link_pattern.sub(r'<a href="\2">\1</a>', line)

    url_pattern = re.compile(r'(http[s]?://[^\s]+)')
    line = url_pattern.sub(r'<a href="\1">\1</a>', line)

    email_pattern = re.compile(r'(\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b)')
    line = email_pattern.sub(r'<a href="mailto:\1">\1</a>', line)

    return line

# Function to escape HTML special characters
def escape_html(text):
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#039;"))

# Function to convert markdown-like text to HTML
def get_html(text: str, is_table: bool = False) -> str:
    lines = text.split('\n')
    html_output = """<div style="max-width: 1000px; padding: 15px; margin: 0 auto; height: 100%; display: flex; flex-direction: column; justify-content: center; overflow-x: auto;">"""
    
    # If is_table is True, start the table
    if is_table:
        html_output += "<table style='border-collapse: collapse; width: 100%;'>"
    
    list_open = False
    for line in lines:
        line = line.strip()
        if not line:
            html_output += '<p></p>'
            continue

        if line.startswith("# "):
            html_output += f'<h2>{escape_html(line[2:])}</h2>'
        elif line.startswith("## "):
            html_output += f'<h3>{escape_html(line[3:])}</h3>'
        elif line.startswith("### "):
            html_output += f'<h4>{escape_html(line[4:])}</h4>' 
        elif line.startswith("**") and line.endswith("**"):
            html_output += f'<strong>{escape_html(line[2:-2])}</strong>'
        elif line.startswith("* "):
            if not list_open:
                html_output += '<ul>'
                list_open = True
            html_output += f'<li>{escape_html(line[2:])}</li>'
        else:
            if list_open:
                html_output += '</ul>'
                list_open = False

            line = handle_links(escape_html(line))
            
            if is_table:
                # Convert line into a table row if 'is_table' is True
                html_output += f"<tr><td>{line}</td></tr>"
            else:
                html_output += f'<div style="margin-bottom: 10px;">{line}</div>'

    # Close the table if 'is_table' is True
    if is_table:
        html_output += "</table>"

    html_output += '</div>'
    return html_output

# Function to generate the system prompt
def generate_system_prompt(user_query, relevant_text):
    return f"""
    You are a knowledgeable assistant. Your role is to provide accurate and concise responses based only on the information in the provided documents. 

    User's Question: "{user_query}"

    Relevant Context from Documents:
    {relevant_text}

    Answer the user's question in a professional tone, using no more than 500 words. Do not include any information that is not found in the documents.
    """

# Chat endpoint
@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message')

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    # Check if the user is asking for a table
    is_table_request = "table" in user_message.lower()

    # Extract content from Word files
    try:
        # Relative file paths
        word_file_1 = './AMRUT-Operational-Guidelines.docx'
        word_file_2 = './swachh-bharat-2.docx'

        content_1 = extract_text_from_word(word_file_1)
        content_2 = extract_text_from_word(word_file_2)

        # Combine Word file content
        relevant_text = content_1 + "\n" + content_2
    except FileNotFoundError as fnfe:
        return jsonify({"error": str(fnfe)}), 404
    except Exception as e:
        return jsonify({"error": f"Error extracting text from Word files: {str(e)}"}), 500

    # Generate the system prompt
    system_prompt = generate_system_prompt(user_message, relevant_text)

    # Define the API URL
    api_url = "https://api.x.ai/v1/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {XAI_API_KEY}",
    }

    # Define the payload for the API request
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "model": "grok-beta",
        "stream": False,
        "temperature": 0
    }

    try:
        # Make the POST request to the external API
        response = requests.post(api_url, json=payload, headers=headers)

        # Check if the request was successful
        if response.status_code == 200:
            chatbot_reply = response.json()
            # Convert the response message to HTML, with or without table format
            html_response = get_html(chatbot_reply['choices'][0]['message']['content'], is_table=is_table_request)
            return jsonify({"response": html_response})
        else:
            return jsonify({"error": "Error from API", "details": response.text}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
