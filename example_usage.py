# Example usage of ScrappedQuestion model
# You can use this in Django shell: python manage.py shell

from mainapp.models import ScrappedQuestion

# Example 1: Creating a multiple choice question
mcq_question = ScrappedQuestion.objects.create(
    subject="Computer Science",
    questions="What is the time complexity of binary search?",
    type="option",
    options=[
        {"A": "O(n)"},
        {"B": "O(log n)"},
        {"C": "O(n²)"},
        {"D": "O(1)"}
    ],
    answer={"correct": "B", "explanation": "Binary search divides the search space in half each time"},
    marks=2,
    semester="Fall 2024"
)

# Example 2: Creating a text-based question
text_question = ScrappedQuestion.objects.create(
    subject="Database Systems",
    questions="Explain the ACID properties in database transactions.",
    type="text",
    text="Expected answer should cover Atomicity, Consistency, Isolation, and Durability",
    answer={"rubric": "Should mention all 4 properties with brief explanations"},
    marks=5,
    semester="Spring 2024"
)

# Querying examples:
# Get all questions for a subject
cs_questions = ScrappedQuestion.objects.filter(subject="Computer Science")

# Get all multiple choice questions
mcq_questions = ScrappedQuestion.objects.filter(type="option")

# Get questions by semester
fall_questions = ScrappedQuestion.objects.filter(semester="Fall 2024")

print("Example usage file created successfully!")