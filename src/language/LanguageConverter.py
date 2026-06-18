import boto3
from dotenv import load_dotenv
import os

load_dotenv()  # Load environment variables from .env file

# AWS Credentials
AWS_ACCESS_KEY = (os.getenv("AWS_ACCESS_KEY") or "YOUR_ACCESS_KEY")
AWS_SECRET_KEY = (os.getenv("AWS_SECRET_KEY") or "YOUR_SECRET_KEY")
AWS_REGION = (os.getenv("AWS_REGION") or "us-east-1")

# Create Translate Client
translate = boto3.client(
    service_name='translate',
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION
)

def translate_to_english(text):
    try:
        response = translate.translate_text(
            Text=text,
            SourceLanguageCode='auto',
            TargetLanguageCode='en'
        )

        return response['TranslatedText']

    except Exception as e:
        print("Translation Error:", e)
        return None


# # Example Sinhala
# sinhala_text = "කපිල චන්ද්‍රසේන අත්අඩංගුවට ගන්නැයි නියෝග"

# result = translate_to_english(sinhala_text)

# print("Translated:")
# print(result)