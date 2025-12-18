# Admin Interface Guide

## Accessing the Admin Interface

The Django admin interface is available at:
```
http://localhost:8000/admin/
```
or
```
http://your-domain.com/admin/
```

## Login

1. You need a superuser account to access the admin
2. If you don't have one, create it with:
   ```bash
   python manage.py createsuperuser
   ```
3. Enter your email/username and password when prompted

## Chatbot Admin Features

### 1. Knowledge Documents Management
**Location:** Admin → Chatbot → Knowledge Documents

**Features:**
- View all knowledge documents
- Add/Edit/Delete documents
- Filter by category, university, priority, active status
- Search by title, content, category, tags
- **Bulk Import:** Click "Bulk Import" button to import from CSV/JSON
- **Export:** Select documents and use "Export selected documents to CSV" action
- **Bulk Actions:** Activate/Deactivate multiple documents

**Bulk Import:**
- Access via: Admin → Chatbot → Knowledge Documents → Bulk Import button
- Supports CSV and JSON formats
- Can assign to specific university or leave general

### 2. Conversations Management
**Location:** Admin → Chatbot → Conversations

**Features:**
- View all conversations
- See message count per conversation
- Filter by active status, dates
- Search by user name, email, title

### 3. Messages Management
**Location:** Admin → Chatbot → Messages

**Features:**
- View all messages
- See tokens used and cost per message
- Filter by role, topic, timestamp
- Search by user, content, topic

### 4. Chat History
**Location:** Admin → Chatbot → Chat Histories

**Features:**
- View user personality notes and preferences
- See usage statistics (messages, tokens, cost)
- Edit personalization data

### 5. Site Navigation
**Location:** Admin → Chatbot → Site Navigations

**Features:**
- Manage Caluu+ app navigation entries
- Add routes, descriptions, keywords
- Enable/disable navigation items

### 6. Feedback Management
**Location:** Admin → Chatbot → Feedbacks

**Features:**
- View user feedback and ratings
- See which knowledge documents were used
- Filter by rating, date
- Identify low-rated responses for improvement

### 7. Conversation Analytics
**Location:** Admin → Chatbot → Conversation Analytics

**Features:**
- View query intent distribution
- See performance metrics (response time, API calls, cache hits)
- Track user satisfaction (average ratings)
- Identify knowledge gaps

## API Analytics Dashboard

**Endpoint:** `GET /api/chatbot/analytics/`

**Access:** Requires staff/admin permissions

**Returns:**
- Overview statistics (conversations, messages, feedback, ratings)
- Knowledge base statistics
- Query intent distribution
- Performance metrics
- Low-rated feedback for improvement

## Quick Start: Adding Knowledge Documents

### Method 1: Admin Interface
1. Go to Admin → Chatbot → Knowledge Documents
2. Click "Add Knowledge Document"
3. Fill in:
   - Title
   - Content (detailed information)
   - Category (select appropriate category)
   - Tags (comma-separated)
   - Priority (1-10, higher = more important)
   - University (optional, leave blank for general)
4. Click "Save"

### Method 2: Bulk Import (CSV)
1. Prepare CSV file with columns: `title,content,category,tags,priority`
2. Go to Admin → Chatbot → Knowledge Documents
3. Click "Bulk Import" button
4. Select file type: CSV
5. Choose university (optional)
6. Upload file
7. Click "Import Documents"

### Method 3: Management Command
```bash
python manage.py add_knowledge --sample  # Add sample documents
python manage.py add_knowledge --title "Title" --content "Content" --category "faq"
```

## Best Practices

1. **Priority Setting:**
   - 9-10: Critical regulations and procedures
   - 7-8: Important FAQs and guides
   - 5-6: General information
   - 1-4: Supplementary information

2. **Tags:**
   - Use relevant keywords students might search for
   - Separate multiple tags with commas
   - Include synonyms and related terms

3. **Content:**
   - Be clear and concise
   - For procedures, use numbered steps
   - Include relevant links using [LINK:/app/route] format
   - Keep content up-to-date

4. **University-Specific:**
   - Create general documents for all universities
   - Override with university-specific documents when needed
   - System automatically prioritizes university-specific content

## Troubleshooting

### Can't access admin?
- Make sure you have a superuser account: `python manage.py createsuperuser`
- Check that `django.contrib.admin` is in `INSTALLED_APPS` (it is by default)

### Bulk import not working?
- Check file format matches examples
- Ensure CSV has proper headers
- JSON must be an array of objects
- Check file encoding (should be UTF-8)

### Can't see chatbot models?
- Run migrations: `python manage.py migrate`
- Check that `chatbot` is in `INSTALLED_APPS` in settings.py

















