from django.core.management.base import BaseCommand
from django.db import transaction
from api.models import Quote


class Command(BaseCommand):
    help = 'Populate database with sample inspirational quotes'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true', help='Clear existing quotes before populating')
        parser.add_argument('--count', type=int, default=50, help='Number of quotes to add (default: 50)')

    def handle(self, *args, **options):
        clear_existing = options['clear']
        count = options['count']

        # Sample inspirational quotes
        sample_quotes = [
            {
                'text': 'The only way to do great work is to love what you do.',
                'author': 'Steve Jobs'
            },
            {
                'text': 'Innovation distinguishes between a leader and a follower.',
                'author': 'Steve Jobs'
            },
            {
                'text': 'Success is not final, failure is not fatal: it is the courage to continue that counts.',
                'author': 'Winston Churchill'
            },
            {
                'text': 'The future belongs to those who believe in the beauty of their dreams.',
                'author': 'Eleanor Roosevelt'
            },
            {
                'text': 'It is during our darkest moments that we must focus to see the light.',
                'author': 'Aristotle'
            },
            {
                'text': 'The way to get started is to quit talking and begin doing.',
                'author': 'Walt Disney'
            },
            {
                'text': 'Don\'t let yesterday take up too much of today.',
                'author': 'Will Rogers'
            },
            {
                'text': 'You learn more from failure than from success. Don\'t let it stop you. Failure builds character.',
                'author': 'Unknown'
            },
            {
                'text': 'It\'s not whether you get knocked down, it\'s whether you get up.',
                'author': 'Vince Lombardi'
            },
            {
                'text': 'People who are crazy enough to think they can change the world, are the ones who do.',
                'author': 'Rob Siltanen'
            },
            {
                'text': 'Failure will never overtake me if my determination to succeed is strong enough.',
                'author': 'Og Mandino'
            },
            {
                'text': 'Entrepreneurs are great at dealing with uncertainty and also very good at minimizing risk. That\'s the classic entrepreneur.',
                'author': 'Mohnish Pabrai'
            },
            {
                'text': 'We may encounter many defeats but we must not be defeated.',
                'author': 'Maya Angelou'
            },
            {
                'text': 'Knowing is not enough; we must apply. Wishing is not enough; we must do.',
                'author': 'Johann Wolfgang Von Goethe'
            },
            {
                'text': 'Imagine your life is perfect in every respect; what would it look like?',
                'author': 'Brian Tracy'
            },
            {
                'text': 'We generate fears while we sit. We overcome them by action.',
                'author': 'Dr. Henry Link'
            },
            {
                'text': 'The man who has confidence in himself gains the confidence of others.',
                'author': 'Hasidic Proverb'
            },
            {
                'text': 'The only limit to our realization of tomorrow will be our doubts of today.',
                'author': 'Franklin D. Roosevelt'
            },
            {
                'text': 'Creativity is intelligence having fun.',
                'author': 'Albert Einstein'
            },
            {
                'text': 'What you lack in talent can be made up with desire, hustle and giving 110% all the time.',
                'author': 'Don Zimmer'
            },
            {
                'text': 'Do what you can with all you have, wherever you are.',
                'author': 'Theodore Roosevelt'
            },
            {
                'text': 'Develop an \'attitude of gratitude\'. Say thank you to everyone you meet for everything they do for you.',
                'author': 'Brian Tracy'
            },
            {
                'text': 'You are never too old to set another goal or to dream a new dream.',
                'author': 'C.S. Lewis'
            },
            {
                'text': 'To see what is right and not do it is a lack of courage.',
                'author': 'Confucius'
            },
            {
                'text': 'Reading is a discount ticket to everywhere.',
                'author': 'Mary Schmich'
            },
            {
                'text': 'For every reason it\'s not possible, there are hundreds of people who have faced the same circumstances and succeeded.',
                'author': 'Jack Canfield'
            },
            {
                'text': 'Things work out best for those who make the best of how things work out.',
                'author': 'John Wooden'
            },
            {
                'text': 'Try to be a rainbow in someone\'s cloud.',
                'author': 'Maya Angelou'
            },
            {
                'text': 'There is little success where there is little laughter.',
                'author': 'Andrew Carnegie'
            },
            {
                'text': 'You don\'t need to see the whole staircase, just take the first step.',
                'author': 'Martin Luther King Jr.'
            },
            {
                'text': 'I find that the harder I work, the more luck I seem to have.',
                'author': 'Thomas Jefferson'
            },
            {
                'text': 'Success does not consist in never making mistakes but in never making the same one a second time.',
                'author': 'George Bernard Shaw'
            },
            {
                'text': 'I would rather die of passion than of boredom.',
                'author': 'Vincent van Gogh'
            },
            {
                'text': 'I attribute my success to this: I never gave or took any excuse.',
                'author': 'Florence Nightingale'
            },
            {
                'text': 'Life is what happens to you while you\'re busy making other plans.',
                'author': 'John Lennon'
            },
            {
                'text': 'Twenty years from now you will be more disappointed by the things that you didn\'t do than by the ones you did do.',
                'author': 'Mark Twain'
            },
            {
                'text': 'The most difficult thing is the decision to act, the rest is merely tenacity.',
                'author': 'Amelia Earhart'
            },
            {
                'text': 'The most common way people give up their power is by thinking they don\'t have any.',
                'author': 'Alice Walker'
            },
            {
                'text': 'The mind is everything. What you think you become.',
                'author': 'Buddha'
            },
            {
                'text': 'The best time to plant a tree was 20 years ago. The second best time is now.',
                'author': 'Chinese Proverb'
            },
            {
                'text': 'Eighty percent of success is showing up.',
                'author': 'Woody Allen'
            },
            {
                'text': 'Your time is limited, so don\'t waste it living someone else\'s life.',
                'author': 'Steve Jobs'
            },
            {
                'text': 'Winning isn\'t everything, but wanting to win is.',
                'author': 'Vince Lombardi'
            },
            {
                'text': 'I am not a product of my circumstances. I am a product of my decisions.',
                'author': 'Stephen Covey'
            },
            {
                'text': 'Every child is an artist. The problem is how to remain an artist once he grows up.',
                'author': 'Pablo Picasso'
            },
            {
                'text': 'You can never cross the ocean until you have the courage to lose sight of the shore.',
                'author': 'Christopher Columbus'
            },
            {
                'text': 'I\'ve learned that people will forget what you said, people will forget what you did, but people will never forget how you made them feel.',
                'author': 'Maya Angelou'
            },
            {
                'text': 'Whether you think you can or you think you can\'t, you\'re right.',
                'author': 'Henry Ford'
            },
            {
                'text': 'The two most important days in your life are the day you are born and the day you find out why.',
                'author': 'Mark Twain'
            },
            {
                'text': 'Whatever you can do, or dream you can, begin it. Boldness has genius, power and magic in it.',
                'author': 'Johann Wolfgang von Goethe'
            },
            {
                'text': 'The best revenge is massive success.',
                'author': 'Frank Sinatra'
            },
            {
                'text': 'Life shrinks or expands in proportion to one\'s courage.',
                'author': 'Anais Nin'
            },
            {
                'text': 'If you hear a voice within you say \'you cannot paint,\' then by all means paint and that voice will be silenced.',
                'author': 'Vincent Van Gogh'
            },
            {
                'text': 'There is only one way to avoid criticism: do nothing, say nothing, and be nothing.',
                'author': 'Aristotle'
            },
            {
                'text': 'Ask and it will be given to you; search, and you will find; knock and the door will be opened for you.',
                'author': 'Jesus'
            },
            {
                'text': 'The only person you are destined to become is the person you decide to be.',
                'author': 'Ralph Waldo Emerson'
            },
            {
                'text': 'Go confidently in the direction of your dreams! Live the life you\'ve imagined.',
                'author': 'Henry David Thoreau'
            },
            {
                'text': 'When I stand before God at the end of my life, I would hope that I would not have a single bit of talent left and could say, I used everything you gave me.',
                'author': 'Erma Bombeck'
            },
            {
                'text': 'Few things can help an individual more than to place responsibility on him, and to let him know that you trust him.',
                'author': 'Booker T. Washington'
            },
            {
                'text': 'Certain things catch your eye, but pursue only those that capture the heart.',
                'author': 'Ancient Indian Proverb'
            },
            {
                'text': 'Believe you can and you\'re halfway there.',
                'author': 'Theodore Roosevelt'
            },
            {
                'text': 'Everything you\'ve ever wanted is on the other side of fear.',
                'author': 'George Addair'
            },
            {
                'text': 'We can easily forgive a child who is afraid of the dark; the real tragedy of life is when men are afraid of the light.',
                'author': 'Plato'
            },
            {
                'text': 'Teach thy tongue to say, "I do not know," and thous shalt progress.',
                'author': 'Maimonides'
            },
            {
                'text': 'Start where you are. Use what you have. Do what you can.',
                'author': 'Arthur Ashe'
            },
            {
                'text': 'When I was 5 years old, my mother always told me that happiness was the key to life. When I went to school, they asked me what I wanted to be when I grew up. I wrote down \'happy\'. They told me I didn\'t understand the assignment, and I told them they didn\'t understand life.',
                'author': 'John Lennon'
            },
            {
                'text': 'Fall seven times and stand up eight.',
                'author': 'Japanese Proverb'
            },
            {
                'text': 'When one door of happiness closes, another opens, but often we look so long at the closed door that we do not see the one that has been opened for us.',
                'author': 'Helen Keller'
            },
            {
                'text': 'Everything has beauty, but not everyone can see it.',
                'author': 'Confucius'
            },
            {
                'text': 'How wonderful it is that nobody need wait a single moment before starting to improve the world.',
                'author': 'Anne Frank'
            },
            {
                'text': 'When I let go of what I am, I become what I might be.',
                'author': 'Lao Tzu'
            },
            {
                'text': 'Life is not measured by the number of breaths we take, but by the moments that take our breath away.',
                'author': 'Maya Angelou'
            },
            {
                'text': 'Happiness is not something readymade. It comes from your own actions.',
                'author': 'Dalai Lama'
            },
            {
                'text': 'If you\'re offered a seat on a rocket ship, don\'t ask what seat! Just get on.',
                'author': 'Sheryl Sandberg'
            },
            {
                'text': 'First, have a definite, clear practical ideal; a goal, an objective. Second, have the necessary means to achieve your ends; wisdom, money, materials, and methods. Third, adjust all your means to that end.',
                'author': 'Aristotle'
            },
            {
                'text': 'If the wind will not serve, take to the oars.',
                'author': 'Latin Proverb'
            },
            {
                'text': 'You can\'t fall if you don\'t climb. But there\'s no joy in living your whole life on the ground.',
                'author': 'Unknown'
            },
            {
                'text': 'We must believe that we are gifted for something, and that this thing, at whatever cost, must be attained.',
                'author': 'Marie Curie'
            },
            {
                'text': 'Too many of us are not living our dreams because we are living our fears.',
                'author': 'Les Brown'
            },
            {
                'text': 'Challenges are what make life interesting and overcoming them is what makes life meaningful.',
                'author': 'Joshua J. Marine'
            },
            {
                'text': 'The way to get started is to quit talking and begin doing.',
                'author': 'Walt Disney'
            },
            {
                'text': 'I have been impressed with the urgency of doing. Knowing is not enough; we must apply. Being willing is not enough; we must do.',
                'author': 'Leonardo da Vinci'
            },
            {
                'text': 'Limitations live only in our minds. But if we use our imaginations, our possibilities become limitless.',
                'author': 'Jamie Paolinetti'
            },
            {
                'text': 'You take your life in your own hands, and what happens? A terrible thing, no one to blame.',
                'author': 'Erica Jong'
            },
            {
                'text': 'What\'s money? A man is a success if he gets up in the morning and goes to bed at night and in between does what he wants to do.',
                'author': 'Bob Dylan'
            },
            {
                'text': 'I didn\'t fail the test. I just found 100 ways to do it wrong.',
                'author': 'Benjamin Franklin'
            },
            {
                'text': 'In order to succeed, your desire for success should be greater than your fear of failure.',
                'author': 'Bill Cosby'
            },
            {
                'text': 'A person who never made a mistake never tried anything new.',
                'author': 'Albert Einstein'
            },
            {
                'text': 'The person who says it cannot be done should not interrupt the person who is doing it.',
                'author': 'Chinese Proverb'
            },
            {
                'text': 'There are no traffic jams along the extra mile.',
                'author': 'Roger Staubach'
            },
            {
                'text': 'It is our choices that show what we truly are, far more than our abilities.',
                'author': 'J. K. Rowling'
            },
            {
                'text': 'If you do what you\'ve always done, you\'ll get what you\'ve always gotten.',
                'author': 'Tony Robbins'
            },
            {
                'text': 'Success is walking from failure to failure with no loss of enthusiasm.',
                'author': 'Winston Churchill'
            },
            {
                'text': 'Just when the caterpillar thought the world was ending, he turned into a butterfly.',
                'author': 'Proverb'
            },
            {
                'text': 'Successful entrepreneurs are givers and not takers of positive energy.',
                'author': 'Unknown'
            },
            {
                'text': 'Whenever you find yourself on the side of the majority, it is time to pause and reflect.',
                'author': 'Mark Twain'
            },
            {
                'text': 'The successful warrior is the average man, with laser-like focus.',
                'author': 'Bruce Lee'
            },
            {
                'text': 'In three words I can sum up everything I\'ve learned about life: it goes on.',
                'author': 'Robert Frost'
            },
            {
                'text': 'You\'ve got to get up every morning with determination if you\'re going to go to bed with satisfaction.',
                'author': 'George Lorimer'
            },
            {
                'text': 'The past has no power over the present moment.',
                'author': 'Eckhart Tolle'
            },
            {
                'text': 'Do not wait; the time will never be \'just right.\' Start where you stand, and work with whatever tools you may have at your command, and better tools will be found as you go along.',
                'author': 'George Herbert'
            },
            {
                'text': 'A journey of a thousand leagues begins beneath one\'s feet.',
                'author': 'Lao Tzu'
            },
            {
                'text': 'What we think, we become.',
                'author': 'Buddha'
            },
            {
                'text': 'The mind is everything. What you think you become.',
                'author': 'Buddha'
            },
            {
                'text': 'Happiness is not the absence of problems, it\'s the ability to deal with them.',
                'author': 'Steve Maraboli'
            },
            {
                'text': 'You must expect great things of yourself before you can do them.',
                'author': 'Michael Jordan'
            },
            {
                'text': 'Motivation is what gets you started. Habit is what keeps you going.',
                'author': 'Jim Ryun'
            },
            {
                'text': 'People often say that motivation doesn\'t last. Well, neither does bathing. That\'s why we recommend it daily.',
                'author': 'Zig Ziglar'
            },
            {
                'text': 'Build your own dreams, or someone else will hire you to build theirs.',
                'author': 'Farrah Gray'
            },
            {
                'text': 'The battles that count aren\'t the ones for gold medals. The struggles within yourself–the invisible battles inside all of us–that\'s where it\'s at.',
                'author': 'Jesse Owens'
            },
            {
                'text': 'Education costs money. But then so does ignorance.',
                'author': 'Sir Claus Moser'
            },
            {
                'text': 'I have learned over the years that when one\'s mind is made up, this diminishes fear.',
                'author': 'Rosa Parks'
            },
            {
                'text': 'It does not matter how slowly you go as long as you do not stop.',
                'author': 'Confucius'
            },
            {
                'text': 'If you look at what you have in life, you\'ll always have more. If you look at what you don\'t have in life, you\'ll never have enough.',
                'author': 'Oprah Winfrey'
            },
            {
                'text': 'Remember that not getting what you want is sometimes a wonderful stroke of luck.',
                'author': 'Dalai Lama'
            },
            {
                'text': 'You can\'t use up creativity. The more you use, the more you have.',
                'author': 'Maya Angelou'
            },
            {
                'text': 'Dream big and dare to fail.',
                'author': 'Norman Vaughan'
            },
            {
                'text': 'Our lives begin to end the day we become silent about things that matter.',
                'author': 'Martin Luther King Jr.'
            },
            {
                'text': 'Do what you can, where you are, with what you have.',
                'author': 'Teddy Roosevelt'
            },
            {
                'text': 'If you want to lift yourself up, lift up someone else.',
                'author': 'Booker T. Washington'
            },
            {
                'text': 'I have been impressed with the urgency of doing. Knowing is not enough; we must apply. Being willing is not enough; we must do.',
                'author': 'Leonardo da Vinci'
            },
            {
                'text': 'The best way to predict the future is to create it.',
                'author': 'Peter Drucker'
            },
            {
                'text': 'You must be the change you wish to see in the world.',
                'author': 'Mahatma Gandhi'
            },
            {
                'text': 'A person who never made a mistake never tried anything new.',
                'author': 'Albert Einstein'
            },
            {
                'text': 'The person who says it cannot be done should not interrupt the person who is doing it.',
                'author': 'Chinese Proverb'
            }
        ]

        with transaction.atomic():
            if clear_existing:
                deleted_count, _ = Quote.objects.all().delete()
                self.stdout.write(f"[INFO] Cleared {deleted_count} existing quotes")

            # Add quotes up to the requested count
            quotes_to_add = min(len(sample_quotes), count)
            quotes_added = 0

            for i in range(quotes_to_add):
                Quote.objects.get_or_create(
                    text=sample_quotes[i]['text'],
                    author=sample_quotes[i]['author'],
                    defaults={'is_active': True}
                )
                quotes_added += 1

                if quotes_added % 10 == 0:
                    self.stdout.write(f"[PROGRESS] Added {quotes_added} quotes...")

            self.stdout.write(
                self.style.SUCCESS(f'Successfully populated database with {quotes_added} inspirational quotes')
            )








