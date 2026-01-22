import json
import os
from typing import Dict

import requests
from dotenv import load_dotenv

load_dotenv()

# API Configuration
BASE_URL = os.getenv("INGEST_API_BASE_URL", "http://localhost:5000")

def ingest_to_hardware_api(
    image_path: str,
    tactile_data: Dict[str, float]
) -> bool:
    """
    Send generated image and tactile data to hardware API.
    
    Args:
        image_path: Path to the generated product image
        tactile_data: Dictionary with 'roughness' and 'stiffness' (0-1 values)
        
    Returns:
        True if successful, False otherwise
    """

    try:
        # Read image as bytes
        if not os.path.exists(image_path):
            print("Image file not found: %s", image_path)
            return False

        with open(image_path, "rb") as f:
            image_bytes = f.read()

        print("Sending data to hardware API at %s/api/ingest", BASE_URL)

        # Prepare form data
        files = {
            'image': (os.path.basename(image_path), image_bytes, 'image/png')
        }
        
        data = {
            'tactile_json': json.dumps(tactile_data)
        }

        # Make POST request
        response = requests.post(
            f"{BASE_URL}/api/ingest",
            files=files,
            data=data,
            timeout=30
        )

        if response.status_code == 200:
            print("Successfully sent data to hardware API")
            return True
        else:
            print("Hardware API returned error: %d - %s", 
                     response.status_code, response.text)
            return False

    except requests.exceptions.RequestException as e:
        print("Error calling hardware API: %s", e)
        return False
    except Exception as e:
        print("Unexpected error in hardware API call: %s", e)
        return False

if __name__ == "__main__":
    ingest_to_hardware_api("/home/pipipi/code/dss_hacakthon/scans/20260122-200309-f9046b28/generated_product.png", {"roughness": 0.3, "stiffness": 0.15})

