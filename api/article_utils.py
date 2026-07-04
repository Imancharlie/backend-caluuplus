"""
Utility functions for article content validation and sanitization.
Handles block-based article editor content with HTML sanitization.
"""
import json
import re
from typing import List, Dict, Any, Optional
import bleach
from django.core.exceptions import ValidationError


# Maximum content size: 1MB (JSON string)
MAX_CONTENT_SIZE = 1024 * 1024

# Allowed block types
ALLOWED_BLOCK_TYPES = {'paragraph', 'image', 'quote', 'divider'}

# HTML tags and attributes allowed in paragraph/quote blocks
ALLOWED_TAGS = ['strong', 'em', 'b', 'i', 'a', 'ul', 'ol', 'li', 'br', 'p']
ALLOWED_ATTRIBUTES = {
    'a': ['href', 'target', 'rel']
}


def validate_block_structure(block: Dict[str, Any]) -> None:
    """
    Validate that a block has the required structure.
    
    Args:
        block: Dictionary representing a content block
        
    Raises:
        ValidationError: If block structure is invalid
    """
    if not isinstance(block, dict):
        raise ValidationError("Block must be a dictionary")
    
    # Check required fields
    if 'id' not in block:
        raise ValidationError("Block must have an 'id' field")
    
    if 'type' not in block:
        raise ValidationError("Block must have a 'type' field")
    
    if 'data' not in block:
        raise ValidationError("Block must have a 'data' field")
    
    # Validate ID format (should be a non-empty string)
    block_id = block['id']
    if not isinstance(block_id, str):
        raise ValidationError("Block 'id' must be a string")
    
    if not block_id or not block_id.strip():
        raise ValidationError("Block 'id' cannot be empty")
    
    # Accept any string as ID (frontend may use custom formats like "block_123_abc")
    # No need to enforce UUID format - any unique string identifier is acceptable
    
    # Validate block type
    block_type = block['type']
    if block_type not in ALLOWED_BLOCK_TYPES:
        raise ValidationError(
            f"Invalid block type '{block_type}'. Allowed types: {', '.join(ALLOWED_BLOCK_TYPES)}"
        )
    
    # Validate data field
    if not isinstance(block['data'], dict):
        raise ValidationError("Block 'data' must be a dictionary")
    
    # Type-specific validation
    if block_type == 'paragraph':
        if 'html' not in block['data']:
            raise ValidationError("Paragraph block must have 'html' in data")
        if not isinstance(block['data']['html'], str):
            raise ValidationError("Paragraph block 'html' must be a string")
    
    elif block_type == 'image':
        if 'imageName' not in block['data']:
            raise ValidationError("Image block must have 'imageName' in data")
        if not isinstance(block['data']['imageName'], str):
            raise ValidationError("Image block 'imageName' must be a string")
        # Validate imageName format
        # Accept either: "filename.jpg" or "articles/filename.jpg"
        image_name = block['data']['imageName']
        if not image_name or not image_name.strip():
            raise ValidationError("Image block 'imageName' cannot be empty")
        
        # Check if it's a valid filename with image extension
        # Allow both formats: "filename.jpg" or "articles/filename.jpg"
        filename_pattern = r'^[a-zA-Z0-9_\-\.]+\.(jpg|jpeg|png|gif|webp)$'
        path_pattern = r'^articles/[a-zA-Z0-9_\-\.]+\.(jpg|jpeg|png|gif|webp)$'
        
        if not (re.match(filename_pattern, image_name) or re.match(path_pattern, image_name)):
            raise ValidationError(
                f"Invalid imageName format: {image_name}. "
                "Expected format: 'filename.jpg' or 'articles/filename.jpg'"
            )
    
    elif block_type == 'quote':
        if 'html' not in block['data']:
            raise ValidationError("Quote block must have 'html' in data")
        if not isinstance(block['data']['html'], str):
            raise ValidationError("Quote block 'html' must be a string")
    
    elif block_type == 'divider':
        # Divider blocks can have empty data or no specific requirements
        pass


def sanitize_html(html_content: str) -> str:
    """
    Sanitize HTML content using bleach.
    Only allows safe tags and attributes for inline formatting.
    
    Args:
        html_content: Raw HTML string to sanitize
        
    Returns:
        Sanitized HTML string
    """
    if not html_content:
        return ""
    
    # Sanitize HTML: remove dangerous tags and attributes
    cleaned = bleach.clean(
        html_content,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        strip=True  # Remove disallowed tags instead of escaping
    )
    
    # Additional safety: ensure links have safe attributes
    # Add rel="noopener noreferrer" to external links
    cleaned = re.sub(
        r'<a\s+([^>]*href=["\']([^"\']+)["\'][^>]*)>',
        lambda m: f'<a {m.group(1)} rel="noopener noreferrer">' if 'rel=' not in m.group(1) else f'<a {m.group(1)}>',
        cleaned
    )
    
    return cleaned


def validate_and_sanitize_content(content: str) -> str:
    """
    Validate and sanitize article content (JSON string of blocks).
    
    Args:
        content: JSON string representing array of blocks
        
    Returns:
        Validated and sanitized JSON string
        
    Raises:
        ValidationError: If content is invalid
    """
    if not content:
        raise ValidationError("Content cannot be empty")
    
    # Check content size
    if len(content) > MAX_CONTENT_SIZE:
        raise ValidationError(
            f"Content exceeds maximum size of {MAX_CONTENT_SIZE / 1024}KB"
        )
    
    # Parse JSON
    try:
        blocks = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValidationError(f"Invalid JSON format: {str(e)}")
    
    # Validate it's a list
    if not isinstance(blocks, list):
        raise ValidationError("Content must be a JSON array of blocks")
    
    if len(blocks) == 0:
        raise ValidationError("Content must contain at least one block")
    
    # Validate and sanitize each block
    sanitized_blocks = []
    for i, block in enumerate(blocks):
        try:
            validate_block_structure(block)
            
            # Sanitize HTML in paragraph and quote blocks
            block_type = block['type']
            if block_type in ('paragraph', 'quote'):
                if 'html' in block['data']:
                    block['data']['html'] = sanitize_html(block['data']['html'])
            
            sanitized_blocks.append(block)
            
        except ValidationError as e:
            raise ValidationError(f"Block {i}: {str(e)}")
    
    # Return sanitized content as JSON string
    return json.dumps(sanitized_blocks, ensure_ascii=False)


def calculate_read_time(blocks: List[Dict[str, Any]]) -> int:
    """
    Calculate estimated read time in minutes from article blocks.
    Assumes average reading speed of 200 words per minute.
    
    Args:
        blocks: List of content blocks
        
    Returns:
        Estimated read time in minutes (minimum 1 minute)
    """
    total_words = 0
    
    for block in blocks:
        block_type = block.get('type')
        data = block.get('data', {})
        
        if block_type == 'paragraph':
            html = data.get('html', '')
            # Extract text from HTML (rough estimate)
            text = bleach.clean(html, tags=[], strip=True)
            words = len(text.split())
            total_words += words
        
        elif block_type == 'quote':
            html = data.get('html', '')
            text = bleach.clean(html, tags=[], strip=True)
            words = len(text.split())
            total_words += words
        
        elif block_type == 'image':
            # Images add minimal reading time, but count caption
            caption = data.get('caption', '')
            if caption:
                words = len(caption.split())
                total_words += words
        
        # Divider blocks don't add reading time
    
    # Calculate minutes: 200 words per minute
    minutes = max(1, round(total_words / 200))
    return minutes


def extract_text_from_blocks(blocks: List[Dict[str, Any]]) -> str:
    """
    Extract plain text from blocks for excerpt generation or search.
    
    Args:
        blocks: List of content blocks
        
    Returns:
        Plain text string
    """
    text_parts = []
    
    for block in blocks:
        block_type = block.get('type')
        data = block.get('data', {})
        
        if block_type == 'paragraph':
            html = data.get('html', '')
            text = bleach.clean(html, tags=[], strip=True)
            if text:
                text_parts.append(text)
        
        elif block_type == 'quote':
            html = data.get('html', '')
            text = bleach.clean(html, tags=[], strip=True)
            if text:
                text_parts.append(text)
        
        elif block_type == 'image':
            caption = data.get('caption', '')
            if caption:
                text_parts.append(caption)
    
    return ' '.join(text_parts)
