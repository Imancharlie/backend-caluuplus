import requests
import time
import csv
import json
from datetime import datetime
import random

BASE_URL = "https://udsm.iratiba.atomatiki.tech/api/v1/data/search/"
PAGE_SIZE = 50 
DELAY_SECONDS = 1.0  # Increased delay to be more respectful
MIN_DELAY = 0.8
MAX_DELAY = 2.0

# Comprehensive search terms to cover different academic fields
SEARCH_TERMS = [
    # Single letters
    "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m", 
    "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
    
    # Common degree prefixes
    "bachelor", "master", "phd", "diploma", "certificate", "degree",
    
    # Academic fields
    "science", "arts", "commerce", "engineering", "medicine", "law", 
    "education", "business", "economics", "agriculture", "veterinary",
    "pharmacy", "nursing", "social", "political", "environmental",
    "computer", "information", "technology", "mathematics", "physics",
    "chemistry", "biology", "geography", "history", "literature",
    "psychology", "sociology", "anthropology", "linguistics",
    
    # Specific terms
    "bsc", "ba", "bcom", "beng", "mbbs", "llb", "mba", "msc", "ma",
    "agriculture", "forestry", "fisheries", "wildlife", "marine",
    "mining", "petroleum", "geology", "meteorology", "statistics",
    "accounting", "finance", "marketing", "management", "administration",
    "public", "international", "development", "policy", "governance",
    "journalism", "communication", "media", "mass", "broadcasting",
    "tourism", "hospitality", "hotel", "catering", "culinary",
    "fashion", "design", "architecture", "planning", "urban",
    "music", "dance", "theatre", "drama", "fine", "visual",
    "sports", "physical", "recreation", "leisure", "fitness",
    "food", "nutrition", "dietetics", "home", "economics",
    "textile", "fashion", "clothing", "apparel", "garment"
]

def extract_programmes_to_csv(output_filename=None):
    """
    Extract programmes data from the API using multiple search terms and save to CSV file.
    Removes duplicates and uses respectful rate limiting.
    
    Args:
        output_filename (str, optional): Name of the output CSV file. 
                                       If None, uses timestamp-based name.
    
    Returns:
        tuple: (total_programmes_extracted, output_filename)
    """
    
    all_programmes = []
    programmes_by_id = {}  # Dictionary to track unique programmes by ID
    search_stats = {}
    
    if output_filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"programmes_extraction_{timestamp}.csv"
    
    print("Starting comprehensive programmes data extraction...")
    print(f"Will search through {len(SEARCH_TERMS)} different terms")
    print("-" * 60)
    
    for i, search_term in enumerate(SEARCH_TERMS, 1):
        print(f"\n🔍 Search {i}/{len(SEARCH_TERMS)}: '{search_term}'")
        
        # Search with this term
        term_programmes, term_pages = search_programmes_by_term(search_term)
        
        # Track statistics
        search_stats[search_term] = {
            'programmes_found': len(term_programmes),
            'pages_searched': term_pages
        }
        
        # Add unique programmes (avoid duplicates)
        new_programmes = 0
        for programme in term_programmes:
            # Use a combination of fields to create unique identifier
            programme_id = create_programme_id(programme)
            
            if programme_id not in programmes_by_id:
                programmes_by_id[programme_id] = programme
                all_programmes.append(programme)
                new_programmes += 1
        
        print(f"   📊 Found {len(term_programmes)} programmes, {new_programmes} new")
        print(f"   📈 Total unique programmes so far: {len(all_programmes)}")
        
        # Random delay to be more respectful to the server
        delay = random.uniform(MIN_DELAY, MAX_DELAY)
        print(f"   ⏱️  Waiting {delay:.1f}s before next search...")
        time.sleep(delay)
    
    print("\n" + "="*60)
    print("EXTRACTION COMPLETE")
    print("="*60)
    print(f"Total Unique Programmes Extracted: {len(all_programmes)}")
    
    # Show search statistics
    print("\n📊 Search Statistics:")
    print("-" * 40)
    for term, stats in search_stats.items():
        if stats['programmes_found'] > 0:
            print(f"'{term}': {stats['programmes_found']} programmes ({stats['pages_searched']} pages)")
    
    # Write to CSV
    if all_programmes:
        print(f"\n💾 Writing {len(all_programmes)} programmes to CSV...")
        write_programmes_to_csv(all_programmes, output_filename)
        print(f"\n✅ Programmes data saved to: {output_filename}")
        
        # Verify file was created
        import os
        if os.path.exists(output_filename):
            file_size = os.path.getsize(output_filename)
            print(f"📁 File size: {file_size} bytes")
        else:
            print("❌ ERROR: CSV file was not created!")
    else:
        print("\n⚠️  No programmes data to save.")
    
    return len(all_programmes), output_filename

def search_programmes_by_term(search_term, max_pages=10):
    """
    Search for programmes using a specific search term with pagination.
    
    Args:
        search_term (str): The search term to use
        max_pages (int): Maximum number of pages to search (safety limit)
        
    Returns:
        tuple: (list of programmes, number of pages searched)
    """
    
    programmes = []
    page_number = 1
    pages_searched = 0
    
    while page_number <= max_pages:  # Safety limit to prevent infinite loops
        params = {
            "q": search_term,
            "page": page_number,
            "limit": PAGE_SIZE
        }
        
        print(f"      📄 Page {page_number}...", end=" ")
        
        try:
            response = requests.get(BASE_URL, params=params, timeout=10)  # 10 second timeout
            response.raise_for_status()
            
            data = response.json()
            results = data.get('results', {})
            current_programmes = results.get('programme', [])  # Fixed: 'programme' not 'programmes'
            
            # Check for termination condition
            if not current_programmes:
                print("No more programmes found")
                break
                
            programmes.extend(current_programmes)
            pages_searched += 1
            print(f"Found {len(current_programmes)} programmes")
            page_number += 1
            
            # Small delay between pages for the same search term
            time.sleep(0.3)
            
        except requests.exceptions.HTTPError as errh:
            print(f"   🛑 HTTP Error for '{search_term}': {errh}")
            break
        except requests.exceptions.RequestException as e:
            print(f"   🛑 Connection Error for '{search_term}': {e}")
            break
        except Exception as e:
            print(f"   🛑 Unexpected error for '{search_term}': {e}")
            break
    
    if page_number > max_pages:
        print(f"      ⚠️  Reached maximum page limit ({max_pages}) for '{search_term}'")
    
    return programmes, pages_searched

def create_programme_id(programme):
    """
    Create a unique identifier for a programme to detect duplicates.
    
    Args:
        programme (dict): Programme data
        
    Returns:
        str: Unique identifier
    """
    
    # Use multiple fields to create a unique ID
    id_fields = []
    
    # Try different possible ID fields
    for field in ['id', 'programme_id', 'code', 'name', 'title']:
        if field in programme and programme[field]:
            id_fields.append(str(programme[field]).lower().strip())
    
    # If no ID fields found, use name as fallback
    if not id_fields and 'name' in programme:
        id_fields.append(str(programme['name']).lower().strip())
    
    return '|'.join(id_fields) if id_fields else str(hash(str(programme)))

def write_programmes_to_csv(programmes, filename):
    """
    Write programmes data to CSV file.
    
    Args:
        programmes (list): List of programme dictionaries
        filename (str): Output CSV filename
    """
    
    if not programmes:
        print("No programmes data to write.")
        return
    
    # Get all unique keys from all programmes to create comprehensive headers
    all_keys = set()
    for programme in programmes:
        all_keys.update(programme.keys())
    
    # Sort keys for consistent column order
    fieldnames = sorted(list(all_keys))
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        # Write header
        writer.writeheader()
        
        # Write data rows
        for programme in programmes:
            # Handle nested objects by converting to JSON string
            row = {}
            for key, value in programme.items():
                if isinstance(value, (dict, list)):
                    row[key] = json.dumps(value, ensure_ascii=False)
                else:
                    row[key] = value
            writer.writerow(row)

def preview_programme_structure(sample_size=3):
    """
    Preview the structure of programmes data by fetching a few samples.
    
    Args:
        sample_size (int): Number of programmes to fetch for preview
    """
    
    print("Previewing programme data structure...")
    print("-" * 40)
    
    params = {
        "q": "",
        "page": 1,
        "limit": sample_size
    }
    
    try:
        response = requests.get(BASE_URL, params=params, timeout=10)  # 10 second timeout
        response.raise_for_status()
        
        data = response.json()
        results = data.get('results', {})
        programmes = results.get('programme', [])  # Fixed: 'programme' not 'programmes'
        
        if programmes:
            print(f"Found {len(programmes)} programmes for preview:")
            print("\nSample programme structure:")
            print(json.dumps(programmes[0], indent=2, ensure_ascii=False))
            
            print(f"\nAll available fields in programmes:")
            all_keys = set()
            for programme in programmes:
                all_keys.update(programme.keys())
            for key in sorted(all_keys):
                print(f"  - {key}")
        else:
            print("No programmes found in the response.")
            
    except Exception as e:
        print(f"Error during preview: {e}")

def test_extraction_with_sample_terms():
    """
    Test the extraction with a small sample of search terms to verify it works.
    """
    
    # Use a small sample of search terms for testing
    test_terms = ["a", "b", "science", "bachelor", "engineering"]
    
    print("🧪 Testing extraction with sample terms...")
    print(f"Testing with: {test_terms}")
    print("Note: Limited to 3 pages per search term for faster testing")
    print("-" * 50)
    
    all_programmes = []
    programmes_by_id = {}
    
    for i, search_term in enumerate(test_terms, 1):
        print(f"\n🔍 Test Search {i}/{len(test_terms)}: '{search_term}'")
        
        # Limit to 3 pages for testing
        term_programmes, term_pages = search_programmes_by_term(search_term, max_pages=3)
        
        new_programmes = 0
        for programme in term_programmes:
            programme_id = create_programme_id(programme)
            
            if programme_id not in programmes_by_id:
                programmes_by_id[programme_id] = programme
                all_programmes.append(programme)
                new_programmes += 1
        
        print(f"   📊 Found {len(term_programmes)} programmes, {new_programmes} new")
        print(f"   📈 Total unique programmes so far: {len(all_programmes)}")
        
        # Shorter delay for testing
        time.sleep(0.5)
    
    print(f"\n✅ Test completed! Found {len(all_programmes)} unique programmes")
    
    if all_programmes:
        print("\nSample programme data:")
        print(json.dumps(all_programmes[0], indent=2, ensure_ascii=False))
        
        # Save test results to CSV for verification
        test_filename = "test_programmes.csv"
        print(f"\n💾 Saving test results to: {test_filename}")
        write_programmes_to_csv(all_programmes, test_filename)
        
        # Verify file was created
        import os
        if os.path.exists(test_filename):
            file_size = os.path.getsize(test_filename)
            print(f"📁 Test file created successfully! Size: {file_size} bytes")
        else:
            print("❌ ERROR: Test CSV file was not created!")
    else:
        print("⚠️  No programmes found during test!")
    
    return len(all_programmes)

if __name__ == "__main__":
    print("🚀 Programme Data Extractor")
    print("=" * 50)
    
    # Ask user what they want to do
    print("Choose an option:")
    print("1. Test with sample terms (recommended first)")
    print("2. Preview data structure")
    print("3. Run full extraction")
    print("4. Run full extraction with custom filename")
    
    choice = input("\nEnter your choice (1-4): ").strip()
    
    if choice == "1":
        # Test with sample terms
        test_count = test_extraction_with_sample_terms()
        print(f"\n🎉 Test completed! Found {test_count} unique programmes")
        
    elif choice == "2":
        # Preview data structure
        preview_programme_structure()
        
    elif choice == "3":
        # Full extraction
        print("\n" + "="*60)
        print("Starting full extraction...")
        print("="*60)
        total_programmes, output_file = extract_programmes_to_csv()
        print(f"\n🎉 Extraction completed!")
        print(f"📊 Total programmes extracted: {total_programmes}")
        print(f"💾 Data saved to: {output_file}")
        
    elif choice == "4":
        # Custom filename
        filename = input("Enter custom filename (e.g., my_programmes.csv): ").strip()
        if not filename.endswith('.csv'):
            filename += '.csv'
        
        print("\n" + "="*60)
        print("Starting full extraction...")
        print("="*60)
        total_programmes, output_file = extract_programmes_to_csv(filename)
        print(f"\n🎉 Extraction completed!")
        print(f"📊 Total programmes extracted: {total_programmes}")
        print(f"💾 Data saved to: {output_file}")
        
    else:
        print("Invalid choice. Please run the script again.")
