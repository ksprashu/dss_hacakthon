#!/usr/bin/env python3
"""
Texture scanning server for Raspberry Pi 5.

Captures multi-modal texture data including:
- Photos under 5 different lighting conditions
- Piezo-based vibration sensor audio
- Material analysis via Gemini API
"""
import atexit
import base64
import enum
import json
import logging
import os
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Configure logging first (needed for import warnings)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scan")

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    log.warning("requests library not installed. Install with: pip install requests")

import RPi.GPIO as GPIO
import board
import neopixel_spi as neopixel
from fastapi import FastAPI, HTTPException
from grove.display.jhd1802 import JHD1802
from grove.grove_ryb_led_button import GroveLedButton
from libcamera import controls
from picamera2 import Picamera2
from pydantic import BaseModel, Field

# Configure GPIO before other hardware initialization
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Global controller instance (set after initialization)
_controller: Optional['ScanController'] = None

# Logging already configured above

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    # Try multiple paths for .env file
    possible_paths = [
        os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),  # Project root
        os.path.join(os.path.dirname(__file__), ".env"),  # Scripts directory
        ".env",  # Current working directory
    ]
    env_loaded = False
    for env_path in possible_paths:
        if os.path.exists(env_path):
            load_dotenv(env_path)
            log.info("Loaded .env file from %s", env_path)
            env_loaded = True
            break
    if not env_loaded:
        log.warning("No .env file found. Tried: %s", ", ".join(possible_paths))
except ImportError:
    log.warning("python-dotenv not installed. Install with: pip install python-dotenv")

# Optional Gemini API import
try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        log.warning("GEMINI_API_KEY not found in environment. Gemini analysis will be disabled.")
        GEMINI_AVAILABLE = False
except ImportError:
    GEMINI_AVAILABLE = False
    GEMINI_API_KEY = None
    log.warning("google-genai not installed. Install with: pip install google-genai")

# Optional PIL import for image generation
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    log.warning("PIL/Pillow not installed. Image generation will be disabled. Install with: pip install Pillow")


# ============================================================================
# Constants
# ============================================================================

# Button event bitmasks
CLICK = 2
DBLCLICK = 4
LONGPRESS = 8
NOISE = 16

# Hardware configuration
BUZZER_PIN = 22
BUTTON_PIN = 26
NUM_PIXELS = 24
MAX_BRIGHTNESS = 0.2

# Timing constants (seconds)
LED_COLOR_SETTLE_TIME = 0.8  # Time for LED to change colors (0.6-1.0 sec)
PHOTO_CAPTURE_DELAY = 0.8  # Gap between photo captures
POSITION_ITEM_COUNTDOWN = 3  # Seconds to position item
TEXTURE_COUNTDOWN = 5  # Seconds before texture capture starts
TEXTURE_RECORDING_DURATION = 3  # Seconds of audio recording
CAMERA_SETTLE_TIME = 1.0  # Camera initialization settle time
AUTO_FOCUS_DELAY = 0.5  # Auto focus trigger delay
EXPOSURE_SETTLE_TIME = 0.6  # Exposure/AWB settle time

# Audio configuration
AUDIO_DEVICE = "hw:2,0"
AUDIO_RATE = 44100
AUDIO_CHANNELS = 1
AUDIO_FORMAT = "S16_LE"
AUDIO_NORMALIZE_PEAK_DB = -6.0  # dBFS for normalization

# Storage
SCAN_ROOT = "./scans"

# API Configuration
BASE_URL = os.getenv("INGEST_API_BASE_URL", "http://localhost:5000")

# Camera configuration
CAMERA_RESOLUTION = (1920, 1080)

# Lighting schedule: (RGB tuple, filename, display_name, color_temp_K)
LIGHTING_SCHEDULE: List[Tuple[Tuple[int, int, int], str, str, int]] = [
    ((255, 147, 41), "candlelight", "Candlelight/Sunset", 1900),
    ((255, 214, 170), "warm_indoor", "Warm Indoor", 2800),
    ((255, 241, 224), "neutral_white", "Neutral White", 4000),
    ((255, 255, 251), "direct_sunlight", "Direct Sunlight", 5500),
    ((201, 226, 255), "overcast", "Overcast/Shade", 7000),
]

# Filename constants - generated from lighting schedule
def _get_photo_filename(name: str) -> str:
    """Generate photo filename from lighting name."""
    return f"photo_{name}.jpg"

def _get_photo_meta_filename(name: str) -> str:
    """Generate photo metadata filename from lighting name."""
    return f"photo_{name}.meta.json"

# Photo filenames (for backward compatibility and direct access)
PHOTO_CANDLELIGHT = _get_photo_filename("candlelight")
PHOTO_WARM_INDOOR = _get_photo_filename("warm_indoor")
PHOTO_NEUTRAL_WHITE = _get_photo_filename("neutral_white")
PHOTO_DIRECT_SUNLIGHT = _get_photo_filename("direct_sunlight")
PHOTO_OVERCAST = _get_photo_filename("overcast")

# Photo metadata filenames
PHOTO_META_CANDLELIGHT = _get_photo_meta_filename("candlelight")
PHOTO_META_WARM_INDOOR = _get_photo_meta_filename("warm_indoor")
PHOTO_META_NEUTRAL_WHITE = _get_photo_meta_filename("neutral_white")
PHOTO_META_DIRECT_SUNLIGHT = _get_photo_meta_filename("direct_sunlight")
PHOTO_META_OVERCAST = _get_photo_meta_filename("overcast")

# Audio filenames
AUDIO_TEXTURE_RAW = "audio_texture_raw.wav"
AUDIO_TEXTURE_NODC = "audio_texture_nodc.wav"
AUDIO_TEXTURE_NORM = "audio_texture_norm.wav"

# Texture/Data filenames
TEXTURE_SPECTROGRAM = "texture_spectrogram.png"
TEXTURE_SCAN_JSON = "texture_scan.json"
RESULTS_FINAL_JSON = "results_final.json"
GENERATED_PRODUCT_IMAGE = "generated_product.png"

# Metadata filenames
METADATA_LABEL_TXT = "metadata_label.txt"
METADATA_LABEL_JSON = "metadata_label.json"


app = FastAPI(title="Hackathon Capture Service", version="0.1.0")

def get_stat(parsed: Dict[str, Any], key: str) -> Any:
    """
    Safe lookup for SoX stat keys that may contain weird spacing.
    
    Args:
        parsed: Dictionary of parsed SoX statistics
        key: Key to look up
        
    Returns:
        Value from dictionary, or None if not found
    """
    return parsed.get(key) or parsed.get(re.sub(r"\s+", " ", key))


def ensure_dir(path: str) -> None:
    """Create directory if it doesn't exist."""
    os.makedirs(path, exist_ok=True)


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value between min and max."""
    return max(min_val, min(max_val, value))

def run_cmd(cmd: List[str], *, timeout: Optional[int] = None) -> str:
    log.info("CMD start: %s", " ".join(cmd))
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,   # IMPORTANT: don't raise automatically
        )
        out = (p.stdout or "").strip()
        if out:
            log.info("CMD output:\n%s", out)
        if p.returncode != 0:
            raise RuntimeError(f"Command failed rc={p.returncode}: {' '.join(cmd)}")
        log.info("CMD ok: %s", " ".join(cmd))
        return out
    except Exception as e:
        log.exception("CMD exception: %s", e)
        raise


def _fit_16(s: str) -> str:
    s = (s or "")
    return s[:16].ljust(16)


def json_safe(obj):
    """Convert libcamera / numpy / enum-rich structures into JSON-serializable types."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    # libcamera enums are Python Enums
    if isinstance(obj, enum.Enum):
        return obj.name  # or obj.value

    # common tuple/list containers
    if isinstance(obj, (list, tuple)):
        return [json_safe(x) for x in obj]

    # dict-like
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}

    # numpy scalars (if any show up)
    try:
        import numpy as np
        if isinstance(obj, np.generic):
            return obj.item()
    except Exception:
        pass

    # fallback: string representation
    return str(obj)


def record_audio_wav(out_wav: str, duration_s: int = TEXTURE_RECORDING_DURATION) -> None:
    """
    Record audio using arecord.
    
    Args:
        out_wav: Output WAV file path
        duration_s: Recording duration in seconds
    """
    cmd = [
        "arecord",
        "-D", AUDIO_DEVICE,
        "-f", AUDIO_FORMAT,
        "-r", str(AUDIO_RATE),
        "-c", str(AUDIO_CHANNELS),
        "-d", str(duration_s),
        out_wav,
    ]
    log.info("Recording texture audio: %s", " ".join(cmd))
    run_cmd(cmd)


def sox_remove_dc(in_wav: str, out_wav: str) -> str:
    cmd = ["sox", in_wav, out_wav, "gain", "-1", "highpass", "20"]
    return run_cmd(cmd)


def sox_stat(wav_path: str) -> Dict[str, Any]:
    out = run_cmd(["sox", wav_path, "-n", "stat"])
    parsed = {}

    for line in out.splitlines():
        if ":" not in line:
            continue

        key, val = line.split(":", 1)

        # Collapse any crazy whitespace to a single space
        key = re.sub(r"\s+", " ", key.strip())

        # Take the first token of the value (numeric)
        val = val.strip().split()[0]
        try:
            val = float(val)
        except ValueError:
            pass

        parsed[key] = val

    return {"raw": out, "parsed": parsed}


def sox_spectrogram(in_wav: str, out_png: str) -> str:
    return run_cmd(["sox", in_wav, "-n", "spectrogram", "-o", out_png])


def sox_normalize(
    in_wav: str, 
    out_wav: str, 
    peak_db: float = AUDIO_NORMALIZE_PEAK_DB
) -> str:
    """
    Normalize audio so peak is at `peak_db` dBFS (negative value).
    -6 dBFS gives good headroom.
    
    Args:
        in_wav: Input WAV file path
        out_wav: Output WAV file path
        peak_db: Target peak level in dBFS
        
    Returns:
        Command output
    """
    cmd = [
        "sox",
        in_wav,
        out_wav,
        "norm",
        str(peak_db),
    ]
    return run_cmd(cmd)


def init_camera() -> Picamera2:
    """
    Initialize and configure the Raspberry Pi camera.
    
    Returns:
        Configured Picamera2 instance
    """
    cam = Picamera2()

    cfg = cam.create_still_configuration(
        main={"size": CAMERA_RESOLUTION},
        controls={
            "AeEnable": True,
            "AwbEnable": True,
            "AfMode": controls.AfModeEnum.Continuous,
        },
    )
    cam.configure(cfg)
    cam.start()
    time.sleep(CAMERA_SETTLE_TIME)

    log.info("Camera initialized (still, %dx%d)", *CAMERA_RESOLUTION)
    return cam


def capture_locked(
    cam: Picamera2, 
    path: str, 
    settle_s: float = EXPOSURE_SETTLE_TIME
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Capture an image with locked exposure, white balance, and focus.
    
    Args:
        cam: Picamera2 instance
        path: Output file path
        settle_s: Time to wait for exposure/AWB to settle
        
    Returns:
        Tuple of (metadata, lock_controls)
    """
    # Let AE/AWB settle on current lighting
    cam.set_controls({
        "AeEnable": True, 
        "AwbEnable": True, 
        "AfMode": controls.AfModeEnum.Continuous
    })
    time.sleep(settle_s)

    # Trigger AF once (more deterministic than hoping continuous AF is done)
    cam.set_controls({
        "AfMode": controls.AfModeEnum.Auto, 
        "AfTrigger": controls.AfTriggerEnum.Start
    })
    time.sleep(AUTO_FOCUS_DELAY)

    # 3) Read metadata and lock exposure + white balance + focus
    md = cam.capture_metadata()

    lock = {}

    # Lock exposure: use whatever AE decided
    if "ExposureTime" in md:
        lock["ExposureTime"] = md["ExposureTime"]
    if "AnalogueGain" in md:
        lock["AnalogueGain"] = md["AnalogueGain"]
    lock["AeEnable"] = False

    # Lock white balance
    if "ColourGains" in md:
        lock["ColourGains"] = md["ColourGains"]
    lock["AwbEnable"] = False

    # Lock focus (LensPosition exists on AF cameras)
    if "LensPosition" in md:
        lock["LensPosition"] = md["LensPosition"]
    lock["AfMode"] = controls.AfModeEnum.Manual

    cam.set_controls(lock)

    # 4) Capture
    cam.capture_file(path)
    return md, lock


@dataclass
class ScanStatus:
    state: str = "IDLE"
    scan_id: Optional[str] = None
    started_at: Optional[float] = None
    message: str = ""
    progress: float = 0.0


class LabelPayload(BaseModel):
    label: str = Field(..., description="Human label for the scanned cloth/item")
    notes: Optional[str] = None
    tags: Optional[list[str]] = None


def analyze_with_gemini(scan_dir: str, label: str) -> Optional[Dict[str, Any]]:
    """
    Analyze the 5 lighting condition images and texture scan data using Gemini API.
    Returns material properties, characteristics, and usage scenarios as JSON.
    """
    if not GEMINI_AVAILABLE:
        log.error("Gemini API not available - google-genai package not installed")
        return None

    if not GEMINI_API_KEY:
        log.error("GEMINI_API_KEY not configured. Set it in .env file in project root.")
        return None

    try:
        # Load texture data
        texture_json_path = os.path.join(scan_dir, TEXTURE_SCAN_JSON)
        if not os.path.exists(texture_json_path):
            log.error("%s not found at %s", TEXTURE_SCAN_JSON, texture_json_path)
            return None

        with open(texture_json_path, "r", encoding="utf-8") as f:
            texture_data = json.load(f)

        # Load the 5 lighting condition images from lighting schedule
        image_files = [_get_photo_filename(name) for _, name, _, _ in LIGHTING_SCHEDULE]

        image_paths = []
        for img_file in image_files:
            img_path = os.path.join(scan_dir, img_file)
            if os.path.exists(img_path):
                image_paths.append(img_path)
            else:
                log.warning("Image not found: %s", img_path)

        # Also load the texture spectrogram if available
        spectrogram_path = os.path.join(scan_dir, TEXTURE_SPECTROGRAM)
        if os.path.exists(spectrogram_path):
            image_paths.append(spectrogram_path)
            log.info("Including texture spectrogram in analysis")
        else:
            log.warning("Spectrogram not found: %s", spectrogram_path)

        if not image_paths:
            log.error("No images found in scan directory")
            return None

        log.info("Analyzing %d images (5 lighting conditions + spectrogram) with Gemini API...", len(image_paths))

        # Initialize Gemini client with API key
        client = genai.Client(api_key=GEMINI_API_KEY)

        # Prepare comprehensive texture data for the prompt
        audio_data = texture_data.get('audio', {})
        texture_summary = {
            "audio_statistics": {
                "raw": audio_data.get('stats_raw', {}),
                "nodc": audio_data.get('stats_nodc', {}),
                "normalized": audio_data.get('stats_norm', {}),
            },
            "audio_files": {
                "raw_wav": audio_data.get('raw_wav'),
                "nodc_wav": audio_data.get('nodc_wav'),
                "norm_wav": audio_data.get('norm_wav'),
                "spectrogram_png": audio_data.get('spectrogram_png'),
            },
            "scan_metadata": {
                "scan_id": texture_data.get('scan_id'),
                "label": texture_data.get('label'),
            }
        }

        # Prepare the prompt
        prompt = f"""Given these images of a "{label}" captured under different lighting conditions (candlelight, warm indoor, neutral white, direct sunlight, and overcast), along with a texture spectrogram showing the frequency analysis of the piezo surface scan, analyze the material and predict its properties.

Complete texture scan data:
{json.dumps(texture_summary, indent=2)}

The spectrogram image shows the frequency domain analysis of the texture - analyze the patterns, energy distribution, and frequency characteristics to understand the material's surface properties.

Analyze the material and provide a comprehensive JSON response with the following structure:
{{
    "material_type": "string - predicted material (e.g., cotton, wool, synthetic, etc.)",
    "confidence": "string - confidence level (high/medium/low)",
    "texture_properties": {{
        "smoothness": {{
            "value": "number 0-10",
            "description": "short text description"
        }},
        "roughness": {{
            "value": "number 0-10",
            "description": "short text description"
        }},
        "stretchiness": {{
            "value": "number 0-10",
            "description": "short text description"
        }},
        "thickness": {{
            "value": "string (thin/medium/thick)",
            "description": "short text description"
        }}
    }},
    "wearable_properties": {{
        "skin_contact": {{
            "recommended": "boolean",
            "description": "short text - should be worn against skin or not"
        }},
        "breathability": {{
            "value": "number 0-10",
            "description": "short text description"
        }},
        "moisture_wicking": {{
            "value": "number 0-10",
            "description": "short text description"
        }},
        "insulation": {{
            "value": "number 0-10",
            "description": "short text description"
        }}
    }},
    "weather_recommendations": {{
        "cool_weather": {{
            "suitable": "boolean",
            "description": "short text"
        }},
        "warm_weather": {{
            "suitable": "boolean",
            "description": "short text"
        }},
        "indoor": {{
            "suitable": "boolean",
            "description": "short text"
        }}
    }},
    "key_characteristics": [
        "short bullet point 1",
        "short bullet point 2",
        "short bullet point 3"
    ],
    "ideal_usage_scenarios": [
        "short scenario 1",
        "short scenario 2",
        "short scenario 3"
    ],
    "color_analysis": {{
        "true_color": "string - what color appears to be under different lighting",
        "color_consistency": "string - how consistent the color appears across lighting conditions"
    }},
    "tactile_data": {{
        "roughness": "number 0-1 - surface roughness normalized to 0-1 scale",
        "stiffness": "number 0-1 - material stiffness normalized to 0-1 scale"
    }}
}}

Provide ONLY valid JSON, no markdown formatting or additional text."""

        # Prepare content with images and text using types.Part.from_bytes
        contents = []
        
        # Add lighting condition images with descriptions
        lighting_names = ["candlelight", "warm indoor", "neutral white", "direct sunlight", "overcast"]
        num_lighting_images = len(lighting_names)
        
        for i, img_path in enumerate(image_paths):
            # Read image as bytes and create Part
            with open(img_path, "rb") as f:
                img_bytes = f.read()
            
            # Determine MIME type based on file extension
            if img_path.endswith('.png'):
                mime_type = "image/png"
            else:
                mime_type = "image/jpeg"
            
            # Use types.Part.from_bytes for images
            image_part = types.Part.from_bytes(
                data=img_bytes,
                mime_type=mime_type
            )
            contents.append(image_part)
            
            # Add description based on image type
            if i < num_lighting_images:
                contents.append(f"Image {i+1}: {lighting_names[i]} lighting condition")
            elif i == num_lighting_images:
                contents.append("Spectrogram: Frequency domain analysis of texture surface scan from piezo sensor")

        # Add main prompt
        contents.append(prompt)

        # Call Gemini API with timing
        log.info("Calling Gemini API with model gemini-3-flash-preview...")
        start_time = time.time()
        
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=contents,
        )
        
        elapsed_time = time.time() - start_time

        # Parse JSON response
        response_text = response.text.strip()
        
        # Remove markdown code blocks if present
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        try:
            analysis_result = json.loads(response_text)
            log.info("Successfully parsed Gemini analysis result")
            
            # Extract and log key results
            material_type = analysis_result.get("material_type", "unknown")
            confidence = analysis_result.get("confidence", "unknown")
            log.info("Gemini API call completed in %.2f seconds - Material: %s, Confidence: %s", 
                    elapsed_time, material_type, confidence)
            
            return analysis_result
        except json.JSONDecodeError as e:
            log.error("Failed to parse Gemini response as JSON: %s", e)
            log.error("Response text: %s", response_text[:500])
            # Try to extract JSON from the response
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                try:
                    analysis_result = json.loads(json_match.group(0))
                    log.info("Extracted JSON from response")
                    return analysis_result
                except json.JSONDecodeError:
                    pass
            return None

    except Exception as e:
        log.exception("Error in Gemini analysis: %s", e)
        return None


def generate_product_image(
    scan_dir: str, 
    label: str, 
    material_analysis: Dict[str, Any]
) -> Optional[str]:
    """
    Generate a real product representation image using Gemini image generation.
    
    Args:
        scan_dir: Directory containing scan files
        label: User-provided label for the item
        material_analysis: Material analysis results from Gemini
        
    Returns:
        Path to generated image file, or None if generation failed
    """
    if not GEMINI_AVAILABLE or not GEMINI_API_KEY:
        log.error("Gemini API not available for image generation")
        return None

    if not PIL_AVAILABLE:
        log.error("PIL/Pillow not available for image generation")
        return None

    try:
        # Load candlelight photo (best exposure)
        candlelight_path = os.path.join(scan_dir, PHOTO_CANDLELIGHT)
        if not os.path.exists(candlelight_path):
            log.error("Candlelight photo not found: %s", candlelight_path)
            return None

        log.info("Generating product image using candlelight photo...")
        
        # Initialize Gemini client
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # Build prompt using label and material analysis
        material_type = material_analysis.get("material_type", "textile")
        key_characteristics = material_analysis.get("key_characteristics", [])
        characteristics_text = ", ".join(key_characteristics[:3]) if key_characteristics else ""
        
        prompt = f"""Create a professional product photography representation of this {label}. 
        
The item is made of {material_type}. {characteristics_text if characteristics_text else ""}

Generate a clean, high-quality product image that showcases the item in a professional setting, 
with proper lighting and composition suitable for e-commerce or catalog use. 
Maintain the authentic appearance and characteristics of the original item."""

        # Load image using PIL
        image = Image.open(candlelight_path)
        
        # Generate image
        start_time = time.time()
        log.info("Calling Gemini image generation API...")
        
        response = client.models.generate_content(
            model="gemini-3-pro-image-preview",
            contents=[prompt, image],
        )
        
        elapsed_time = time.time() - start_time
        
        # Extract and save generated image
        generated_image_path = os.path.join(scan_dir, GENERATED_PRODUCT_IMAGE)
        image_saved = False
        
        for part in response.parts:
            if part.text is not None:
                log.info("Image generation response text: %s", part.text)
            elif part.inline_data is not None:
                try:
                    generated_image = part.as_image()
                    generated_image.save(generated_image_path)
                    image_saved = True
                    log.info("Generated product image saved to %s (took %.2f seconds)", 
                            GENERATED_PRODUCT_IMAGE, elapsed_time)
                except Exception as e:
                    log.error("Failed to save generated image: %s", e)
        
        if not image_saved:
            log.warning("No image data found in Gemini response")
            return None
        
        return generated_image_path

    except Exception as e:
        log.exception("Error in product image generation: %s", e)
        return None


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
    if not REQUESTS_AVAILABLE:
        log.error("requests library not available for API call")
        return False

    try:
        # Read image as bytes
        if not os.path.exists(image_path):
            log.error("Image file not found: %s", image_path)
            return False

        with open(image_path, "rb") as f:
            image_bytes = f.read()

        log.info("Sending data to hardware API at %s/api/ingest", BASE_URL)

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
            log.info("Successfully sent data to hardware API")
            return True
        else:
            log.error("Hardware API returned error: %d - %s", 
                     response.status_code, response.text)
            return False

    except requests.exceptions.RequestException as e:
        log.error("Error calling hardware API: %s", e)
        return False
    except Exception as e:
        log.exception("Unexpected error in hardware API call: %s", e)
        return False


class Buzzer:
    """Hardware buzzer controller."""
    
    BEEP_DURATION = 0.15
    TRIPLE_BEEP_DURATION = 0.12
    TRIPLE_BEEP_GAP = 0.08
    LONG_BEEP_DURATION = 0.4
    
    def __init__(self, pin: int):
        """Initialize buzzer on specified GPIO pin."""
        self.pin = pin
        GPIO.setup(self.pin, GPIO.OUT)
        GPIO.output(self.pin, GPIO.LOW)
        log.info("Buzzer ready on GPIO%d", pin)

    def beep(self, duration: float = BEEP_DURATION) -> None:
        """Generate a single beep."""
        if GPIO.getmode() is None:
            GPIO.setmode(GPIO.BCM)

        GPIO.output(self.pin, GPIO.HIGH)
        time.sleep(duration)
        GPIO.output(self.pin, GPIO.LOW)

    def triple(self) -> None:
        """Generate three quick beeps."""
        for _ in range(3):
            self.beep(self.TRIPLE_BEEP_DURATION)
            time.sleep(self.TRIPLE_BEEP_GAP)

    def long(self) -> None:
        """Generate a long beep."""
        self.beep(self.LONG_BEEP_DURATION)


class ScanController:
    def __init__(self):
        self.status = ScanStatus()
        self._lock = threading.Lock()
        self._busy = threading.Event()

        self.buzzer = Buzzer(BUZZER_PIN)

        # LED button
        self.ledbtn = GroveLedButton(BUTTON_PIN)
        self.led_state = {"on": False}
        self.ledbtn.on_event = self._handle_button_event

        # Ring
        self.pixels = neopixel.NeoPixel_SPI(
            board.SPI(),
            NUM_PIXELS,
            pixel_order=neopixel.GRB,
            brightness=0.0,
            auto_write=False,
        )
        self.pixels.fill((0, 0, 0))
        self.pixels.show()

        # Pi Camera
        self.cam = init_camera()

        ensure_dir(SCAN_ROOT)

        # LCD
        self.lcd = JHD1802()
        self.lcd_lock = threading.Lock()

        # optional boot message
        self.lcd_write("Texture scanner", "Ready...")

    def shutdown(self):
        """Clean shutdown of all hardware components."""
        # Stop button event handler first to prevent GPIO access after cleanup
        try:
            if hasattr(self, 'ledbtn') and self.ledbtn is not None:
                # Try to stop the button thread if the library supports it
                if hasattr(self.ledbtn, 'stop') or hasattr(self.ledbtn, 'close'):
                    try:
                        if hasattr(self.ledbtn, 'stop'):
                            self.ledbtn.stop()
                        elif hasattr(self.ledbtn, 'close'):
                            self.ledbtn.close()
                    except Exception as e:
                        log.debug("Button cleanup: %s", e)
                # Clear event handler to prevent new events
                self.ledbtn.on_event = None
        except Exception as e:
            log.debug("Button shutdown: %s", e)
        
        # Small delay to let button thread finish current operation
        time.sleep(0.1)
        
        # Stop camera cleanly
        try:
            if self.cam is not None:
                log.info("Stopping camera...")
                self.cam.stop()
        except Exception as e:
            log.warning("Camera stop failed: %s", e)

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return asdict(self.status)

    def lcd_write(self, line1: str, line2: str = "") -> None:
        try:
            l1, l2 = _fit_16(line1), _fit_16(line2)
            with self.lcd_lock:
                self.lcd.setCursor(0, 0)
                self.lcd.write(l1)
                self.lcd.setCursor(1, 0)
                self.lcd.write(l2)
        except Exception as e:
            log.warning("LCD write failed: %s", e)


    def lcd_step(self, step: str, detail: str = "") -> None:
        """Convenience wrapper for step/status display."""
        # Keep step short; detail can be label/color/timer/etc.
        self.lcd_write(step, detail)

    def start_scan(self) -> str:
        with self._lock:
            if self._busy.is_set():
                raise RuntimeError("Scan already in progress")
            scan_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
            self.status = ScanStatus(
                state="ARMING",
                scan_id=scan_id,
                started_at=time.time(),
                message="Arming scan...",
                progress=0.05,
            )
            self._busy.set()

        t = threading.Thread(target=self._run_scan, args=(scan_id,), daemon=True)
        t.start()
        return scan_id

    def label_scan(self, scan_id: str, payload: LabelPayload) -> None:
        scan_dir = os.path.join(SCAN_ROOT, scan_id)
        if not os.path.isdir(scan_dir):
            raise FileNotFoundError("Unknown scan_id")
        with open(os.path.join(scan_dir, METADATA_LABEL_JSON), "w", encoding="utf-8") as f:
            json.dump(payload.model_dump(), f, indent=2)

    def _set_button_led(self, on: bool) -> None:
        """Set button LED state."""
        try:
            self.ledbtn.led.light(on)
            self.led_state["on"] = on
        except Exception as e:
            log.warning("LED set error: %s", e)

    def _handle_button_event(self, index, code, t):
        if GPIO.getmode() is None:
            GPIO.setmode(GPIO.BCM)

        if code == NOISE:
            return
        if code & CLICK:
            try:
                self.start_scan()
            except RuntimeError:
                pass
        elif code & LONGPRESS:
            self._set_button_led(False)

    def _ring_off(self):
        self.pixels.brightness = 0.0
        self.pixels.fill((0, 0, 0))
        self.pixels.show()

    def _ring_set(self, rgb: Tuple[int, int, int], brightness: float = MAX_BRIGHTNESS) -> None:
        """Set ring light color and brightness."""
        self.pixels.brightness = clamp(brightness, 0.0, MAX_BRIGHTNESS)
        self.pixels.fill(rgb)
        self.pixels.show()

    def _update_status(self, state: str, message: str, progress: float) -> None:
        """Update scan status."""
        with self._lock:
            self.status.state = state
            self.status.message = message
            self.status.progress = progress

    def _prompt_for_label(self, scan_id: str, scan_dir: str) -> str:
        """Prompt user for item label and save it."""
        self._update_status("LABEL", "Waiting for terminal label...", 0.05)
        self.lcd_step("Enter label", "in terminal...")
        
        log.info("Prompting for label in terminal...")
        label = input(f"[{scan_id}] Enter item label: ").strip()
        if not label:
            label = "unlabeled"
        log.info("Label = %r", label)
        self.lcd_step("Label set", label[:16])

        # Save label immediately
        label_path = os.path.join(scan_dir, METADATA_LABEL_TXT)
        with open(label_path, "w", encoding="utf-8") as f:
            f.write(f"{label}\n")
        
        return label

    def _wait_for_positioning(self) -> None:
        """Wait for user to position item."""
        self._update_status("POSITION", "Position item (3s)...", 0.10)
        log.info("Waiting %d seconds for user to position item...", POSITION_ITEM_COUNTDOWN)
        for i in range(POSITION_ITEM_COUNTDOWN, 0, -1):
            self.lcd_step("Position item", f"starting in {i}")
            time.sleep(1.0)

    def _capture_photos(self, scan_dir: str) -> Dict[str, str]:
        """Capture photos under different lighting conditions."""
        self._update_status("IMAGES", "Capturing images under 5 lights...", 0.25)
        self.buzzer.triple()
        
        # Freeze exposure after initial settle
        self.cam.set_controls({"AeEnable": False})

        # Build photo metadata map
        photo_meta_map = {
            _get_photo_filename(name): _get_photo_meta_filename(name)
            for _, name, _, _ in LIGHTING_SCHEDULE
        }

        self.lcd_step("Taking photos", "5 lighting conds")
        captured_images = {}
        
        for rgb, name, display_name, temp_k in LIGHTING_SCHEDULE:
            filename = _get_photo_filename(name)
            log.info("Ring -> %s (%s) [%dK]", name, rgb, temp_k)
            
            self._ring_set(rgb, brightness=MAX_BRIGHTNESS)
            time.sleep(LED_COLOR_SETTLE_TIME)

            self.lcd_step("Photo", name)
            img_path = os.path.join(scan_dir, filename)
            md, lock = capture_locked(self.cam, img_path)

            # Save metadata
            try:
                meta_filename = photo_meta_map[filename]
                meta_path = os.path.join(scan_dir, meta_filename)
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(json_safe({"metadata": md, "lock": lock}), f, indent=2)
            except Exception as e:
                log.warning("Failed to write metadata JSON: %s", e)

            captured_images[name] = filename
            time.sleep(PHOTO_CAPTURE_DELAY)

        self.cam.set_controls({"AeEnable": True})
        return captured_images

    def _record_texture_audio(self, scan_dir: str) -> str:
        """Record texture audio using piezo sensor."""
        self.buzzer.triple()
        self._ring_off()
        self.lcd_step("Texture mode", "get ready")

        log.info("Beep: texture starts in %d seconds", TEXTURE_COUNTDOWN)
        self.buzzer.triple()
        for i in range(TEXTURE_COUNTDOWN, 0, -1):
            self.lcd_step("Texture in", f"{i} sec")
            time.sleep(1.0)

        log.info("Beep: START texture audio capture (%ds)", TEXTURE_RECORDING_DURATION)
        self.buzzer.long()

        self._update_status("TEXTURE", f"Recording texture audio ({TEXTURE_RECORDING_DURATION}s)...", 0.70)
        
        audio_raw = os.path.join(scan_dir, AUDIO_TEXTURE_RAW)
        record_audio_wav(audio_raw, TEXTURE_RECORDING_DURATION)
        
        log.info("Beep: texture capture done")
        self.buzzer.long()
        
        return audio_raw

    def _process_audio(self, audio_raw: str, scan_dir: str) -> Tuple[Dict[str, Any], bool]:
        """Process audio: DC removal, normalization, spectrogram."""
        self._update_status("PROCESSING", "Post-processing audio...", 0.85)
        
        audio_nodc = os.path.join(scan_dir, AUDIO_TEXTURE_NODC)
        audio_norm = os.path.join(scan_dir, AUDIO_TEXTURE_NORM)
        spec_png = os.path.join(scan_dir, TEXTURE_SPECTROGRAM)

        # DC removal
        self.lcd_step("Processing", "DC remove")
        sox_dc_log = sox_remove_dc(audio_raw, audio_nodc)

        raw_stats = sox_stat(audio_raw)
        log.info("RAW  RMS=%s MAX=%s MID=%s",
            get_stat(raw_stats["parsed"], "RMS amplitude"),
            get_stat(raw_stats["parsed"], "Maximum amplitude"),
            get_stat(raw_stats["parsed"], "Midline amplitude"))

        nodc_stats = sox_stat(audio_nodc)
        log.info("NODC RMS=%s MAX=%s MID=%s",
            get_stat(nodc_stats["parsed"], "RMS amplitude"),
            get_stat(nodc_stats["parsed"], "Maximum amplitude"),
            get_stat(nodc_stats["parsed"], "Midline amplitude"))

        # Normalization
        self.lcd_step("Processing", "normalize")
        sox_norm_log = sox_normalize(audio_nodc, audio_norm)

        norm_stats = sox_stat(audio_norm)
        log.info("NORM RMS=%s MAX=%s MID=%s",
            get_stat(norm_stats["parsed"], "RMS amplitude"),
            get_stat(norm_stats["parsed"], "Maximum amplitude"),
            get_stat(norm_stats["parsed"], "Midline amplitude"))

        # Spectrogram
        spec_ok = True
        try:
            self.lcd_step("Processing", "spectrogram")
            sox_spectrogram(audio_nodc, spec_png)
        except Exception:
            spec_ok = False
            log.warning("Spectrogram failed (continuing)")

        audio_data = {
            "device": AUDIO_DEVICE,
            "raw_wav": os.path.basename(audio_raw),
            "nodc_wav": os.path.basename(audio_nodc),
            "norm_wav": os.path.basename(audio_norm),
            "spectrogram_png": os.path.basename(spec_png) if spec_ok else None,
            "arecord_log": "",  # arecord doesn't return output
            "sox_dc_log": sox_dc_log,
            "sox_norm_log": sox_norm_log,
            "stats_raw": raw_stats,
            "stats_nodc": nodc_stats,
            "stats_norm": norm_stats,
        }
        
        return audio_data, spec_ok

    def _save_scan_results(
        self, 
        scan_dir: str, 
        scan_id: str, 
        label: str, 
        captured_images: Dict[str, str],
        audio_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Save scan results to texture_scan.json."""
        results = {
            "scan_id": scan_id,
            "label": label,
            "audio": audio_data,
            "images": captured_images,
        }

        texture_json_path = os.path.join(scan_dir, TEXTURE_SCAN_JSON)
        with open(texture_json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        
        return results

    def _run_gemini_analysis(self, scan_dir: str, label: str, results: Dict[str, Any]) -> None:
        """Run Gemini API analysis and save final results."""
        self._update_status("ANALYZING", "Gemini AI analysis...", 0.90)
        self.lcd_step("AI Analysis", "Gemini...")
        log.info("Starting Gemini analysis...")
        
        gemini_analysis = analyze_with_gemini(scan_dir, label)
        
        if gemini_analysis:
            # Only save the Gemini analysis, not the full texture_scan data
            final_results = {
                "scan_id": results["scan_id"],
                "label": label,
                "material_analysis": gemini_analysis,
            }
            
            final_results_path = os.path.join(scan_dir, RESULTS_FINAL_JSON)
            with open(final_results_path, "w", encoding="utf-8") as f:
                json.dump(final_results, f, indent=2)
            
            log.info("Saved %s with Gemini analysis", RESULTS_FINAL_JSON)
            self.lcd_step("Analysis done", "Saved")
            
            # Generate product image after analysis completes
            self._update_status("GENERATING", "Creating product image...", 0.95)
            self.lcd_step("Product image", "Generating...")
            log.info("Starting product image generation...")
            
            generated_image_path = generate_product_image(scan_dir, label, gemini_analysis)
            if generated_image_path:
                # Add generated image reference to final results
                final_results["generated_product_image"] = GENERATED_PRODUCT_IMAGE
                with open(final_results_path, "w", encoding="utf-8") as f:
                    json.dump(final_results, f, indent=2)
                log.info("Product image generation completed")
                self.lcd_step("Image done", "Complete")
                
                # Send to hardware API
                self._update_status("INGESTING", "Sending to API...", 0.98)
                self.lcd_step("API Upload", "Sending...")
                log.info("Sending data to hardware API...")
                
                # Extract tactile_data from material analysis
                tactile_data = gemini_analysis.get("tactile_data", {})
                tactile_payload = {
                    "roughness": tactile_data.get("roughness", 0.0),
                    "stiffness": tactile_data.get("stiffness", 0.0),
                }
                
                if ingest_to_hardware_api(generated_image_path, tactile_payload):
                    log.info("Successfully sent data to hardware API")
                    self.lcd_step("API done", "Complete")
                else:
                    log.warning("Failed to send data to hardware API, continuing")
                    self.lcd_step("API failed", "Continue")
            else:
                log.warning("Product image generation failed, continuing without it")
                self.lcd_step("Image skipped", "Continue")
        else:
            log.warning("Gemini analysis failed, continuing without it")
            self.lcd_step("Analysis skipped", "Continue")

    def _run_scan(self, scan_id: str) -> None:
        """Main scan workflow orchestrator."""
        scan_dir = os.path.join(SCAN_ROOT, scan_id)
        ensure_dir(scan_dir)

        log.info("=== SCAN BEGIN %s ===", scan_id)
        self.lcd_step("Scan started", scan_id[-8:])

        try:
            self._set_button_led(True)
            
            # Step 1: Get label from user
            label = self._prompt_for_label(scan_id, scan_dir)
            
            # Step 2: Wait for positioning
            self._wait_for_positioning()
            
            # Step 3: Capture photos under different lighting
            captured_images = self._capture_photos(scan_dir)
            
            # Step 4: Record texture audio
            audio_raw = self._record_texture_audio(scan_dir)
            
            # Step 5: Process audio
            audio_data, _ = self._process_audio(audio_raw, scan_dir)
            
            # Step 6: Save scan results
            results = self._save_scan_results(scan_dir, scan_id, label, captured_images, audio_data)
            
            # Step 7: Run Gemini analysis
            self._run_gemini_analysis(scan_dir, label, results)

            self._update_status("DONE", "Scan complete", 1.0)
            log.info("=== SCAN DONE %s ===", scan_id)
            self.lcd_step("Done", label[:16])

        except Exception as e:
            self._update_status("ERROR", str(e), 1.0)
            log.exception("=== SCAN ERROR %s ===", scan_id)

        finally:
            self._ring_off()
            self._set_button_led(False)
            self._busy.clear()
            log.info("Cleanup complete; back to IDLE")
            with self._lock:
                last_id = self.status.scan_id
                last_msg = self.status.message
            time.sleep(0.2)
            self.lcd_step("Idle", "Ready")
            with self._lock:
                self.status.state = "IDLE"
                self.status.scan_id = last_id
                self.status.message = last_msg
                self.status.progress = 0.0


controller = ScanController()
_controller = controller

# Register cleanup handler
def _atexit_cleanup():
    """Cleanup GPIO and shutdown controller on exit."""
    try:
        # Shutdown controller first (stops hardware threads)
        if _controller is not None:
            _controller.shutdown()
        
        # Small delay to let threads finish
        time.sleep(0.2)
        
        # Then cleanup GPIO (button thread may still try to access, but that's expected)
        try:
            GPIO.cleanup()
        except Exception as e:
            # Expected: button thread may try to access GPIO after cleanup
            # This is harmless and can be ignored
            log.debug("GPIO cleanup warning (expected): %s", e)
    except Exception as e:
        # Suppress all cleanup errors - they're expected during shutdown
        log.debug("Cleanup error (expected during shutdown): %s", e)

atexit.register(_atexit_cleanup)

@app.get("/scan/status")
def scan_status():
    return controller.get_status()


@app.post("/scan/start")
def scan_start():
    try:
        scan_id = controller.start_scan()
        return {"ok": True, "scan_id": scan_id}
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/scan/{scan_id}/label")
def scan_label(scan_id: str, payload: LabelPayload):
    try:
        controller.label_scan(scan_id, payload)
        return {"ok": True}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="scan_id not found")


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    # Now `python texture_server.py` will actually run the server.
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
