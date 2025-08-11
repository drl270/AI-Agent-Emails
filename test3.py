import json
import os

import boto3
import requests
from dotenv import load_dotenv


def is_ec2_instance():
    """Check if running on an EC2 instance by querying instance metadata."""
    try:
        # Query EC2 instance metadata service (IMDSv2 requires a token)
        token = requests.put('http://169.254.169.254/latest/api/token', 
                            headers={'X-aws-ec2-metadata-token-ttl-seconds': '21600'}, 
                            timeout=2).text
        response = requests.get('http://169.254.169.254/latest/meta-data/', 
                               headers={'X-aws-ec2-metadata-token': token}, 
                               timeout=2)
        return response.status_code == 200
    except (requests.RequestException, ConnectionError):
        return False

# Initialize Bedrock client based on environment
if is_ec2_instance():
    client = boto3.client('bedrock-runtime', region_name='us-east-1')
else:
    load_dotenv()
    client = boto3.client(
        'bedrock-runtime',
        region_name=os.getenv('AWS_REGION'),
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
    )

response = client.invoke_model(
    modelId='amazon.titan-text-express-v1',
    contentType='application/json',
    accept='application/json',
    body=json.dumps({
        'inputText': 'What is the capital of Paris',
        'textGenerationConfig': {
            'maxTokenCount': 128,
            'temperature': 0.7
        }
    })
)

result = json.loads(response['body'].read().decode('utf-8'))
print(result['results'][0]['outputText'])