# FILE: src/utils/image_utils.py | PURPOSE: Image file helpers for base64 writes and resizing
import os
import base64
import shutil
from PIL import Image

async def write_base64_image(base64_string: str, output_path: str) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    buffer = base64.b64decode(base64_string)
    with open(output_path, "wb") as f:
        f.write(buffer)
    return output_path

async def resize_image(input_path: str, output_path: str, width: int, height: int) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with Image.open(input_path) as img:
        # Fit image like object-fit: cover
        img_ratio = img.width / img.height
        target_ratio = width / height
        
        if img_ratio > target_ratio:
            # Image is wider
            new_width = int(target_ratio * img.height)
            offset = (img.width - new_width) / 2
            crop_box = (offset, 0, img.width - offset, img.height)
        else:
            # Image is taller
            new_height = int(img.width / target_ratio)
            offset = (img.height - new_height) / 2
            crop_box = (0, offset, img.width, img.height - offset)
            
        img = img.crop(crop_box)
        img = img.resize((width, height), Image.Resampling.LANCZOS)
        
        if img.mode != 'RGB':
            img = img.convert('RGB')
            
        img.save(output_path, "JPEG", quality=90)
        
    return output_path

async def copy_fallback_image(fallback_path: str, output_path: str) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    shutil.copy2(fallback_path, output_path)
    return output_path
