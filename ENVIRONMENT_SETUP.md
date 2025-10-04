# Environment Setup

## Required Environment Variables

Create a `.env` file in the project root with the following variables:

```bash
# API Keys (Required)
ANTHROPIC_API_KEY=your_anthropic_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here

# Pricing Configuration (Optional - defaults provided)
ANTHROPIC_INPUT_USD_PER_TOKEN=0.00000025
ANTHROPIC_OUTPUT_USD_PER_TOKEN=0.00000125
USD_TO_TSH_RATE=2700

# Django Settings
SECRET_KEY=your_secret_key_here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

## Getting API Keys

### Anthropic API Key
1. Go to [Anthropic Console](https://console.anthropic.com/)
2. Sign up or log in
3. Navigate to API Keys section
4. Create a new API key
5. Copy the key and add it to your `.env` file

### Gemini API Key
1. Go to [Google AI Studio](https://aistudio.google.com/)
2. Sign up or log in
3. Create a new API key
4. Copy the key and add it to your `.env` file

## Installation

1. Clone the repository
2. Create a virtual environment
3. Install dependencies: `pip install -r requirements.txt`
4. Create `.env` file with your API keys
5. Run migrations: `python manage.py migrate`
6. Start the server: `python manage.py runserver`

## Security Note

Never commit your `.env` file or hardcode API keys in your code. The `.env` file should be added to `.gitignore`.