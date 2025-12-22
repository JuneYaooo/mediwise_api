import random
import string
from typing import List, Set, Optional


def generate_alphanumeric_code(
    length: int = 8,
    existing_codes: Optional[Set[str]] = None
) -> str:
    """
    Generate a random alphanumeric code consisting of uppercase letters and digits.
    
    Args:
        length: Length of the code to generate
        existing_codes: Set of existing codes to avoid duplicates
        
    Returns:
        A randomly generated code with a mix of uppercase letters and digits
    """
    if length < 6:
        length = 6  # Minimum length for security
    
    # Generate code with at least one letter and one digit
    letters = random.choices(string.ascii_uppercase, k=length//2)
    digits = random.choices(string.digits, k=length - length//2)
    
    # Combine and shuffle
    all_chars = letters + digits
    random.shuffle(all_chars)
    code = ''.join(all_chars)
    
    # If we need to check for duplicates
    if existing_codes and code in existing_codes:
        return generate_alphanumeric_code(length, existing_codes)
    
    return code


def generate_multiple_codes(
    count: int = 1,
    length: int = 8,
    existing_codes: Optional[Set[str]] = None
) -> List[str]:
    """
    Generate multiple unique alphanumeric codes.
    
    Args:
        count: Number of codes to generate
        length: Length of each code
        existing_codes: Set of existing codes to avoid duplicates
        
    Returns:
        List of unique generated codes
    """
    if existing_codes is None:
        existing_codes = set()
    else:
        existing_codes = set(existing_codes)  # Create a copy to avoid modifying the original
    
    generated_codes = []
    
    for _ in range(count):
        code = generate_alphanumeric_code(length, existing_codes)
        generated_codes.append(code)
        existing_codes.add(code)
    
    return generated_codes 