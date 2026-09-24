import os
import django
import random

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "satmakon.settings")
django.setup()

from apps.sat.models import Test, English_Question, Math_Question

# Keep a reference to the questions from earlier tests (if they still exist in memory)
# Wait, Test.objects.all().delete() deleted all questions!
# BUT I saved them in the template arrays!
# Wait! Since the script crashed, they are deleted!
# Let me see if there are any questions left.
print(English_Question.objects.count(), Math_Question.objects.count())

