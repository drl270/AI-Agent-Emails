import json
import os

import boto3
import requests
from dotenv import load_dotenv


class BedrockAPI:
    def __init__(self, uri=None, db=None, region='us-east-1'):
        load_dotenv()
        self.uri = uri
        self.db_name = db
        self.region = region
        self.client = self._get_client()

    def _get_client(self):
        if self._is_ec2_instance():
            return boto3.client('bedrock-runtime', region_name=self.region)
        else:
            return boto3.client(
                'bedrock-runtime',
                region_name=os.getenv('AWS_REGION', self.region),
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
            )

    def _is_ec2_instance(self):
        try:
            token = requests.put('http://169.254.169.254/latest/api/token', 
                                headers={'X-aws-ec2-metadata-token-ttl-seconds': '21600'}, 
                                timeout=2).text
            response = requests.get('http://169.254.169.254/latest/meta-data/', 
                                   headers={'X-aws-ec2-metadata-token': token}, 
                                   timeout=2)
            return response.status_code == 200
        except:
            return False

    def call_bedrock(self, prompt, model_id='amazon.titan-text-express-v1', max_token_count=128, temperature=0.7):
        body = json.dumps({
            'inputText': prompt,
            'textGenerationConfig': {
                'maxTokenCount': max_token_count,
                'temperature': temperature
            }
        })

        response = self.client.invoke_model(
            modelId=model_id,
            contentType='application/json',
            accept='application/json',
            body=body
        )

        result = json.loads(response['body'].read().decode('utf-8'))
        return result['results'][0]['outputText']

if __name__ == "__main__":
    bedrock_api = BedrockAPI()

    response = bedrock_api.call_bedrock("What is the capital of Paris")
    print(response)