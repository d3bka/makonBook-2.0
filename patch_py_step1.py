import re

api_path = "apps/sat/api_views.py"
with open(api_path, "r") as f:
    api = f.read()

# Update valid modes
api = api.replace(
    "_PTC_VALID_MODES = {'full_test', 'rw_only', 'math_only', 'single_english', 'single_math'}",
    "_PTC_VALID_MODES = {'m1_ebrw', 'm2_ebrw', 'm1_math', 'm2_math'}"
)
with open(api_path, "w") as f:
    f.write(api)

views_path = "apps/sat/views.py"
with open(views_path, "r") as f:
    views = f.read()

old_get_test_sequence = """def get_test_sequence(test, mode='full_test'):
    \"\"\"Return only supported SAT module slots that actually contain questions.

    Older code allowed NULL or arbitrary module values into the sequence.  The UI,
    draft models, scoring, and guest completion logic support only module_1/m1 and
    module_2/m2, so an invalid admin/import value could trap an attempt forever.
    \"\"\"
    supported = [('module_1', 'm1'), ('module_2', 'm2')]
    sequence = []
    
    english_modules = set(
        English_Question.objects.filter(test=test, module__in=['module_1', 'module_2'])
        .values_list('module', flat=True)
    ) if mode in ('full_test', 'rw_only', 'single_english') else set()
    
    math_modules = set(
        Math_Question.objects.filter(test=test, module__in=['module_1', 'module_2'])
        .values_list('module', flat=True)
    ) if mode in ('full_test', 'math_only', 'single_math') else set()
    
    for db_module, runtime_module in supported:
        if db_module in english_modules:
            sequence.append(('english', runtime_module))
    for db_module, runtime_module in supported:
        if db_module in math_modules:
            sequence.append(('math', runtime_module))
            
    if mode in ('single_english', 'single_math') and len(sequence) > 0:
        return [sequence[0]]
        
    return sequence"""

new_get_test_sequence = """def get_test_sequence(test, mode='full_test'):
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
    
    # Fallback/Legacy
    supported = [('module_1', 'm1'), ('module_2', 'm2')]
    sequence = []
    
    english_modules = set(
        English_Question.objects.filter(test=test, module__in=['module_1', 'module_2'])
        .values_list('module', flat=True)
    ) if mode in ('full_test', 'rw_only', 'single_english') else set()
    
    math_modules = set(
        Math_Question.objects.filter(test=test, module__in=['module_1', 'module_2'])
        .values_list('module', flat=True)
    ) if mode in ('full_test', 'math_only', 'single_math') else set()
    
    for db_module, runtime_module in supported:
        if db_module in english_modules:
            sequence.append(('english', runtime_module))
    for db_module, runtime_module in supported:
        if db_module in math_modules:
            sequence.append(('math', runtime_module))
            
    if mode in ('single_english', 'single_math') and len(sequence) > 0:
        return [sequence[0]]
        
    return sequence"""

views = views.replace(old_get_test_sequence, new_get_test_sequence)
with open(views_path, "w") as f:
    f.write(views)

