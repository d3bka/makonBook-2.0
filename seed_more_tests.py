import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "satmakon.settings")
django.setup()

from apps.sat.models import Test, English_Question, Math_Question

old_test = Test.objects.filter(name='Day-1').first()
if not old_test:
    print("Base test 'Day-1' not found!")
    exit(1)

for i in range(3, 9):
    test_name = f"Day-{i}"
    if Test.objects.filter(name=test_name).exists():
        print(f"{test_name} already exists. Skipping.")
        continue
    
    new_test = Test.objects.create(
        name=test_name,
        is_available=True,
    )
    print(f"Created {test_name}. Copying questions...")
    
    eq_count = 0
    for q in English_Question.objects.filter(test=old_test):
        q.pk = None
        q.test = new_test
        q.save()
        eq_count += 1
        
    mq_count = 0
    for q in Math_Question.objects.filter(test=old_test):
        q.pk = None
        q.test = new_test
        q.save()
        mq_count += 1
        
    print(f"  -> Cloned {eq_count} English, {mq_count} Math questions.")

print("Finished adding 6 tests.")
