import re

api_path = "apps/sat/api_views.py"
with open(api_path, "r") as f:
    api = f.read()

# Restore valid modes
api = api.replace(
    "_PTC_VALID_MODES = {'m1_ebrw', 'm2_ebrw', 'm1_math', 'm2_math'}",
    "_PTC_VALID_MODES = {'full_test', 'rw_only', 'math_only', 'single_english', 'single_math'}"
)
with open(api_path, "w") as f:
    f.write(api)

views_path = "apps/sat/views.py"
with open(views_path, "r") as f:
    views = f.read()

# Restore get_test_sequence
old_sequence = """def get_test_sequence(test, mode='full_test'):
    \"\"\"Return only supported SAT module slots that actually contain questions.

    Older code allowed NULL or arbitrary module values into the sequence.  The UI,
    draft models, scoring, and guest completion logic support only module_1/m1 and
    module_2/m2, so an invalid admin/import value could trap an attempt forever.
    \"\"\"
    if mode == 'm1_ebrw':
        return [('english', 'm1')]
    if mode == 'm2_ebrw':
        return [('english', 'm2')]
    if mode == 'm1_math':
        return [('math', 'm1')]
    if mode == 'm2_math':
        return [('math', 'm2')]
    
    # Fallback/Legacy"""
new_sequence = """def get_test_sequence(test, mode='full_test'):
    \"\"\"Return only supported SAT module slots that actually contain questions.

    Older code allowed NULL or arbitrary module values into the sequence.  The UI,
    draft models, scoring, and guest completion logic support only module_1/m1 and
    module_2/m2, so an invalid admin/import value could trap an attempt forever.
    \"\"\"
    # Fallback/Legacy"""
views = views.replace(old_sequence, new_sequence)
with open(views_path, "w") as f:
    f.write(views)
