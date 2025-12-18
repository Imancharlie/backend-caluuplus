"""
Management command to add knowledge documents to the chatbot
"""
from django.core.management.base import BaseCommand
from chatbot.models import KnowledgeDocument
from api.models import University


class Command(BaseCommand):
    help = 'Add knowledge documents to chatbot knowledge base'

    def add_arguments(self, parser):
        parser.add_argument('--title', type=str, help='Document title')
        parser.add_argument('--content', type=str, help='Document content')
        parser.add_argument('--category', type=str, choices=['faq', 'policy', 'guide', 'schedule'], 
                          default='faq', help='Document category')
        parser.add_argument('--university', type=str, help='University name (optional, leave empty for all universities)')
        parser.add_argument('--file', type=str, help='Path to text file with content')
        parser.add_argument('--sample', action='store_true', help='Add sample knowledge documents')

    def handle(self, *args, **options):
        if options['sample']:
            self.add_sample_documents()
            return

        title = options.get('title')
        content = options.get('content')
        category = options.get('category', 'faq')
        university_name = options.get('university')
        file_path = options.get('file')

        if not title:
            self.stdout.write(self.style.ERROR('Title is required'))
            return

        # Get content from file if provided
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error reading file: {e}'))
                return

        if not content:
            self.stdout.write(self.style.ERROR('Content is required (use --content or --file)'))
            return

        # Get university if specified
        university = None
        if university_name:
            try:
                university = University.objects.get(name__icontains=university_name)
            except University.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'University not found: {university_name}'))
                return

        # Create document
        doc = KnowledgeDocument.objects.create(
            title=title,
            content=content,
            category=category,
            university=university
        )

        self.stdout.write(self.style.SUCCESS(f'Successfully created knowledge document: {doc.title}'))
        if university:
            self.stdout.write(self.style.SUCCESS(f'University: {university.name}'))

    def add_sample_documents(self):
        """Add sample knowledge documents for testing"""
        
        sample_docs = [
            {
                'title': 'AutoCAD Essential Shortcuts',
                'category': 'guide',
                'content': '''AutoCAD Shortcuts for Architecture Students:

BASIC COMMANDS:
- L = Line (draw straight lines)
- C = Circle (create circles)
- R = Rectangle (draw rectangles)
- TR = Trim (remove parts of objects)
- EX = Extend (lengthen objects)
- X = Explode (break apart blocks)
- CO = Copy (duplicate objects)
- M = Move (relocate objects)
- RO = Rotate (turn objects)
- SC = Scale (resize objects)

MODIFY COMMANDS:
- F = Fillet (create rounded corners)
- CHA = Chamfer (create beveled edges)
- MI = Mirror (create mirror image)
- AR = Array (create multiple copies)
- O = Offset (create parallel copies)
- S = Stretch (modify object size)

VIEW COMMANDS:
- Z = Zoom (change view scale)
- P = Pan (move view)
- RE = Regen (refresh display)
- V = View (saved views)

LAYERS & PROPERTIES:
- LA = Layer Manager (organize drawing layers)
- MA = Match Properties (copy formatting)
- CH = Properties (modify object properties)

QUICK TIPS:
- Press Spacebar to repeat last command
- Ctrl+Z = Undo
- Ctrl+Y = Redo
- ESC = Cancel current command
- F8 = Ortho mode (draw at 90° angles)
- F3 = Object snap

HOUSE DESIGN WORKFLOW:
1. Start with wall outlines using Line (L) and Offset (O)
2. Add doors and windows using Rectangle (R) and blocks
3. Use Fillet (F) for rounded corners
4. Layer organization is crucial - use LA for different elements
5. Dimension last using aligned and linear dimensions'''
            },
            {
                'title': 'How to Check Your Class Schedule',
                'category': 'faq',
                'content': '''To check your class schedule on Caluu+:

1. Open the Caluu+ app
2. Tap on the Timetable icon in the navigation menu
3. Your weekly schedule will be displayed

You can:
- View today's classes
- See the full week schedule
- Check upcoming classes
- Get notifications before class starts

To add or edit your timetable:
1. Go to Timetable
2. Tap the "+" button
3. Fill in course details (name, code, time, venue)
4. Save

Pro tip: Ask Mr. Caluu "What's my schedule today?" or "What's my next class?" for quick answers!'''
            },
            {
                'title': 'Academic Integrity Policy',
                'category': 'policy',
                'content': '''Academic Integrity Guidelines:

DEFINITION:
Academic integrity means honest and responsible scholarship. Students must submit their own work and properly cite sources.

PROHIBITED BEHAVIORS:
- Plagiarism: Using someone else's work without credit
- Cheating: Using unauthorized materials during exams
- Fabrication: Making up data or sources
- Collusion: Unauthorized collaboration on assignments

CONSEQUENCES:
First Offense: Warning and grade reduction
Second Offense: Failing grade for the course
Third Offense: Academic suspension

PROPER CITATION:
Always cite sources using the required format (APA, MLA, etc.)

COLLABORATION GUIDELINES:
- Study groups are encouraged
- Discuss concepts, not answers
- Write your own solutions
- When in doubt, ask your instructor

EXAM CONDUCT:
- No phones or electronic devices
- Keep eyes on your own paper
- Raise hand for questions
- Submit work on time

Remember: Academic honesty builds credibility and real knowledge!'''
            },
            {
                'title': 'How to Submit Assignments',
                'category': 'faq',
                'content': '''Assignment Submission Guide:

ONLINE SUBMISSION:
1. Check assignment deadline in course portal
2. Prepare your document (PDF preferred)
3. Name file: StudentID_CourseName_Assignment#
4. Upload to course management system
5. Verify submission was successful

LATE SUBMISSIONS:
- 1 day late: 10% penalty
- 2 days late: 20% penalty
- 3+ days late: Not accepted (special circumstances only)

FILE FORMATS ACCEPTED:
- PDF (preferred)
- DOCX (Microsoft Word)
- ZIP (for multiple files)

FILE SIZE LIMIT: 25MB

TIPS FOR SUCCESS:
- Submit early to avoid last-minute issues
- Keep a backup copy
- Include your name and ID on every page
- Follow formatting guidelines
- Check rubric before submitting

TECHNICAL ISSUES:
If you experience technical problems:
1. Screenshot the error
2. Email instructor immediately
3. Save timestamped proof of attempt'''
            },
            {
                'title': 'Study Tips for Exam Success',
                'category': 'guide',
                'content': '''Effective Study Strategies:

TIME MANAGEMENT:
- Start studying 2-3 weeks before exams
- Create a study schedule
- Use 25-minute study blocks (Pomodoro)
- Take 5-minute breaks
- Review notes within 24 hours of class

ACTIVE LEARNING:
- Don't just re-read - actively engage
- Create summaries in your own words
- Teach concepts to others
- Make flashcards for key terms
- Practice problems and past papers

STUDY ENVIRONMENT:
- Find a quiet space
- Remove distractions (phone, social media)
- Use good lighting
- Keep study materials organized
- Stay hydrated

GROUP STUDY:
- Quiz each other
- Discuss difficult concepts
- Share notes and resources
- Explain topics to peers
- Stay focused on subject matter

EXAM PREPARATION:
- Review syllabus and course outcomes
- Practice with past exams
- Understand question formats
- Prepare materials allowed in exam
- Get good sleep before exam

DURING EXAM:
- Read instructions carefully
- Budget time for each section
- Answer easy questions first
- Show your work
- Review answers before submitting

AFTER EXAM:
- Reflect on what worked
- Note areas for improvement
- Celebrate your effort!'''
            },
            {
                'title': 'University Registration Process',
                'category': 'guide',
                'content': '''Student Registration Guide:

NEW STUDENTS:
1. Receive admission letter
2. Pay registration fees
3. Submit required documents:
   - Birth certificate
   - Academic transcripts
   - Passport photos (2)
   - ID copy
4. Get student ID card
5. Register for courses

RETURNING STUDENTS:
1. Check registration dates
2. Clear any outstanding fees
3. Meet with academic advisor
4. Register for courses online
5. Print course schedule

COURSE REGISTRATION:
- Minimum credits per semester: 12
- Maximum credits per semester: 21
- Prerequisites must be completed
- Some courses require permission

ADD/DROP PERIOD:
- First 2 weeks of semester
- No penalty for dropping courses
- After 2 weeks: "W" grade appears

REGISTRATION HOLDS:
Common holds that prevent registration:
- Unpaid fees
- Missing documents
- Academic probation
- Advisor approval needed

CONTACT INFORMATION:
- Registrar Office: Hours 8AM-5PM
- Academic Advisors: By appointment
- Student Portal: 24/7 online access

IMPORTANT DATES:
Check academic calendar for:
- Registration periods
- Add/drop deadlines
- Exam schedules
- Holiday breaks'''
            }
        ]

        created_count = 0
        for doc_data in sample_docs:
            doc, created = KnowledgeDocument.objects.get_or_create(
                title=doc_data['title'],
                defaults={
                    'content': doc_data['content'],
                    'category': doc_data['category']
                }
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'Created: {doc.title}'))
            else:
                self.stdout.write(self.style.WARNING(f'Already exists: {doc.title}'))

        self.stdout.write(self.style.SUCCESS(f'\n[+] Added {created_count} new sample documents'))
        self.stdout.write(self.style.SUCCESS(f'[+] Total knowledge documents: {KnowledgeDocument.objects.count()}'))

