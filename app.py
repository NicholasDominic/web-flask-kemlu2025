from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
from bs4 import BeautifulSoup
import os
import base64
import requests

app = Flask(__name__)
api_key = "sk-2mUc_hjicmZro-wudaVKuQ" # will be expired today at 11:59pm.
api_endpoint = "https://dekallm.cloudeka.ai/v1/chat/completions"

# Simple in-memory database
visa_requests = []

# VisaRequest class
class VisaRequest:
    def __init__(self, name, nationality, purpose, date):
        self.name = name
        self.nationality = nationality
        self.purpose = purpose
        self.date = date

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/request-visa', methods=['GET', 'POST'])
def request_visa():
    if request.method == 'POST':
        name = request.form['name']
        nationality = request.form['nationality']
        purpose = request.form['purpose']
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        new_request = VisaRequest(name, nationality, purpose, date)
        visa_requests.append(new_request)
        return redirect(url_for('success', name=name))
    
    return render_template('request_form.html')

@app.route('/success')
def success():
    name = request.args.get('name')
    return render_template('success.html', name=name)

@app.route('/admin/requests')
def admin_view():
    return render_template('admin.html', requests=visa_requests)

# GenAI-based Chatbot
def encode_image(image_path): # function to encode the image in base64 format
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def extract_text_from_url(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Remove script and style tags
        for tag in soup(['script', 'style']):
            tag.decompose()

        # Get visible text
        text = soup.get_text(separator=' ', strip=True)
        return text[:5000]  # limit to avoid exceeding token limits

    except Exception as e:
        return f"Error fetching URL: {str(e)}"
    
def run(user_prompt : str, model_name : str, image_path : str = None, *args, **kwargs) -> str:
    # Set up the headers for the request
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    # Define the payload for the API request
    content = [{"type": "text", "text": user_prompt}]
    if model_name == "qwen/qwen25-vl-7b-instruct":
        base64_image = encode_image(image_path) # encode the image
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}})
    
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": content}]
    }

    # Send the POST request
    response = requests.post(api_endpoint, headers=headers, json=payload)

    # Check if the request was successful and print the response
    if response.status_code == 200:
        result = response.json()
    else:
        return "Error: {}\n{}".format(response.status_code, response.text)

    return result["choices"][0]["message"]["content"]

@app.route('/chatbot', methods=['GET', 'POST'])
def chatbot():
    response = None
    if request.method == 'POST':
        user_prompt = request.form.get('prompt')
        uploaded_file = request.files.get('file')
        url = request.form.get('url')

        # Text
        if user_prompt and not uploaded_file and not url:
            llm_model = "goto/sahabat-ai-v2-70b-it"
            response = run(user_prompt=user_prompt, model_name=llm_model)

        # Image (.jpg)
        elif uploaded_file and uploaded_file.filename.lower().endswith('.jpg'):
            vlm_model = "qwen/qwen25-vl-7b-instruct"
            image_path = os.path.join("temp", uploaded_file.filename)
            uploaded_file.save(image_path)
            response = run(user_prompt=user_prompt or "Describe this image", model_name=vlm_model, image_path=image_path)

        # PDF 
        elif uploaded_file and uploaded_file.filename.lower().endswith('.pdf'):
            llm_model = "goto/sahabat-ai-v2-70b-it"
            pdf_path = os.path.join("temp", secure_filename(uploaded_file.filename))
            uploaded_file.save(pdf_path)

            try:
                reader = PdfReader(pdf_path)
                extracted_text = ""
                for page in reader.pages:
                    extracted_text += page.extract_text() or ""

                if extracted_text.strip():
                    # Send the extracted text to your model
                    if not user_prompt:
                        user_prompt = "Describe this document: "
                    user_prompt += "\n{}".format(extracted_text)
                    response = run(user_prompt=user_prompt, model_name=llm_model)
                else:
                    response = "No readable text found in the PDF."

            except Exception as e:
                response = f"Error reading PDF: {str(e)}"

        # Website (URL)
        elif url and not uploaded_file:
            llm_model = "goto/sahabat-ai-v2-70b-it"
            extracted_text = extract_text_from_url(url)
            
            # Send the extracted text to your model
            if extracted_text:
                if not user_prompt:
                    user_prompt = "Describe this document: "
                user_prompt += "\n{}".format(extracted_text)
                response = run(user_prompt=user_prompt, model_name=llm_model)
            else:
                response = "No readable text found in the URL."
            
            del extracted_text

    return render_template('chatbot.html', response=response)


if __name__ == '__main__':
    app.run(debug=True)
