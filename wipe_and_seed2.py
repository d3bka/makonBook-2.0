import os
import django
import random

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "satmakon.settings")
django.setup()

from apps.sat.models import Test, English_Question, Math_Question

template_eq = list(English_Question.objects.filter(test__isnull=True))
template_mq = list(Math_Question.objects.filter(test__isnull=True))

if not template_eq or not template_mq:
    print("NO TEMPLATE QUESTIONS!")
    exit(1)

Test.objects.all().delete()

for i in range(1, 6):
    test_name = f"Practice Test {i}"
    test = Test.objects.create(name=test_name, is_available=True)
    
    # English M1
    for q_idx in range(15):
        q = random.choice(template_eq)
        English_Question.objects.create(
            test=test, module='module_1', number=q_idx+1, question=q.question, answer=q.answer,
            a=q.a, b=q.b, c=q.c, d=q.d, response_type=q.response_type, type=q.type, domain=q.domain
        )
    # English M2
    for q_idx in range(15):
        q = random.choice(template_eq)
        English_Question.objects.create(
            test=test, module='module_2', number=q_idx+1, question=q.question, answer=q.answer,
            a=q.a, b=q.b, c=q.c, d=q.d, response_type=q.response_type, type=q.type, domain=q.domain
        )
    # Math M1
    for q_idx in range(15):
        q = random.choice(template_mq)
        Math_Question.objects.create(
            test=test, module='module_1', number=q_idx+1, question=q.question, answer=q.answer,
            a=q.a, b=q.b, c=q.c, d=q.d, written=q.written, type=q.type, domain=q.domain
        )
    # Math M2
    for q_idx in range(15):
        q = random.choice(template_mq)
        Math_Question.objects.create(
            test=test, module='module_2', number=q_idx+1, question=q.question, answer=q.answer,
            a=q.a, b=q.b, c=q.c, d=q.d, written=q.written, type=q.type, domain=q.domain
        )
    
    print(f"Created {test_name} with M1 and M2")
