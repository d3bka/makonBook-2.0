import re

py_path = "apps/sat/views.py"
with open(py_path, "r") as f:
    py = f.read()

old_block = """    english_modules = set(
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

new_block = """    english_modules = set()
    if mode in ('full_test', 'rw_only'):
        english_modules = set(English_Question.objects.filter(test=test, module__in=['module_1', 'module_2']).values_list('module', flat=True))
    elif mode == 'single_english_m1':
        english_modules = set(English_Question.objects.filter(test=test, module='module_1').values_list('module', flat=True))
    elif mode == 'single_english_m2':
        english_modules = set(English_Question.objects.filter(test=test, module='module_2').values_list('module', flat=True))
        
    math_modules = set()
    if mode in ('full_test', 'math_only'):
        math_modules = set(Math_Question.objects.filter(test=test, module__in=['module_1', 'module_2']).values_list('module', flat=True))
    elif mode == 'single_math_m1':
        math_modules = set(Math_Question.objects.filter(test=test, module='module_1').values_list('module', flat=True))
    elif mode == 'single_math_m2':
        math_modules = set(Math_Question.objects.filter(test=test, module='module_2').values_list('module', flat=True))
    
    for db_module, runtime_module in supported:
        if db_module in english_modules:
            sequence.append(('english', runtime_module))
    for db_module, runtime_module in supported:
        if db_module in math_modules:
            sequence.append(('math', runtime_module))
            
    return sequence"""

if old_block in py:
    py = py.replace(old_block, new_block)
    with open(py_path, "w") as f:
        f.write(py)
    print("Patched get_dynamic_test_sequence successfully")
else:
    print("Could not find old_block")
